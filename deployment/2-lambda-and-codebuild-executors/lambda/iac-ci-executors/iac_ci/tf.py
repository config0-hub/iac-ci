#!/usr/bin/env python

import os
from time import time

from iac_ci.utilities import write_awscli_entrypt
from iac_ci.utilities import write_unzip_cli
from iac_ci.utilities import write_zip_cli
from iac_ci.utilities import write_decrypt_cli
from iac_ci.utilities import write_b64_decode
from iac_ci.utilities import write_untar
from iac_ci.utilities import write_curl_cli
from iac_ci.utilities import write_get_ssm_cli
from iac_ci.utilities import str_to_py_obj

from iac_ci.exec_log_s3 import ShellOut
from iac_ci.s3_unzip_and_env_vars import S3UnzipEnvVar
from iac_ci.loggerly import DirectPrintLogger

logger = DirectPrintLogger(f'{os.environ["EXECUTION_ID"]}')

class TF_Lambda(object):
    """
    A class to handle Terraform operations in AWS Lambda environments.

    This class manages the execution of Terraform commands, environment setup,
    and S3 interactions for source files and logging.
    """

    def __init__(self,**event):
        """
        Initialize TF_Lambda with event parameters and set up environment.

        Args:
            **event: Dictionary containing Lambda event parameters including:
                    - cmds_b64: Base64 encoded commands
                    - env_vars_b64: Base64 encoded environment variables
        """
        write_awscli_entrypt()
        write_unzip_cli()
        write_zip_cli()
        write_decrypt_cli()
        write_b64_decode()
        write_untar()
        write_curl_cli()
        write_get_ssm_cli()

        self._add_env_var_path()
        self._init_env_vars(**event)
        self._init_src_run_vars()

        self.cmds_obj = str_to_py_obj(event["cmds_b64"])
        self._set_init_cmd_env_vars()

    def _init_src_run_vars(self):
        """
        Initialize source and runtime variables.

        Sets up directory structures and validates required environment variables
        for source file management and execution.

        Raises:
            Exception: If required environment variables are missing
        """
        self.iac_platform = os.environ.get("IAC_PLATFORM","config0")
        self.tmpdir = os.environ["TMPDIR"]
        self.method = os.environ["METHOD"]

        self.stateful_id = os.environ.get("STATEFUL_ID")
        self.remote_stateful_bucket = os.environ.get("REMOTE_STATEFUL_BUCKET")
        self.remote_src_bucket = os.environ.get("REMOTE_SRC_BUCKET")
        self.remote_src_bucket_key = os.environ.get("REMOTE_SRC_BUCKET_KEY")

        if not self.remote_src_bucket and self.remote_stateful_bucket:
            self.remote_src_bucket = self.remote_stateful_bucket

        if not self.remote_src_bucket_key and self.stateful_id:
            self.remote_src_bucket_key = f'{self.stateful_id}/state/src.{self.stateful_id}.zip'

        if not self.stateful_id:
            raise Exception("STATEFUL_ID needs to be set as an env var")

        if not self.remote_src_bucket:
            raise Exception("cannot determine the s3 bucket for source files")

        if not self.remote_src_bucket_key:
            raise Exception("cannot determine the s3 bucket key for source files")

        self.app_dir = os.environ.get("APP_DIR")
        self.stateful_dir = f'{self.tmpdir}/{self.iac_platform}/{self.stateful_id}'
        self.run_dir = f'{self.stateful_dir}/run'
        self.exec_dir = f'{self.run_dir}/{self.app_dir}'

        os.makedirs(self.run_dir,exist_ok=True)

    def _load_zip_file_and_build_env_vars(self):
        """
        Load source files from S3 and set up build environment variables.

        Downloads and extracts source files from S3, and initializes build
        environment variables with necessary configurations.

        Returns:
            dict: Dictionary of build environment variables
        """
        logger.debug('-'*32)
        logger.debug(f'fetching source file "s3://{self.remote_src_bucket}/{self.remote_src_bucket_key}"')
        logger.debug('-'*32)

        s3_env_vars = S3UnzipEnvVar(self.remote_src_bucket,
                                    self.remote_src_bucket_key,
                                    dest_dir=self.run_dir,
                                    app_dir=self.app_dir)

        try:
            self.build_env_vars = s3_env_vars.run()
        except Exception:
            self.build_env_vars = {}

        if self.app_dir:
            self.build_env_vars["APP_DIR"] = self.app_dir

        if self.stateful_id:
            self.build_env_vars["STATEFUL_ID"] = self.stateful_id

        # this variable is required since the remote_stateful_bucket
        # is used to download the source files originally
        # may want to refactor at some point
        if self.remote_stateful_bucket:
            self.build_env_vars["REMOTE_STATEFUL_BUCKET"] = self.remote_stateful_bucket
        elif self.remote_src_bucket:
            self.build_env_vars["REMOTE_STATEFUL_BUCKET"] = self.remote_src_bucket

        return self.build_env_vars

    def _add_env_var_path(self,newdir="/tmp"):
        """
        Add a new directory to the PATH environment variable.

        Args:
            newdir (str, optional): Directory to add to PATH. Defaults to "/tmp"
        """
        existing = os.environ.get('PATH', '')
        new_path = existing + os.pathsep + newdir
        os.environ['PATH'] = new_path

    def _set_init_cmd_env_vars(self):
        """
        Set initial command environment variables.

        Processes and sets environment variables specified in the commands object.
        """
        env_vars = self.cmds_obj.get("env_vars")

        if not env_vars:
            return

        for k,v in env_vars:
            try:
                os.environ[k] = v
            except Exception:
                logger.debug(f"could not set initial env_var {k}")

    def _init_env_vars(self,**event):
        """
        Initialize environment variables from base64 encoded event data.

        Args:
            **event: Event dictionary containing env_vars_b64 key with
                    base64 encoded environment variables
        """
        env_vars_b64 = event.get("env_vars_b64")

        if not env_vars_b64:
            return

        logger.debug("# _init_env_vars")

        for k,v in str_to_py_obj(env_vars_b64).items():
            logger.debug(f'# {k} -> {v}')
            os.environ[k] = v

    def run(self):
        """
        Execute the main Terraform operation workflow.

        Handles the complete execution process including:
        - Loading source files
        - Setting up environment
        - Executing prebuild, build, and postbuild commands
        - Managing S3 logging

        Returns:
            dict: Dictionary containing:
                - exitcode (int): Exit code of the operation
                - status (bool): Success status
                - message (str): Operation result message
        """
        self._load_zip_file_and_build_env_vars()
        os.chdir(self.tmpdir)

        try:
            build_expire_at = int(os.environ.get("BUILD_EXPIRE_AT"))  # default must be less than 900s
        except Exception:
            build_expire_at = int(time()) + 800

        shell_to_s3 = ShellOut(self.build_env_vars,
                               exec_dir=self.exec_dir,
                               build_expire_at=build_expire_at)

        status = True

        for phase in ["prebuild", "build", "postbuild"]:
            try:
                cmds = self.cmds_obj.get(phase)["cmds"]
            except Exception:
                cmds = None

            if not cmds:
                logger.debug(f"no cmds found for phase {phase}")
                continue

            logger.debug(f"cmds found for phase {phase}")
            results = shell_to_s3.exec_cmds(cmds)
            if results.get("status") is False:
                return results

        return {
            "exitcode":0,
            "status": status,
            "message":"running terraform completed"
        }
