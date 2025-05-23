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


def get_tf_install(**kwargs):
    """
    Generate commands for installing Terraform or OpenTofu from either S3 cache or source.
    
    This function creates a series of shell commands to:
    1. Attempt to download the binary from an S3 bucket cache
    2. If cache miss, download from official sources (HashiCorp or OpenTofu GitHub)
    3. Install the binary in the specified directory
    
    Args:
        **kwargs: Keyword arguments including:
            runtime_env (str): Runtime environment ('codebuild' or 'lambda')
            binary (str): Binary name ('terraform' or 'opentofu')
            version (str): Version of the binary to install
            bucket_path (str): S3 bucket path for caching
            arch (str): Architecture (e.g., 'linux_amd64')
            bin_dir (str): Directory to install the binary
    
    Returns:
        list: Shell commands for downloading and installing the binary
    
    Example URLs:
        Terraform: https://releases.hashicorp.com/terraform/x.y.z/terraform_x.y.z_linux_amd64.zip
        OpenTofu: https://github.com/opentofu/opentofu/releases/download/vx.y.z/tofu_x.y.z_linux_amd64.zip
    """
    runtime_env = kwargs["runtime_env"]
    binary = kwargs["binary"]
    version = kwargs["version"]
    bucket_path = kwargs["tf_bucket_path"]
    arch = kwargs["arch"]
    bin_dir = kwargs["bin_dir"]

    hash_delimiter = f'echo "{"#" * 32}"'

    # Commands for downloading from S3 cache
    bucket_download = f'aws s3 cp {bucket_path} $TMPDIR/{binary}_{version} --quiet'
    bucket_success_msg = f'echo "# GOT {binary} from s3/cache"'
    bucket_install = f'{bucket_download} && {hash_delimiter} && {bucket_success_msg} && {hash_delimiter}'

    # Common messages for direct download
    source_download_msg = f'echo "# NEED {binary}_{version} FROM SOURCE"'
    s3_upload_cmd = f'aws s3 cp {binary}_{version} {bucket_path} --quiet'

    # Terraform-specific download command
    terraform_download_cmd = (
        f'cd $TMPDIR && curl -L -s '
        f'https://releases.hashicorp.com/terraform/{version}/{binary}_{version}_{arch}.zip '
        f'-o {binary}_{version}'
    )
    terraform_direct = (
        f'{hash_delimiter} && {source_download_msg} && {hash_delimiter} && '
        f'{terraform_download_cmd} && {s3_upload_cmd}'
    )

    # OpenTofu-specific download command
    tofu_download_cmd = (
        f'cd $TMPDIR && curl -L -s '
        f'https://github.com/opentofu/opentofu/releases/download/v{version}/{binary}_{version}_{arch}.zip '
        f'-o {binary}_{version}'
    )
    tofu_direct = (
        f'{hash_delimiter} && {source_download_msg} && {hash_delimiter} && '
        f'{tofu_download_cmd} && {s3_upload_cmd}'
    )

    # Choose appropriate installation command based on binary type
    cache_miss_msg = f'echo "terraform/tofu not found in local s3 bucket"'
    if binary == "terraform":
        install_cmd = f'({bucket_install}) || ({cache_miss_msg} && {terraform_direct})'
    else:  # opentofu
        install_cmd = f'({bucket_install}) || ({cache_miss_msg} && {tofu_direct})'

    # Post-download installation commands
    return [
        install_cmd,
        *[
            f'mkdir -p {bin_dir} || echo "trouble making bin_dir {bin_dir}"',
            f'(cd $TMPDIR && unzip {binary}_{version} && mv {binary} {bin_dir}/{binary} > /dev/null) || exit 0',
            f'chmod 777 {bin_dir}/{binary}',
        ],
    ]