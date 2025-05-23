#!/usr/bin/env python
"""
TFAwsBaseBuildParams - AWS base build parameter manager for infrastructure as code.

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


class TFAwsBaseBuildParams(object):
    """
    A class to manage AWS base build parameters for infrastructure as code.

    This class encapsulates the configuration needed for building and deploying
    AWS resources, including S3 bucket settings, temporary directories, and other
    parameters necessary for the build process.
    """
    def __init__(self, **kwargs):
        """
        Initializes the TFAwsBaseBuildParams instance.

        Args:
            **kwargs: Additional keyword arguments including:
                - method (str): The method of operation (default: "create").
                - s3_output_folder (str): The S3 folder for output.
                - stateful_id (str): Unique identifier for stateful operations.
                - tmpdir (str): Temporary directory for build operations.
                - tmp_bucket (str): Temporary S3 bucket for storage.
                - remote_src_bucket (str): Remote S3 bucket for source files.
                - remote_src_bucket_key (str): Key for the remote source bucket.
                - commit_hash (str): Optional commit hash for versioning.
                - build_timeout (int): Timeout for the build process (default: 1800).
                - ssm_name (str): Name of the AWS Systems Manager parameter store.
                - remote_stateful_bucket (str): Remote S3 bucket for stateful storage.
                - app_name (str): Name of the application (default: "terraform").
                - binary (str): Binary to use for the build.
                - version (str): Version of the binary.
                - run_share_dir (str): Shared directory for running processes.
                - app_dir (str): Application directory for build context.

        Raises:
            Exception: If any of the required parameters are None.
        """
        self.classname = "TFAwsBaseBuildParams"
        self.method = kwargs.get("method", "create")
        self.s3_output_folder = kwargs["s3_output_folder"]
        self.stateful_id = kwargs["stateful_id"]
        self.tmpdir = kwargs["tmpdir"]
        self.tmp_bucket = kwargs["tmp_bucket"]
        self.remote_src_bucket = kwargs["remote_src_bucket"]
        self.remote_src_bucket_key = kwargs["remote_src_bucket_key"]
        self.commit_hash = kwargs.get("commit_hash")

        if not self.tmp_bucket:
            raise Exception("tmp_bucket cannot be None")

        if not self.remote_src_bucket:
            raise Exception("remote_src_bucket cannot be None")

        if not self.remote_src_bucket_key:
            raise Exception("remote_src_bucket_key cannot be None")

        if not self.stateful_id:
            raise Exception("stateful_id cannot be None")

        self.build_timeout = int(kwargs.get("build_timeout", 1800))

        self.aws_region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        self.ssm_name = kwargs.get("ssm_name")
        self.s3_bucket_output = kwargs.get("remote_stateful_bucket")

        self.skip_env_vars = ["AWS_SECRET_ACCESS_KEY"]

        self.app_name = kwargs.get("app_name", "terraform")

        self.binary = kwargs["binary"]
        self.version = kwargs["version"]

        self.run_share_dir = kwargs["run_share_dir"]
        self.app_dir = kwargs["app_dir"]

        self._set_tmp_tf_bucket_loc()

    def _set_tmp_tf_bucket_loc(self):
        """
        Sets the temporary Terraform bucket location based on the binary and version.

        This method configures the S3 bucket path and key for downloading Terraform
        binaries, and sets the appropriate attributes for bucket access.
        """
        if self.binary in ["opentofu", "tofu"]:
            self.tf_bucket_key = f"downloads/tofu/{self.version}"
        else:
            self.tf_bucket_key = f"downloads/terraform/{self.version}"

        self.tf_bucket_path = f"s3://{self.tmp_bucket}/{self.tf_bucket_key}"