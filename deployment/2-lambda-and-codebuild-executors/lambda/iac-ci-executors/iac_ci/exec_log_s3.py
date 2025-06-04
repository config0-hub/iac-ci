#!/usr/bin/env python

import os
import subprocess
from time import time

class ShellOut:
    """
    Execute shell commands and log their output to both local files and S3.

    Attributes:
        env_vars (dict): Environment variables for command execution
        exec_dir (str): Directory for command execution
        build_expire_at (int): Timestamp when build should expire
    """

    def __init__(self, env_vars, exec_dir=None, build_expire_at=None):
        """
        Initialize ShellOut instance.

        Args:
            env_vars (dict): Environment variables
            exec_dir (str, optional): Execution directory
            build_expire_at (int, optional): Build expiration timestamp
        """
        self.env_vars = env_vars
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

        self.epoch_time = str(int(time()))

    def _exec_cmd(self, command, env=None, heartbeat_interval=None, to_s3_int=10):
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
        print("Starting process with stderr redirected to stdout")

        try:
            # First, force an error output for testing
            if os.environ.get("DEBUG_LAMBDA"):
                print("Generating test error output")
                process.stdin.write("this will cause an error\n") if hasattr(process, 'stdin') and process.stdin else None

            # Read output using a more robust approach
            for line in iter(process.stdout.readline, ''):
                if line:
                    last_output_time = int(time())  # Update last output time
                    print(line.rstrip())

                # Check for timeout if specified
                if int(time()) > self.build_expire_at:
                    print("Lambda Process Timed Out!")
                    process.terminate()
                    break

                # Check for heartbeat timeout
                if heartbeat_interval and int(time()) - last_output_time > heartbeat_interval:
                    msg = "No output received for a while, process may be stalled!"
                    print(msg)
                    process.terminate()
                    break

                # Check if process has finished
                if process.poll() is not None:
                    break

        except KeyboardInterrupt:
            process.terminate()  # Terminate on keyboard interrupt
        finally:
            if os.environ.get("DEBUG_LAMBDA"):
               msg = "process waiting to close"
               print(msg)

            # Make sure to get any remaining output
            remaining_output = process.stdout.read()
            if remaining_output:
                print(remaining_output)

            process.stdout.close()
            process.wait()  # Wait for the process to complete

            if os.environ.get("DEBUG_LAMBDA"):
                msg = "process fully closed"
                print(msg)

        return process.returncode  # Get the exit code

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
                print(_msg)
            else:
                print(_msg,end='')

            try:
                exitcode = self._exec_cmd(command,
                                          env,
                                          heartbeat_interval)

                if exitcode != 0:
                    if name:
                        failed_message = "#"*32 + f"\n# FAILED\n action: {name}\n command: {command}\n\nexit code: {exitcode}.\n" + "#"*32
                    else:
                        failed_message = "#" * 32 + f"\n# FAILED\n command: {command}\n\nexit code: {exitcode}.\n" + "#" * 32

                    print(failed_message)
                    status = False
                    break

            except Exception as e:
                failed_message = f'An error occurred while executing the commands: {e}'
                print(failed_message)
                status = False

        return {
            "status":status,
            "exitcode":exitcode,
            "failed_message":failed_message
        }

