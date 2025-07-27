#!/usr/bin/env python

import uuid
import shlex
import os
import subprocess
from time import time
from iac_ci.loggerly import DirectPrintLogger

logger = DirectPrintLogger(f'{os.environ.get("EXECUTION_ID", "sync")}')

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

        logger.debug(f"build_expire_at {build_expire_at} in {build_expire_at-int(time())} secs")

        self.epoch_time = str(int(time()))
        
    def _exec_cmd(self, command, env=None):
        """
        Execute a command using subprocess.Popen and capture output and exit code.

        Args:
            command (str): Command to execute
            env (dict, optional): Environment variables, if None the current environment is used

        Returns:
            int: Process return code
        """
        # Generate random filename for this execution's output
        unique_id = uuid.uuid4().hex
        output_file = f"/tmp/cmd_output_{unique_id}.log"

        logger.debug(f"Starting command: {command}")

        # Execute command with output redirected to file
        with open(output_file, 'w') as output_redirect:
            process = subprocess.Popen(
                command,
                env=env,
                stdout=output_redirect,
                stderr=subprocess.STDOUT,
                shell=True,
                universal_newlines=True
            )
            exitcode = process.wait()

        # Read and log the output
        with open(output_file, 'r') as f:
            for line in f:
                logger.debug(line.rstrip())

        # Clean up temporary file
        if os.path.exists(output_file):
            os.remove(output_file)

        return exitcode

    def _exec_cmd2(self, command, env=None):
        """
        Execute a command using os.system and capture exit code from a file.
        Adds optional to each line of output when printing.

        Args:
            command (str): Command to execute
            env (dict, optional): Environment variables

        Returns:
            int: Process return code
        """
        # Generate random filenames for this execution
        unique_id = uuid.uuid4().hex
        output_file = f"/tmp/cmd_output_{unique_id}.log"
        exitcode_file = f"/tmp/cmd_exitcode_{unique_id}.txt"

        # Set environment variables properly if provided
        if env:
            # Save original environment
            old_env = os.environ.copy()
            # Update environment with new values
            os.environ.update(env)

        # Modify command to capture output and exit code
        # We don't need to set env vars in the command itself
        full_command = f"{command} > {output_file} 2>&1; echo $? > {exitcode_file}"

        logger.debug(f"Starting command: {command}")

        # Run the command
        os.system(full_command)

        # Restore original environment if we modified it
        if env:
            os.environ.clear()
            os.environ.update(old_env)

        # Read and print the output
        try:
            with open(output_file, 'r') as f:
                output_lines = f.readlines()
                if output_lines:
                    for line in output_lines:
                        logger.debug(f"{line.rstrip()}")
        except Exception as e:
            logger.debug(f"Error reading output file: {str(e)}")

        # Read the exit code
        exitcode = 1  # Default to error code
        try:
            with open(exitcode_file, 'r') as f:
                exitcode = int(f.read().strip())
        except Exception as e:
            logger.debug(f"Error reading exit code file: {str(e)}")

        # Clean up temporary files
        try:
            os.remove(output_file)
            os.remove(exitcode_file)
        except:
            pass  # Ignore cleanup errors

        return exitcode

    def exec_cmds(self, commands):
        """
        Execute a list of commands.

        Args:
            commands (list): List of commands to execute
            debug (bool, optional): Enable debug logging

        Returns:
            dict: Execution results
        """
        status = True
        exitcode = 0
        failed_message = None

        for key in self.env_vars:
            _log = f'env_vars: add env var key "{key}" to execute commands'
            if os.environ.get("DEBUG_IAC_CI"):
                logger.debug(_log)

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

            logger.debug(_msg)

            exitcode = self._exec_cmd(command,env)

            if exitcode not in [0, "0" ]:
                if name:
                    failed_message = "#"*32 + f"\n# FAILED\n action: {name}\n command: {command}\n\nexit code: {exitcode}.\n" + "#"*32
                else:
                    failed_message = "#" * 32 + f"\n# FAILED\n command: {command}\n\nexit code: {exitcode}.\n" + "#" * 32

                logger.debug(failed_message)
                status = False
                break

        results = {
            "status":status,
            "exitcode":exitcode
        }

        if failed_message:
            results["failed_message"] = failed_message

        return results