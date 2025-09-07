#!/usr/bin/python
# Copyright 2025 Gary Leong gary@config0.com
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import os
import json
import base64
import uuid
import traceback
import hmac
import hashlib
import six

from time import sleep
from datetime import datetime
from datetime import timedelta

from iac_ci.common.boto3_dynamo import Dynamodb_boto3
from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.notify_slack import SlackNotify

import hmac
import hashlib


class CreateTempParamStoreEntry:
    """
    Creates temporary entries in AWS Systems Manager Parameter Store with expiration.
    """

    def __init__(self, expire_mins=60):
        """
        Initialize with expiration time for parameters.

        Args:
            expire_mins (int): Minutes until parameter expiration
        """
        self.ssm_tmp_prefix = os.environ.get("IAC_CI_SSM_TMP_PREFIX", 
                                             '/iac-ci/imported/tmp')
        self.ssm_expire_mins = expire_mins

    def _fetch_ssm_param(self, name):
        """
        Fetch a parameter from AWS Systems Manager Parameter Store.

        Args:
            name (str): Parameter name to fetch

        Returns:
            str: Parameter value
        """
        try:
            response = self.ssm.get_parameter(Name=name, WithDecryption=True)
            return response['Parameter']['Value']
        except Exception as e:
            self.logger.error(f'could not get parameter {e}')
            return False
    
    def _get_expiration_parameter_policy(self):
        """
        Generate expiration policy for SSM parameter.

        Returns:
            str: JSON string containing expiration policy
        """
        current_datetime = datetime.now()
        future_datetime = current_datetime + timedelta(minutes=self.ssm_expire_mins)
        iso_instant_str = future_datetime.isoformat(timespec='seconds') + 'Z'

        policy = [{
            "Type": "Expiration",
            "Version": "1.0",
            "Attributes": {
                "Timestamp": iso_instant_str
            }
        }]

        return json.dumps(policy)

    def put_advance_param(self, name, value):
        """
        Put a parameter in SSM Parameter Store with advanced features.

        Args:
            name (str): Parameter name
            value (str): Parameter value

        Returns:
            dict: Response from SSM put_parameter
        """
        inputargs = {
            "Name": name,
            "Value": value,
            "Type": "SecureString",
            "Overwrite": True,
            "Tier": "Advanced",
            "Description": 'Temp Parameter with expiration',
            "Policies": self._get_expiration_parameter_policy()
        }

        return self.ssm.put_parameter(**inputargs)

    @staticmethod
    def _decode_env_to_dict(encoded_env):
        """
        Decode base64 encoded environment variables to dictionary.

        Args:
            encoded_env (str): Base64 encoded environment variables

        Returns:
            dict: Decoded environment variables
        """
        decoded_bytes = base64.b64decode(encoded_env)
        decoded_str = decoded_bytes.decode('utf-8')
        return dict(
            line.split('=', 1)
            for line in decoded_str.strip().split('\n')
            if line and not line.startswith('#')
        )

    @staticmethod
    def _dict_to_env_str(env_dict):
        """
        Convert dictionary to environment variable string format.

        Args:
            env_dict (dict): Environment variables dictionary

        Returns:
            str: Environment variables in string format
        """
        return '\n'.join(f'{key}={value}' for key, value in env_dict.items())

    def create_temp_ssm_name(self, ssm_name, additional_values):
        """
        Create temporary SSM parameter with combined values.

        Args:
            ssm_name (str): Existing SSM parameter name to fetch values from
            additional_values (dict): Additional values to combine

        Returns:
            str: New SSM parameter name
        """
        env_dict = {}

        if ssm_name:
            try:
                base64_env = self._fetch_ssm_param(ssm_name)
                env_dict = self._decode_env_to_dict(base64_env)
            except (KeyError, ValueError, AttributeError) as e:
                env_dict = {}
                self.logger.warn(f"Could not get env from ssm_name {ssm_name}: {str(e)}")

        if additional_values:
            env_dict.update(additional_values)

        if not env_dict:
            return

        new_env_string = self._dict_to_env_str(env_dict)
        new_base64_env = base64.b64encode(new_env_string.encode('utf-8')).decode('utf-8')
        random_suffix = str(uuid.uuid4())
        new_ssm_name = f"{self.ssm_tmp_prefix}/{random_suffix}"
        self.put_advance_param(new_ssm_name, new_base64_env)

        return new_ssm_name

class Notification:
    """
    Handles notifications to Slack for IaC CI events.
    """
    
    def __init__(self):
        """Initialize notification handler."""
        self.classname = "Notification"
        self.logger = IaCLogger(self.classname)
        self.slack = SlackNotify(username="IaCCINotifyBot",
                               header_text="IaCCI")

        self.slack_webhook_b64 = None
        self.infracost_api_key = None

    def _set_slack_token(self):
        """
        Set Slack webhook token from SSM parameter.

        Returns:
            str: Slack webhook hash
        """
        if self.slack_webhook_b64:
            return self.slack_webhook_b64

        ssm_name = self.trigger_info.get("ssm_slack_webhook_b64")

        if not ssm_name:
            ssm_name = self.trigger_info.get("ssm_slack_webhook_hash")

        if not ssm_name:
            self.logger.warn("ssm_name for slack not found - notification not enabled")
            return

        try:
            _ssm_info = self.ssm.get_parameter(Name=ssm_name, WithDecryption=True)
            self.slack_webhook_b64 = _ssm_info["Parameter"]["Value"]
        except (KeyError, ValueError, AttributeError) as e:
            self.logger.warn(f"Could not fetch slack webhook: {str(e)}")

        return self.slack_webhook_b64

    def get_run_status(self):

        if self.run_info.get('status') in ["failed", False]:
            status_suffix = self.get_pr_status(status="failed")
        else:
            status_suffix = self.get_pr_status(status="successful")

        return status_suffix

    def _eval_links(self):
        """
        Evaluate and collect links for notification.

        Returns:
            list: List of link dictionaries
        """
        links = []

        if self.results["notify"].get("links"):
            links = self.results["notify"]["links"]

        if self.webhook_info.get("commit_hash"):
            commit_hash = self.webhook_info["commit_hash"]
            url = f'https://github.com/{self.webhook_info["owner"]}/{self.webhook_info["repo_name"]}/commit/{commit_hash}'
            links.append({f'commit - {commit_hash[:6]}': url})

        if self.run_info.get("console_url"):
            links.append({"ci pipeline": self.run_info["console_url"]})

        if self.run_info.get("build_url"):
            links.append({"execution details": self.run_info["build_url"]})

        if self.report_url:
            links.append({"IaC-CI summary": self.report_url})

        return links

    def _get_notify_message(self):
        """
        Prepare notification message.

        Returns:
            str: Formatted notification message
        """
        message = f"status: {self.results.get('status')}"
        message = f"{message}\ngit repo: {self.trigger_info.get('repo_name')}"

        if self.run_info:
            message = f"{message}\nbuild_id: {self.run_info.get('build_id')}"

        if self.results.get("traceback"):
            message = f"{message}\n{'#'*32}"
            message = f"{message}\n# Traceback         "
            message = f"{message}\n{'#'*32}"
            message = f"{message}\n"
            message = f"{message}\n{self.results['traceback']}"
            message = f"{message}\n"
            message = f"{message}\n{'#'*32}"

        return message

    def _get_slack_inputargs(self, **kwargs):
        """
        Prepare arguments for Slack notification.

        Args:
            **kwargs: Additional arguments for notification

        Returns:
            dict: Input arguments for Slack notification
        """
        self._set_slack_token()

        message = self._get_notify_message()

        inputargs = {
            "message": message,
            "slack_webhook_b64": self.slack_webhook_b64
        }

        if self.run_info.get("status") in ["failed", "timed_out", False, "false"]:
            inputargs["emoji"] = ":x:"
        elif self.results.get("status") in ["failed", "timed_out", False, "false"]:
            inputargs["emoji"] = ":x:"
        elif self.run_info.get("status") in ["successful", "success", True, "true"]:
            inputargs["emoji"] = ":white_check_mark:"
        elif self.results.get("status") in ["successful", "success", True, "true"]:
            inputargs["emoji"] = ":white_check_mark:"
        else:
            inputargs["emoji"] = ":information_source:"

        try:
            inputargs["title"] = self.results["notify"]["title"]
        except (KeyError, TypeError) as e:
            if kwargs.get("title"):
                inputargs["title"] = kwargs["title"]
            else:
                inputargs["title"] = f'{inputargs["emoji"]} - iac-ci report'

        if links := self._eval_links():
            inputargs["links"] = links

        if self.trigger_info.get("slack_channel"): 
            inputargs["slack_channel"] = self.trigger_info["slack_channel"]

        return inputargs

    def notify(self):
        """
        Send notification to Slack.
        """
        if not self.results.get("notify"):
            self.logger.debug("no notification messages requested")
            return

        try:
            inputargs = self._get_slack_inputargs()
        except Exception as e:
            self.logger.warn(f"_get_slack_inputargs with error {e}")
            inputargs = None

        if not inputargs:
            self.logger.warn("could not get slack inputargs")
            return

        try:
            self.slack.run(inputargs)
        except Exception as e:
            self.logger.error(f"Could not slack notify: {str(e)}\n{traceback.format_exc()}")


class GetFrmDb:
    """
    Retrieve information from DynamoDB tables.
    """

    def __init__(self, **kwargs):
        """
        Initialize database connection.

        Args:
            **kwargs: Must include 'app_name' for table names
        """

        self.classname = "GetFrmDb"
        self.logger = IaCLogger(self.classname)
        dynamodb_boto3 = Dynamodb_boto3()

        app_name = kwargs.get("app_name")

        if not app_name:
            app_name = os.environ.get("APP_NAME_IAC", "iac-ci")

        self.table_runs_name = f'{app_name}-runs'
        self.table_settings_name = f'{app_name}-settings'

        self.table_runs = dynamodb_boto3.set(table=self.table_runs_name)
        self.table_settings = dynamodb_boto3.set(table=self.table_settings_name)

    def get_run_info(self, run_id=None, build_id=None):
        """
        Get run information by run_id or build_id.

        Args:
            run_id (str, optional): Run ID to search for
            build_id (str, optional): Build ID to search for

        Returns:
            dict: Run information
        """
        if run_id:
            return self._run_info_by_run_id(run_id)
        elif build_id:
            return self._run_info_by_build_id(build_id)

    def _run_info_by_run_id(self, run_id):
        """
        Get run information by run ID.

        Args:
            run_id (str): Run ID to search for

        Returns:
            dict: Run information
        """
        _match = {"_id": run_id}

        try:
            run_info = self.table_runs.get(_match)["Item"]
        except (KeyError, AttributeError) as e:
            run_info = None
            self.logger.warn(f"Could not find {_match} in {self.table_runs}: {str(e)}")

        return run_info

    def _run_info_by_build_id(self, build_id):
        """
        Get run information by build ID with retries.

        Args:
            build_id (str): Build ID to search for

        Returns:
            dict: Run information
        """
        run_info = None

        try:
            for _ in range(24):
                query = self.table_runs.search_key("build_id", build_id)
                if query.get("Items"):
                    self.logger.warn(f"Found build_id: {build_id} in {self.table_runs_name}")
                    run_info = query["Items"][0]
                    break
                else:
                    sleep(5)
        except (KeyError, AttributeError) as e:
            self.logger.warn(f"Could not find build_id: {build_id} in {self.table_runs_name}: {str(e)}")
            run_info = None

        return run_info

    def get_trigger_info(self, trigger_id=None, repo_name=None):
        """
        Get trigger information by trigger_id or repo_name.

        Args:
            trigger_id (str, optional): Trigger ID to search for
            repo_name (str, optional): Repository name to search for

        Returns:
            list: List of trigger information
        """
        if trigger_id:
            items = self._trigger_info_by_trigger_id(trigger_id)
        elif repo_name:
            items = self._trigger_info_by_repo_name(repo_name)
        else:
            items = []

        trigger_info = [_item for _item in items if _item.get("type") == "registered_repo"]

        if not trigger_info:
            self.logger.warn(f'No type "registered_repo" trigger found for trigger_id: {trigger_id}/repo_name: {repo_name}')

        return trigger_info

    def _trigger_info_by_trigger_id(self, trigger_id):
        """
        Get trigger information by trigger ID.

        Args:
            trigger_id (str): Trigger ID to search for

        Returns:
            list: List containing trigger information
        """
        match = {"_id": trigger_id}
        self.logger.debug(f"Looking for trigger match {match}")

        try:
            items = [self.table_settings.get(match)["Item"]]
        except (KeyError, AttributeError) as e:
            items = []
            self.logger.warn(f"Could not find trigger with id {trigger_id}: {str(e)}")

        return items

    def _trigger_info_by_repo_name(self, repo_name):
        """
        Get trigger information by repository name with retries.

        Args:
            repo_name (str): Repository name to search for

        Returns:
            list: List of trigger information
        """
        items = []

        for _ in range(24):

            try:
                query = self.table_settings.search_key("repo_name", repo_name)
                items = query["Items"]
                break
            except (KeyError, AttributeError) as e:
                items = []
                self.logger.warn(f"Error finding repo {repo_name}: {str(e)}")
                sleep(5)

        if not items:
            self.logger.warn(f"could not get the trigger info for repo {repo_name}")
        else:
            self.logger.debug(f"found trigger info for repo {repo_name}")

        return items

    def update_iac_ci_folders(self, iac_ci_id, folders):

        """
        Update or create the iac_ci_folders field for the given iac_ci_id with the provided list of folders.
        """
        match = {"_id": iac_ci_id}
        update_expression = "SET iac_ci_folders = :folders"
        expression_attribute_values = {
            ":folders": folders
        }

        return self.table_settings.update(match,
                                          update_expression,
                                          expression_attribute_values,
                                          total_retries=2,
                                          wait_int=2)

    def get_iac_info(self, iac_ci_id):
        """
        Get IaC information by ID.

        Args:
            iac_ci_id (str): IaC CI ID to search for

        Returns:
            dict: IaC CI information
        """
        match = {"_id": iac_ci_id}
        
        try:
            query = self.table_settings.get(match)
            iac_ci_info = query["Item"]
        except (KeyError, AttributeError) as e:
            iac_ci_info = None
            self.logger.warn(f"Could not find iac_ci_id {iac_ci_id}: {str(e)}")

        return iac_ci_info