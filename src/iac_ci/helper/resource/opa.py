#!/usr/bin/env python
"""
Helper class for Open Policy Agent (OPA) integration with Terraform.
"""

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


class TFOpaHelper(TFAppHelper):
    """
    Helper class for Open Policy Agent (OPA) integration with Terraform.
    Inherits from TFAppHelper to manage OPA installation and execution.
    """

    def __init__(self, **kwargs):
        """
        Initialize TFOpaHelper with OPA-specific configurations.

        Args:
            **kwargs: Keyword arguments including:
                version (str): OPA version, defaults to "0.68.0"
                arch (str): Architecture type, defaults to "linux_amd64"
                tmp_bucket (str): Temporary S3 bucket for storage
                runtime_env (str): Runtime environment specification
        """
        self.classname = "TFOpaHelper"

        binary = 'opa'
        version = kwargs.get("version", "0.68.0")
        arch = kwargs.get("arch", "linux_amd64")

        src_remote_path = f"https://github.com/open-policy-agent/{binary}/releases/download/v{version}/{binary}_{arch}_static"

        TFAppHelper.__init__(self,
                             binary=binary,
                             version=version,
                             arch=arch,
                             bucket=kwargs["tmp_bucket"],
                             runtime_env=kwargs["runtime_env"],
                             src_remote_path=src_remote_path)

    def install_cmds(self):
        """
        Generate commands for downloading and installing OPA.

        Returns:
            list: Commands for downloading and setting up OPA binary
        """
        cmds = self.download_cmds()
        cmds.append(f'(mv {self.dl_file_path} {self.bin_dir}/{self.binary} > /dev/null) || exit 0')
        cmds.append(f'chmod 777 {self.bin_dir}/{self.binary}')

        return cmds

    @staticmethod
    def exec_cmds():
        """
        Generate commands for executing OPA operations.
        Currently a placeholder for future implementation.

        Returns:
            list: Empty list as implementation is pending
        """
        # cmds tbd
        return []

    def get_all_cmds(self):
        """
        Combine installation and execution commands.

        Returns:
            list: Combined list of installation and execution commands
        """
        cmds = self.install_cmds()
        cmds.extend(self.exec_cmds())

        return cmds