#!/usr/bin/env python

import json
import os
import traceback
import boto3
import base64
from time import time

from iac_ci.common.github_pr import GitHubRepo
from iac_ci.common.boto3_file import S3FileBoto3
from iac_ci.common.boto3_lambda import LambdaBoto3
from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.run_helper import Notification, CreateTempParamStoreEntry, GetFrmDb
from iac_ci.common.serialization import b64_encode, b64_decode
from iac_ci.common.utilities import id_generator, get_hash_from_string, rm_rf, id_generator2
from iac_ci.common.utilities import clean_and_convert_data


def get_queue_id(size=6, input_string=None):
    """
    Generates a unique queue ID based on the current epoch time and a random string.

    Parameters:
    size (int): The length of the random string to append to the epoch time. Default is 6.
    input_string (str): Optional input string (not used in this implementation).

    Returns:
    str: A unique queue ID.
    """
    date_epoch = str(int(time()))
    return f"{date_epoch}{id_generator(size)}"


def new_run_id(**kwargs):
    """
    Creates a new run ID consisting of a random string and the current epoch time.

    Parameters:
    **kwargs: Additional keyword arguments (not used in this implementation).

    Returns:
    str: A new run ID.
    """
    checkin = str(int(time()))
    return f"{id_generator()[:6]}{checkin}"


class PlatformReporter(Notification, CreateTempParamStoreEntry):
    """
    Helper class for managing orders and stages in the IAC CI pipeline.
    Provides functionality for tracking, reporting, and managing the pipeline execution.
    """

    def __init__(self, **kwargs):
        """
        Initialize the PlatformReporter with the provided parameters.
        
        Args:
            **kwargs: Keyword arguments including iac_ci_id, run_id, trigger_id,
                      build_id, and step_func.
        """
        self.start_time = int(time())

        self.classname = "PlatformReporter"
        self.logger = IaCLogger(self.classname)
        self.s3_file = S3FileBoto3()

        session = boto3.Session()
        self.ssm = session.client('ssm')
        self.lambda_client = LambdaBoto3()

        self.app_name_iac = os.environ.get("APP_NAME_IAC", "iac-ci")
        self.db = GetFrmDb(app_name=self.app_name_iac)

        inputargs = self._eval_report_inputargs(**kwargs)
        self.parent_run_id = inputargs.get("parent_run_id")
        self.report = inputargs.get("report")

        self.ssh_url = inputargs.get("ssh_url")
        self.commit_hash = inputargs.get("commit_hash")

        self.stateful_id = None
        self.iac_ci_id = inputargs.get("iac_ci_id")
        self.run_id = inputargs.get("run_id")
        self.trigger_id = inputargs.get("trigger_id")
        self.build_id = inputargs.get("build_id")
        self.step_func = inputargs.get("step_func")

        self.webhook_info = None
        self.queue_host = None
        self.active = None
        self.callback_token = None
        self.data = None
        self.order = None
        self.status = None
        self.report_url = None
        self.github_token = None

        self.build_env_vars = {}
        self.iac_platform = None

        self.app_info_iac = {"name": self.app_name_iac}
        self.trigger_info = {}
        self.stateful_info = {}
        self.run_info = {}

        Notification.__init__(self)
        CreateTempParamStoreEntry.__init__(self)

        self.set_misc_pr_tags()
        self.results = {
            "msg": None,
            "step_func": self.step_func,
            "status": None,
            "chk_t0": None,  # reserved mostly for codebuild, maybe want to remove it
            "chk_count": None,  # reserved mostly for codebuild, maybe want to remove it
            "build_status": None,  # reserved mostly for codebuild, maybe want to remove it
            "log": "",
            "close": None,  # close data pipeline
            "initialized": True,
            "update": None,  # writing data pipeline to s3
            "notify": None,
            "continue": True,  # this is used for connecting step functions
            "apply": None,
            "check": None,
            "destroy": None,
            "_id": self.run_id,
            "run_id": self.run_id,
            "trigger_id": self.trigger_id
        }

        # set it initially
        self.set_misc_pr_tags()

    def _get_kwargs_body(self,**kwargs):

        body = {}

        if kwargs.get("body"):
            body = kwargs["body"]
            if isinstance(body, str):
                try:
                    body = json.loads(body)
                except json.JSONDecodeError:
                    self.logger.error("Failed to decode body as JSON")

        return body

    def _eval_report_inputargs(self,**kwargs):

        body = self._get_kwargs_body(**kwargs)

        if not kwargs.get("report") and not body.get("report"):
            return kwargs

        if "_id" in kwargs:
            inputargs = clean_and_convert_data(self.db.table_runs.search_key(key="_id", value=kwargs["_id"])["Items"][0])
        elif "_id" in body:
            inputargs = clean_and_convert_data(self.db.table_runs.search_key(key="_id", value=body["_id"])["Items"][0])
        else:
            raise Exception("need to provide _id in kwargs or body")

        keys2pass = [
            "status",
            "close",
            "initialized",
            "update",
            "notify",
            "continue",
            "trigger_id",
            "event_type",
            "commit_hash",
            "execution_arn",
            "console_url",
            "status_comment_id",
            "iac_ci_id"
        ]

        # for lambda stage
        if body and body.get("parent_run_id"):
            inputargs["parent_run_id"] = body["parent_run_id"]
        # for pkg to s3 stage
        elif body:
            inputargs["parent_run_id"] = body["run_id"]
        elif kwargs.get("run_id"):
            inputargs["parent_run_id"] = kwargs["run_id"]

        for key in keys2pass:
            if key in body:
                inputargs[key] = body[key]

        inputargs["status"] = "in_progress"
        inputargs["update"] = None
        inputargs["report"] = True

        return inputargs

    def _set_infracost_api_key(self):
        """
        Sets the Infracost API key for the current instance.

        This function attempts to retrieve the Infracost API key from AWS SSM
        Parameter Store using the key name stored in `self.trigger_info`.
        If the key is already set, it returns the existing key. If the key
        cannot be retrieved, it logs a warning.

        Returns:
            str or None: The Infracost API key if successfully retrieved,
            otherwise None.
        """
        if self.infracost_api_key:
            return self.infracost_api_key

        if not self.trigger_info.get("ssm_infracost_api_key"):
            self.logger.warn("ssm_infracost_api_key not found - notification not enabled")
            return

        try:
            _ssm_info = self.ssm.get_parameter(
                Name=self.trigger_info["ssm_infracost_api_key"],
                WithDecryption=True
            )
            self.infracost_api_key = _ssm_info["Parameter"]["Value"]
            return self.infracost_api_key
        except Exception:
            self.logger.warn("could not fetch infracost api key")
            return

    @staticmethod
    def extract_from_substring(obj_str, substring):
        """
        Extract a substring from a string.

        This method searches for a substring within a given string and returns
        the portion of the string starting from the substring if found.
        If the substring is not found, it returns None.

        Args:
            obj_str (str): The string to search within.
            substring (str): The substring to search for.

        Returns:
            str or None: The portion of the string starting from the substring
            if found, otherwise None.
        """
        if substring in obj_str:
            start_index = obj_str.index(substring)
            return obj_str[start_index:]
        else:
            return

    def _wrapper_clean_pr_comments(self,search_tag=None):
        """
        Cleans up outdated or irrelevant pull request comments in the GitHub repository.

        This function retrieves comments from the GitHub repository associated with the
        current instance, searches for comments containing a specific search tag, and
        deletes comments that are either expired or associated with the current run ID.

        Returns:
            bool: False if the GitHub repository is not set or accessible, otherwise None.
        """
        if not hasattr(self, "github_repo") or not self.github_repo:
            self.logger.warn("_wrapper_clean_pr_comments: github_repo not set to clean up pr comments")
            return False

        if not search_tag:
            search_tag = self.update_status_tag

        search_tag_comments = self.github_repo.get_pr_comments(search_tag=search_tag)

        if search_tag_comments:
            comments = search_tag_comments
        else:
            comments = []

        error_comments = self.github_repo.get_pr_comments(search_tag=self.error_tag)

        if error_comments:
            comments.extend(error_comments)

        update_comments = self.github_repo.get_pr_comments(search_tag=self.update_status_tag)

        if update_comments:
            comments.extend(update_comments)

        self._delete_pr_comments(comments)

    def get_github_token(self):
        """
        Retrieves the GitHub token.

        This method retrieves the GitHub token from AWS SSM Parameter Store.
        It first checks if trigger information is available and if not, attempts to retrieve it from the database.
        If the trigger information is found, it retrieves the token from SSM.

        Returns:
            str or dict: The GitHub token if successfully retrieved, otherwise a dictionary
            indicating failure with a status and an optional failed message.
        """
        if not self.trigger_info:
            self._set_trigger_info()

        if not self.trigger_info:
            return {
                "status": False,
                "failed_message": "trigger info could not be set"
            }

        try:
            _ssm_info = self.ssm.get_parameter(
                Name=self.trigger_info["ssm_iac_ci_github_token"],
                WithDecryption=True
            )
        except Exception as e:
            self.logger.warn(f"could not fetch SSM info: {e}")
            return {
                "status": False,
                "failed_message": "trigger info could not be set"
            }


        return {
            "status": True,
            "value": _ssm_info["Parameter"]["Value"]
        }

    def set_github_token(self):
        """
        Sets the GitHub token for the instance.

        This method retrieves the GitHub token using `get_github_token()`
        and stores it in the `github_token` attribute. If the token is
        already set, it returns the existing token without retrieving it again.

        Returns:
            str or dict: The GitHub token if successfully retrieved and set,
            otherwise the existing value of `self.github_token`.
        """
        if self.github_token:
            return self.github_token

        github_token_info = self.get_github_token()

        if github_token_info.get("status"):
            self.github_token = github_token_info["value"]
        else:
            self.github_token = False
            self.logger.error(f"Failed to retrieve GitHub token: {github_token_info['failed_message']}")

        return self.github_token

    def setup_github(self,reset=True):
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

        if hasattr(self,"github_repo") and self.github_repo and not reset:
            return self.github_repo

        self.github_repo = GitHubRepo(
            repo_name=self.webhook_info["repo_name"],
            pr_number=self.webhook_info["pr_number"],
            token=self.github_token,
            owner=self.webhook_info["owner"]
        )

    def set_misc_pr_tags(self):

        try:
            self.error_tag = f"iac-ci:::tag::error:status repo_name: `{self.webhook_info['repo_name']}`, pr_number: `{self.webhook_info['pr_number']}`"
        except:
            self.error_tag = "iac-ci:::tag::error:status"


        try:
            self.update_status_tag = f"iac-ci:::status_comment repo_name: `{self.webhook_info['repo_name']}`, pr_number: `{self.webhook_info['pr_number']}`"
        except:
            self.update_status_tag = "iac-ci:::status_comment"

        return

    def add_error_comment_to_pr(self,failed_message):
        self.set_misc_pr_tags()
        content = f'{failed_message}\n\n#{self.error_tag}'
        self.setup_github()
        self.github_repo.add_pr_comment(content)

    def set_search_tag(self):
        """
        Sets the search tag for the instance.

        This method generates a unique search tag based on various attributes
        like iac-ci, platform, stateful ID, and pull request number.
        The generated tag is stored in the `search_tag` attribute.

        Returns:
            str: The generated search tag.
        """

        #tags = [
        #    "iac-ci",
        #    self.iac_ci_info["stateful_id"],
        #    f'pr_number:{self.webhook_info["pr_number"]}'
        #]

        tags = [
            "iac-ci",
            self.webhook_info["repo_name"],
            f'pr_number:{self.webhook_info["pr_number"]}'
        ]

        self.search_tag = f'iac-ci:::tag::{get_hash_from_string(".".join(tags))}'

        self.logger.debug(f'set_search_tag: {self.search_tag} with repo_name and pr_number')

        return self.search_tag
    
    @staticmethod
    def get_pr_status(status=None):

        if status == "successful":
            return '✅ <span style="color:green">**SUCCESS**</span>'
        else:
            return '❌ <span style="color:red">**FAILED**</span>'

    def _ci_links(self, base_comment):
        """
        Generates a markdown string containing a link to the CodeBuild console
        and a link to the CodeBuild execution details if available.

        Parameters:
        base_comment (str): The markdown comment to which the links will be appended.
        
        Returns:
        str: A markdown string with the links.
        """
        content = f'''\n##  Run(s) Info
{base_comment}
+ {self.webhook_info.get("commit_hash")}
'''
        if self.run_info.get("console_url"):
            content = f'{content}\n+ [ci pipeline]({self.run_info["console_url"]})'

        if self.run_info.get("build_url"):
            content = f'{content}\n+ [execution details]({self.run_info["build_url"]})'

        return content

    def get_cur_status_comment(self):
        self.github_repo = self._set_up_github_conn_to_repo()
        status_comment_id = self.get_status_comment_id()

        return self.github_repo.get_comment_by_id(status_comment_id)

    def get_status_comment_id(self):
        try:
            status_comment_id = self.run_info["status_comment_id"]
        except KeyError as e:
            self.logger.debug(f"No status comment ID found: {str(e)}")
            status_comment_id = None
        except Exception as e:
            self.logger.debug(f"Error retrieving status comment ID: {str(e)}")
            status_comment_id = None

        return status_comment_id

    def _delete_pr_comments(self,comments):

        if not comments:
            return

        for comment in comments:
            comment_id = comment["id"]
            self.logger.debug(f'deleting update related comment {comment_id}')
            self.github_repo.delete_pr_comment(comment_id)

    def _clean_update_status_tag(self):

        try:
            comments = self.github_repo.get_pr_comments(search_tag=self.update_status_tag)
        except:
            comments = None

        return self._delete_pr_comments(comments)

    def _clean_report_status_tag(self):
        try:
            comments = self.github_repo.get_pr_comments(search_tag=f'#{self.base_report_tag}')
        except:
            comments = None

        return self._delete_pr_comments(comments)

    def clear_report_all_comments(self):

        if not hasattr(self, "github_repo") or not self.github_repo:
            self.logger.warn(f'self.github_repo was not initialized')
            self.logger.warn("clean_report_all_comments: github_repo not set to clean up pr comments")
            return False

        search_tag = "report all tf"
        comments = self.github_repo.get_pr_comments(search_tag=search_tag)
        if comments and len(comments) > 1:
            comments.sort(key=lambda comment: comment["id"])
            for comment in comments[:-1]:
                comment_id = comment["id"]
                self.logger.debug(f'deleting "report all tf" comment {comment_id}')
                self.github_repo.delete_pr_comment(comment_id)

        self._clean_update_status_tag()
        self._clean_report_status_tag()

    def clean_all_pr_comments(self):
        """
        Clean out existing comments in the PR by deleting them.

        This includes any status comment created by this application, as well as
        any other comments that may have been created with the same search tag.
        """
        self._wrapper_clean_pr_comments()
        self._clean_run_status_comment_id()
        self._clean_update_status_tag()

    def _clean_run_status_comment_id(self):

        self.github_repo = self._set_up_github_conn_to_repo()
        status_comment_id = self.get_status_comment_id()

        if status_comment_id:
            try:
                self.github_repo.delete_pr_comment(status_comment_id)
            except Exception as e:
                self.logger.debug(f"could not delete pr comment {status_comment_id}: {str(e)}")

    def _set_up_github_conn_to_repo(self):

        repo_name = self.webhook_info["repo_name"]
        pr_number = self.webhook_info["pr_number"]

        self.set_search_tag()

        if not self.set_github_token():
            self.logger.error("Failed to get GitHub token.")
            return

        return GitHubRepo(repo_name,
                          pr_number,
                          search_tag=self.search_tag,
                          token=self.github_token,
                          owner=self.webhook_info["owner"])

    def finalize_build_pr(self,status):
        """
        Finalizes the PR by adding a comment to the PR with the CodeBuild console and execution details links.

        This method retrieves the necessary information from the `webhook_info` dictionary, sets the search tag,
        and creates a `GitHubRepo` instance to interact with the pull request. It then generates a markdown string
        with the links and adds the comment to the pull request. If an existing comment with the same search tag
        exists, it updates the comment. Otherwise, it adds a new comment.

        Finally, the method deletes any existing comment with the ID stored in the `status_comment_id` key of the
        `run_info` dictionary.

        Returns:
        dict: A dictionary with the comment ID and URL of the added comment.
        """
        self.github_repo = self._set_up_github_conn_to_repo()
        base_comment = f'+ Executed By iac-ci\n    + owner: {self.github_repo.owner}\n    + repo: {self.github_repo.repo_name}\n    + pr_number: {self.github_repo.pr_number}'
        status_comment = f'{base_comment}\n+ {self.get_pr_status(status=status)}'
        ci_link_content = self._ci_links(status_comment)
        existing_comments = self.github_repo.get_pr_comments(use_default_search_tag=True)

        if existing_comments:
            comment_id = existing_comments[0]["id"]
            comment = existing_comments[0]["body"].replace(f'#{self.search_tag}', "").strip().rstrip('\n').rstrip('\r')
            comment = comment + "\n" + ci_link_content
            self.github_repo.delete_pr_comment(comment_id)
        else:
            comment = ci_link_content

        self.clean_all_pr_comments()

        pr_info = self.github_repo.add_pr_comment(comment)

        self._wrapper_clean_pr_comments()

        try:
            status_comment_id = self.run_info["status_comment_id"]
            if status_comment_id:
                self.github_repo.delete_pr_comment(status_comment_id)
        except KeyError:
            self.logger.debug("No status_comment_id found in run_info")

        self.results["notify"] = {
            "links": [{"github comment": pr_info["url"]}]
        }

        return pr_info

    def _set_trigger_info(self,trigger_id=None,repo_name=None):
        items = None
        if trigger_id and repo_name:
            items = self.db.get_trigger_info(
                trigger_id=self.trigger_id,
                repo_name=repo_name
            )
        elif self.trigger_id:
            items = self.db.get_trigger_info(trigger_id=self.trigger_id)
        elif self.webhook_info.get("trigger_id"):
            items = self.db.get_trigger_info(trigger_id=self.webhook_info["trigger_id"])
        elif self.webhook_info.get("repo_name"):
            items = self.db.get_trigger_info(repo_name=self.webhook_info["repo_name"])
        else:
            self.logger.error("need to provide repo_name or trigger_id")
            return False

        if items and len(items) == 1:
            self.trigger_info = items[0]
            return True

        if not items:
            self.logger.error("could not find trigger_info with provided trigger_id/repo_name")

        if len(items) > 1:
            self.logger.error('too many values for trigger_id/repo_name found in db')

        return False

    def _set_trigger_info_and_iac_ci_info(self):
        """
        Sets the trigger information for the instance.

        This method retrieves and sets trigger-related information, including
        trigger_info, trigger_id, iac_ci_id, and iac_ci_info. It prioritizes
        information from existing attributes and falls back to retrieving from
        the database or generating if necessary.

        Returns:
            dict: A dictionary indicating the status of the operation.
                If successful, the dictionary contains {"status": True}.
                If unsuccessful, it contains {"status": False} and a
                "failed_message" explaining the reason.
        """
        if not self.trigger_id and (self.build_id or self.run_id):
            self._load_run_info()

        if not self.run_info and not self.webhook_info and self.run_id and self.trigger_id:
            self._load_run_info()

        try:
            repo_name = self.run_info.get("repo_name")
        except Exception:
            repo_name = None

        if not self.trigger_id:
            try:
                self.trigger_id = self.webhook_info.get("trigger_id")
            except Exception:
                self.trigger_id = None

        if not repo_name:
            try:
                repo_name = self.webhook_info.get("repo_name")
            except Exception:
                repo_name = None

        self.logger.debug(f'_set_trigger_info_and_iac_ci_info: trigger_id: {self.trigger_id}')
        self.logger.debug(f'_set_trigger_info_and_iac_ci_info: repo_name: {repo_name}')

        self._set_trigger_info()
        if not self.trigger_info:
            self.trigger_info = False
            return {
                "status": False,
                "failed_message": "could not get self.trigger_info"
            }

        if not self.trigger_id:
            self.trigger_id = self.trigger_info['trigger_id']

        self.logger.debug(f'_set_trigger_info_and_iac_ci_info: trigger_id: {self.trigger_id}')

        if not self.iac_ci_id and self.webhook_info:
            self.logger.debug(f'hash inputs: trigger_id:{self.trigger_id}/branch:{self.webhook_info["branch"]}')
            self.logger.debug(f'hash object: iac_ci.{self.trigger_id}.{self.webhook_info["branch"]}')
            self.iac_ci_id = get_hash_from_string(f'iac_ci.{self.trigger_id}.{self.webhook_info["branch"]}')

        if not self.iac_ci_id:
            return {
                "status": False,
                "failed_message": "cannot determine iac_ci_id"
            }

        self.iac_ci_info = self.db.get_iac_info(self.iac_ci_id)

        if not self.iac_ci_info:
            return {
                "status": False,
                "failed_message": f'iac_ci_info iac_ci_id => "{self.iac_ci_id}" not found in db'
            }

        return {"status": True}

    def set_s3_key(self):
        """
        Sets the S3 key and related attributes.

        This method sets the local source path, remote S3 bucket key,
        and remote S3 bucket for storing source code. It uses the
        stateful ID and commit hash to generate unique keys.

        Raises:
            Exception: If the stateful ID is not set.
        """
        if not self.stateful_id:
            raise Exception("stateful_id needs to be set")

        self.remote_src_bucket = self.tmp_bucket
        self.local_src = f'/tmp/{self.webhook_info["commit_hash"]}.zip'

        if self.report:
            ref_subkey = self.run_id
        else:
            ref_subkey = self.webhook_info["commit_hash"]

        if self.report and self.phase in ["update-pr"]:
            return

        if not self.iac_ci_folder:
            raise Exception("set_s3_key: iac_ci_folder needs to be set")

        common_base = f'{self.webhook_info["repo_name"]}/{self.webhook_info["branch"]}/{str(self.webhook_info["pr_number"])}/{self.iac_ci_folder}'
        self.remote_src_bucket_key = f'{common_base}/state/src.{ref_subkey}.zip'
        self.remote_build_env_vars_key = f'{common_base}/state/{ref_subkey}/build_env_vars.env.enc'

    def _set_iac_ci_folder(self):

        try:
            self.iac_ci_folder = self.run_info["iac_ci_folder"]
        except:
            self.iac_ci_folder = None

    def _set_add_class_vars(self):
        """
        Sets additional class variables based on webhook, trigger, and runtime information.
        
        This method initializes various attributes needed for the pipeline execution.
        """
        if self.webhook_info:
            self.ssh_url = self.webhook_info["ssh_url"]

        self.ssm_ssh_key = self.trigger_info["ssm_ssh_key"]
        self.repo_name = self.trigger_info["repo_name"]
        self.git_depth = self.run_info.get("git_depth", 1)

        self._set_iac_ci_folder()

        if self.run_info.get("app_dir"):
            self.app_dir = self.run_info["app_dir"]
        else:
            self.app_dir = self.iac_ci_info["app_dir"]

        if self.report:
            self.stateful_id = self.run_id
        else:
            self.stateful_id = self.webhook_info["commit_hash"]

        self.run_share_dir = f'/var/tmp/share/{self.stateful_id}'

        self.set_s3_key()

    def _set_s3_data_key(self):

        # s3_key for run data
        if self.report and self.parent_run_id:
            # data is from the parent run_id
            self.s3_data_key = f"{self.build_name}/runs/{self.parent_run_id}"
        elif self.run_id:
            self.s3_data_key = f"{self.build_name}/runs/{self.run_id}"

    def _setup(self):
        """
        Sets up the necessary information for the reporter.

        This method performs the initial setup for the Config0Reporter,
        including retrieving trigger information, setting SSM parameters,
        and loading run information if available. It also initializes
        new run data if this is a new run.

        Returns:
            dict: A dictionary indicating the status of the setup operation.
            Returns {"status": True} if successful, or a dictionary with
            "status": False and a "failed_message" if an error occurred.
        """
        set_info = self._set_trigger_info_and_iac_ci_info()

        if set_info.get("status") is False:
            self.add_log(set_info.get("failed_message"))
            self.results["status"] = "failed"
            self.results["msg"] = set_info.get("failed_message")

            if set_info.get("failed_message"):
                self.results["notify"] = {
                    "failed_message": set_info["failed_message"]
                }
            else:
                self.results["notify"] = {
                    "failed_message": "_setup failed"
                }
            return set_info

        self.ssm_callback_token = self.trigger_info.get("ssm_callback_token")
        self.user_endpoint = self.trigger_info.get("user_endpoint")
        self.ssm_ssh_key = self.trigger_info.get("ssm_ssh_key")
        self.tmp_bucket = self.trigger_info.get("s3_bucket_tmp")
        self.build_name = "iac-ci"

        self._set_s3_data_key()

        try:
            self.build_timeout = int(self.trigger_info.get("build_timeout", 600))
        except Exception:
            self.build_timeout = 600

        # this is a new run
        if not self.run_id:
            self._init_run_id()
            self._set_s3_data_key()
            return {"status": True}

        if os.environ.get("DEBUG_IAC_CI"):
            self.logger.debug("#" * 32)
            self.logger.debug(f"provided run_id: {self.run_id}")
            self.logger.debug(f"s3_data_key: {self.s3_data_key}")
            self.logger.debug(f"phase: {self.phase}")
            self.logger.debug("#" * 32)

        # existing run
        self._load_run_info()
        self._set_add_class_vars()

        if self.phase not in [ "pkgcode-to-s3" ]:
            if self.run_info.get("build_env_vars_b64"):
                try:
                    self.build_env_vars = json.loads(base64.b64decode(self.run_info["build_env_vars_b64"]).decode('utf-8'))
                except Exception as e:
                    self.logger.error(f"could not decode build_env_vars_b64: {str(e)}")
                    self.build_env_vars = {}
            else:
                try:
                    self.build_env_vars = self._get_b64_data_frm_s3(self.remote_src_bucket, self.remote_build_env_vars_key)
                except Exception as e:
                    self.logger.error(f"could not get build_env_vars from s3: {str(e)}")
                    self.build_env_vars = {}
        else:
            self.build_env_vars = {}

        if os.environ.get("DEBUG_IAC_CI"):
            self.logger.debug("#"*32)
            self.logger.debug(f"# phase {self.phase}")
            self.logger.json(self.build_env_vars)
            self.logger.debug("#"*32)

        if os.environ.get("DEBUG_IAC_CI"):
            os.environ["DEBUG_IAC_CI"] = "True"

        if not self.iac_platform:
            if os.environ.get("IAC_PLATFORM"):
                self.iac_platform = os.environ["IAC_PLATFORM"]
                self.logger.debug(f"iac platform {self.iac_platform} set by os.environ")
            elif self.build_env_vars.get("IAC_PLATFORM"):
                self.iac_platform = self.build_env_vars["IAC_PLATFORM"]
                os.environ["IAC_PLATFORM"] = self.iac_platform
                self.logger.debug(f"iac platform {self.iac_platform} set by build_env_vars")
            else:
                self.iac_platform = "config0"
                os.environ["IAC_PLATFORM"] = self.iac_platform
                self.logger.debug(f"iac platform {self.iac_platform} set by default")

        if self.webhook_info:
            self.commit_hash = self.webhook_info["commit_hash"]

        if self._get_data_frm_s3():
            self.logger.debug("got existing run data from s3")
        else:
            self.logger.warn("could not get data from s3")

        return {"status": True}

    def _init_run_id(self):
        """
        Initializes a new run ID.

        This method generates a new run ID using the `new_run_id()` function,
        updates the `run_id` attribute and the `results` dictionary with the new ID,
        sets the S3 key for the run, and initializes new data for the run.

        Returns:
            dict: A dictionary indicating success with {"status": True}.
        """
        self.run_id = new_run_id()
        self.results["run_id"] = self.run_id
        self.results["_id"] = self.run_id
        self._init_new_data()
        return {"status": True}

    def put_data_in_s3(self):
        """
        Puts data into S3.

        This method encodes the instance's data, writes it to a temporary file,
        uploads the file to S3, and then removes the temporary file.

        Returns:
            bool: True if the data was successfully uploaded to S3.
        """
        srcfile = os.path.join("/tmp", id_generator())
        self.logger.debug(f"putting data in s3: bucket: {self.tmp_bucket}, key: {self.s3_data_key}")
        _data_hash = b64_encode(json.dumps(self.data))

        with open(srcfile, 'w') as _file:
            _file.write(_data_hash)

        self.s3_file.insert(
            s3_bucket=self.tmp_bucket,
            s3_key=self.s3_data_key,
            srcfile=srcfile
        )

        rm_rf(srcfile)

        return True

    def _get_b64_data_frm_s3(self,s3_bucket,s3_key):

        dstfile = os.path.join("/tmp", id_generator())

        try:
            self.s3_file.get(
                s3_bucket=s3_bucket,
                s3_key=s3_key,
                dstfile=dstfile
            )

            _datab64 = open(dstfile, "r").read()
            _decoded = b64_decode(_datab64)

            try:
                data = json.loads(_decoded)
            except Exception:
                data = _decoded
        except Exception as e:
            self.logger.error(f"could not get data from s3 {s3_bucket}/{s3_key}: {str(e)}")
            return {}

        rm_rf(dstfile)

        return data

    def _get_data_frm_s3(self):
        """
        Retrieves data from S3.

        This method retrieves data from S3, decodes it from base64,
        and loads it as JSON into the `data` attribute.

        Returns:
            bool: True if the data was successfully retrieved and loaded.
        """

        self.logger.debug(f"getting data from s3: bucket: {self.tmp_bucket}, key: {self.s3_data_key}")
        self.data = self._get_b64_data_frm_s3(self.tmp_bucket,self.s3_data_key)
        self.active = True

        return True

    def _init_new_data(self):
        """
        Initializes new data for a run.

        This method creates a new data dictionary with default values
        for a new run, including status, start time, automation phase,
        and job-related information. It also populates additional fields
        from the trigger_info if available.

        Returns:
            dict: The initialized data dictionary.
        """
        self.data = {
            "status": "running",
            "start_time": str(int(time())),
            "automation_phase": "continuous_delivery",
            "job_name": self.app_info_iac["name"],
            "run_title": self.app_info_iac["name"],
            "sched_name": self.app_info_iac["name"],
            "sched_type": "build"
        }

        if self.trigger_info.get("project_id"):
            self.data["project_id"] = self.trigger_info["project_id"]

        if self.trigger_info.get("schedule_id"):
            self.data["schedule_id"] = self.trigger_info["schedule_id"]

        if self.trigger_info.get("sched_type"):
            self.data["sched_type"] = self.trigger_info["sched_type"]

        if self.trigger_info.get("sched_name"):
            self.data["sched_name"] = self.trigger_info["sched_name"]

        if self.trigger_info.get("run_title"):
            self.data["run_title"] = self.trigger_info["run_title"]

        if self.trigger_info.get("job_name"):
            self.data["job_name"] = self.trigger_info["job_name"]

        self.data["first_jobs"] = [self.data["job_name"]]
        self.data["final_jobs"] = [self.data["job_name"]]
        self.data["orders"] = []
        self.data["run_id"] = self.run_id

        return self.data

    def _load_run_info(self):
        """
        Loads run information.

        This method loads run information from the database based on
        the run_id or build_id. It retrieves the trigger_id and
        webhook_info from the run_info and decodes the webhook_info
        if available.

        Raises:
            Exception: If run_info cannot be found in the database.

        Returns:
            None
        """
        if self.run_info and self.webhook_info:
            return

        self.run_info = self.db.get_run_info(
            run_id=self.run_id,
            build_id=self.build_id
        )

        if not self.run_info:
            raise Exception("cannot find run_info")

        if self.run_info.get("build_env_vars_b64"):
            self.build_env_vars_b64 = self.run_info["build_env_vars_b64"]
            try:
                iac_platform = b64_decode(self.build_env_vars_b64)["IAC_PLATFORM"]
            except Exception:
                iac_platform = None

            if iac_platform:
                os.environ["IAC_PLATFORM"] = iac_platform
                self.logger.debug(f'iac platform {iac_platform} set by run_info')

        try:
            self.trigger_id = self.run_info["trigger_id"]
        except Exception:
            self.trigger_id = None

        try:
            self.webhook_info = b64_decode(self.run_info["webhook_info_hash"])
        except Exception:
            self.webhook_info = None

    def new_order(self, **kwargs):
        """
        Creates a new order.

        This method creates a new order dictionary with information about a specific task or step
        in the workflow. It includes details such as queue ID, start time, role, human-readable
        description, and initial status.

        Args:
            kwargs (dict): Keyword arguments providing additional details for the order.
                This should include "role" and "human_description", and optionally "status".

        Returns:
            dict: The newly created order dictionary.
        """
        self.order = {
            "queue_id": get_queue_id(size=15),
            "start_time": str(self.start_time),
            "role": kwargs["role"],
            "human_description": kwargs["human_description"],
            "status": kwargs.get("status", "in_progress")
        }

        return self.order

    def add_log(self, log=None):
        """
        Adds a log message to the results.

        This method adds a log message to the "log" section of the results dictionary.
        If the "log" section doesn't exist, it creates it. If it does exist, it appends
        the new log message to the existing log, separated by a newline character.

        Args:
            log (str, optional): The log message to add. Defaults to None.

        Returns:
            str: The updated log string.
        """
        if not self.results.get("log"):
            self.results["log"] = log
        else:
            self.results["log"] = self.results["log"] + "\n" + log

        return self.results["log"]

    def insert_to_return(self):
        """
        Inserts IDs into the results dictionary.

        This method inserts iac_ci_id, trigger_id, and run_id into the
        results dictionary if they are set and not already present in the results.

        Returns:
            None
        """
        if self.iac_ci_id and not self.results.get("iac_ci_id"):
            self.results["iac_ci_id"] = self.iac_ci_id

        if self.trigger_id and not self.results.get("trigger_id"):
            self.results["trigger_id"] = self.trigger_id

        if self.run_id and not self.results.get("run_id"):
            self.results["run_id"] = self.run_id

    def finalize_order(self,ignore_status=False):
        """
        Finalizes an order.

        This method finalizes an order by updating its status, stop time,
        checkin time, and total time. It also adds a log message indicating
        the success or failure of the order and appends the order to the
        data dictionary.

        Returns:
            str: A message indicating the final status of the order.
        """
        stop_time = int(time())
        self.order["status"] = self.results["status"]
        self.order["stop_time"] = str(stop_time)
        self.order["checkin"] = stop_time
        self.order["total_time"] = stop_time - self.start_time
        self.order["total_time"] = int(max(self.order["total_time"], 1))

        if ignore_status:
            msg = f"SUCCESS ORDER: {self.order['human_description']}"
            self.order["status"] = "completed"
        else:
            if self.results.get("status") in ["timed_out"]:
                msg = f"TIMED_OUT ORDER: {self.order['human_description']}"
                self.order["status"] = "timed_out"
            elif self.results.get("status") in ['failed', False, "false", "timed_out"]:
                msg = f"FAILED ORDER: {self.order['human_description']}"
                self.order["status"] = "failed"
            else:
                msg = f"SUCCESS ORDER: {self.order['human_description']}"
                self.order["status"] = "completed"

        self.add_log("\n")
        self.add_log(msg)
        self.add_log("\n")

        self.logger.debug("#" * 32)
        self.logger.debug(msg)
        self.logger.debug("#" * 32)

        self.order["log"] = self.results["log"]

        if self.data:
            self.data["orders"].append(self.order)

        return msg

    def close_pipeline(self):
        """
        Closes the pipeline.

        This method updates the pipeline data with the final status, stop time, and total time.
        It iterates through the orders in the data and updates the overall pipeline status
        to "timed_out" or "failed" if any order has that status.

        Returns:
            dict: The updated data dictionary.
        """
        self.data["status"] = self.results.get("status")
        self.data["stop_time"] = str(int(time()))
        self.data["total_time"] = int(self.data["stop_time"]) - int(self.data["start_time"])

        if not self.data.get("orders"):
            return self.data

        self._update_orders_in_data()

        for order in self.data["orders"]:
            # one failure is failure of the pipeline
            if order.get("status") in ["timed_out"]:
                self.data["status"] = "timed_out"
                break

            if order.get("status") in ["failed", "timed_out", "unsuccessful"]:
                self.data["status"] = "failed"
                break

        return self.data

    def _insert_to_order_frm_trigger_info(self, order, wt):
        """
        Inserts trigger information into an order.

        This method updates the given order dictionary with relevant information
        from the trigger_info, including project ID, schedule ID, schedule type,
        schedule name, job name, job instance ID, automation phase, and weight.

        Args:
            order (dict): The order dictionary to update.
            wt (int): The weight to assign to the order.

        Returns:
            None
        """
        if self.trigger_info.get("project_id"):
            order["project_id"] = self.trigger_info["project_id"]

        if self.trigger_info.get("schedule_id"):
            order["schedule_id"] = self.trigger_info["schedule_id"]

        if self.trigger_info.get("sched_type"):
            order["sched_type"] = self.trigger_info["sched_type"]

        if self.trigger_info.get("sched_name"):
            order["sched_name"] = self.trigger_info["sched_name"]

        if self.trigger_info.get("job_name"):
            order["job_name"] = self.trigger_info["job_name"]

        if self.trigger_info.get("job_instance_id"):
            order["job_instance_id"] = self.trigger_info["job_instance_id"]

        order["automation_phase"] = "continuous_delivery"
        order["wt"] = wt

    def _update_orders_in_data(self):
        """
        Updates order details within the data dictionary.

        This method iterates through the 'orders' list in the data dictionary and
        populates additional fields for each order based on information from
        trigger_info. It also adds a weight ('wt') to each order, incrementing
        sequentially.

        Returns:
            dict: The updated data dictionary.
        """
        if not self.data.get("orders"):
            return self.data

        # place other fields orders
        for wt, order in enumerate(self.data["orders"], start=1):
            self._insert_to_order_frm_trigger_info(order, wt)

        return self.data

    def get_publish_vars(self):
        """
        Retrieves variables to publish.

        This method retrieves variables to be published, primarily from the
        webhook_info. It ensures a webhook_info dictionary exists and removes
        the "status" key if present.

        Returns:
            dict: The dictionary of variables to publish.
        """
        if not self.webhook_info:
            self.webhook_info = {}

        if self.webhook_info and "status" in self.webhook_info:
            del self.webhook_info["status"]

        return self.webhook_info

    def _eval_data(self):
        """
        Evaluates and updates the data dictionary.

        This method performs several operations on the data dictionary:
        1. Adds the webhook_info to the data under the "commit" key if it's not already present.
        2. Retrieves publish variables from various sources (existing data, get_publish_vars, results)
           and merges them into the data["publish_vars"].
        3. Calls _update_orders_in_data to update order details.

        Raises:
            Exception: If the data dictionary is empty.

        Returns:
            dict: The updated data dictionary.
        """
        if not self.data:
            raise Exception('_eval_data: data is empty')

        if not self.data.get("commit") and self.webhook_info:
            self.data["commit"] = self.webhook_info

        _publish_vars = self.data.get("publish_vars") or {}

        _publish_vars = dict(_publish_vars, **self.get_publish_vars())

        if self.results.get("publish_vars"):
            _publish_vars = dict(_publish_vars, **self.results["publish_vars"])

        self.data["publish_vars"] = _publish_vars

        return self._update_orders_in_data()

    def _get_inputargs_http(self):
        """
        Gets input arguments for HTTP requests.

        This method retrieves and assembles the necessary input arguments for making
        HTTP POST requests, including headers, API endpoint, and data payload.
        It retrieves the callback token from SSM if not already set and constructs
        the API endpoint URL. It also adds "automation_phase" and "cdonly" to the
        data dictionary.

        Returns:
            dict: A dictionary containing the input arguments for HTTP requests.
        """
        if not self.callback_token:
            try:
                _ssm_info = self.ssm.get_parameter(
                    Name=self.ssm_callback_token,
                    WithDecryption=True
                )
                self.callback_token = _ssm_info["Parameter"]["Value"]
            except Exception as e:
                self.logger.error(f'could not get call back token: {e}')
                return False

        name = f"{self.build_name}-{self.phase}" if self.phase else self.build_name
        api_endpoint = f"https://{self.user_endpoint}/api/v1.0/run"

        inputargs = {
            "verify": False,
            "headers": {
                'content-type': 'application/json',
                "Token": self.callback_token
            },
            "api_endpoint": api_endpoint,
            "name": name
        }

        self.data["automation_phase"] = "continuous_delivery"
        self.data["cdonly"] = "true"

        if os.environ.get("DEBUG_IAC_CI"):
            self.logger.debug("*" * 32)
            self.logger.json(self.data)
            self.logger.debug("*" * 32)

        inputargs["data"] = json.dumps(self.data)

        return inputargs

    def eval_results(self):
        """
        Evaluates and processes the results of a pipeline run.

        This method handles the final steps of a pipeline run, including evaluating data,
        updating run information in S3, closing the pipeline, sending results to Config0,
        and triggering notifications. It checks for various conditions such as initialization
        status, close status, and update status to determine the appropriate actions.

        Returns:
            dict: The final results of the pipeline run.
        """
        try:
            self._eval_data()
        except Exception:
            failed_message = traceback.format_exc()
            self.logger.warn(f"could not eval data:\n\n{failed_message}")

        # if not initialized, then we never got into build pipeline
        # e.g. webhook never triggered anything
        if not self.results.get("initialized") and self.phase == "load_webhook":
            self.results["continue"] = False
            self.results["update"] = False
            self.results["close"] = False
            return self.results

        if self.results.get("close"):
            self.results["continue"] = False
            self.results["update"] = True

        # do not update if close is True
        if self.results.get("update"):
            try:
                self.put_data_in_s3()
            except Exception:
                self.logger.warn("could not put data")

        # evaluate if close now and return results
        if self.results.get("close"):
            try:
                self.close_pipeline()
            except Exception:
                self.logger.warn("could not close pipeline")

            # TODO add different saas reporting here
            # e.g.
            # try:
            #    self.sent_to_config0()
            # except Exception:
            #    self.logger.warn("could not update saas")

            if self.results.get("status") in ["failed", "timed_out", False, "false"]:
                if not self.results.get("failed_message") and self.results.get('traceback'):
                    self.results["failed_message"] = self.results["traceback"]

                # we don't notify loading webhook
                if self.phase == "load_webhook":
                    return self.results

        self.notify()

        return self.results

    def _get_notify_message(self):
        """
        Constructs the notification message.

        This method builds the notification message by combining various pieces of information
        from the results and trigger_info. It starts with a base message, adds the status,
        repo name, and includes any failed or appended messages if available. If an override
        message is provided, it returns that instead.

        Returns:
            str: The constructed notification message.
        """
        if self.results["notify"].get("overide"):
            return self.results["notify"]["overide"]

        base_message = self.results["notify"].get("message")
        failed_message = self.results["notify"].get("failed_message")
        append_message = self.results["notify"].get("append_message")

        if base_message:
            message = f"{base_message}\nstatus: {self.results.get('status')}"
        else:
            message = f"status: {self.results.get('status')}"

        _message = f"repo name: {self.trigger_info.get('repo_name')}\n\n"
        message = message + "\n" + _message

        if failed_message:
            message = message + "#" * 32 + "\n# failed message\n" + "#" * 32 + f"\n\n{failed_message}\n\n" + "#" * 32

        if append_message:
            message = message + "\n" + append_message

        return message

    def _process_new_order_failure(self):
        """
        Processes a new order failure during setup.

        This method handles failures that occur during the initial setup phase of a new order.
        It sets the start time, creates a new order with a description indicating the failure,
        and adds log messages detailing the failure.

        Returns:
            None
        """
        self.start_time = int(time())

        human_description = f'Setup failed phase "{self.phase}"'

        inputargs = {
            "human_description": human_description,
            "role": "run_helper/internal"
        }

        self.new_order(**inputargs)

        self.add_log("#" * 32)
        self.add_log(f'# Failed setup for the lambda "{self.phase}" function')
        self.add_log("#" * 32)
        self.add_log("\n")

    def _process_execution_failure(self):
        """
        Processes an execution failure.

        This method handles failures that occur during the execution phase of a run.
        It sets the start time, creates a new order with a description indicating the failure,
        and adds log messages detailing the failure. It specifically targets failures within
        the lambda function associated with the current phase.

        Returns:
            None
        """
        self.start_time = int(time())

        inputargs = {
            "human_description": f'Run failed phase "{self.phase}"',
            "role": "run_helper/internal"
        }

        self.new_order(**inputargs)

        self.add_log("#" * 32)
        self.add_log(f'# Failed execution for the lambda "{self.phase}" function')
        self.add_log("#" * 32)
        self.add_log("\n")

    def _update_with_failure(self, failed_message):
        """
        Updates the run status and results with failure information.

        This method updates the internal state and results of the run to reflect a failure.
        It adds the failed message to the logs, sets the status to "failed", stops continuation,
        enables updates, adds the failed message to notifications, and sets the close flag.
        Finally, it finalizes the current order and saves the run information.

        Args:
            failed_message (str): The message describing the failure.

        Returns:
            None
        """
        self.add_log(failed_message)
        self.results["status"] = "failed"
        self.results["continue"] = False
        self.results["update"] = True
        if self.results.get("notify"):
            self.results["notify"]["failed_message"] = failed_message
        else:
            self.results["notify"] = {
                "failed_message": failed_message
            }
        self.results["close"] = True

        self.run_info["status"] = "failed"

        self.finalize_order()
        self._save_run_info()

    def _print_run_results(self):
        """
        Prints run results for debugging.

        This method prints the run results to the logs for debugging purposes.
        It checks if DEBUG_IAC_CI environment variable is set or if the results
        indicate a step function execution. If either condition is met, it prints
        a copy of the results after removing the "log" and "publish_vars" keys.

        Returns:
            None
        """
        if not os.environ.get("DEBUG_IAC_CI") and not self.results.get("step_func"):
            return

        results = self.results.copy()

        if results.get("log"):
            del results["log"]

        if results.get("publish_vars"):
            del results["publish_vars"]

        self.logger.debug("+" * 32)
        self.logger.json(results)
        self.logger.debug("+" * 32)

    def _eval_step_func(self, e_status=None):
        """
        Evaluates step function execution status.

        This method handles specific logic related to step function executions.
        It checks if the run is part of a step function and performs actions based on the
        provided execution status (e_status). It prints run results, handles continuation
        or failure of CodeBuild checks, and returns specific results for discontinuation.

        Args:
            e_status (str, optional): The execution status from a previous step. Defaults to None.

        Returns:
            dict or None: A dictionary containing execution details if the run is part of a step function
            and a specific action is taken (continue, fail, or discontinue). Otherwise, returns None.
        """
        if not self.results.get("step_func"):
            return

        self._print_run_results()

        # special keywords for check_codebuild
        if e_status == "check_codebuild/_continue":
            self.logger.debug("." * 32)
            self.logger.debug("." * 32)
            self.logger.debug("check_codebuild running in step function - should continue in loop")
            self.logger.debug("." * 32)
            self.logger.debug("." * 32)
            return self.results

        if e_status == "check_codebuild/_failed":
            raise Exception(f'codebuild failed - status: "{self.results.get("status")}", build_id: "{self.build_id}"')

        if e_status == "check_codebuild/_discontinue":
            results = {
                "continue": False,
                "build_id": self.build_id,
                "chk_t0": self.chk_t0,
                "chk_count": self.chk_count
            }

            return results

        return

    def run(self, **kwargs):
        """
        Runs the main reporting process.

        This method orchestrates the entire reporting workflow. It starts by running the setup
        and handles any initialization failures. Then, it executes the core logic defined by
        the `execute` method (which should be implemented by subclasses). It processes execution
        failures, evaluates step function information if applicable, prints run results, and
        finally evaluates and returns the overall results.

        Args:
            kwargs (dict): Keyword arguments passed to the `execute` method.

        Returns:
            dict: The results of the pipeline run, or information about step function execution.
        """
        self.logger.debug("running setup")

        if hasattr(self, "init_failure") and self.init_failure:
            self.logger.warn(f'processing init_failure: init_failure {self.init_failure}')
            self._process_new_order_failure()
            self._update_with_failure(self.init_failure)
            return self.eval_results()

        failed_message = None

        try:
            setup_info = self._setup()
        except Exception:
            setup_info = {"status": False}
            failed_message = traceback.format_exc()

        if setup_info.get("status") is False or failed_message:
            if not failed_message:
                failed_message = setup_info.get("failed_message")
            self.logger.warn(f"setup_info failed:\n\n{failed_message}")
            self._process_new_order_failure()
            self._update_with_failure(failed_message)
            return self.eval_results()

        # execute method will be in the
        # class inheriting this class
        try:
            e_status = self.execute(**kwargs)
        except Exception:
            failed_message = traceback.format_exc()
            self.logger.warn(f"execute failed:\n\n{failed_message}")
            self._process_execution_failure()
            self._update_with_failure(failed_message)
            return self.eval_results()

        step_func_info = self._eval_step_func(e_status=e_status)

        if step_func_info:
            return step_func_info

        self._print_run_results()

        return self.eval_results()

    def add_publish(self, values):
        """
        Adds variables to be published.

        This method adds the provided `values` to the "publish_vars" section
        of the results dictionary. If "publish_vars" doesn't exist, it creates it.

        Args:
            values (dict): The variables to add to "publish_vars".

        Returns:
            None
        """
        if not self.results.get("publish_vars"):
            self.results["publish_vars"] = {}

        self.results["publish_vars"].update(values)

    def set_additional_build_vars(self):
        """
        Initializes build variables.

        This method initializes various build-related variables from trigger_info and iac_ci_info.
        It sets up parameters for remote state, runtime environment, application directory,
        shared directory, output folder, AWS region, and SSM parameters. It also handles
        Infracost API key setup and creates a temporary SSM name if needed.

        Returns:
            None
        """

        self.remote_stateful_bucket = self.trigger_info["remote_stateful_bucket"]

        self.logger.debug("#" * 32)
        self.logger.debug("# build_env_vars")

        self.s3_output_folder = id_generator2()

        # ref 436365256
        if self.report:
            self.logger.debug("Overwriting build_env_vars for report/parallel folders")
            self.build_env_vars["RUN_ID"] = self.run_id
            self.build_env_vars["STATEFUL_ID"] = self.run_id
        else:
            self.build_env_vars["STATEFUL_ID"] = self.webhook_info["commit_hash"]

        self.build_env_vars["RUN_SHARE_DIR"] = f'/var/tmp/share/{self.build_env_vars["STATEFUL_ID"]}'
        self.logger.json(self.build_env_vars)
        self.logger.debug("#" * 32)

        self.tf_runtime = self.iac_ci_info["tf_runtime"]
        self.aws_region = self.iac_ci_info.get("aws_default_region", "us-east-1")

        # TODO: may want to change this on a run level
        # ssm_name and infracost_api_key is typically set at the repo level
        ssm_name = self.iac_ci_info.get("ssm_name")
        infracost_api_key = self._set_infracost_api_key()

        update_ssm_values = {}

        if infracost_api_key:
            update_ssm_values = {"INFRACOST_API_KEY": infracost_api_key}

        new_ssm_name = self.create_temp_ssm_name(ssm_name, update_ssm_values)
        self.logger.debug(f'new ssm name "{new_ssm_name}"')

        self.ssm_name = new_ssm_name or ssm_name

    def get_aws_exec_cinputargs(self, method="ci"):
        """
        Gets input arguments for AWS execution.

        This method retrieves and assembles input arguments for AWS execution,
        including build timeout, bucket information, directories, stateful ID,
        output folder, commit hash, SSM name, Terraform runtime details.

        Args:
            method (str, optional): Execution method ("ci" or other). Defaults to "ci".

        Returns:
            dict: A dictionary containing the input arguments for AWS execution.
        """
        cinputargs = {
            "method": method,
            "tmp_bucket": self.tmp_bucket,
            "aws_region": self.aws_region,
            "remote_src_bucket": self.remote_src_bucket,
            "remote_src_bucket_key": self.remote_src_bucket_key,
            "app_dir": self.app_dir,
            "run_share_dir": self.run_share_dir,
            "stateful_id": self.stateful_id,
            "s3_output_folder": self.s3_output_folder,
            "commit_hash": self.webhook_info["commit_hash"]
        }

        if self.ssm_name:
            cinputargs["ssm_name"] = self.ssm_name

        if self.build_env_vars.get("BUILD_TIMEOUT"):
            cinputargs["build_timeout"] = int(self.build_env_vars["BUILD_TIMEOUT"])
        else:
            cinputargs["build_timeout"] = self.build_timeout

        if self.build_env_vars.get("TMPDIR"):
            cinputargs["tmpdir"] = self.build_env_vars["TMPDIR"]
        else:
            cinputargs["tmpdir"] = "/tmp"

        if self.build_env_vars.get("AWS_DEFAULT_REGION"):
            cinputargs["aws_region"] = self.build_env_vars["AWS_DEFAULT_REGION"]
        else:
            cinputargs["aws_region"] = self.aws_region

        if self.build_env_vars.get("TF_RUNTIME"):
            tf_runtime = self.build_env_vars["TF_RUNTIME"]
        else:
            tf_runtime = self.tf_runtime

        binary, version = tf_runtime.split(":")

        cinputargs.update({
            "version": version,
            "binary": binary,
            "tf_runtime": tf_runtime
        })

        if self.build_env_vars.get("DOCKER_IMAGE"):
            cinputargs["docker_image"] = self.build_env_vars["DOCKER_IMAGE"]
        else:
            cinputargs["docker_image"] = tf_runtime

        if self.build_env_vars.get("IAC_PLATFORM"):
            cinputargs["build_env_vars"] = {"IAC_PLATFORM": self.build_env_vars["IAC_PLATFORM"]}
            cinputargs["iac_platform"] = self.build_env_vars["IAC_PLATFORM"]

        return cinputargs