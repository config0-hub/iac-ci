#!/usr/bin/env python
"""
Package code to S3 module for IAC CI.

This module provides functionality to clone a git repository and upload it to S3.

Copyright 2025 Gary Leong <gary@config0.com>
License: GNU General Public License v3.0
"""

import shutil
import os
import boto3

from iac_ci.common.serialization import b64_encode
from iac_ci.common.shellouts import system_exec
from iac_ci.common.utilities import find_filename

from iac_ci.common.utilities import id_generator
from iac_ci.common.utilities import rm_rf
from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.orders import PlatformReporter

class CloneCheckOutCode:
    """
    Base class that contains functionality to clone and checkout code from a git repository.
    """
    def __init__(self, **kwargs):
        self.logger = IaCLogger("CloneCheckOutCode")
        
        self.ssm_ssh_key = None
        self.git_depth = None
        self.ssh_url = None
        self.commit_hash = None
        self.iac_ci_folder = None
        self.private_key_path = "/tmp/id_rsa"
        self.base_clone_dir = "/tmp/code/src"
        self.base_ssh = f"GIT_SSH_COMMAND='ssh -i {self.private_key_path} -o StrictHostKeyChecking=no -o IdentitiesOnly=yes'"
        
        # Initialize SSM client
        session = boto3.Session()
        self.ssm = session.client('ssm')

        # Clean up existing paths
        rm_rf(self.private_key_path)
        rm_rf(self.base_clone_dir)

    def write_private_key(self):
        """
        Writes a private key to a file.

        It first checks if the private key hash is set as an environment variable.
        If not, it then checks if the SSM name for the private key hash is set. If so,
        it retrieves the private key hash from the SSM parameter store and
        writes it to a file. If neither are set, it raises an exception.

        Raises:
            Exception: if private_key_hash is not found
        """
        private_key_hash = os.environ.get("PRIVATE_KEY_HASH")

        if not private_key_hash and self.ssm_ssh_key:
            _ssm_info = self.ssm.get_parameter(Name=self.ssm_ssh_key, WithDecryption=True)
            private_key_hash = _ssm_info["Parameter"]["Value"]

        if not private_key_hash:
            failed_message = "private_key_hash not found"
            raise Exception(failed_message)

        cmd = f'echo "{private_key_hash}" | base64 -d > {self.private_key_path}'
        system_exec(cmd)

        os.chmod(self.private_key_path, 0o600)

    def fetch_code(self):
        """
        Fetches the source code from github.

        It first creates a temporary directory and initializes a git repository.
        Then it adds the remote origin with the ssh url and fetches the code.
        If the git_depth is set, it fetches the code with the specified depth.
        Finally, it moves the code to the clone directory and removes the temporary directory.

        Raises:
            Exception: if any of the git commands fail
        """
        temp_dir = os.path.join("/tmp", id_generator())

        os.makedirs(temp_dir, exist_ok=True)
        os.chdir(temp_dir)

        cmd = "git init"
        cmds = [cmd]
        cmd = f'git remote add origin "{self.ssh_url}"'
        cmds.append(cmd)

        if self.git_depth:
            cmd = f'{self.base_ssh} git fetch --quiet origin --depth {self.git_depth}'
        else:
            cmd = f'{self.base_ssh} git fetch --quiet origin'

        cmds.append(cmd)

        if self.git_depth:
            cmd = f'{self.base_ssh} git fetch --quiet --depth {self.git_depth} origin {self.commit_hash}'
        else:
            cmd = f'{self.base_ssh} git fetch --quiet origin {self.commit_hash}'

        cmds.append(cmd)
        cmd = f'{self.base_ssh} git checkout --quiet -f {self.commit_hash}'
        cmds.extend((cmd, 'rm -rf .git'))
        
        for _cmd in cmds:
            self.logger.debug("#" * 32)
            self.logger.debug("")
            self.logger.debug(_cmd)
            self.logger.debug("")
            system_exec(_cmd)

        os.makedirs(self.clone_dir, exist_ok=True)

        if self.iac_ci_folder:
            src_dir = f'{temp_dir}/{self.iac_ci_folder}'
        else:
            src_dir = temp_dir

        for item in os.listdir(src_dir):
            source_item = os.path.join(src_dir, item)
            target_item = os.path.join(self.clone_dir, item)
            try:
                shutil.move(source_item, target_item)
                self.logger.debug(f"Moved '{source_item}' to '{target_item}'.")
            except (shutil.Error, OSError, IOError) as e:
                self.logger.debug(f"Error moving '{source_item}': {e}")