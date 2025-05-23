#!/usr/bin/env python
"""
File system utility functions for directory and file operations.
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

def mkdir(directory):
    """
    Create a directory and any necessary parent directories.
    
    Args:
        directory (str): Path to the directory to create.
        
    Returns:
        bool: True if the directory exists or was created successfully, False otherwise.
    """
    try:
        if not os.path.exists(directory):
            # Use os.makedirs instead of os.system for better portability and security
            os.makedirs(directory, exist_ok=True)
        return True
    except Exception as e:
        # Log the specific error for debugging
        print(f"Error creating directory {directory}: {e}")
        return False


def rm_rf(location):
    """
    Forcefully and recursively removes a file or directory using shell command 'rm -rf'.

    Args:
        location (str): Path of file or directory to remove.

    Returns:
        bool or None: 
            - True if removal was successful
            - False if removal failed
            - None if location is empty or doesn't exist

    Notes:
        First attempts to use os.remove(), falls back to shell 'rm -rf' command if that fails.
        Redirects stderr and stdout to /dev/null when using shell command.
    """
    if not location:
        return

    if not os.path.exists(location):
        return

    try:
        os.remove(location)
        status = True
    except OSError:
        status = False

    if status:
        return True

    if os.path.exists(location):
        try:
            os.system(f"rm -rf {location} > /dev/null 2>&1")
            status = True
        except OSError:
            print(f"Problems with removing {location}")
            status = False

        return status
    
    # If we reach here, location no longer exists (perhaps it was
    # removed by another process or partially removed by os.remove())
    return True


def system_exec(command, raise_on_error=True):
    """
    Executes a shell command and handles the return status.

    Args:
        command (str): Shell command to execute.
        raise_on_error (bool, optional): If True, raises RuntimeError on non-zero exit code.
                                       Defaults to True.

    Returns:
        dict: Dictionary containing:
            - status (bool): True if exitcode is 0, False otherwise
            - exitcode (int): The command's exit code

    Raises:
        RuntimeError: If command returns non-zero exit code and raise_on_error is True.

    Notes:
        Extracts exit code from system call return value using binary manipulation.
    """
    _return = os.system(command)

    # Calculate the return value code
    exitcode = int(bin(_return).replace("0b", "").rjust(16, "0")[:8], 2)

    if exitcode != 0 and raise_on_error:
        failed_msg = f"The system command\n{command}\nexited with return code {exitcode}"
        raise RuntimeError(failed_msg)

    results = {"status": True}

    if exitcode != 0:
        results = {"status": False}

    results["exitcode"] = exitcode

    return results