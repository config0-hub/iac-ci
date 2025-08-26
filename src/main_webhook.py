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
import traceback
import base64
from time import time
from time import sleep
from copy import deepcopy

from iac_ci.common.orders import new_run_id
from iac_ci.common.orders import PlatformReporter
from iac_ci.common.serialization import b64_encode
from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.github_pr import GitHubRepo
from iac_ci.common.gitclone import CloneCheckOutCode
from iac_ci.common.serialization import b64_decode
from iac_ci.common.utilities import id_generator


class WebhookProcess(PlatformReporter, CloneCheckOutCode):
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

        try:
            self.basic_events = b64_decode(os.environ['BASIC_EVENTS_B64'])
        except:
            self.basic_events = [
                "push",
                "apply",
                "pull_request",
                "issue_comment"
            ]

        try:
            self.valid_actions = b64_decode(os.environ['VALID_ACTIONS_B64'])
        except:
            # Valid actions for issue comments
            self.valid_actions = [
                "plan",
                "check",
                "destroy",
                "apply",
                "validate",
                "report"
            ]

        self.db_keys_to_delete = [
            "chk_t0",
            "chk_count",
            "build_status",
            "step_func",
            "log",
            "msg",
            "apply",
            "check",
            "destroy"
        ]

        # testtest456
        #self.results["report"] = True
        self.plan_destroy = None
        self.report_folders = None
        self.github_repo = None
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

        CloneCheckOutCode.__init__(self,
                                   ssh_url=self.webhook_info.get("ssh_url"),
                                   commit_hash=self.webhook_info.get("commit_hash"))

        try:
            CloneCheckOutCode.__init__(self,
                                       ssh_url=self.webhook_info.get("ssh_url"),
                                       commit_hash=self.webhook_info.get("commit_hash"))
        except:
            self.logger.error("Failed to initialize CloneCheckOutCode")

        self._set_order()

    def clone_and_get_iac_folders_configs(self):

        try:
            self.write_private_key()
            self.fetch_code()
        except:
            failed_message = traceback.format_exc()

        return self.find_and_process_config_files(config_path=".iac_ci/config.yaml")

    # deprecating
    def clone_and_get_yaml(self):

        try:
            self.write_private_key()
            self.fetch_code()
        except:
            failed_message = traceback.format_exc()
            return {"failed_message": failed_message}

        contents = self.get_repo_file(".iac_ci/config.yaml")

        if contents:
            return contents["iac_ci_folders"]

        return contents

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

    def _get_changed_dirs(self):
        self._setup_github()
        return self.github_repo.get_changed_dirs()

    def _setup_github(self,reset=True):
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

        if self.github_repo and not reset:
            return self.github_repo

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

    def _eval_init_save_run_info(self):
        """
        Save run information to the database.

        This method saves the current run information to the database, including
        details from the results, trigger information, webhook information, and
        run status. It also handles cases where the webhook information is missing
        or when a traceback occurred.
        """
        values = {"status": None}

        for _key in self.results:
            if _key in self.db_keys_to_delete:
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

        return values

    def _save_run_info(self):

        values = self._eval_init_save_run_info()

        if values["status"] == "failed":
            self.db.table_runs.insert(values)
            return {
                "status": False,
                "failed_message": values.get("failed_message", "unknown error")
            }

        if not self.report_folders:
            if self.plan_destroy:
                values["plan_destroy"] = True
            if self.run_info.get("iac_ci_folder"):
                values["iac_ci_folder"] = self.run_info["iac_ci_folder"]
            values["parent"] = True
            self.db.table_runs.insert(values)
            msg = f"trigger_id/{self.trigger_id} iac_ci_id/{self.iac_ci_id} saved"
            self.add_log(msg)
            return { "status": True }

        # testtest456
        # this is map report_folders inputs
        parallel_folder_builds = []

        keys_to_delete = [
            "_id",
            "run_id",
            "report_folders"
        ]

        for folder in self.report_folders:
            _values = deepcopy(values)
            for _key in keys_to_delete:
                if _key in _values:
                    del _values[_key]

            _values["parent_run_id"] = self.run_id
            _values["child"] = True
            _values["report"] = True

            p_run_id = new_run_id()
            parallel_folder_builds.append(p_run_id)
            _values["_id"] = p_run_id
            _values["run_id"] = p_run_id
            _values["iac_ci_folder"] = folder

            # testtest456
            print('y0'*32)
            self.logger.json(_values)
            print('y0'*32)
            self.db.table_runs.insert(_values)

        values["parallel_folder_builds"] = parallel_folder_builds
        values["parent"] = True
        values["report"] = True

        self.db.table_runs.insert(values)

        return {
            "status": True,
            "parallel_folder_builds": parallel_folder_builds
        }

    def _eval_iac_action(self):
        """
        Evaluate the IaC action to be performed based on the webhook comment.

        This method checks the webhook comment for an action command (check, plan, destroy, apply, validate, drift).
        It compares the command with the configured action string in the database.
        For "apply" actions, it also checks if approval is required and if the PR is approved.

        Returns:
            dict: A dictionary containing the action, status, and optional message or failed message.
        """
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

        if comment_params[0] not in self.valid_actions:
            self.logger.warn(f"comment {comment_params[0]} must be {self.valid_actions}")
            return {
                "status": False
            }

        for action in self.valid_actions:
            if action != comment_params[0]:
                continue

            if comment_params[0] in ["plan", "validate", "drift", "report"]:
                db_key = "check_str"
                action_chk = "check"
            else:
                db_key = f"{action}_str"
                action_chk = action

            # only match one
            if not self.iac_ci_info.get(db_key):
                failed_message = f'key "{db_key}" not set in db - required to enable iac-ci with vcs comments'
                return {
                    "failed_message": failed_message,
                    "status": False
                }

            try:
                _db_params = [_db_param.strip() for _db_param in (self.iac_ci_info.get(f"{db_key}").strip()).split(" ")]
            except AttributeError:
                _db_params = None

            if not _db_params:
                return {
                    "failed_message": f'issue parsing element "{db_key}" in db',
                    "status": False
                }

            self.logger.debug(f'_eval_iac_action: evaluating action {action} with comment str {comment_params}/ db params "{_db_params}" with action {action}')

            if _db_params[0] != action_chk:
                failed_message = f'the first element of field "{db_key}" = "{_db_params[0]}" != "{action}"'
                return {
                    "failed_message": failed_message,
                    "status": False
                }

            if action in ["check", "plan" ] and comment_params[1] == "destroy":
                try:
                    comment_check = comment_params[2]
                except:
                    comment_check = None
                self.plan_destroy = True
            elif action == "report" and comment_params[1] == "all":
                try:
                    comment_check = comment_params[2]
                except:
                    comment_check = None
                self.report_folders = 'all'
            elif action == "report" and comment_params[1] != "all":
                try:
                    comment_check = comment_params[2]
                except:
                    comment_check = None
                self.report_folders = comment_params[1]
            else:
                comment_check = comment_params[1]

            # second element
            if _db_params[1] != comment_check:
                failed_message = f'action: "{action}"\n\nvcs comment "{action} {comment_check}" but expected "{action} {_db_params[1]}"'
                return {
                    "failed_message": failed_message,
                    "status": False
                }

            if self.plan_destroy or action_chk == "check":
                return {
                    "action": action_chk,
                    "status": True
                }

            elif self.report_folders:
                return {
                    "action": "report",
                    "status": True
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

    def _set_return_eval_iac(self, msg):
        """
        Set the return value for _eval_iac_action when apply is True.

        This method logs a message and returns a dictionary indicating that the
        "apply" action is set to run, along with a True status.

        Args:
            arg0 (str): The message to log.

        Returns:
            dict: A dictionary containing the action, status, and message.
        """
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

    def _pr_id(self):

        # Create the concatenated string using an f-string
        concatenated_string = f"{self.webhook_info['repo_name']}:{self.webhook_info['owner']}:{self.webhook_info['pr_number']}"

        # Encode the string to base64
        encoded_bytes = base64.b64encode(concatenated_string.encode("utf-8"))

        # Decode the bytes to string and extract the substring
        return encoded_bytes.decode("utf-8")[1:12]

    def _get_iac_ci_folder(self):

        # check directories
        changed_dirs = self._get_changed_dirs()
        iac_ci_folders_configs = self.clone_and_get_iac_folders_configs()

        self.logger.debug(f"iac_ci_folders_configs: {iac_ci_folders_configs}")
        self.logger.debug(f"changed_dirs: {changed_dirs}")

        match_folders = []

        for iac_ci_folder in iac_ci_folders_configs:
            if iac_ci_folder in changed_dirs:
                match_folders.append(iac_ci_folder)

        if len(match_folders) != 1:
            failed_message = f"should only find one matched folder - found instead {match_folders} in the same PR"
            return {
                "failed_message":failed_message,
                "status":False
            }

        pr_id = self._pr_id()

        try:
            iac_ci_folder_db = self.db.table_runs.search_key(key="_id", value=pr_id)["Items"][0]["iac_ci_folder"]
        except IndexError:
            iac_ci_folder_db = None

        iac_ci_folder = match_folders[0]

        if iac_ci_folder_db and iac_ci_folder_db != iac_ci_folder:
            failed_message = f"iac_ci_folder in db: {iac_ci_folder_db} not same as iac_ci_folder: {iac_ci_folder}"
            self.logger.warn(failed_message)
            return {
                "failed_message": failed_message,
                "status": False
            }

        # Extract destroy and apply values from the inner dictionary
        config_values = iac_ci_folders_configs[iac_ci_folder]
        destroy_value = config_values["destroy"]
        apply_value = config_values["apply"]

        # if it got this far, then it is probably
        # the first time it is registered the pr_id
        values = {
            "_id": pr_id,
            "pr_id": pr_id,
            "iac_ci_folder": iac_ci_folder,
            "destroy": destroy_value,
            "apply": apply_value,
            "repo_name": self.webhook_info['repo_name'],
            "repo_owner": self.webhook_info['owner'],
            "pr_number": self.webhook_info['pr_number'],
            "checkin": int(time()),  # Removed the extra "="
            "expire_at": int(time()) + 604800,  # 7 days (604800 seconds) from now
            "iac_ci_id": self.iac_ci_id
        }

        if self.webhook_info.get("branch"):
            values["branch"] = self.webhook_info["branch"]

        self.logger.debug(f'registering pr_number: "{self.webhook_info["pr_number"]}", iac_ci_folder: "{iac_ci_folder}"')
        self.db.table_runs.insert(values)

        self.logger.debug(f"iac_ci_folder: {iac_ci_folder}")

        return {
            "iac_ci_folder": iac_ci_folder,
            "destroy": destroy_value,
            "apply": apply_value,
            "status": True
        }

    # deprecating
    def _get_iac_ci_folder_2(self):

        # check directories
        changed_dirs = self._get_changed_dirs()

        # explicit on dynamodb
        iac_ci_folder = self.iac_ci_info.get("iac_ci_folder")

        if iac_ci_folder:
            return {
                "iac_ci_folder": iac_ci_folder,
                "status": True
            }

        pr_id = self._pr_id()

        try:
            iac_ci_folder = self.db.table_runs.search_key(key="_id", value=pr_id)["Items"][0]["iac_ci_folder"]
        except IndexError:
            iac_ci_folder = None

        if iac_ci_folder:
            return {
                "iac_ci_folder": iac_ci_folder,
                "status": True
            }

        iac_ci_folders = self.clone_and_get_yaml()

        if not iac_ci_folders:
            return {
                "failed_message": "no yaml provided at .iac_ci/config.yaml",
                "status": False
            }

        match_folders = []

        for iac_ci_folder in iac_ci_folders:
            if iac_ci_folder in changed_dirs:
                match_folders.append(iac_ci_folder)

        if len(match_folders) != 1:
            failed_message = f"should only find one matched folder - found instead {match_folders} in the same PR"
            return {
                "failed_message":failed_message,
                "status":False
            }

        iac_ci_folder = match_folders[0]

        # if it got this far, then it is probably
        # the first time it is registered the pr_id
        values = {
            "_id": pr_id,
            "pr_id": pr_id,
            "iac_ci_folder": iac_ci_folder,
            "repo_name": self.webhook_info['repo_name'],
            "repo_owner": self.webhook_info['owner'],
            "pr_number": self.webhook_info['pr_number'],
            "checkin": int(time()),  # Removed the extra "="
            "expire_at": int(time()) + 604800,  # 7 days (604800 seconds) from now
            "iac_ci_id": self.iac_ci_id
        }

        if self.webhook_info.get("branch"):
            values["branch"] = self.webhook_info["branch"]

        self.logger.debug(f'registering pr_number: "{self.webhook_info["pr_number"]}", iac_ci_folder: "{iac_ci_folder}"')
        self.db.table_runs.insert(values)

        self.logger.debug(f"iac_ci_folder: {iac_ci_folder}")

        return {
            "iac_ci_folder": iac_ci_folder,
            "status": True
        }

    def _exec_report_folders(self):

        iac_ci_folders_configs = self.clone_and_get_iac_folders_configs()
        iac_ci_folders = list(iac_ci_folders_configs.keys())

        if self.report_folders == 'all':
            self.report_folders = iac_ci_folders
            self.results["report_folders"] = self.report_folders
        elif self.report_folders in iac_ci_folders:
            self.report_folders = [self.report_folders]
            self.results["report_folders"] = self.report_folders
        else:
            failed_message = f"report_folders {self.report_folders} not found in iac_ci_folders {iac_ci_folders}"
            self.logger.error(failed_message)
            self.results["status"] = None
            self.results["initialized"] = None
            self.results["msg"] = failed_message
            self.add_log(self.results["msg"])
            return False

        return iac_ci_folders_configs

    def _exec_iac_ci_folder(self):

        iac_ci_folder_configs = self._get_iac_ci_folder()

        if not iac_ci_folder_configs.get("status"):
            failed_message = iac_ci_folder_configs.get("failed_message")
            self.logger.error(failed_message)
            self.results["status"] = None
            self.results["initialized"] = None
            self.results["msg"] = failed_message
            self.add_log(self.results["msg"])
            return False

        return iac_ci_folder_configs

    def _process_post_save_run_info(self,_save_run_info):

        if not _save_run_info.get("parallel_folder_builds"):
            self.results["publish_vars"] = {
                "trigger_id": self.trigger_id,
                "iac_ci_id": self.iac_ci_id
            }
        else:
            self.results["report"] = True

            for _key in self.db_keys_to_delete:
                if _key in self.results:
                    del self.results[_key]

            self.results["parallel_folder_builds"] = _save_run_info["parallel_folder_builds"]

    def _update_false(self):
        self.results["initialized"] = None
        self.results["apply"] = False
        self.results["destroy"] = False
        self.results["check"] = False
        self.results["continue"] = False
        self.results["status"] = None

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
            self._update_false()
            self.results["msg"] = msg
            self.add_log(self.results["msg"])
            return False

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
                msg = f'{self.valid_actions} str not found in event_type "issue_comment"'

            self._update_false()
            self.results["status"] = "failed"
            self.results["msg"] = msg
            self.add_log(self.results["msg"])
            self.notify()
            return False

        action = action_info.get("action")

        if not action:
            self._update_false()
            self.results["status"] = "failed"
            self.results["msg"] = "action cannot be evaluated"
            self.add_log(self.results["msg"])
            return False

        if self.webhook_info.get("status") is False:
            msg = self.webhook_info["msg"]
            self._update_false()
            self.results["status"] = "failed"
            self.results["msg"] = msg
            self.add_log(self.results["msg"])
            return False

        if self.report_folders:
            iac_ci_folder_configs = self._exec_report_folders()
        else:
            iac_ci_folder_configs = self._exec_iac_ci_folder()

        if not iac_ci_folder_configs:
            self._update_false()
            return False

        if not self.report_folders and (action in ["destroy","apply"] and not iac_ci_folder_configs.get(action)):
            self.logger.error(f'iac_ci_folder {iac_ci_folder_configs["iac_ci_folder"]} action "{action}" set to "{iac_ci_folder_configs[action]}" not allowed')
            self._update_false()
            self.results["status"] = "failed"
            return False

        if self.report_folders:
            action = "report"
        else:
            self.results["iac_ci_folder"] = iac_ci_folder_configs["iac_ci_folder"]
            self.run_info["iac_ci_folder"] = iac_ci_folder_configs["iac_ci_folder"]

        # There is an action
        self.results[action] = True
        self.run_info[action] = True
        self.webhook_info[action] = True

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
        _save_run_info = self._save_run_info()

        if _save_run_info.get("status") is False:
            self._update_false()
            self.results["status"] = "failed"
            self.results["update"] = True
            self.results["msg"] = _save_run_info["failed_message"]
            self.results["failed_message"] = _save_run_info["failed_message"]
            return False

        self.results["status"] = "successful"
        self.results["msg"] = "webhook processed"
        self.results["initialized"] = True
        self.results["update"] = True

        # _process_post_save_run_info
        self._process_post_save_run_info(_save_run_info)

        self.insert_to_return()

        return True