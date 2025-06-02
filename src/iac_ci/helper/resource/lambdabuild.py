#!/usr/bin/env python
"""
AWS Lambda function management with Terraform integration.

This module provides classes for managing AWS Lambda function parameters, 
configurations, and build processes with Terraform, TFSec, Infracost, and OPA integrations.

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
"""

import os
from iac_ci.common.loggerly import IaCLogger
from iac_ci.helper.cloud.aws.lambdabuild import LambdaResourceHelper
from iac_ci.helper.resource.aws import TFAwsBaseBuildParams
from iac_ci.helper.resource.terraform import TFCmdOnAWS
from iac_ci.helper.resource.infracost import TFInfracostHelper
from iac_ci.helper.resource.tfsec import TFSecHelper
from iac_ci.helper.resource.opa import TFOpaHelper


class LambdaParams(TFAwsBaseBuildParams):
    """
    Class for managing AWS Lambda function parameters and configurations.
    Inherits from TFAwsBaseBuildParams.
    """

    def __init__(self, **kwargs):
        """
        Initialize LambdaParams with AWS Lambda configurations.
        
        Args:
            **kwargs: Additional keyword arguments including:
                infracost_api_key (str): Optional API key for Infracost
        """
        self.classname = "LambdaParams"
        self.logger = IaCLogger(self.classname)

        self.iac_platform = os.environ.get("IAC_PLATFORM", "config0")
        self.build_env_vars = kwargs.get("build_env_vars")

        if self.iac_platform == "config0":
            self.lambda_basename = f"{self.iac_platform}-iac"
        else:
            self.lambda_basename = "iac-ci"

        TFAwsBaseBuildParams.__init__(self, **kwargs)

        self.infracost_api_key = kwargs.get("infracost_api_key")

    def _debug_build_params(self, build_env_vars):
        """
        Debug method to log build parameters and environment variables.
        
        Args:
            build_env_vars (dict): Environment variables for the build
        
        Returns:
            dict: Build parameters
        """
        self.logger.debug("-" * 32)
        self.logger.debug("- build_env_vars")
        self.logger.json(build_env_vars)
        self.logger.debug("-" * 32)
        self.logger.debug("- self.build_params")
        self.logger.debug("-" * 32)
        self.logger.json(self.buildparams)
        self.logger.debug("-" * 32)

        return self.buildparams

    def _set_buildparams(self):
        """
        Set build parameters and environment variables for Lambda function.
        
        Returns:
            dict: Build parameters including environment variables and configurations
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
            "APP_DIR": self.app_dir,
        })

        if self.ssm_name:
            build_env_vars["SSM_NAME"] = self.ssm_name

        self.buildparams = {
            "build_env_vars": build_env_vars,
            "cmds": self.get_cmds(),
            "lambda_basename": self.lambda_basename,
            "aws_region": self.aws_region,
            "build_timeout": self.build_timeout,
            "method": self.method,
            "tmp_bucket": self.tmp_bucket,
            "app_dir": self.app_dir
        }

        if os.environ.get("DEBUG_IAC_CI"):
            self._debug_build_params(build_env_vars)

        return self.buildparams

    def exec(self):
        """
        Execute Lambda function with configured parameters.
        
        Returns:
            dict: Results from Lambda execution
        """
        self._set_buildparams()
        lambda_helper = LambdaResourceHelper(**self.buildparams)
        lambda_helper.submit()
        return lambda_helper.results


class Lambdabuild(LambdaParams):
    """
    Class for managing Lambda build process with Terraform, TFSec, Infracost, and OPA integrations.
    Inherits from LambdaParams.
    """

    def __init__(self, **kwargs):
        """
        Initialize Lambdabuild with various helper configurations.
        
        Args:
            **kwargs: Additional keyword arguments passed to parent class
        """
        self.classname = "Lambdabuild"

        LambdaParams.__init__(self, **kwargs)

        self.tfcmds = TFCmdOnAWS(runtime_env="lambda",
                                 run_share_dir=self.run_share_dir,
                                 app_dir=self.app_dir,
                                 envfile="build_env_vars.env",
                                 binary=self.binary,
                                 version=self.version,
                                 tf_bucket_path=self.tf_bucket_path,
                                 arch="linux_amd64")

        self.tfsec_cmds = TFSecHelper(runtime_env="lambda",
                                      envfile="build_env_vars.env",
                                      binary='tfsec',
                                      version="1.28.10",
                                      tmp_bucket=self.tmp_bucket,
                                      app_dir=self.app_dir,
                                      arch="linux_amd64")

        self.infracost_cmds = TFInfracostHelper(runtime_env="lambda",
                                                envfile="build_env_vars.env",
                                                binary='infracost',
                                                version="0.10.39",
                                                app_dir=self.app_dir,
                                                tmp_bucket=self.tmp_bucket,
                                                arch="linux_amd64")

        self.opa_cmds = TFOpaHelper(runtime_env="lambda",
                                    envfile="build_env_vars.env",
                                    binary='opa',
                                    version="0.68.0",
                                    app_dir=self.app_dir,
                                    tmp_bucket=self.tmp_bucket,
                                    arch="linux_amd64")

    def _get_prebuild_cmds(self):
        """
        Get commands needed for pre-build setup.
        
        Returns:
            list: Terraform installation commands
        """
        return self.tfcmds.get_tf_install()

    def _get_build_cmds(self):
        """
        Get commands for build process based on method.
        
        Returns:
            list: Build commands for specified method
            
        Raises:
            ValueError: If method is not one of create/validate/ci/pre-create/check/apply/destroy
        """
        tfsec_cmds = self.tfsec_cmds.get_all_cmds()
        infracost_cmds = self.infracost_cmds.get_all_cmds()

        if self.method in ["create", "apply"]:
            cmds = self.tfcmds.get_tf_apply()
        elif self.method in [ "ci", "check", "regenerate"]:
            cmds = [ self.tfsec_cmds.backup_s3_file(suffix="out") ]
            cmds.append(self.tfsec_cmds.backup_s3_file(suffix="json"))
            cmds.append(self.infracost_cmds.backup_s3_file(suffix="out"))
            cmds.append(self.infracost_cmds.backup_s3_file(suffix="json"))
            cmds.extend(self.tfcmds.backup_cmds_tf())
            cmds.extend(self.tfcmds.get_tf_ci())
            cmds.extend(tfsec_cmds)
            cmds.extend(infracost_cmds)
        elif self.method == "pre-create":
            cmds = self.tfcmds.get_tf_pre_create()
        elif self.method in ["validate", "drift"]:
            cmds = self.tfcmds.get_tf_chk_drift()
        elif self.method == "destroy":
            cmds = self.tfcmds.get_tf_destroy()
        else:
            raise ValueError("method needs to be create/validate/ci/pre-create/check/apply/destroy")

        return cmds

    def get_cmds(self):
        """
        Get complete set of commands for both pre-build and build phases.
        
        Returns:
            dict: Dictionary containing prebuild and build commands
        """
        cmds = {}

        prebuild_cmds = self._get_prebuild_cmds()
        if prebuild_cmds:
            cmds["prebuild"] = {"cmds": prebuild_cmds}

        if build_cmds := self._get_build_cmds():
            cmds["build"] = {"cmds": build_cmds}

        return cmds