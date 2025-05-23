#!/usr/bin/env python
"""
TFAppHelper - Terraform Application Helper

A helper class for managing Terraform application installation, setup, and file operations.
Handles binary downloads, directory management, and S3 file transfers.
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
from time import time
from iac_ci.common.loggerly import IaCLogger


class TFAppHelper:
    """
    Helper class for managing Terraform application installation, setup, and file operations.
    Handles binary downloads, directory management, and S3 file transfers.
    """

    def __init__(self, **kwargs):
        """
        Initialize TFAppHelper with configuration parameters.

        Args:
            **kwargs: Keyword arguments including:
                binary (str): Required - Name of the binary
                version (str): Required - Version of the binary
                bucket (str): S3 bucket for storage
                installer_format (str): Format of installer (zip/targz)
                src_remote_path (str): Remote source path
                runtime_env (str): Runtime environment (codebuild/lambda)
                app_name (str): Application name
                app_dir (str): Application directory
                arch (str): Architecture type
        """
        self.classname = "TFAppHelper"
        self.logger = IaCLogger(self.classname, logcategory="cloudprovider")
        self.iac_platform = os.environ.get("IAC_PLATFORM", "config0")

        # Required parameters
        self.binary = kwargs['binary']
        self.version = kwargs['version']

        # Optional parameters
        self.bucket = kwargs.get("bucket")
        self.installer_format = kwargs.get("installer_format")
        self.src_remote_path = kwargs.get("src_remote_path")
        self.start_time = str(time())

        # Environment and directories
        self.runtime_env = kwargs.get("runtime_env", 'codebuild')
        
        if not hasattr(self, "app_name"):
            self.app_name = kwargs.get("app_name", self.binary)

        self.stateful_dir = f'$TMPDIR/{self.iac_platform}/$STATEFUL_ID'
        self.app_dir = kwargs.get("app_dir", "var/tmp/terraform")
        self.arch = kwargs.get("arch", 'linux_amd64')

        if self.runtime_env == "lambda":
            self.bin_dir = f"/tmp/{self.iac_platform}/bin"
        else:
            self.bin_dir = "/usr/local/bin"

        os.makedirs(self.bin_dir, exist_ok=True)

        # Execution directory is in "run" subdirectory
        self.exec_dir = f'{self.stateful_dir}/run/{self.app_dir}'
        self.base_cmd = f'cd {self.exec_dir} && {self.bin_dir}/{self.binary} '

        # File paths
        self.base_file_path = f'{self.binary}_{self.version}_{self.arch}'
        self.bucket_path = f"s3://{self.bucket}/downloads/{self.app_name}/{self.base_file_path}"
        self.dl_file_path = f'$TMPDIR/{self.base_file_path}'

        # Output files
        self.tmp_base_output_file = f'/tmp/{self.app_name}.$STATEFUL_ID'
        self.base_output_file = f'{self.stateful_dir}/output/{self.app_name}.$STATEFUL_ID'

    def _get_initial_preinstall_cmds(self):
        """
        Get initial commands needed before installation.

        Returns:
            list: List of commands for pre-installation setup
        """
        if self.runtime_env == "codebuild":
            cmds = [
                'which zip || apt-get update',
                'which zip || apt-get install -y unzip zip',
            ]
        else:
            cmds = [f'echo "downloading {self.base_file_path}"']

        return cmds

    def reset_dirs(self):
        """
        Generate commands to reset and create necessary directories.

        Returns:
            list: List of commands for directory setup
        """
        cmds = [
            f'rm -rf $TMPDIR/{self.iac_platform} > /dev/null 2>&1 || echo "{self.iac_platform} already removed"',
            f'mkdir -p {self.stateful_dir}/run',
            f'mkdir -p {self.stateful_dir}/output/{self.app_name}',
            f'mkdir -p {self.stateful_dir}/generated/{self.app_name}',
            f'echo "##############"; df -h; echo "##############"'
        ]

        cmds.extend(self._get_initial_preinstall_cmds())

        return cmds

    def download_cmds(self):
        """
        Generate commands for downloading and installing the binary.

        Returns:
            list: List of commands for downloading and installation
        """
        if self.installer_format == "zip":
            _suffix = "zip"
        elif self.installer_format == "targz":
            _suffix = "tar.gz"
        else:
            _suffix = None

        if not _suffix:
            base_file_path = self.base_file_path
            dl_file_path = self.dl_file_path
            bucket_path = self.bucket_path
            src_remote_path = self.src_remote_path
        else:
            base_file_path = f'{self.base_file_path}.{_suffix}'
            dl_file_path = f'{self.dl_file_path}.{_suffix}'
            bucket_path = f'{self.bucket_path}.{_suffix}'
            src_remote_path = f'{self.src_remote_path}.{_suffix}'

        _hash_delimiter = f'echo "{"#" * 32}"'

        _bucket_install_1 = f'aws s3 cp {bucket_path} {dl_file_path} --quiet'
        _bucket_install_2 = f'echo "# GOT {base_file_path} from s3 bucket/cache"'
        _src_install_1 = f'echo "# NEED to get {base_file_path} from source"'
        _src_install_2 = f'curl -L -s {src_remote_path} -o {dl_file_path}'
        _src_install_3 = f'aws s3 cp {dl_file_path} {bucket_path} --quiet'

        _bucket_install = f'{_bucket_install_1} && {_hash_delimiter} && {_bucket_install_2} && {_hash_delimiter}'
        _src_install = f'{_hash_delimiter} && {_src_install_1} && {_hash_delimiter} && {_src_install_2} && {_src_install_3}'

        install_cmd = f'({_bucket_install}) || ({_src_install})'

        cmds = [
            install_cmd,
            f'mkdir -p {self.bin_dir} || echo "trouble making self.bin_dir {self.bin_dir}"'
        ]

        if self.installer_format == "zip":
            cmds.append(f'(cd $TMPDIR && unzip {base_file_path} > /dev/null) || exit 0')
        elif self.installer_format == "targz":
            cmds.append(f'(cd $TMPDIR && tar xfz {base_file_path} > /dev/null) || exit 0')

        return cmds

    def local_output_to_s3(self, srcfile=None, suffix=None, last_apply=None):
        """
        Generate commands to copy local files to S3.

        Args:
            srcfile (str): Source file path
            suffix (str): File suffix
            last_apply (bool): Flag for last apply operation

        Returns:
            list/str: Command(s) for S3 upload

        Raises:
            ValueError: If srcfile cannot be determined
        """
        if not srcfile and suffix:
            srcfile = f'{self.tmp_base_output_file}.{suffix}'

        if not srcfile:
            raise ValueError("srcfile needs to be determined to upload to s3")

        _filename = os.path.basename(srcfile)
        base_cmd = f'aws s3 cp {srcfile} s3://$REMOTE_STATEFUL_BUCKET/$STATEFUL_ID'

        if last_apply:
            cmds = f'{base_cmd}/applied/{_filename} || echo "trouble uploading output file"'
        else:
            cmds = [
                f'aws s3 cp s3://$REMOTE_STATEFUL_BUCKET/$STATEFUL_ID/cur/{_filename} '
                f's3://$REMOTE_STATEFUL_BUCKET/$STATEFUL_ID/previous/{_filename} || '
                f'echo "trouble copying file {_filename} in s3"',
                
                f'aws s3 rm s3://$REMOTE_STATEFUL_BUCKET/$STATEFUL_ID/cur/{_filename} || '
                f'echo "trouble removing file cur {_filename} in s3"',
                
                f'{base_cmd}/cur/{_filename} || echo "trouble uploading output file"'
            ]

        return cmds

    def s3_file_to_local(self, dstfile=None, suffix=None, last_apply=None):
        """
        Generate commands to copy S3 files to local filesystem.

        Args:
            dstfile (str): Destination file path
            suffix (str): File suffix
            last_apply (bool): Flag for last apply operation

        Returns:
            list: Commands for downloading from S3

        Raises:
            ValueError: If dstfile cannot be determined
        """
        if not dstfile and suffix:
            dstfile = f'{self.base_output_file}.{suffix}'

        if not dstfile:
            raise ValueError("dstfile needs to be determined to upload to s3")

        _filename = os.path.basename(dstfile)

        if last_apply:
            cmds = [f'aws s3 cp s3://$REMOTE_STATEFUL_BUCKET/$STATEFUL_ID/applied/{_filename} {dstfile}']
        else:
            cmds = [f'aws s3 cp s3://$REMOTE_STATEFUL_BUCKET/$STATEFUL_ID/cur/{_filename} {dstfile}']

        return cmds