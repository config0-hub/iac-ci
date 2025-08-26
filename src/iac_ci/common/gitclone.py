#!/usr/bin/env python
"""
Package code to S3 module for IAC CI.

This module provides functionality to clone a git repository and upload it to S3.

Copyright 2025 Gary Leong <gary@config0.com>
License: GNU General Public License v3.0
"""

import shutil
import os
import yaml
from pathlib import Path
import boto3
import json

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
    def __init__(self, ssh_url=None, commit_hash=None):
        self.logger = IaCLogger("CloneCheckOutCode")
        
        self.ssm_ssh_key = None
        self.git_depth = None

        self.ssh_url = ssh_url
        self.commit_hash = commit_hash

        self.logger.info(self.ssh_url)
        self.logger.info(self.commit_hash)

        self.iac_ci_folder = None
        self.private_key_path = "/tmp/id_rsa"
        self.base_clone_dir = "/tmp/code/src"
        self.clone_dir = f'{self.base_clone_dir}/{id_generator()}'

        # Updated GIT_SSH_COMMAND to avoid writing to known_hosts
        self.base_ssh = (
            f"GIT_SSH_COMMAND='ssh -i {self.private_key_path} "
            "-o StrictHostKeyChecking=no "
            "-o IdentitiesOnly=yes "
            "-o UserKnownHostsFile=/dev/null'"
        )
        
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
        self.logger.debug(f"wrote private key cmd {self.private_key_path}")

        os.chmod(self.private_key_path, 0o600)

    def fetch_code(self,iac_ci_folder_must_exists=None):
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

        cmds = [
            "git init",
            f'git remote add origin "{self.ssh_url}"',
        ]

        if self.git_depth:
            cmds.append(f"{self.base_ssh} git fetch --quiet origin --depth {self.git_depth}")
        else:
            cmds.append(f"{self.base_ssh} git fetch --quiet origin")

        cmds.append(f"{self.base_ssh} git fetch --quiet origin {self.commit_hash}")
        cmds.append(f"{self.base_ssh} git checkout --quiet -f {self.commit_hash}")
        cmds.append("rm -rf .git")

        for cmd in cmds:
            self.logger.debug(f"Executing: {cmd}")
            system_exec(cmd)

        os.makedirs(self.clone_dir, exist_ok=True)

        if not self.iac_ci_folder and iac_ci_folder_must_exists:
            raise Exception("iac_ci_folder not set")

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

    def find_and_process_config_files(self, basedir=None, config_path=".iac_ci/config.yaml"):
        """
        Searches for directories containing the specified config file, reads the YAML,
        and extracts 'destroy' and 'apply' values.

        Args:
            basedir (str): Root directory to start the search from
            config_path (str): Relative path to the config file to search for

        Returns:
            dict: Dictionary with directory paths as keys and subdictionaries of 'destroy' and 'apply' values
        """

        if not basedir:
            basedir = self.clone_dir

        results = {}

        # Convert to absolute path and resolve any symlinks
        root_path = Path(basedir).resolve()

        # Walk through all directories
        for dirpath, dirnames, filenames in os.walk(root_path):
            # Create the potential config file path
            current_path = Path(dirpath)
            config_file = current_path / config_path

            # Check if the config file exists
            if config_file.exists() and config_file.is_file():
                try:
                    # Read and parse the YAML file
                    with open(config_file, 'r') as file:
                        config_data = yaml.safe_load(file)

                    # Extract destroy and apply values, defaulting to False if not present
                    destroy_value = config_data.get('destroy', False)
                    apply_value = config_data.get('apply', False)

                    # Only consider True if explicitly set to True
                    destroy_value = True if destroy_value is True else False
                    apply_value = True if apply_value is True else False

                    # Store the results
                    # Use relative path from basedir for cleaner output
                    rel_path = str(current_path.relative_to(root_path))
                    results[rel_path] = {
                        'destroy': destroy_value,
                        'apply': apply_value
                    }

                except Exception as e:
                    print(f"Error processing {config_file}: {e}")

        return results

    def get_repo_file(self, rel_file_path, file_type=None):
        """
        Reads a file as YAML, JSON, or raw text.

        Args:
            file_path (str): The path to the file.
            file_type (str): The expected file type (yaml, json, etc.).

        Returns:
            dict or str: Parsed content if the file is YAML/JSON, else raw text.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        file_path = os.path.join(self.clone_dir, rel_file_path)

        if not os.path.exists(file_path):
            self.logger.warn(f"The file '{file_path}' does not exist.")
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
        except Exception as e:
            self.logger.error(f"Error reading file '{file_path}': {e}")
            return False

        if file_type in ["yaml", "yml"]:
            try:
                return yaml.safe_load(content)
            except yaml.YAMLError:
                return content

        elif file_type in ["json", "dict"]:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return content
        else:
            return content