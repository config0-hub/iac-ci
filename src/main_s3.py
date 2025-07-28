#!/usr/bin/env python
"""
Package code to S3 module for IAC CI.

This module provides functionality to clone a git repository and upload it to S3.

Copyright 2025 Gary Leong <gary@config0.com>
License: GNU General Public License v3.0
"""

import shutil
import os
import base64
import traceback

from iac_ci.common.serialization import b64_encode
from iac_ci.common.utilities import find_filename
from iac_ci.common.utilities import id_generator
from iac_ci.common.utilities import rm_rf
from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.orders import PlatformReporter
from iac_ci.common.gitclone import CloneCheckOutCode

class PkgCodeToS3(PlatformReporter, CloneCheckOutCode):
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
        CloneCheckOutCode.__init__(self, **kwargs)

        self.app_dir = None
        self.archive_dir = None
        self.clone_dir = None
        self.repo_name = None
        self.phase = "pkgcode-to-s3"
        self.maxtime = 180

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

        shutil.make_archive(
            f'/tmp/{self.commit_hash}',
            'zip',
            verbose=True
        )

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
        self.db.table_runs.insert(self.run_info)
        msg = f"trigger_id/{self.trigger_id} iac_ci_id/{self.iac_ci_id} saved"
        self.add_log(msg)

    def clone_and_archive_code(self):

        failed_message = None

        try:
            self.write_private_key()
            self.fetch_code()
            self._archive_code()
        except:
            failed_message = traceback.format_exc()

        return {"failed_message": failed_message}

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

        failed_message = self.clone_and_archive_code()

        self.results["publish_vars"] = {
            "remote_src_bucket": self.remote_src_bucket,
            "remote_src_bucket_key": self.remote_src_bucket_key
        }

        if failed_message:
            failure_s3_key = id_generator()
            failed_file = os.path.join("/tmp", failure_s3_key)
            with open(failed_file, 'w') as _file:
                _file.write(failed_message)

            self.s3_file.insert(
                s3_bucket=self.tmp_bucket,
                s3_key=failure_s3_key,
                srcfile=failed_file
            )
            rm_rf(failed_file)
            self.results["failure_s3_key"] = failure_s3_key
            self.logger.error(f'failure log uploaded to "{failure_s3_key}"')
            raise Exception(failed_message)

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