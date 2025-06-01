#!/usr/bin/env python

import os
import subprocess
import random
import string
from time import time
import boto3
from iac_ci.utilities import append_to_log

class ShellOutToS3:
    """
    Execute shell commands and log their output to both local files and S3.

    Attributes:
        env_vars (dict): Environment variables for command execution
        bucket_name (str): S3 bucket name for log storage
        bucket_key (str): S3 key for log file
        exec_dir (str): Directory for command execution
        build_expire_at (int): Timestamp when build should expire
        log_file_path (str): Path to local log file
    """

    def __init__(self, env_vars, bucket_name, bucket_key, exec_dir=None, build_expire_at=None):
        """
        Initialize ShellOutToS3 instance.

        Args:
            env_vars (dict): Environment variables
            bucket_name (str): S3 bucket name
            bucket_key (str): S3 key for log file
            exec_dir (str, optional): Execution directory
            build_expire_at (int, optional): Build expiration timestamp
        """
        self.env_vars = env_vars
        self.bucket_name = bucket_name
        self.bucket_key = bucket_key
        self.exec_dir = exec_dir

        self.init_time = int(time())

        # max time per command
        try:
            self.build_expire_at = int(build_expire_at)
            self.build_timeout = self.build_expire_at - self.init_time
        except Exception:
            self.build_timeout = 800
            self.build_expire_at = int(time()) + self.build_timeout

        print(f"build_expire_at {build_expire_at} in {build_expire_at-int(time())} secs")

        if not os.path.isdir("/tmp/log"):
            os.mkdir("/tmp/log")

        self._random_log = None
        self.epoch_time = str(int(time()))

        if os.environ.get('STATEFUL_ID'):
            self.log_file_path = f'/tmp/log/{os.environ["STATEFUL_ID"]}.log'
        elif 'stateful_id' in self.env_vars:
            self.log_file_path = f"/tmp/log/{self.env_vars['stateful_id']}.log"
        elif 'STATEFUL_ID' in self.env_vars:
            self.log_file_path = f"/tmp/log/{self.env_vars['STATEFUL_ID']}.log"
        else:
            random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
            self.log_file_path = f"/tmp/log/{random_suffix}.log"
            self._random_log = True

        self.s3_client = boto3.client('s3')
        self._get_existing_log()

    def _execute_and_log(self, command, env=None, heartbeat_interval=None, to_s3_int=10):
        """
        Execute a command and log output to file.

        Args:
            command (str): Command to execute
            env (dict, optional): Environment variables
            heartbeat_interval (int, optional): Interval for heartbeat checks
            to_s3_int (int, optional): Interval for S3 uploads

        Returns:
            int: Process return code
        """
        log_dir = os.path.dirname(self.log_file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        # Start the subprocess
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Redirect stderr to stdout
            text=True,
            shell=True,  # Use shell=True to allow command as a string
            env=env,
            bufsize=1  # Line buffered
        )

        last_output_time = int(time())
        last_upload_to_s3 = int(time())

        # Add a debug message to confirm redirection is set up
        append_to_log(self.log_file_path, "Starting process with stderr redirected to stdout")

        try:
            # First, force an error output for testing
            if os.environ.get("DEBUG_LAMBDA"):
                append_to_log(self.log_file_path, "Generating test error output")
                process.stdin.write("this will cause an error\n") if hasattr(process, 'stdin') and process.stdin else None

            # Read output using a more robust approach
            for line in iter(process.stdout.readline, ''):
                if line:
                    print(f'Output: {line.rstrip()}')
                    last_output_time = int(time())  # Update last output time
                    append_to_log(self.log_file_path, line.rstrip())

                    time_elapse = int(time()) - last_upload_to_s3
                    if time_elapse > to_s3_int:
                        self._upload_log_to_s3(include_time=None)
                        last_upload_to_s3 = int(time())

                # Check for timeout if specified
                if int(time()) > self.build_expire_at:
                    append_to_log(self.log_file_path, "Lambda Process Timed Out!")
                    self._upload_log_to_s3(include_time=None)
                    process.terminate()
                    break

                # Check for heartbeat timeout
                if heartbeat_interval and int(time()) - last_output_time > heartbeat_interval:
                    msg = "No output received for a while, process may be stalled!"
                    append_to_log(self.log_file_path, msg)
                    self._upload_log_to_s3(include_time=None)
                    process.terminate()
                    break

                # Check if process has finished
                if process.poll() is not None:
                    self._upload_log_to_s3(include_time=None)
                    break

        except KeyboardInterrupt:
            process.terminate()  # Terminate on keyboard interrupt
            self._upload_log_to_s3(include_time=None)
        finally:
            if os.environ.get("DEBUG_LAMBDA"):
               msg = "process waiting to close"
               append_to_log(self.log_file_path, msg)

            self._upload_log_to_s3(include_time=None)

            # Make sure to get any remaining output
            remaining_output = process.stdout.read()
            if remaining_output:
                append_to_log(self.log_file_path, remaining_output)

            process.stdout.close()
            process.wait()  # Wait for the process to complete

            if os.environ.get("DEBUG_LAMBDA"):
                msg = "process fully closed"
                append_to_log(self.log_file_path, msg)
            self._upload_log_to_s3(include_time=None)

        return process.returncode  # Get the exit code

    def _print_log(self):
        """Print the contents of the log file."""
        with open(self.log_file_path, 'r') as log_file:
            print(log_file.read())

    def _get_existing_log(self):
        """Retrieve existing log file from S3 if it exists."""
        epoch_time = str(int(time()))
        try:
            self.s3_client.download_file(self.bucket_name,
                                         self.bucket_key,
                                         self.log_file_path)
            msg = f"{epoch_time}: Log file existing found @ s3://{self.bucket_name}/{self.bucket_key}"
        except Exception:
            msg = f"{epoch_time}: Log file not found @ s3://{self.bucket_name}/{self.bucket_key}"
        append_to_log(self.log_file_path, msg)

    def _upload_log_to_s3(self,include_time=None):
        """Upload log file to S3."""
        epoch_time = str(int(time()))
        time_elapse = int(epoch_time) - self.init_time
        msg = f'# Lambda times # time_elapse: {str(time_elapse)} init_time: {str(self.init_time)} current_time: {str(epoch_time)} build_timeout: {str(self.build_timeout)}'
        if os.environ.get("DEBUG_IAC_CI"):
            print(f'DEBUG: {msg}')
        if include_time:
            append_to_log(self.log_file_path, msg)
        try:
            self.s3_client.upload_file(self.log_file_path,
                                       self.bucket_name,
                                       self.bucket_key)
            msg = f"{epoch_time}: Log file uploaded to s3://{self.bucket_name}/{self.bucket_key}"
        except Exception as e:
            msg = f"{epoch_time}: Log file failed to upload log file to S3: {e}"
        if os.environ.get("DEBUG_IAC_CI"):
            print(msg)
    def exec_cmds(self, commands, heartbeat_interval=60, debug=None):
        """
        Execute a list of commands.

        Args:
            commands (list): List of commands to execute
            heartbeat_interval (int, optional): Interval for heartbeat checks
            debug (bool, optional): Enable debug logging

        Returns:
            dict: Execution results
        """
        status = True
        exitcode = None
        failed_message = None

        for key in self.env_vars:
            _log = f'env_vars: add env var key "{key}" to execute commands'
            if os.environ.get("DEBUG_IAC_CI"):
                print(_log)
            append_to_log(self.log_file_path, _log)

        env = os.environ.copy()
        env.update(self.env_vars)

        for command_item in commands:
            name = None
            if isinstance(command_item, str):
                # Execute the command string
                command = command_item
            elif isinstance(command_item, dict) and len(command_item) == 1:
                # Extract the title and comment
                name, command = next(iter(command_item.items()))

            if name:
                _msg = f"// executing action: {name} //" + '\n'
            else:
                _msg = f"// executing: {command} //" + '\n'

            if debug:
                append_to_log(self.log_file_path, _msg)
            else:
                print(_msg,end='')

            try:
                exitcode = self._execute_and_log(command,
                                                 env,
                                                 heartbeat_interval)

                if exitcode != 0:
                    if name:
                        failed_message = "#"*32 + f"\n# FAILED\n action: {name}\n command: {command}\n\nexit code: {exitcode}.\n" + "#"*32
                    else:
                        failed_message = "#" * 32 + f"\n# FAILED\n command: {command}\n\nexit code: {exitcode}.\n" + "#" * 32

                    append_to_log(self.log_file_path, failed_message)
                    status = False
                    break

            except Exception as e:
                failed_message = f'An error occurred while executing the commands: {e}'
                append_to_log(self.log_file_path, failed_message)
                status = False
            finally:
                if os.environ.get('IAC_CI_PRINT_LOG'):
                    self._print_log()
                self._upload_log_to_s3(include_time=None)
                # we only remove random log files, otherwise, we just append
                if os.path.exists(self.log_file_path) and self._random_log:
                    os.remove(self.log_file_path)

        return {
            "status":status,
            "exitcode":exitcode,
            "failed_message":failed_message
        }

