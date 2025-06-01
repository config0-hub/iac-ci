#!/usr/bin/env python
# 
# Copyright (C) 2025 Gary Leong <gary@config0.com>
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

from iac_ci.helper.resource.common import TFAppHelper


class TFInfracostHelper(TFAppHelper):
    """
    A helper class for managing Infracost installations and executions.

    Inherits from TFAppHelper to facilitate the installation and execution
    of the Infracost binary within a specified runtime environment.
    """

    def __init__(self, **kwargs):
        """
        Initializes the TFInfracostHelper instance.

        Args:
            **kwargs: Additional keyword arguments including:
                - version (str): Version of Infracost to install (default: "0.10.39").
                - arch (str): Architecture of the Infracost binary (default: "linux_amd64").
                - app_dir (str): Directory for the application.
                - tmp_bucket (str): Temporary bucket for storage.
                - runtime_env (str): Runtime environment for execution.
        """
        self.classname = "TFInfracostHelper"

        binary = 'infracost'
        version = kwargs.get("version", "0.10.39")
        arch = kwargs.get("arch", "linux_amd64")

        # tfsec uses hyphen
        arch_with_hyphen = arch.replace("_", "-")
        src_remote_path = f'https://github.com/infracost/{binary}/releases/download/v{version}/{binary}-{arch_with_hyphen}'

        TFAppHelper.__init__(
            self,
            binary=binary,
            version=version,
            app_dir=kwargs.get("app_dir"),
            arch=arch,
            bucket=kwargs["tmp_bucket"],
            installer_format="targz",
            runtime_env=kwargs["runtime_env"],
            src_remote_path=src_remote_path
        )

    def install_cmds(self):
        """
        Generates installation commands for Infracost.

        Returns:
            list: A list of shell commands to install the Infracost binary.
        """
        arch_with_hyphen = self.arch.replace("_", "-")
        dl_file = f'{self.binary}-{arch_with_hyphen}'

        cmds = self.download_cmds()
        cmds.append(f'(cd $TMPDIR && mv {dl_file} {self.bin_dir}/{self.binary} > /dev/null) || exit 0')
        cmds.append(f'chmod 777 {self.bin_dir}/{self.binary}')

        return cmds

    # infracost only executed in lambda
    def exec_cmds(self):
        """
        Generates execution commands for Infracost.

        Returns:
            list: A list of shell commands to execute Infracost and handle output.
        """
        cmds = [
            f'echo "executing INFRACOST"',
            f'({self.base_cmd} --no-color breakdown --path . --out-file {self.tmp_base_output_file}.out && cat {self.tmp_base_output_file}.out | tee -a /tmp/$STATEFUL_ID.log ) || (echo "WARNING: looks like INFRACOST failed")'
        ]
        self.wrapper_cmds_to_s3(cmds, suffix="out", last_apply=None)

        cmds.append(f'({self.base_cmd} --no-color breakdown --path . --format json --out-file {self.tmp_base_output_file}.json) || (echo "WARNING: looks like INFRACOST failed")')
        self.wrapper_cmds_to_s3(cmds, suffix="json", last_apply=None)

        return cmds

    def get_all_cmds(self):
        """
        Combines installation and execution commands.

        Returns:
            list: A list of all shell commands for installation and execution of Infracost.
        """
        cmds = self.install_cmds()
        cmds.extend(self.exec_cmds())

        return cmds