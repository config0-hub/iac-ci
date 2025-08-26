#!/usr/bin/env python
"""
This module provides functionality to trigger AWS CodeBuild projects.

It includes a TriggerCodebuild class that handles the process of
initiating CodeBuild jobs and recording their execution details.

Copyright (C) 2025 Gary Leong <gary@config0.com>
License: GNU General Public License v3.0
"""

import os
from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.orders import PlatformReporter
from iac_ci.helper.resource.codebuild import Codebuild


class TriggerCodebuild(PlatformReporter):
    """
    A class for triggering AWS CodeBuild projects.
    
    This class extends the PlatformReporter to interact with AWS CodeBuild,
    allowing for the execution of build projects in apply or destroy modes.
    """

    def __init__(self, **kwargs):
        """
        Initialize the TriggerCodebuild instance.
        
        Args:
            **kwargs: Arbitrary keyword arguments including 'apply' or 'destroy'
                      to specify the execution method.
        
        Raises:
            ValueError: If neither 'apply' nor 'destroy' is specified in kwargs.
        """
        self.classname = "TriggerCodebuild"
        self.logger = IaCLogger(self.classname)
        PlatformReporter.__init__(self, **kwargs)

        self.phase = "trigger-codebuild"
        self.build_timeout = 2700

        if kwargs.get("apply"):
            self.method = "apply"
        elif kwargs.get("destroy"):
            self.method = "destroy"
        else:
            raise ValueError("method needs to be apply or destroy")

    def _exec_in_aws(self):
        """
        Executes a CodeBuild project in AWS using the specified method.

        This function gathers the necessary input arguments for execution
        by calling `get_aws_exec_cinputargs` with the defined method.
        It then initializes a `Codebuild` object with these arguments and
        triggers the build process by calling the `run` method on the
        `Codebuild` instance.

        Returns:
            The result of the Codebuild `run` method, which typically
            contains build execution details.
        """
        cinputargs = self.get_aws_exec_cinputargs(method=self.method)

        if self.build_env_vars.get("CODEBUILD_IMAGE"):
            cinputargs["build_image"] = self.build_env_vars["CODEBUILD_IMAGE"]

        if self.build_env_vars.get("CODEBUILD_COMPUTE_TYPE"):
            cinputargs["compute_type"] = self.build_env_vars["CODEBUILD_COMPUTE_TYPE"]

        if self.build_env_vars.get("CODEBUILD_IMAGE_TYPE"):
            cinputargs["image_type"] = self.build_env_vars["CODEBUILD_IMAGE_TYPE"]

        if self.build_env_vars.get("ADD_SSM_NAMES"):
            cinputargs["add_ssm_names"] = self.build_env_vars["ADD_SSM_NAMES"]

        if os.environ.get("DEBUG_IAC_CI"):
            self.logger.debug("#" * 32)
            self.logger.debug("# cinputargs")
            self.logger.json(cinputargs)
            self.logger.debug("#" * 32)

        _awsbuild = Codebuild(**cinputargs)
        return _awsbuild.run()

    def _set_order(self):
        """
        Sets the order for the current process with a human-readable description
        and a specified role. It constructs input arguments including a description
        of triggering a codebuild build with the s3 key and assigns the order using
        the new_order method.
        """
        human_description = f"Trigger codebuild build {self.s3_data_key}"

        inputargs = {
            "human_description": human_description,
            "role": "codebuild/build"
        }

        self.order = self.new_order(**inputargs)

    def _save_run_info(self):
        """
        Saves the current run information to the database.

        This method inserts the run information into the 'table_runs' of the database
        and logs a message indicating that the 'trigger_id' has been saved.
        """
        self.db.table_runs.insert(self.run_info)
        msg = f"trigger_id: {self.trigger_id} saved"
        self.add_log(msg)

    def execute(self):
        """
        Execute the main process of this class.

        This method sets the order, initializes the build variables, sets the
        s3 key, and executes the build in AWS. It logs a message indicating
        that the trigger_id has been triggered and saves the run information
        to the database.

        Returns:
            bool: True if execution is successful.
            
        Raises:
            RuntimeError: If the AWS CodeBuild execution fails.
        """
        self._set_order()
        self.set_additional_build_vars()
        self.set_s3_key()

        self.results["publish_vars"] = {
            "remote_src_bucket": self.remote_src_bucket,
            "remote_src_bucket_key": self.remote_src_bucket_key
        }

        results = self._exec_in_aws()

        if results.get("status") is False:
            self.results["continue"] = False
            self.results["update"] = True
            if results.get("failed_message"):
                self.results["failed_message"] = results["failed_message"]
            raise RuntimeError(self.results["failed_message"])

        # successful at this point
        self.results["inputargs"] = results["inputargs"]
        self.run_info["build_id"] = results["inputargs"]["build_id"]
        self.run_info["build_url"] = results["inputargs"]["url"]
        self.run_info["build_expire_at"] = results["inputargs"]["build_expire_at"]

        self.results["update"] = True
        self.results["msg"] = f"triggered lambda with s3://{self.remote_src_bucket}/{self.remote_src_bucket_key}"
        self.results["remote_src_bucket"] = self.remote_src_bucket
        self.results["remote_src_bucket_key"] = self.remote_src_bucket_key

        summary_msg = f"# Triggered \n# trigger_id: {self.trigger_id} \n# iac_ci_id: {self.iac_ci_id} \n"

        self.add_log("#" * 32)
        self.add_log("# Summary")
        self.add_log(summary_msg)
        self.add_log("#" * 32)

        self.finalize_order()
        self.insert_to_return()
        self._save_run_info()

        return True