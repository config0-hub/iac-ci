#!/usr/bin/python
'''
Copyright (C) 2025 Gary Leong gary@config0.com

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
'''

import contextlib
import os
import json
from time import time
from time import sleep
from copy import deepcopy

from iac_ci.common.orders import new_run_id
from iac_ci.common.orders import PlatformReporter
from iac_ci.common.serialization import b64_encode
from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.github_pr import GitHubRepo


class WebhookProcess(PlatformReporter):
    """
    Process webhooks from GitHub or Bitbucket repositories.
    
    This class is responsible for handling webhook events from version control systems,
    parsing the payload, and triggering appropriate CI/CD actions based on the event type
    and content.
    """

    def __init__(self, **kwargs):
        self.classname = "WebhookProcess"
        self.logger = IaCLogger(self.classname)

        self.event = kwargs["event"]
        self.event_body = kwargs["event_body"]
        self.headers = self.event["headers"]

        step_func = self.event_body.get("step_func")

        PlatformReporter.__init__(
            self,
            step_func=step_func,
            **kwargs
        )

        self.phase = "load_webhook"
        self.expire_at = int(os.environ.get("BUILD_TTL", "3600"))
        self.init_failure = None

        self.basic_events = [
            "push",
            "apply",
            "pull_request",
            "issue_comment"
        ]

        self.webhook_info = self._get_webhook_info()

        if self.event.get("path"):
            self.webhook_info["trigger_id"] = self.event["path"].split("/")[-1]  # get trigger_id from url

        if not self.webhook_info.get("trigger_id"):
            raise Exception('need to provide a valid trigger_id to process webhook')

        self.trigger_info = self.db.get_trigger_info(trigger_id=self.webhook_info["trigger_id"])[0]
        self._eval_issue()

        if os.environ.get("DEBUG_IAC_CI"):
            webhook_info = deepcopy(self.webhook_info)
            if "comment" in webhook_info and len(webhook_info["comment"]) > 100:
                del webhook_info["comment"]
            self.logger.debug("#" * 32)
            self.logger.debug("# webhook info")
            self.logger.json(webhook_info)
            self.logger.debug("#" * 32)

        self._set_order()

    def get_stepf_arn(self):
        """
        Retrieves the execution ARN and console URL associated with the step function.

        :return: A dictionary containing the execution ARN and console URL.
        """
        search_str = str(self.event["iac_ci"]["body"]["search_str"].strip())
        items = None

        for _ in range(24):
            try:
                query = self.db.table_runs.search_key("_id", search_str)
                items = query["Items"]
            except (KeyError, IndexError):
                items = []

            if not items:
                sleep(5)
                continue
                
            break  # Exit loop if items found

        if not items:
            return {"status": False}

        execution_arn = items[0]["execution_arn"]
        self.logger.debug(f'+++ execution_arn: {execution_arn}')

        parts = execution_arn.split(':')
        region = parts[3]  # The region is the 4th part of the ARN
        console_url = f"https://console.aws.amazon.com/states/home?region={region}#/executions/details/{execution_arn}"

        return {
            "execution_arn": execution_arn,
            "console_url": console_url
        }

    def _setup_github(self):
        """
        Sets up the GitHub repository configuration.
    
        This method initializes the GitHub token for authentication and creates
        an instance of the GitHubRepo class using information from the webhook.
        It extracts the repository name, pull request number, and owner from
        the webhook information to configure the GitHub repository settings.
    
        Raises:
            Exception: If the GitHub token cannot be set or if the webhook
            information is incomplete.
        """

        self.set_github_token()

        self.github_repo = GitHubRepo(
            repo_name=self.webhook_info["repo_name"],
            pr_number=self.webhook_info["pr_number"],
            token=self.github_token,
            owner=self.webhook_info["owner"]
        )

    def _eval_issue(self):
        """
        Evaluate the issue comment and update webhook_info with the PR details.

        If the event type is not an issue comment, this function does nothing.
        Otherwise, it sets up the GitHub instance and attempts to get the PR
        details from the issue comment. If the PR details are not found, this
        function sets the init_failure to "could not get pr details".
        """
        if self.webhook_info["event_type"] != "issue_comment":
            return

        self._setup_github()
        pr_details = self.github_repo.issue_to_pr()

        if not pr_details:
            self.init_failure = "could not get pr details"
            return

        self.webhook_info.update(pr_details)

    def _set_order(self):
        """
        Set the order for the current process with a human-readable description
        and a specified role.

        The method constructs input arguments including a description of loading
        webhook information and assigns the order using the new_order method.
        """
        human_description = "Loading webhook information"

        inputargs = {
            "human_description": human_description,
            "role": "github/webhook_read"
        }

        self.new_order(**inputargs)

    def _chk_event(self):
        """
        BACKUP EVENT VALIDATION - This check is now primarily performed in app.py
        
        Check if the event type is valid. If it is a ping, simply return with
        a message indicating nothing was done. If the event type is an issue
        comment, make sure the action is "created". If the event is a basic
        event, return True. Otherwise, return a message indicating the type of
        event must be one of the basic events.

        Returns:
            string or boolean
        """
        user_agent = str(self.headers.get('User-Agent')).lower()

        if "bitbucket" in user_agent:
            event_type = str(self.headers.get('X-Event-Key'))
        else:
            event_type = self.headers.get('X-GitHub-Event')

        if event_type == "ping":
            return "event is ping - nothing done"

        if self.webhook_info.get("event_type") == "issue_comment" and self.webhook_info.get("action") != "created":
            return 'issue_comment needs to have action == "created"'

        if event_type in self.basic_events:
            return True

        return f'event = "{event_type}" must be {self.basic_events}'

    def _get_webhook_info(self):
        """
        Get webhook information from request headers and body.

        _get_webhook_info will parse the incoming request headers and event body
        to determine which type of webhook event it is and return the webhook_info

        For Bitbucket, it will check the User-Agent header is Bitbucket-Webhooks/2.0
        and parse the event body for the fields repo_name, owner, commit_hash, and event_type

        For Github, it will check the X-GitHub-Event header and parse the event body
        for the fields repo_name, owner, commit_hash, and event_type

        :return: webhook_info as a dictionary
        """
        user_agent = str(self.headers.get('User-Agent')).lower()

        if "bitbucket" in user_agent:
            return self._get_bitbucket_webhook()

        # Get github fields
        if self.headers.get('X-GitHub-Event'):
            return self._get_github_webhook()
        
        return

    def _get_bitbucket_webhook(self):
        """
        Parse Bitbucket webhook information from request headers and body.

        _get_bitbucket_webhook will parse the incoming request headers and event body
        to determine which type of webhook event it is and return the webhook_info

        For Bitbucket, it will check the User-Agent header is Bitbucket-Webhooks/2.0
        and parse the event body for the fields repo_name, owner, commit_hash, and event_type

        Returns:
            dict: webhook_info as a dictionary or a dict with status=False and msg=string
        """
        event_type = str(self.headers.get('X-Event-Key'))
        commit_hash = None

        try:
            _payload = json.loads(self.event_body)
        except (json.JSONDecodeError, TypeError):
            _payload = self.event_body

        webhook_info = {}

        if event_type == "repo:push": 
            # Make it more like github, just call it push
            event_type = "push"

            commit_info = _payload["push"]["changes"][0]["commits"][0]

            commit_hash = commit_info["hash"]
            webhook_info["message"] = commit_info["message"]

            if commit_info.get("user"):
                webhook_info["author"] = commit_info["author"]["user"]["display_name"]
            else:
                webhook_info["author"] = commit_info["author"]["raw"]

            webhook_info["authored_date"] = commit_info["date"]
            # add these fields to make it consistent with Github
            webhook_info["committer"] = webhook_info["author"]
            webhook_info["committed_date"] = webhook_info["authored_date"]

            webhook_info["url"] = commit_info["links"]["html"]["href"]

            repo = _payload["repository"]

            webhook_info["repo_url"] = repo["links"]["html"]["href"]

            # More fields
            webhook_info["compare"] = _payload["push"]["changes"][0]["links"]["html"]["href"]

            try:
                webhook_info["email"] = commit_info["author"]["raw"].split("<")[1].split(">")[0].strip()
            except (IndexError, KeyError):
                webhook_info["email"] = commit_info["author"]["raw"]

            webhook_info["branch"] = _payload["push"]["changes"][0]["new"]["name"]

        elif event_type in {"pullrequest:created"}:
            # Make it more like github, just call it pull_request
            event_type = "pull_request"

            pullrequest = _payload["pullrequest"]
            source_hash = pullrequest["source"]["commit"]["hash"]
            dest_hash = pullrequest["destination"]["commit"]["hash"]

            # Branch to commit pull request to
            dest_branch = pullrequest["destination"]["branch"]["name"]
            src_branch = pullrequest["source"]["branch"]["name"]

            webhook_info["dest_branch"] = dest_branch
            webhook_info["src_branch"] = src_branch
            webhook_info["branch"] = dest_branch

            commit_hash = source_hash
            webhook_info["message"] = pullrequest["title"]
            webhook_info["author"] = pullrequest["author"]["display_name"]
            webhook_info["url"] = pullrequest["source"]["commit"]["links"]["html"]["href"]
            webhook_info["created_at"] = pullrequest["created_on"]
            webhook_info["authored_date"] = pullrequest["created_on"]
            webhook_info["updated_at"] = pullrequest["updated_on"]
            webhook_info["committer"] = None
            webhook_info["committed_date"] = None
            webhook_info["repo_url"] = pullrequest["destination"]["repository"]["links"]["html"]["href"]
            webhook_info["compare"] = f"{webhook_info['repo_url']}/branches/compare/{source_hash}..{dest_hash}"

        webhook_info["event_type"] = event_type

        if event_type in {"pull_request", "push"}:
            webhook_info["commit_hash"] = commit_hash
            return webhook_info

        msg = f"event_type = {event_type} not allowed"

        return {
            "status": False,
            "msg": msg
        }

    def _get_github_webhook(self):
        """
        Parse GitHub webhook information from request headers and body.

        The function handles different types of GitHub events such as 'push', 'pull_request',
        and 'issue_comment', extracting relevant fields from the payload to populate the
        `webhook_info` dictionary. The information includes commit hash, author, message,
        branch details, repository details, and more, depending on the event type.

        If the event type is not supported, it returns a dictionary with status set to False
        and a message indicating the event type is not allowed.

        Returns:
            dict: A dictionary containing parsed webhook event information.
        """
        try:
            _payload = json.loads(self.event_body)
        except (json.JSONDecodeError, TypeError):
            _payload = self.event_body

        event_type = self.headers.get('X-GitHub-Event')

        webhook_info = {
            "event_type": event_type
        }

        if event_type == "push": 
            commit_hash = _payload["head_commit"]["id"]
            webhook_info["commit_hash"] = commit_hash
            webhook_info["message"] = _payload["head_commit"]["message"]
            webhook_info["author"] = _payload["head_commit"]["author"]["name"]
            webhook_info["authored_date"] = _payload["head_commit"]["timestamp"]
            webhook_info["committer"] = _payload["head_commit"]["committer"]["name"]
            webhook_info["committed_date"] = _payload["head_commit"]["timestamp"]

            repo = _payload['repository']
            webhook_info["owner"] = repo['owner']['login']
            webhook_info["repo_name"] = repo['name']

            webhook_info["repo_url"] = repo["html_url"]
            webhook_info["html_url"] = repo["html_url"]
            webhook_info["url"] = repo["url"]
            webhook_info["git_url"] = repo["git_url"]
            webhook_info["ssh_url"] = repo["ssh_url"]
            webhook_info["clone_url"] = repo["clone_url"]

            webhook_info["compare"] = _payload["compare"]
            webhook_info["email"] = _payload["head_commit"]["author"]["email"]
            webhook_info["branch"] = _payload["ref"].split("refs/heads/")[1]
        elif event_type == "pull_request":
            commit_hash = _payload["pull_request"]["head"]["sha"]
            webhook_info["commit_hash"] = commit_hash
            webhook_info["number"] = _payload["pull_request"]["number"]
            webhook_info["pr_number"] = _payload["pull_request"]["number"]
            webhook_info["message"] = _payload["pull_request"]["body"]
            webhook_info["author"] = _payload["pull_request"]["user"]["login"]

            repo = _payload['repository']
            webhook_info["owner"] = repo['owner']['login']
            webhook_info["repo_name"] = repo['name']
            webhook_info["repo_url"] = repo["html_url"]
            webhook_info["html_url"] = repo["html_url"]
            webhook_info["url"] = repo["url"]
            webhook_info["git_url"] = repo["git_url"]
            webhook_info["ssh_url"] = repo["ssh_url"]
            webhook_info["clone_url"] = repo["clone_url"]

            webhook_info["created_at"] = _payload["pull_request"]["created_at"]
            webhook_info["authored_date"] = _payload["pull_request"]["created_at"]
            webhook_info["committer"] = None
            webhook_info["committed_date"] = None
            webhook_info["updated_at"] = _payload["pull_request"]["updated_at"]

            dest_branch = _payload["pull_request"]["base"]["ref"]
            src_branch = _payload["pull_request"]["head"]["ref"]

            webhook_info["dest_branch"] = dest_branch
            webhook_info["src_branch"] = src_branch
            webhook_info["branch"] = dest_branch

        elif event_type in ["issue_comment"] and "issue" in _payload:
            data = _payload['issue']

            if 'pull_request' not in data:  # Check if it's a pull request
                msg = f"event_type = {event_type} not a pull request"
                return {
                    "status": False,
                    "msg": msg
                }

            repo = _payload['repository']
            webhook_info["pr_number"] = data['number']
            webhook_info["comment"] = _payload['comment']['body']
            webhook_info["owner"] = repo['owner']['login']
            webhook_info["repo_name"] = repo['name']
            try:
                webhook_info["action"] = _payload['action']
            except KeyError:
                webhook_info["action"] = None

        webhook_info["event_type"] = event_type

        if event_type in ["pull_request", "push", "issue_comment"]:
            return webhook_info

        msg = f"event_type = {event_type} not allowed"

        return {
            "status": False,
            "msg": msg
        }

    def _save_run_info(self):
        """
        Save run information to the database.

        This method saves the current run information to the database, including
        details from the results, trigger information, webhook information, and
        run status. It also handles cases where the webhook information is missing
        or when a traceback occurred.
        """
        keys_to_delete = [
            "chk_count",
            "chk_t0",
            "close",
            "update",
            "continue",
            "log",
            "msg",
            "status"
        ]

        values = {"status": None}

        for _key in self.results:
            if _key in keys_to_delete:
                continue
            values[_key] = self.results[_key]

        keys_to_pass = [
            "repo_name",
            "git_url",
            "aws_default_region",
            "trigger_id",
            "run_id"
        ]

        for _key in keys_to_pass:
            if not self.trigger_info.get(_key):
                continue
            values[_key] = self.trigger_info[_key]

        if not self.run_id:
            self.run_id = new_run_id()

        values["checkin"] = int(time())
        values["expire_at"] = values["checkin"] + self.expire_at
        values["phases"] = [self.phase]
        values["_id"] = self.run_id
        values["run_id"] = self.run_id

        if self.iac_ci_id:
            values["iac_ci_id"] = self.iac_ci_id

        if self.webhook_info:
            values["webhook_info_hash"] = b64_encode(self.webhook_info)

            if self.webhook_info.get("commit_hash"):
                values["commit_hash"] = self.webhook_info["commit_hash"]

            values["status"] = "in_progress"
        else:
            values["status"] = "failed"

            with contextlib.suppress(Exception):
                values["failed_message"] = str(self.results["traceback"])
                del values["traceback"]

        self.db.table_runs.insert(values)

        msg = f"trigger_id/{self.trigger_id} iac_ci_id/{self.iac_ci_id} saved"
        self.add_log(msg)

        return

    def _eval_iac_action(self):
        """
        Evaluate the IaC action to be performed based on the webhook comment.

        This method checks the webhook comment for an action command (check, destroy, apply, validate, drift, regenerate).
        It compares the command with the configured action string in the database.
        For "apply" actions, it also checks if approval is required and if the PR is approved.

        Returns:
            dict: A dictionary containing the action, status, and optional message or failed message.
        """
        actions = ["check", "destroy", "apply", "validate", "drift", "regenerate" ]

        if self.webhook_info.get("event_type") != "issue_comment":
            self.logger.debug('event_type is not an issue_comment - return default check')
            return {
                "action": "check",
                "status": True
            }

        # need a comment to compare
        try:
            comment = str(self.webhook_info.get("comment").strip().split("\n")[0]).strip()
        except (AttributeError, IndexError):
            try:
                comment = str(self.webhook_info.get("comment").strip())
            except AttributeError:
                comment = None

        if not comment:
            self.logger.debug("comment not set")
            return {
                "status": False
            }

        if len(comment) < 100:
            self.logger.debug(f'_eval_iac_action: comment "{comment}"')

        comment_params = [comment.strip() for comment in comment.split(" ")]

        if comment_params[0] not in actions:
            self.logger.warn(f"comment {comment_params[0]} must be {actions}")
            return {
                "status": False
            }

        for action in actions:
            if action != comment_params[0]:
                self.logger.debug(f'evaluating action: "{action}" != comment action: "{comment_params[0]}"')
                continue

            # only match one
            if not self.iac_ci_info.get(f"{action}_str"):
                failed_message = f'key "{action}_str" not set in db - required to enable iac-ci with vcs comments'
                return {
                    "failed_message": failed_message,
                    "status": False
                }

            try:
                _db_params = [_db_param.strip() for _db_param in (self.iac_ci_info.get(f"{action}_str").strip()).split(" ")]
            except AttributeError:
                _db_params = None

            if not _db_params:
                return {
                    "failed_message": f'issue parsing element "{action}_str" in db',
                    "status": False
                }

            self.logger.debug(f'_eval_iac_action: evaluating action {action} with comment str {comment_params}/ db params "{_db_params}" with action {action}')

            if _db_params[0] != action:
                failed_message = f'the first element of field "{action}_str" = "{_db_params[0]}" != "{action}"'
                return {
                    "failed_message": failed_message,
                    "status": False
                }

            # second element
            if _db_params[1] != comment_params[1]:
                failed_message = f'action: "{action}"\n\nvcs comment "{action} {comment_params[1]}" but expected "{action} {_db_params[1]}"'
                return {
                    "failed_message": failed_message,
                    "status": False
                }

            if action != "apply":
                msg = f"{action} set to run by vcs comment"
                self.logger.debug(msg)
                return {
                    "msg": msg,
                    "action": action,
                    "status": True
                }

            if comment_params[0] != "apply":
                failed_message = 'first comment element should be set to "apply"'
                return {
                    "failed_message": failed_message,
                    "status": False
                }

            #######################################
            # apply is True at this point
            #######################################

            # we need this b/c Github Enterprise and Public repos
            # allows rules on the repos it seems
            if self.iac_ci_info.get("require_approval") in [None, "False", False, "false", "None"]:
                require_approval = False
            else:
                require_approval = True

            self.logger.debug(f'_eval_iac_action: require_approval "{require_approval}"')

            if not require_approval:
                return self._set_return_eval_iac(
                    '_eval_iac_action: apply is True - approval not needed'
                )
            if self.webhook_info.get("pr_approved"):
                return self._set_return_eval_iac(
                    '_eval_iac_action: apply is True - approval is True'
                )
            failed_message = 'pr_approved required to "apply"'
            return {
                "failed_message": failed_message,
                "status": False
            }

        failed_message = "no action settled on"
        return {
            "failed_message": failed_message,
            "action": None,
            "status": False
        }

    def _set_return_eval_iac(self, arg0):
        """
        Set the return value for _eval_iac_action when apply is True.

        This method logs a message and returns a dictionary indicating that the
        "apply" action is set to run, along with a True status.

        Args:
            arg0 (str): The message to log.

        Returns:
            dict: A dictionary containing the action, status, and message.
        """
        msg = arg0
        self.logger.debug(msg)
        return {
            "msg": msg,
            "action": "apply",
            "status": True
        }

    def _add_comment_to_github(self):
        """
        Add a comment to the GitHub pull request with CI details.

        This method adds a comment to the GitHub pull request containing information
        about the CI pipeline, including the commit hash, a link to the CI pipeline
        console, and the current status. It also includes a special formatted string
        for later updates and sets the status comment ID in the run_info and results.
        """
        if not self.results.get("console_url"):
            return

        self._setup_github()

        expire_epoch = str(int(time()) + 3600)

        comment = f'''\n## CI Details 
+ {self.webhook_info["commit_hash"]}
+ [ci pipeline]({self.run_info["console_url"]})
+ status: in_progress\n\n

#iac-ci:::status_comment\t{self.run_id}\t{expire_epoch}
'''
        pr_info = self.github_repo.add_pr_comment(comment)

        self.run_info["status_comment_id"] = pr_info["comment_id"]
        self.results["status_comment_id"] = pr_info["comment_id"]

        return

    def execute(self, **kwargs):
        """
        Execute the webhook processing logic.

        This method orchestrates the entire webhook handling process, from checking
        the event type and evaluating the IaC action to saving run information and
        updating the GitHub pull request with CI details. It handles various scenarios,
        including failures and successful processing, and returns True if the webhook
        was processed successfully, False otherwise.
        
        Note: Event type checking is now primarily performed in app.py, but we keep
        a backup check here for safety during the transition.
        """
        # Backup check for event type - primarily done in app.py now
        msg = self._chk_event()

        if msg is not True:
            self.logger.debug(f"BACKUP EVENT CHECK FAILED: {msg} - This should have been caught in app.py")
            self.results["status"] = None
            self.results["initialized"] = None
            self.results["msg"] = msg
            self.add_log(self.results["msg"])
            return False

        self.results["apply"] = False
        self.results["destroy"] = False
        self.results["event_type"] = "issue_comment"

        _log = "event checked out ok"
        self.logger.debug(_log)
        self.add_log(_log)

        # Check event_issue
        action_info = self._eval_iac_action()

        if action_info.get("status") is False:
            if failed_message := action_info.get("failed_message"):
                msg = failed_message
                self.results["notify"] = {
                    "failed_message": failed_message
                }
            else:
                msg = 'apply/check/destroy str not found in event_type "issue_comment"'

            self.results["status"] = "failed"
            self.results["initialized"] = None
            self.results["msg"] = msg
            self.add_log(self.results["msg"])

            self.notify()

            return False

        action = action_info.get("action")

        if not action:
            self.results["status"] = None
            self.results["initialized"] = None
            self.results["msg"] = "action cannot be evaluated"
            self.add_log(self.results["msg"])
            return False

        # There is an action
        self.results[action] = True
        self.webhook_info[action] = True
        self.run_info[action] = True

        if self.webhook_info.get("status") is False:
            msg = self.webhook_info["msg"]
            self.results["status"] = "failed"
            self.results["initialized"] = None
            self.results["msg"] = msg
            self.add_log(self.results["msg"])
            return False

        self.results["continue"] = True
        self.results["commit_hash"] = self.webhook_info["commit_hash"]
        self.data["job_name"] = self.webhook_info["commit_hash"][:6]

        _log = "webhook_info checked out ok"
        self.logger.debug(_log)
        self.add_log(_log)

        # Load step func params
        stepf_info = self.get_stepf_arn()

        if stepf_info.get("status") is not False:
            self.run_info.update(stepf_info)
            self.results.update(stepf_info)

        self.add_log("#" * 32)
        self.add_log("# Summary")
        self.add_log("# Webhook loaded")
        self.add_log(f"# trigger_id: {self.trigger_id}")
        self.add_log(f"# iac_ci_id: {self.iac_ci_id}")
        self.add_log(f"# commit_hash: {self.webhook_info['commit_hash']}")
        self.add_log("#" * 32)

        if self.webhook_info["event_type"] != "push":
            self._add_comment_to_github()

        # Save run info
        self.finalize_order()
        self._save_run_info()

        self.results["status"] = "successful"
        self.results["msg"] = "webhook processed"
        self.results["initialized"] = True
        self.results["update"] = True
        self.results["publish_vars"] = {
            "trigger_id": self.trigger_id,
            "iac_ci_id": self.iac_ci_id
        }

        self.insert_to_return()

        return True