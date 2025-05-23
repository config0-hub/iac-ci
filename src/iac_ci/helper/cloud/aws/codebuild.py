#!/usr/bin/env python
"""
Module for managing AWS CodeBuild processes and executions.
Provides functionality for triggering builds, monitoring status,
and retrieving build logs from AWS CodeBuild service.
"""

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
import re
import gzip
import traceback
import boto3
import logging

from io import BytesIO
from time import sleep
from time import time
from botocore.exceptions import ClientError
from iac_ci.common.loggerly import IaCLogger

class CodebuildResourceHelper:
    """
    Helper class for managing AWS CodeBuild resources and build processes.
    
    This class handles CodeBuild project management, build triggering,
    status monitoring, and log retrieval. It provides utilities for
    managing build environments and processing build results.
    
    Attributes:
        classname (str): Name of the class for logging purposes
        logger (IaCLogger): Logger instance for the class
        buildspec (str): BuildSpec configuration for CodeBuild
    """
    def __init__(self, **kwargs):
        """
        Initialize CodebuildResourceHelper with build configuration.
        
        Args:
            **kwargs: Dictionary containing build configuration including:
                buildspec (str): BuildSpec for CodeBuild
                build_env_vars (dict): Environment variables for the build
                aws_region (str): AWS region for CodeBuild execution
                build_timeout (int): Timeout in seconds for the build
                method (str): Build method to execute
        """
        self.classname = "CodebuildResourceHelper"
        self.logger = IaCLogger(self.classname)

        self.buildspec = kwargs.get("buildspec")
        self.build_id = None
        self.project_name = None
        self.logarn = None
        self.output = None

        self.iac_platform = kwargs.get("iac_platform") or os.environ.get("IAC_PLATFORM", "config0")

        if self.iac_platform == "config0":
            self.lambda_function_name = f"{self.iac_platform}-iac"
        elif self.iac_platform == "config0-iac":
            self.lambda_function_name = "config0-iac"
        elif self.iac_platform == "iac-ci":
            self.lambda_function_name = "iac-ci"
        else:
            self.lambda_function_name = "iac-ci"

        self.build_env_vars = kwargs["build_env_vars"]
        self.aws_region = kwargs["aws_region"]
        self.build_timeout = kwargs.get("build_timeout")

        if self.build_timeout <= 600:
            self.build_timeout = 2700  # we want to overide timeouts for defaults to lambda time limits

        self.method = kwargs["method"]

        # codebuild
        self.results = {
            "run_t0": int(time()),
            "inputargs": {}
        }

        self.build_image = kwargs.get("build_image") or "aws/codebuild/standard:7.0"
        self.image_type = kwargs.get("image_type") or "LINUX_CONTAINER"
        self.compute_type = kwargs.get("compute_type") or "BUILD_GENERAL1_SMALL"

        if self.iac_platform == "config0":
            self.codebuild_basename = f"{self.iac_platform}-iac"
        elif self.iac_platform == "iac-ci":
            self.codebuild_basename = "iac-ci"
        else:
            self.codebuild_basename = "iac-ci"

        self.build_expire_at = int(time()) + int(self.build_timeout)

        logging.basicConfig()
        logging.getLogger('botocore').setLevel(logging.WARNING)
        logging.getLogger('botocore.hooks').setLevel(logging.WARNING)
        logging.getLogger('botocore.session').setLevel(logging.WARNING)
        logging.getLogger('boto3.resources.action').setLevel(logging.WARNING)
        logging.getLogger('s3transfer').setLevel(logging.WARNING)
        logging.getLogger('s3transfer.utils').setLevel(logging.WARNING)
        logging.getLogger('s3transfer.tasks').setLevel(logging.WARNING)
        logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)

        # codebuild specific settings and variables
        self.codebuild_client = boto3.client('codebuild')

        if not self.results["inputargs"].get("build_image"):
            self.results["inputargs"]["build_image"] = self.build_image

        if not self.results["inputargs"].get("image_type"):
            self.results["inputargs"]["image_type"] = self.image_type

        if not self.results["inputargs"].get("compute_type"):
            self.results["inputargs"]["compute_type"] = self.compute_type

        if not self.results["inputargs"].get("codebuild_basename"):
            self.results["inputargs"]["codebuild_basename"] = self.codebuild_basename

    @staticmethod
    def get_set_env_vars():
        """
        Get a set of environment variables for the build process.

        Returns:
            dict: A dictionary of environment variable names and their default values.
        """
        return {
            "tmp_bucket": True,
            "log_bucket": True,
            "build_image": True,
            "image_type": True,
            "compute_type": True,
            "codebuild_basename": True,
            "app_dir": None,
            "stateful_id": None,
            "remote_stateful_bucket": None,
            "run_share_dir": None,
            "share_dir": None
        }

    def _get_build_status(self, build_ids):
        """
        Retrieve the build status for a list of build IDs.

        Args:
            build_ids (list): List of build IDs to check status for.

        Returns:
            dict: A dictionary mapping build IDs to their status and log ARN.
        """
        builds = self.codebuild_client.batch_get_builds(ids=build_ids)['builds']

        return {
            build["id"]: {
                "status": build["buildStatus"],
                "logarn": build["logs"]["s3LogsArn"],
            }
            for build in builds
        }

    def _set_current_build(self):
        """
        Set the current build information based on the build ID.
        """
        _build = self._get_build_status([self.build_id])[self.build_id]
        self.logarn = _build["logarn"]

        self.results["build_status"] = _build["status"]
        self.results["inputargs"]["logarn"] = self.logarn

    def _check_build_status(self):
        """
        Check the status of the current build and update the results.

        Returns:
            str: The status of the build if it is completed, otherwise None.
        """
        _build = self._get_build_status([self.build_id])[self.build_id]

        build_status = _build["status"]
        self.results["build_status"] = build_status

        self.logger.debug(f"codebuild status: {build_status}")

        if build_status == 'IN_PROGRESS':
            return

        done = [
            "SUCCEEDED",
            "STOPPED",
            "TIMED_OUT",
            "FAILED_WITH_ABORT",
            "FAILED",
            "FAULT"
        ]

        if build_status in done:
            return build_status

    def _set_build_status_codes(self):
        """
        Set the status codes based on the current build status.

        Returns:
            bool: True if the status was set successfully, otherwise False.
        """
        build_status = self.results["build_status"]

        if build_status == 'SUCCEEDED':
            self.results["status_code"] = "successful"
            self.results["status"] = True
            return True

        failed_message = f"codebuld failed with build status {build_status}"

        if build_status == 'FAILED':
            self.results["failed_message"] = failed_message
            self.results["status_code"] = "failed"
            self.results["status"] = False
            return True

        if build_status == 'FAULT':
            self.results["failed_message"] = failed_message
            self.results["status_code"] = "failed"
            self.results["status"] = False
            return True

        if build_status == 'STOPPED':
            self.results["failed_message"] = failed_message
            self.results["status_code"] = "failed"
            self.results["status"] = False
            return True

        if build_status == 'TIMED_OUT':
            self.results["failed_message"] = failed_message
            self.results["status_code"] = "timed_out"
            self.results["status"] = False
            return True

        if build_status == 'FAILED_WITH_ABORT':
            self.results["failed_message"] = failed_message
            self.results["status_code"] = "failed"
            self.results["status"] = False
            return True

        _time_elapsed = int(time()) - self.results["run_t0"]

        # if run time exceed 5 minutes, then it
        # will be considered failed
        if _time_elapsed > 300:
            failed_message = "build should match one of the build status: after 300 seconds"
            self.logger.error(failed_message)
            self.results["failed_message"] = failed_message
            self.results["status_code"] = "failed"
            self.results["status"] = False
            return False

        return

    def _eval_build(self):
        """
        Evaluate the current build status and manage the build lifecycle.
        
        Returns:
            bool: True if the build was successful, otherwise False.
        """
        self._set_current_build()

        _t1 = int(time())
        status = None

        while True:
            sleep(5)

            if self._check_build_status() and self._set_build_status_codes():
                status = True
                break

            _time_elapsed = _t1 - self.results["run_t0"]

            if _time_elapsed > self.build_timeout:
                failed_message = f"run max time exceeded {self.build_timeout}"
                self.results["failed_message"] = failed_message
                self.results["status"] = False
                self.logger.warn(failed_message)
                status = False
                break

            # check build exceeded total build time alloted
            if _t1 > self.build_expire_at:
                self.results["status_code"] = "timed_out"
                self.results["status"] = False
                failed_message = f"build timed out: after {self.build_timeout} seconds."
                self.results["failed_message"] = failed_message
                self.logger.warn(failed_message)
                status = False
                break

        self.wait_for_log()
        self.results["time_elapsed"] = int(time()) - self.results["run_t0"]

        if not self.output:
            self.output = f'Could not get log build_id "{self.build_id}"'

        return status

    def wait_for_log(self):
        """
        Wait for the build logs to become available.

        Returns:
            dict: The results of the log retrieval process.
        """
        maxtime = 30
        t0 = int(time())

        build_id_suffix = self.build_id.split(":")[1]

        results = {"status": None}

        while True:
            _time_elapsed = int(time()) - t0

            if _time_elapsed > maxtime:
                self.logger.debug(f"time expired to retrieved log {_time_elapsed} seconds")
                break

            results = self._get_log(build_id_suffix)

            if results.get("status") == True:
                return results

            if results.get("status") is False and results.get("failed_message"):
                self.logger.warn(results["failed_message"])
                return {"status": False}

            sleep(2)

        return results

    def _get_log(self, build_id_suffix):
        """
        Retrieve the build log from S3.

        Args:
            build_id_suffix (str): The suffix of the build ID to retrieve logs for.

        Returns:
            dict: A dictionary indicating the success status and the log content if successful.
        """
        if self.output:
            return {"status": True}

        if self.logarn:
            _log_elements = self.logarn.split("/codebuild/logs/")
            _logname = f"codebuild/logs/{_log_elements[1]}"
            _log_bucket = _log_elements[0].split("arn:aws:s3:::")[1]
        else:
            _logname = f"codebuild/logs/{build_id_suffix}.gz"
            _log_bucket = self.log_bucket

        _dstfile = f'/tmp/{build_id_suffix}.gz'

        try:
            obj = self.s3.Object(_log_bucket, _logname)
            _read = obj.get()['Body'].read()
        except ClientError as e:
            msg = traceback.format_exc()
            failed_message = f"failed to get log: s3://{_log_bucket}/{_logname}\n\nstacktrace:\n\n{msg}"
            return {"status": False, "failed_message": failed_message}

        self.logger.debug(f"retrieved log: s3://{_log_bucket}/{_logname}")

        gzipfile = BytesIO(_read)
        gzipfile = gzip.GzipFile(fileobj=gzipfile)
        log = gzipfile.read().decode('utf-8')

        self.output = log

        return {"status": True}

    def _set_build_summary(self):
        """
        Set the build summary based on the build results.

        Returns:
            str: The summary message for the build.
        """
        if self.results["status_code"] == "successful":
            summary_msg = f"# Successful \n# build_id {self.build_id}"

        elif self.results["status_code"] == "timed_out":
            summary_msg = f"# Timed out \n# build_id {self.build_id}"

        elif self.build_id is False:
            self.results["status_code"] = "failed"
            summary_msg = "# Never Triggered"

        elif self.build_id:
            self.results["status_code"] = "failed"
            summary_msg = f"# Failed \n# build_id {self.build_id}"

        else:
            self.results["status_code"] = "failed"
            summary_msg = "# Never Triggered"

        self.results["msg"] = summary_msg

        return summary_msg

    def _env_vars_to_codebuild_format(self):
        """
        Convert environment variables to the format required by CodeBuild.

        Returns:
            list: A list of environment variable dictionaries formatted for CodeBuild.
        """
        skip_keys = [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_SESSION_TOKEN"
        ]

        env_vars = []
        _added = []

        if not self.build_env_vars:
            return env_vars

        pattern = r"^CODEBUILD"

        for _k, _v in self.build_env_vars.items():
            if not _v:
                self.logger.debug(f"env var {_k} is empty/None - skipping")
                continue

            if _k in skip_keys:
                continue

            if re.search(pattern, _k):
                continue

            # cannot duplicate env vars
            if _k in _added:
                continue

            _added.append(_k)

            _env_var = {
                'name': _k,
                'value': _v,
                'type': 'PLAINTEXT'
            }

            env_vars.append(_env_var)

        return env_vars

    def _get_avail_codebuild_projects(self, max_queue_size=5):
        """
        Get available CodeBuild projects that can be triggered.

        Args:
            max_queue_size (int): Maximum number of concurrent builds allowed.

        Returns:
            list: A sorted list of available CodeBuild project names.
        """
        results = {}

        # Get a list of all projects
        response = self.codebuild_client.list_projects()

        for project in response['projects']:
            self.logger.debug(f"evaluating codebuild project {project}")

            if self.codebuild_basename not in project:
                self.logger.debug(f"codebuild project {project} not a match")
                continue

            response = self.codebuild_client.list_builds_for_project(
                projectName=project,
                sortOrder='ASCENDING'
            )

            if not response["ids"]:
                results[project] = 0
                continue

            build_statues = self._get_build_status(response["ids"])

            current_build_ids = []

            for build_id, build_status in build_statues.items():
                if build_status["status"] == "IN_PROGRESS":
                    current_build_ids.append(build_id)
                    continue

            if not current_build_ids:
                results[project] = 0
                continue

            build_count = len(current_build_ids)

            self.logger.debug(f"Project: {project}, Build Count: {build_count}")

            if build_count < max_queue_size:
                results[project] = build_count

        if not results:
            return

        return sorted(results, key=lambda x: results[x])

    def _get_codebuild_projects(self, sleep_int=10):
        """
        Retrieve a list of CodeBuild projects that are available for triggering.

        Args:
            sleep_int (int): Time to wait between retries.

        Returns:
            list: A list of available CodeBuild project names or False if none found.
        """
        for retry in range(3):
            try:
                empty_queue_projects = self._get_avail_codebuild_projects()
            except ClientError as e:
                empty_queue_projects = False

            if empty_queue_projects:
                return empty_queue_projects

            sleep(sleep_int)

        return False

    def _trigger_build(self):
        """
        Trigger a build on an available CodeBuild project.

        Returns:
            dict: The response from the CodeBuild start build API call.
        """
        projects = self._get_codebuild_projects()
        self.project_name = None

        if not projects:
            self.logger.warn(f"cannot find matching project - using codebuild_basename {self.codebuild_basename}")
            projects = [self.codebuild_basename]

        try:
            timeout = int(self.build_timeout/60)
        except (ValueError, TypeError):
            timeout = 60

        for project_name in projects:
            self.logger.debug_highlight(f"running job on codebuild project {project_name}")

            env_vars_codebuild_format = self._env_vars_to_codebuild_format()

            inputargs = {
                "projectName": project_name,
                "environmentVariablesOverride": env_vars_codebuild_format,
                "timeoutInMinutesOverride": timeout,
                "imageOverride": self.build_image,
                "computeTypeOverride": self.compute_type,
                "environmentTypeOverride": self.image_type
            }

            if self.buildspec:
                inputargs["buildspecOverride"] = self.buildspec

            try:
                new_build = self.codebuild_client.start_build(**inputargs)
            except ClientError as e:
                msg = traceback.format_exc()
                self.logger.warn(f"could not start build on codebuild {project_name}\n\n{msg}")
                continue

            self.project_name = project_name
            break

        if not self.project_name:
            raise Exception("could not trigger codebuild execution")

        self.build_id = new_build['build']['id']
        url = f"https://console.aws.amazon.com/codesuite/codebuild/projects/{self.project_name}/build/{self.build_id}/?region={self.aws_region}"
        self.results["inputargs"]["url"] = url
        self.results["inputargs"]["build_id"] = self.build_id
        self.results["inputargs"]["build_expire_at"] = self.build_expire_at
        self.results["inputargs"]["project_name"] = project_name

        _log = f"trigger run on codebuild project: {project_name}, build_id: {self.build_id}, build_expire_at: {self.build_expire_at}"
        self.logger.debug(_log)

        return new_build

    def submit(self):
        """
        Submit a build request to CodeBuild.

        Returns:
            dict: The results of the build submission process.
        """
        self._trigger_build()
        return self.results

    def check(self, wait_int=10, retries=12):
        """
        Check the status of the current build.

        Args:
            wait_int (int): Time to wait between status checks.
            retries (int): Number of retries before giving up.

        Returns:
            bool: True if the build is complete, otherwise False.
        """
        self._set_current_build()

        for retry in range(retries):
            self.logger.debug(f'check: codebuild_project_name "{self.project_name}" codebuild_id "{self.build_id}" retry {retry}/{retries} {wait_int} seconds')
            if self._check_build_status():
                return True
            sleep(wait_int)

        return

    def retrieve(self, **kwargs):
        """
        Retrieve the results of the build process.

        Args:
            **kwargs: Dictionary of parameters for retrieval including:
                interval (int): Time to wait between checks
                retries (int): Number of retries before giving up

        Returns:
            dict: The results of the build retrieval process.
        """
        wait_int = kwargs.get("interval", 10)
        retries = kwargs.get("retries", 12)

        if not self.check(wait_int=wait_int, retries=retries):
            return

        return self._retrieve()

    def _retrieve(self):
        """
        Internal method to evaluate the build and retrieve its results.

        Returns:
            dict: The results of the build retrieval process.
        """
        self._eval_build()

        self.clean_output()

        if self.output:
            self.results["output"] = self.output

        return self.results
