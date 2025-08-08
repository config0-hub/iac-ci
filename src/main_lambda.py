#!/usr/bin/env python
"""
This module provides functionality to trigger Lambda builds for CI/CD processes.
It handles AWS execution, logging, and result processing.
"""

# Copyright 2025 Gary Leong <gary@config0.com>
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
import traceback
import boto3

from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.orders import PlatformReporter
from iac_ci.helper.resource.lambdabuild import Lambdabuild
from iac_ci.common.utilities import id_generator2


class TriggerLambdabuild(PlatformReporter):
    """
    Class to trigger Lambda builds for CI/CD processes.
    """

    def __init__(self, **kwargs):
        self.classname = "TriggerLambda"
        self.logger = IaCLogger(self.classname)
        PlatformReporter.__init__(self, **kwargs)

        self.phase = "trigger-lambda"
        self.build_timeout = 300

    def _exec_in_aws(self, method="ci"):
        """
        Execute the build in AWS

        This method will trigger the actual build. It will generate
        the necessary input arguments and then call the Lambdabuild
        class to execute the build.

        Args:
            method: The method to use for the build. Defaults to "ci".

        Returns:
            A dictionary with the results of the build.
        """

        try:
            plan_destroy = self.run_info["plan_destroy"]
        except:
            plan_destroy = None

        if plan_destroy:
            cinputargs = self.get_aws_exec_cinputargs(method="plan_destroy")
        else:
            cinputargs = self.get_aws_exec_cinputargs(method=method)

        if self.infracost_api_key:
            cinputargs["infracost_api_key"] = self.infracost_api_key

        if os.environ.get("DEBUG_IAC_CI"):
            self.logger.debug("#" * 32)
            self.logger.debug("# cinputargs")
            self.logger.json(cinputargs)
            self.logger.debug("#" * 32)

        _awsbuild = Lambdabuild(**cinputargs)
        results = _awsbuild.exec()

        self.logger.debug("#" * 32)
        self.logger.debug("# output")
        self.logger.debug(f"# {self.tmp_bucket}/{self.s3_output_folder}")
        self.logger.debug("#" * 32)

        return results

    def _set_order(self):
        """
        Sets the order for the current process with a human-readable description and a specified role.

        The method constructs input arguments including a description of triggering a lambda build 
        and assigns the order using the new_order method.
        """
        human_description = f"Trigger lambda build {self.s3_key}"

        inputargs = {
            "human_description": human_description,
            "role": "lambda/build"
        }

        self.order = self.new_order(**inputargs)

    def _save_run_info(self):
        """
        Saves the current run information to the database.

        This method will insert the self.run_info dictionary into the 'table_runs'
        table in DynamoDB and log a message indicating that the trigger_id has
        been saved.
        """
        self.db.table_runs.insert(self.run_info)
        msg = f"trigger_id: {self.trigger_id} saved"
        self.add_log(msg)

    def _get_log_frm_s3(self):
        """
        Retrieves a log file from S3 and returns its content as a string.

        The method takes the bucket name and the log file name from the object's
        attributes and uses boto3 to download the file to a temporary local
        file. It then reads the file content and returns it as a string.

        Returns:
            The content of the log file as a string.

        Raises:
            S3UploadFailedError: If S3 download fails.
            IOError: If local file operations fail.
        """
        local_file = f"/tmp/{id_generator2()}"

        s3 = boto3.resource("s3")

        s3.Bucket(self.remote_src_bucket).download_file(
            self.s3_output_folder, local_file
        )

        with open(local_file, "r", encoding="utf-8") as file:
            file_content = file.read()

        if os.path.exists(local_file):
            os.remove(local_file)

        return file_content

    def execute(self):
        """
        Execute the main process of this class.

        This method sets the order, initializes the build variables, sets the
        s3 key, and executes the build in AWS. It logs a message indicating
        that the trigger_id has been triggered and saves the run information
        to the database.

        If the build is successful, it will log a summary message and add a
        notify message to the results if the event_type is "push".

        Returns:
            bool: True if execution is successful.
        """
        self._set_order()
        self.init_build_vars()
        self.set_s3_key()

        results = self._exec_in_aws(method="ci")

        try:
            _log = self._get_log_frm_s3()
        except IOError:
            _log = None
            self.add_log(f"Failed to download log: {traceback.format_exc()}")

        self.results["update"] = True
        self.results["remote_src_bucket"] = self.remote_src_bucket
        self.results["remote_src_bucket_key"] = self.remote_src_bucket_key

        # we never close even if failure happens
        # we need to evaluate and update the pr
        self.results["close"] = False

        if results.get("status") is False:
            self.results["status"] = "failed"
            self.run_info["status"] = "failed"
            if _log:
                self.logger.debug(f"\n\n{_log}\n\n")
        else:
            self.results["status"] = "successful"
            if self.webhook_info.get("event_type") == "push":
                if self.results.get("notify"):
                    self.results["notify"]["message"] = "iac-ci completed with event_type push"
                else:
                    self.results["notify"] = {"message": "iac-ci completed with event_type push"}

            summary_msg = f"# Triggered \n# trigger_id: {self.trigger_id} \n# iac_ci_id: {self.iac_ci_id} \n"

            self.add_log("#" * 32)
            self.add_log("# Summary")
            self.add_log(summary_msg)
            self.add_log("#" * 32)

        self.finalize_order()
        self.insert_to_return()
        self._save_run_info()

        return True