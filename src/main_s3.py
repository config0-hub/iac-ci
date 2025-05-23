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
import base64
from botocore.exceptions import ClientError

from iac_ci.common.serialization import b64_encode
from iac_ci.common.shellouts import system_exec
from iac_ci.common.utilities import find_filename

from iac_ci.common.utilities import id_generator
from iac_ci.common.utilities import rm_rf
from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.orders import OrdersStagesHelper as PlatformReporter


class PkgCodeToS3(PlatformReporter):
    """
    This is not currently being used.

    It was initially built to be packaged as lambda function to:

    1) get ssh_url and s3 bucket from environment variables
    2) get ssh deploy key either from the environment variable or SSM in AWS
    3) clone the commit hash for the code repository and upload as a zip file to s3 bucket
    """
    def __init__(self, **kwargs):
        self.classname = "PkgCodeToS3"
        self.logger = IaCLogger(self.classname)
        PlatformReporter.__init__(self, **kwargs)

        session = boto3.Session()
        self.ssm = session.client('ssm')

        self.app_dir = None
        self.iac_ci_folder = None
        self.archive_dir = None
        self.clone_dir = None
        self.ssm_ssh_key = None
        self.repo_name = None
        self.git_depth = None
        self.ssh_url = None
        self.phase = "pkgcode-to-s3"
        self.private_key_path = "/tmp/id_rsa"
        self.base_clone_dir = "/tmp/code/src"
        self.base_ssh = f"GIT_SSH_COMMAND='ssh -i {self.private_key_path} -o StrictHostKeyChecking=no -o IdentitiesOnly=yes'"
        self.maxtime = 180

        rm_rf(self.private_key_path)
        rm_rf(self.base_clone_dir)

        self._set_order()

    def _set_order(self):
        """
        Sets the order for the current process with a human-readable description
        and a specified role. It constructs input arguments including a description
        of fetching code and uploading to s3 and assigns the order using the new_order method.
        """
        human_description = "Fetch code and upload to s3"
        inputargs = {
            "human_description": human_description,
            "role": "s3/upload"
        }
        self.new_order(**inputargs)

    def _write_private_key(self):
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
            try:
                _ssm_info = self.ssm.get_parameter(Name=self.ssm_ssh_key, WithDecryption=True)
                private_key_hash = _ssm_info["Parameter"]["Value"]
            except ClientError as e:
                raise Exception(f"Failed to retrieve private key from SSM: {str(e)}")

        if not private_key_hash:
            failed_message = "private_key_hash not found"
            raise Exception(failed_message)

        cmd = f'echo "{private_key_hash}" | base64 -d > {self.private_key_path}'
        system_exec(cmd)

        os.chmod(self.private_key_path, 0o600)

    def _fetch_code(self):
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

    def _get_build_env_vars_frm_file(self):
        """
        Retrieves and decodes build environment variables from an encrypted file.

        This method changes the current working directory to `archive_dir` and searches
        for a file named 'build_env_vars.env.enc'. If found, it reads and decodes the
        base64-encoded content of the file to extract environment variables, which are
        returned as a dictionary. The file is also uploaded to an S3 bucket.

        Returns:
            dict: A dictionary containing the decoded environment variables as key-value pairs.
                  Returns an empty dictionary if the file is not found.
        """
        os.chdir(self.archive_dir)

        match_files = find_filename(self.archive_dir, 'build_env_vars.env.enc')

        if not match_files:
            self.logger.debug(f"No build_env_vars.env.enc file found in '{self.archive_dir}'")
            return {}

        build_file_path = match_files[0]

        env_vars = {}

        try:
            with open(build_file_path, 'rb') as enc_file:
                encoded_content = enc_file.read()
                decoded_content = base64.b64decode(encoded_content)
                env_var_lines = decoded_content.decode('utf-8').strip().splitlines()
                for line in env_var_lines:
                    if '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
        except (IOError, UnicodeDecodeError) as e:
            self.logger.debug(f"Error processing build environment variables file: {e}")
            return {}

        self.s3_file.insert(
            s3_bucket=self.remote_src_bucket,
            s3_key=self.remote_build_env_vars_key,
            srcfile=build_file_path
        )

        return env_vars

    def _archive_code(self):
        """
        Archives the code in the `archive_dir` to a zip file and uploads it to s3.

        It first changes the directory to the `archive_dir` and creates a zip file
        of all the files in the directory. It then uploads the zip file to the
        specified s3 bucket and key.

        Raises:
            Exception: if any of the commands fail
        """
        os.chdir(self.archive_dir)

        try:
            shutil.make_archive(
                f'/tmp/{self.commit_hash}',
                'zip',
                verbose=True
            )
        except (shutil.Error, OSError) as e:
            raise Exception(f"Failed to create archive: {str(e)}")

        # for some reason, if set self.s3_key and insert it here
        # the upload to s3 is an ascii file
        self.s3_file.insert(
            s3_bucket=self.remote_src_bucket,
            s3_key=self.remote_src_bucket_key,
            srcfile=self.local_src
        )

        print("#" * 32)
        print("")
        print(f"Uploading code {self.remote_src_bucket}/{self.remote_src_bucket_key}")
        print("")
        print("#" * 32)

    def _save_run_info(self):
        """
        Saves the run_info to the table_runs in DynamoDB.

        It sets the remote_src_bucket and remote_src_bucket_key in the run_info
        and saves the run_info to the DynamoDB table. It then logs a message
        indicating that the trigger_id has been saved.

        Raises:
            Exception: if the insert to DynamoDB fails
        """
        self.run_info["remote_src_bucket"] = self.remote_src_bucket
        self.run_info["remote_src_bucket_key"] = self.remote_src_bucket_key

        try:
            self.db.table_runs.insert(self.run_info)
        except Exception as e:
            raise Exception(f"Failed to save run info to DynamoDB: {str(e)}")

        msg = f"trigger_id/{self.trigger_id} iac_ci_id/{self.iac_ci_id} saved"
        self.add_log(msg)

    def execute(self):
        """
        Execute the main process of this class.

        This method sets the order, initializes the build variables, fetches the
        code, archives the code, uploads the code to s3 and saves the run
        information to the database.

        It logs a message indicating that the trigger_id has been triggered and
        saves the run information to the database. It also sets the inputargs
        variable for the next step and logs a summary message.

        Returns:
            bool: True if execution is successful
        """
        self.archive_dir = f'{self.base_clone_dir}/{id_generator()}'
        self.clone_dir = f'{self.archive_dir}/{self.app_dir}'

        self.results["publish_vars"] = {
            "remote_src_bucket": self.remote_src_bucket,
            "remote_src_bucket_key": self.remote_src_bucket_key
        }

        self._write_private_key()
        self._fetch_code()
        self._archive_code()

        # set the iac platform if explicitly provided in the build_enva_vars
        build_env_vars = self._get_build_env_vars_frm_file()

        if os.environ.get('DEBUG_IAC_CI'):
            self.logger.debug("*" * 32)
            self.logger.debug("* build_env_vars")
            self.logger.json(build_env_vars)
            self.logger.debug("*" * 32)

        if build_env_vars:
            self.run_info["build_env_vars_b64"] = b64_encode(build_env_vars)

        # successful at this point
        self.results["msg"] = f"code fetched repo_name {self.repo_name}, commit_hash {self.commit_hash} to {self.remote_src_bucket}/{self.remote_src_bucket_key}"
        self.results["update"] = True
        self.results["continue"] = True

        self.insert_to_return()

        self.add_log("#" * 32)
        self.add_log("# Summary")
        self.add_log("# Code fetched and uploaded")
        self.add_log(f'# Git Repo: "{self.repo_name}"')
        self.add_log(f'# Commit hash: "{self.commit_hash}"')
        self.add_log(f'# Remote Location: "{self.remote_src_bucket}/{self.remote_src_bucket_key}"')
        self.add_log("#" * 32)

        self.finalize_order()
        self._save_run_info()

        return True
