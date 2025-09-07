#!/usr/bin/env python
"""
Terraform Command on AWS Module

This module provides utilities for executing Terraform commands in AWS environments.
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

#import shlex
import os
from iac_ci.common.serialization import b64_encode
from iac_ci.s3_unzip_and_env_vars import SSMHelper
from iac_ci.helper.resource.tfinstaller import get_tf_install
from iac_ci.helper.resource.common import TFAppHelper

class TFCmdOnAWS(TFAppHelper):
    """
    Class for managing Terraform commands execution on AWS.
    Provides methods for Terraform operations including init, plan, apply, and destroy.
    Inherits from TFAppHelper.
    """

    def __init__(self, **kwargs):
        """
        Initialize TFCmdOnAWS with AWS-specific configurations.

        Args:
            **kwargs: Keyword arguments including:
                app_dir (str): Application directory path
                envfile (str): Environment file name
                tf_bucket_path (str): Terraform bucket path
                run_share_dir (str): Shared directory path
                binary (str): Binary name
                version (str): Version number
                arch (str): Architecture type
                runtime_env (str): Runtime environment
        """
        self.classname = "TFCmdOnAWS"

        self.app_name = "terraform"
        self.app_dir = kwargs["app_dir"]  # e.g. var/tmp/terraform
        self.envfile = kwargs["envfile"]  # e.g. build_env_vars.env
        self.tf_bucket_path = kwargs["tf_bucket_path"]
        self.run_share_dir = kwargs["run_share_dir"]
        self.add_ssm_names = kwargs.get("add_ssm_names")
        self.ssm_tmp_dir = "/tmp"
        self.ssm_names_b64 = None
        self.wait_destroy = kwargs.get("wait_destroy",120)
        self.wait_apply = kwargs.get("wait_apply",30)

        TFAppHelper.__init__(
            self,
            binary=kwargs["binary"],
            app_dir=self.app_dir,
            version=kwargs["version"],
            arch=kwargs["arch"],
            runtime_env=kwargs["runtime_env"]
        )

    def get_tf_install(self):
        """
        Get Terraform installation commands.

        Returns:
            list: Commands for installing Terraform
        """
        return get_tf_install(
            runtime_env=self.runtime_env,
            binary=self.binary,
            version=self.version,
            tf_bucket_path=self.tf_bucket_path,
            arch=self.arch,
            bin_dir=self.bin_dir
        )

    @staticmethod
    def _get_ssm_concat_cmds():
        """
        Get commands for concatenating SSM parameters.
        Used only for CodeBuild.

        Returns:
            list: Commands for SSM parameter handling
        """
        if os.environ.get("DEBUG_STATEFUL"):
            return ['echo $SSM_VALUE | base64 -d >> $TMPDIR/.ssm_value && cat $TMPDIR/.ssm_value']
        else:
            return ['echo $SSM_VALUE | base64 -d >> $TMPDIR/.ssm_value']

    def _get_add_ssm_names(self):

        if not self.add_ssm_names:
            return

        try:
            additional_ssm_names = [name.strip() for name in self.add_ssm_names.split(',')]
        except:
            additional_ssm_names = [self.add_ssm_names]

        ssm_helper = SSMHelper()

        ssm_value_lines = []

        for additional_ssm_name in additional_ssm_names:
            self.logger.debug(f'fetching ssm value from ssm name "{additional_ssm_name}"')
            _ssm_value = ssm_helper.get_and_parse_ssm_param(additional_ssm_name,
                                                            set_in_env=False,
                                                            insert=False)
            ssm_value_lines.extend(_ssm_value)

        cmds = ["#!/bin/bash", ""]

        for num, ssm_value_line in enumerate(ssm_value_lines, start=1):
            key_value = ssm_helper.get_key_value_from_line(ssm_value_line)
            if not key_value:
                continue  # Skip lines that can't be parsed

            if ssm_value_line.startswith('export '):
                ssm_value_line = ssm_value_line[len('export '):]

            key, value = key_value
            if key == "GITHUB_TOKEN":
                base64_str = ssm_helper.create_netrc_file(value,get_base_64=True)
                cmds.extend([
                    f'echo "{base64_str}" | base64 -d > $TMPDIR/.netrc',
                    f'echo "{base64_str}" | base64 -d > ~/.netrc'
                ])
            elif num == 1:
                cmds.append(f'echo "{ssm_value_line}" > $TMPDIR/.ssm_values')
            else:
                cmds.append(f'echo "{ssm_value_line}" >> $TMPDIR/.ssm_values')

        return cmds

    def _set_src_envfiles_cmd(self):
        """
        Set commands for environment file setup.
        Used only for CodeBuild.

        Returns:
            list: Commands for environment file setup
        """
        exclude_var_cmd = '''export $(awk -F= '!/^#/ && !($1 in ENVIRON) {print $1 "=" $2}' .env)'''
        ssm_cmd = 'if [ -f $TMPDIR/.ssm_value ]; then cd $TMPDIR/; . ./.ssm_value; fi'

        return [
            f'if [ -f {self.stateful_dir}/{self.envfile} ]; then mv {self.stateful_dir}/{self.envfile} /tmp/.env; fi',
            f'if [ -f /tmp ]; then cd /tmp && {exclude_var_cmd}; fi',
            ssm_cmd,
        ]

    def set_ssm_names(self):

        try:
            add_ssm_names_content = "\n".join(self._get_add_ssm_names())
            self.ssm_names_b64 = b64_encode(add_ssm_names_content)
        except:
            self.ssm_names_b64 = None

    def load_env_files(self):
        """
        Load environment files and SSM parameters.

        Returns:
            list: Commands for loading environment files
        """
        envfile = os.path.join(self.app_dir, self.envfile)

        cmds = [
            f'rm -rf {self.stateful_dir}/{envfile} > /dev/null 2>&1 || echo "env file already removed"',
            f'if [ -f {self.stateful_dir}/run/{envfile}.enc ]; then cat {self.stateful_dir}/run/{envfile}.enc | base64 -d > {self.stateful_dir}/{self.envfile}; fi'
        ]

        cmds.extend(self._get_ssm_concat_cmds())
        cmds.extend(self._set_src_envfiles_cmd())

        # Only extend if add_cmds is not None
        if self.ssm_names_b64:
            cmds.append('echo $SSM_SCRIPT_VALUE | base64 -d >> $TMPDIR/.addd_ssm_names_script')
            cmds.append('chmod 755 $TMPDIR/.addd_ssm_names_script')
            cmds.append('$TMPDIR/.addd_ssm_names_script')
            cmds.append('if [ -f $TMPDIR/.ssm_values ]; then cd $TMPDIR/; . ./.ssm_values; fi')
        return cmds

    def s3_tfpkg_to_local(self):
        """
        Copy Terraform package from S3 to local filesystem.

        Returns:
            list: Commands for copying and extracting Terraform package
        """
        cmds = self.reset_dirs()

        # ref 4353253452354
        cmds.extend([
            'echo "remote bucket s3://$REMOTE_SRC_BUCKET/$REMOTE_SRC_BUCKET_KEY"',
            f'aws s3 cp s3://$REMOTE_SRC_BUCKET/$REMOTE_SRC_BUCKET_KEY {self.stateful_dir}/src.$STATEFUL_ID.zip --quiet',
            f'rm -rf {self.stateful_dir}/run > /dev/null 2>&1 || echo "stateful already removed"',
            f'unzip -o {self.stateful_dir}/src.$STATEFUL_ID.zip -d {self.stateful_dir}/run',
            f'rm -rf {self.stateful_dir}/src.$STATEFUL_ID.zip'
        ])
        return cmds
    
    def _get_tf_validate(self,last_apply=None):
        """Get Terraform validation commands"""
        status_file = "status.tf_validate.failed.code"
        cmds = [
            f'{self.base_cmd} validate -no-color > {self.tmp_base_output_file}.validate 2>&1 || echo $? > {status_file}',
            f'cat {self.tmp_base_output_file}.validate'
            ]
        cmds.extend(self.wrapper_cmds_to_s3(cmds, suffix="validate", last_apply=last_apply))
        cmds.append(f'if [ -f {status_file} ]; then rm -f {status_file}; exit 10; fi')

        return cmds

    def _get_tf_init(self,last_apply=None):
        """Get Terraform initialization commands"""
        status_file = "status.tf_init.failed.code"
        suffix_cmd = f'{self.base_cmd} init -no-color > {self.tmp_base_output_file}.init 2>&1'
        cmds = [
            f'({suffix_cmd}) || (rm -rf .terraform && {suffix_cmd}) || echo $? > {status_file}',
            f'cat {self.tmp_base_output_file}.init'
        ]
        cmds.extend(self.wrapper_cmds_to_s3(cmds, suffix="init", last_apply=last_apply))
        cmds.append(f'if [ -f {status_file} ]; then rm -f {status_file}; exit 10; fi')

        return cmds

    def _get_tf_plan(self,last_apply=None,destroy=None):
        """Get Terraform plan commands"""

        status_file = "status.tf_plan.failed.code"

        plan_cmd = "plan"

        if destroy:
            plan_cmd = f'plan -destroy'

        # output cmds
        cmds = [
            f'{self.base_cmd} {plan_cmd} -no-color > {self.tmp_base_output_file}.tfplan.out 2>&1 || echo $? > {status_file}',
            f'cat {self.tmp_base_output_file}.tfplan.out'
        ]

        if destroy:
            self.wrapper_cmds_to_s3(cmds, suffix="tfplan.out", last_apply=last_apply, additional_suffix="destroy")
        else:
            self.wrapper_cmds_to_s3(cmds, suffix="tfplan.out", last_apply=last_apply)

        cmds.append(f'if [ -f {status_file} ]; then rm -f {status_file}; exit 10; fi')

        # plan cmds
        if not destroy:
            plan_cmds = [ f'{self.base_cmd} {plan_cmd} -out={self.tmp_base_output_file}.tfplan' ]
            self.wrapper_cmds_to_s3(plan_cmds, suffix="tfplan", last_apply=last_apply)
            cmds.extend(plan_cmds)

        return cmds

    def backup_cmds_tf(self):
        cmds = [ self.backup_s3_file(suffix="init") ]
        cmds.append(self.backup_s3_file(suffix="validate"))
        cmds.append(self.backup_s3_file(suffix="fmt"))
        cmds.append(self.backup_s3_file(suffix="tfplan.out"))
        cmds.append(self.backup_s3_file(suffix="tfplan"))

        return cmds

    def get_tf_ci(self):
        """Get commands for CI pipeline"""
        cmds = self._get_tf_init()
        cmds.extend(self._get_tf_validate())
        cmds.extend(self._get_tf_plan())
        return cmds

    def get_tf_apply(self, destroy_on_failure=None):
        """
        Get commands for applying Terraform configuration.

        Args:
            destroy_on_failure (bool): Whether to destroy resources on failure

        Returns:
            list: Commands for applying Terraform configuration
        """
        cmds = self._get_tf_init(last_apply=None)
        cmds.extend(self._get_tf_validate(last_apply=None))
        cmds.extend(self.s3_file_to_local(suffix="tfplan", last_apply=None))

        # disabled this for now b/c you won't want to destroy entire infrastructure
        # if an apply update fails
        #if destroy_on_failure:
        #    cmds.append(f"({self.base_cmd} apply {self.base_output_file}.tfplan) || ({self.base_cmd} destroy -auto-approve && exit 9)")
        #else:
        #    cmds.append(f"({self.base_cmd} apply {self.base_output_file}.tfplan)")

        cmds.append(f'echo "{"#"*32}"')
        cmds.append(f"{self.base_cmd} show {self.base_output_file}.tfplan")
        cmds.append(f'echo "{"#"*32}"')
        cmds.append(f'echo "# Be sure to look at proposed apply - pausing {self.wait_apply}s"')
        cmds.append(f'echo "{"#"*32}"')

        # Pause for the specified time
        cmds.append(f'sleep {self.wait_apply}')

        # run the actually apply
        cmds.append(f"{self.base_cmd} apply {self.base_output_file}.tfplan")

        return cmds

    def get_tf_destroy(self):
        """Get commands for destroying Terraform resources"""
        cmds = self._get_tf_init(last_apply=True)

        # this is just a self check
        cmds.extend(self.s3_file_to_local(suffix="tfplan.out.destroy", last_apply=None))
        cmds.extend(self.remove_s3_file(suffix="tfplan.out.destroy"))

        cmds.append(f'echo "{"#"*32}"')
        cmds.append(f"cat {self.base_output_file}.tfplan.out.destroy")
        cmds.append(f'echo "{"#"*32}"')
        cmds.append(f'echo "# Be sure to look at proposed destroy - pausing {self.wait_destroy}s"')
        cmds.append(f'echo "{"#"*32}"')
        cmds.append(f'sleep {int(self.wait_destroy)}')

        # run the actually destroy
        cmds.append(f'{self.base_cmd} destroy -auto-approve')

        return cmds

    def get_tf_plan_destroy(self):
        """Get commands for destroying Terraform resources"""
        cmds = self._get_tf_init()
        cmds.extend(self._get_tf_validate())
        cmds.extend(self._get_tf_plan(destroy=True))
        return cmds

    def get_tf_chk_drift(self,cmds_alone=None):
        """Get commands for checking infrastructure drift"""
        cmds = self._get_tf_init()
        add_cmds = [
            f'({self.base_cmd} refresh)',
            f'({self.base_cmd} plan -detailed-exitcode)'
        ]
        if cmds_alone:
            return add_cmds
        cmds.extend(add_cmds)
        return cmds