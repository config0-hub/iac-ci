#!/usr/bin/env python
#
# Copyright (C) 2025 Gary Leong gary@config0.com
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
# along with this program. If not, see <https://www.gnu.org/licenses/>.

from iac_ci.helper.resource.common import TFAppHelper


class TFSecHelper(TFAppHelper):
    """
    Helper class for managing TFSec security scanner operations.
    Provides functionality for installing and executing TFSec security checks on Terraform code.
    Inherits from TFAppHelper.
    """

    def __init__(self, **kwargs):
        """
        Initialize TFSecHelper with TFSec-specific configurations.

        Args:
            **kwargs: Keyword arguments including:
                version (str): TFSec version, defaults to "1.28.10"
                arch (str): Architecture type, defaults to "linux_amd64"
                app_dir (str): Application directory path
                tmp_bucket (str): Temporary S3 bucket name
                runtime_env (str): Runtime environment specification
        """
        self.classname = "TFSecHelper"

        binary = 'tfsec'
        version = kwargs.get("version", "1.28.10")
        arch = kwargs.get("arch", "linux_amd64")

        # TFSec uses hyphens instead of underscores in its release URLs
        src_remote_path = f'https://github.com/aquasecurity/{binary}/releases/download/v{version}/{binary}-{arch.replace("_", "-")}'

        TFAppHelper.__init__(
            self,
            binary=binary,
            version=version,
            arch=arch,
            app_dir=kwargs.get("app_dir"),
            bucket=kwargs["tmp_bucket"],
            runtime_env=kwargs["runtime_env"],
            src_remote_path=src_remote_path
        )

    def install_cmds(self):
        """
        Generate commands for downloading and installing TFSec.

        Returns:
            list: Commands for downloading and setting up TFSec binary
        """
        cmds = self.download_cmds()
        cmds.append(f'(mv {self.dl_file_path} {self.bin_dir}/{self.binary} > /dev/null) || exit 0')
        cmds.append(f'chmod 777 {self.bin_dir}/{self.binary}')

        return cmds

    def exec_cmds(self):
        """
        Generate commands for executing TFSec security checks.
        Creates both human-readable and JSON format outputs.

        Returns:
            list: Commands for running TFSec checks and storing results
        """
        cmds = [
            f'({self.base_cmd} --no-color --out {self.tmp_base_output_file}.out | tee -a /tmp/$STATEFUL_ID.log) || echo "tfsec check failed"',
            f'({self.base_cmd} --no-color --format json --out {self.tmp_base_output_file}.json) || echo "tfsec check with json output failed"'
        ]

        cmds.extend(self.local_output_to_s3(suffix="json", last_apply=None))
        cmds.extend(self.local_output_to_s3(suffix="out", last_apply=None))

        return cmds

    def get_all_cmds(self):
        """
        Combine installation and execution commands.

        Returns:
            list: Combined list of installation and execution commands
        """
        cmds = self.install_cmds()
        cmds.extend(self.exec_cmds())

        return cmds