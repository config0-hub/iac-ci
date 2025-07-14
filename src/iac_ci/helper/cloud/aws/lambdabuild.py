#!/usr/bin/env python
"""
Module for managing AWS Lambda build processes and executions.
This module provides functionality to handle Lambda function invocations,
environment variable management, and build result processing.

Copyright (C) 2025 Gary Leong <gary@config0.com>

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
"""

import os
import logging
import boto3
import botocore
import json
from time import time

from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.serialization import b64_encode
from iac_ci.common.serialization import b64_decode


class LambdaResourceHelper:
    """
    Helper class for managing AWS Lambda resources and build processes.
    
    This class handles Lambda function invocations, manages build environments,
    processes build results, and provides utilities for Lambda execution monitoring.
    
    Attributes:
        classname (str): Name of the class for logging purposes
        logger (IaCLogger): Logger instance for the class
    """
    def __init__(self, **kwargs):
        """
        Initialize LambdaResourceHelper with build configuration.
        
        Args:
            **kwargs: Dictionary containing build configuration including:
                build_env_vars (dict): Environment variables for the build
                aws_region (str): AWS region for Lambda execution
                build_timeout (int): Timeout in seconds for the build
                method (str): Build method to execute
        """
        self.classname = "LambdaResourceHelper"
        self.logger = IaCLogger(self.classname)

        self.iac_platform = os.environ.get("IAC_PLATFORM", "config0")

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
        self.build_timeout = kwargs["build_timeout"]
        self.method = kwargs["method"]

        logging.basicConfig()
        logging.getLogger('botocore').setLevel(logging.WARNING)
        logging.getLogger('botocore.hooks').setLevel(logging.WARNING)
        logging.getLogger('botocore.session').setLevel(logging.WARNING)
        logging.getLogger('boto3.resources.action').setLevel(logging.WARNING)
        logging.getLogger('s3transfer').setLevel(logging.WARNING)
        logging.getLogger('s3transfer.utils').setLevel(logging.WARNING)
        logging.getLogger('s3transfer.tasks').setLevel(logging.WARNING)
        logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)

        self.s3 = boto3.resource('s3')
        self.session = boto3.Session(region_name=self.aws_region)

        cfg = botocore.config.Config(
            retries={'max_attempts': 0},
            read_timeout=900,
            connect_timeout=900,
            region_name=self.aws_region
        )

        self.lambda_client = boto3.client(
            'lambda',
            config=cfg,
            region_name=self.aws_region
        )

        self.cmds_b64 = b64_encode(kwargs["cmds"])
        self.logs_client = self.session.client('logs')

        self.results = {
            "status": None,
            "status_code": None,
            "build_status": None,
            "run_t0": int(time()),
            "inputargs": {},
            "env_vars": {},
        }

        if "lambda_function_name" not in self.results["inputargs"]:
            self.results["inputargs"]["lambda_function_name"] = self.lambda_function_name

    @staticmethod
    def get_set_env_vars():
        """
        Get the environment variables for the Lambda function.

        Returns:
            dict: A dictionary of environment variables for the Lambda function.
        """
        return {
            "tmp_bucket": True,
            "log_bucket": True,
            "app_dir": None,
            "stateful_id": None,
            "remote_stateful_bucket": None,
            "lambda_function_name": None,
            "run_share_dir": None,
            "share_dir": None
        }

    def _trigger_build(self):
        """
        Trigger the build process by invoking the Lambda function.

        Returns:
            dict: The response from the Lambda function invocation.
        """
        try:
            timeout = int(self.build_timeout)
        except (ValueError, TypeError):
            timeout = 800

        if timeout > 800:
            timeout = 800

        self.build_expire_at = time() + timeout

        self.logger.debug("#" * 32)
        self.logger.debug("# ref 324523453 env vars for lambda build")
        self.logger.json(self.build_env_vars)
        self.logger.debug("#" * 32)

        invocation_config = {
            'FunctionName': f'{self.lambda_function_name}',
            'InvocationType': 'RequestResponse',
            'LogType': 'Tail',
            'Payload': json.dumps({
                "cmds_b64": self.cmds_b64,
                "env_vars_b64": b64_encode(self.build_env_vars),
            })
        }

        return self.lambda_client.invoke(**invocation_config)

    def _submit(self):
        """
        Submit the build request and process the response.

        Returns:
            dict: The results of the build submission.
        """
        # ['ResponseMetadata', 'StatusCode', 'LogResult', 'ExecutedVersion', 'Payload']
        self.response = self._trigger_build()
        self.results["lambda_status"] = int(self.response["StatusCode"])

        try:
            payload = json.loads(self.response["Payload"].read().decode())
        except:
            payload = {}

        try:
            lambda_results = json.loads(payload["body"])
        except:
            lambda_results = {}

        if "stackTrace" in lambda_results:
            stackTrace = lambda_results["stackTrace"]
            self.results["failed_message"] = " ".join(stackTrace)
            self.results["output"] = " ".join(stackTrace)

        self.results["lambda_results"] = lambda_results

        if lambda_results.get("status") is True or self.results.get("lambda_status") == 200:
            self.results["status"] = True
            self.results["exitcode"] = 0
        elif lambda_results.get("status") is False or self.results.get("lambda_status") != 200:
            self.results["status"] = False
            self.results["exitcode"] = "78"
            if "failed_message" not in self.results:
                self.results["failed_message"] = "lambda function failed"
        else:
            # if there is a failed message, we considered it failed
            if "failed_message" in self.results:
                self.results["status"] = False
                self.results["exitcode"] = "78"
            else:
                self.results["status"] = True
                self.results["exitcode"] = 0

        if "output" not in self.results:
            self.results["output"] = b64_decode(self.response["LogResult"])

        return self.results

    def submit(self):
        """
        Submit the build process and handle the results.

        Returns:
            dict: The results of the build submission.
        """
        self._submit()

        # Check for status without using .get()
        if "status" in self.results and self.results["status"] is False:
            if self.method == "validate":
                self.results["failed_message"] = "the resources have drifted"
            elif self.method == "check":
                self.results["failed_message"] = "the resources failed check"
            elif self.method == "pre-create":
                self.results["failed_message"] = "the resources failed pre-create"
            elif self.method == "apply":
                self.results["failed_message"] = "applying of resources have failed"
            elif self.method == "create":
                self.results["failed_message"] = "creation of resources have failed"
            elif self.method == "destroy":
                self.results["failed_message"] = "destroying of resources have failed"

        return self.results