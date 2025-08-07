#!/usr/bin/env python
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

import boto3
import uuid
import os

from iac_ci.common.loggerly import IaCLogger
from iac_ci.helper.cloud.aws.codebuild import CodebuildResourceHelper
from iac_ci.helper.resource.aws import TFAwsBaseBuildParams
from iac_ci.helper.resource.terraform import TFCmdOnAWS
from iac_ci.common.run_helper import CreateTempParamStoreEntry


class CodebuildParams(TFAwsBaseBuildParams):
    """
    A class to handle AWS CodeBuild parameters and configuration.
    Inherits from TFAwsBaseBuildParams.
    """

    def __init__(self, **kwargs):
        """
        Initialize CodebuildParams with AWS role and environment configurations.
        
        Args:
            **kwargs: Additional keyword arguments passed to parent class
        """
        self.classname = "CodebuildParams"
        self.logger = IaCLogger(self.classname)

        self.iac_platform = os.environ.get("IAC_PLATFORM", "config0")
        self.build_env_vars = kwargs.get("build_env_vars")

        if self.iac_platform == "config0":
            self.codebuild_basename = f"{self.iac_platform}-iac"
        elif self.iac_platform == "iac-ci":
            self.codebuild_basename = "iac-ci"
        else:
            self.codebuild_basename = "iac-ci"

        TFAwsBaseBuildParams.__init__(self, **kwargs)

        self.build_image = kwargs.get("build_image") or "aws/codebuild/standard:7.0"
        self.image_type = kwargs.get("image_type") or "LINUX_CONTAINER"
        self.compute_type = kwargs.get("compute_type") or "BUILD_GENERAL1_SMALL"

    def _set_buildparams(self):
        """
        Set build parameters for CodeBuild project including environment variables.
        
        Returns:
            dict: Dictionary containing build parameters and environment variables
        """
        build_env_vars = self.build_env_vars or {}

        build_env_vars.update({
            "IAC_PLATFORM": self.iac_platform,
            "TF_PATH": f"/tmp/{self.iac_platform}/bin/{self.binary}",
            "METHOD": self.method,
            "OUTPUT_BUCKET": self.tmp_bucket,
            "OUTPUT_BUCKET_KEY": self.s3_output_folder,
            "REMOTE_SRC_BUCKET": self.remote_src_bucket,
            "REMOTE_STATEFUL_BUCKET": self.remote_src_bucket,
            "REMOTE_SRC_BUCKET_KEY": self.remote_src_bucket_key,
            "TMPDIR": self.tmpdir,
            "STATEFUL_ID": self.stateful_id,
        })

        if hasattr(self, "commit_hash") and self.commit_hash:
            build_env_vars["COMMIT_HASH"] = self.commit_hash

        self.buildparams = {
            "buildspec": self.get_buildspec(),
            "remote_stateful_bucket": self.s3_bucket_output,
            "codebuild_basename": self.codebuild_basename,
            "aws_region": self.aws_region,
            "build_timeout": self.build_timeout,
            "method": self.method,
            "build_env_vars": build_env_vars,
            "build_image": self.build_image,
            "image_type": self.image_type,
            "compute_type": self.compute_type
        }

        return self.buildparams


class Codebuild(CodebuildParams, CreateTempParamStoreEntry):
    """
    Class for managing AWS CodeBuild projects and buildspec generation.
    Inherits from CodebuildParams.
    """

    def __init__(self, **kwargs):
        """
        Initialize Codebuild with TFCmdOnAWS configuration.
        
        Args:
            **kwargs: Additional keyword arguments passed to parent class
        """
        self.classname = "Codebuild"

        CodebuildParams.__init__(self, **kwargs)

        session = boto3.Session()
        self.ssm = session.client('ssm')
        CreateTempParamStoreEntry.__init__(self)

        self.tfcmds = TFCmdOnAWS(runtime_env="codebuild",
                                 run_share_dir=self.run_share_dir,
                                 app_dir=self.app_dir,
                                 envfile="build_env_vars.env",
                                 binary=self.binary,
                                 version=self.version,
                                 tf_bucket_path=self.tf_bucket_path,
                                 add_ssm_names=kwargs.get("add_ssm_names"),
                                 arch="linux_amd64"
                                 )

        self.add_ssm_names_path = None

    @staticmethod
    def _add_cmds(contents, cmds):
        """
        Add commands to buildspec content.
        
        Args:
            contents (str): Current buildspec content
            cmds (list): List of commands to add
            
        Returns:
            str: Updated buildspec content with added commands
        """
        for cmd in cmds:
            contents = f"{contents}       - {cmd}\n"

        return contents

    def _get_codebuildspec_prebuild(self):
        """
        Generate pre-build phase content for buildspec.
        
        Returns:
            str: Pre-build phase content for buildspec
        """
        cmds = self.tfcmds.s3_tfpkg_to_local()
        cmds.extend(self.tfcmds.get_tf_install())
        cmds.extend(self.tfcmds.load_env_files())

        contents = '''
  pre_build:
    on-failure: ABORT
    commands:
'''
        return self._add_cmds(contents, cmds)

    def _get_codebuildspec_build(self):
        """
        Generate build phase content for buildspec based on method.
        
        Returns:
            str: Build phase content for buildspec
            
        Raises:
            ValueError: If method is not create/apply/destroy
        """
        contents = '''
  build:
    on-failure: ABORT
    commands:
'''
        if self.method in ["create", "apply"]:
            cmds = self.tfcmds.get_tf_apply()
        elif self.method == "destroy":
            cmds = self.tfcmds.get_tf_destroy()
        else:
            raise ValueError(f"Method '{self.method}' is invalid. Must be one of: create, apply, destroy")

        return self._add_cmds(contents, cmds)

    def get_buildspec(self):
        """
        Generate complete buildspec by combining init, pre-build and build phases.
        
        Returns:
            str: Complete buildspec YAML content
        """
        init_contents = self.get_init_contents()
        prebuild = self._get_codebuildspec_prebuild()
        build = self._get_codebuildspec_build()

        return f"{init_contents}{prebuild}{build}"

    def get_init_contents(self):
        """
        Generate initial buildspec contents with environment variables.

        Returns:
            str: Initial buildspec YAML content
        """

        self.tfcmds.set_ssm_names()

        if self.tfcmds.ssm_names_b64:
            random_suffix = str(uuid.uuid4())
            self.add_ssm_names_path = f"{self.ssm_tmp_prefix}/{random_suffix}"
            self.put_advance_param(self.add_ssm_names_path,
                                   self.tfcmds.ssm_names_b64)

        contents = f'''
version: 0.2
env:
  variables:
    TMPDIR: /tmp
    TF_PATH: /usr/local/bin/{self.binary}
'''
        if self.ssm_name and self.add_ssm_names_path:
            ssm_params_content = f'''
  parameter-store:
    SSM_VALUE: {self.ssm_name}
    SSM_SCRIPT_VALUE: {self.add_ssm_names_path}
'''
        elif self.ssm_name:
            ssm_params_content = f'''
  parameter-store:
    SSM_VALUE: {self.ssm_name}
'''
        elif self.add_ssm_names_path:
            ssm_params_content = f'''
  parameter-store:
    ADD_SSM_NAMES: {self.add_ssm_names_path}
'''
        else:
            ssm_params_content = None

        if ssm_params_content:
            contents = f"{contents}{ssm_params_content}"

        return f"{contents}\nphases:\n"

    @staticmethod
    def retrieve(**inputargs):
        """
        Retrieve results from phase JSON file using CodebuildResourceHelper.

        Args:
            **inputargs: Arguments passed to CodebuildResourceHelper.retrieve()

        Returns:
            dict: Results from CodebuildResourceHelper
        """
        codebuild_helper = CodebuildResourceHelper()
        codebuild_helper.retrieve(**inputargs)

        return codebuild_helper.results

    def run(self):
        """
        Execute the CodeBuild project with configured parameters.

        Returns:
            dict: Results from CodebuildResourceHelper
        """
        self._set_buildparams()
        codebuild_helper = CodebuildResourceHelper(**self.buildparams)
        codebuild_helper.submit()

        return codebuild_helper.results