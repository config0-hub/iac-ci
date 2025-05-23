#!/usr/bin/env python
"""
Utility module providing common helper functions for data type conversion,
hash generation, and ID generation. This module includes functions for
string splitting, JSON conversion, MD5 hash calculation, and random string
generation.

Copyright (C) 2025 Gary Leong <gary@config0.com>
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import string
import random
import json
import os
import hashlib
from string import ascii_lowercase
from iac_ci.common.loggerly import IaCLogger


def find_filename(dir, file_name):
    """
    Finds all instances of a filename within a directory, recursively.

    This function searches for a given filename within a specified directory and
    all its subdirectories. It returns a list of full paths for each matching file.

    Args:
        dir (str): The directory to search within.
        file_name (str): The name of the file to search for.

    Returns:
        list: A list of full paths to the matching files.
    """
    matches = []
    for root, dirs, files in os.walk(dir):
        if file_name in files:
            matches.append(os.path.join(root, file_name))
    return matches


def to_list(_object, split_char=None, raise_on_error=None):
    """
    Converts a string into a list by splitting on specified character.
    
    Args:
        _object (str): String to be split into a list
        split_char (str, optional): Character to split on. Defaults to space if None
        raise_on_error (bool, optional): Whether to raise errors
    
    Returns:
        list: List of strings after splitting and stripping whitespace
    """
    return (
        [entry.strip() for entry in _object.split(split_char)]
        if split_char
        else [entry.strip() for entry in _object.split(" ")]
    )


def to_json(_object, raise_on_error=None):
    """
    Converts a string representation of a JSON object into a Python dict/list.
    
    Args:
        _object (str/dict/list): Object to convert to JSON
        raise_on_error (bool, optional): Whether to exit with code 13 on error
    
    Returns:
        dict/list/bool: Converted JSON object if successful,
                       original object if already correct type,
                       False if conversion fails and raise_on_error is False
    
    Raises:
        SystemExit: If conversion fails and raise_on_error is True
    """
    if isinstance(_object, dict):
        return _object

    if isinstance(_object, list):
        return _object

    try:
        _object = json.loads(_object)
        status = True
    except json.JSONDecodeError:
        # logger.debug("Cannot convert str to a json. Will try to eval")
        status = False

    if not status:
        try:
            _object = eval(_object)
        except (SyntaxError, NameError, TypeError):
            if raise_on_error:
                exit(13)
            return False

    return _object


def get_hash(data):
    """
    Calculates MD5 hash of input data using Python's hashlib or shell command.
    
    Args:
        data (str/bytes): Data to hash
    
    Returns:
        str/bool: MD5 hash string if successful, False if both methods fail
    
    Notes:
        Falls back to shell command if Python's hashlib fails
    """
    logger = IaCLogger("get_hash")

    try:
        calculated_hash = hashlib.md5(data).hexdigest()
    except ValueError:
        calculated_hash = None

    if not calculated_hash:
        logger.debug("Falling back to shellout md5sum for hash")
        try:
            cmd = os.popen(f'echo "{data}" | md5sum | cut -d " " -f 1', "r")
            calculated_hash = cmd.read().rstrip()
        except OSError:
            print(f"Failed to calculate the md5sum of a string {data}")
            calculated_hash = False

    if not calculated_hash:
        logger.error(f"Could not calculate hash for {data}")
        return False

    return calculated_hash


def id_generator2(size=6, lowercase=True):
    """
    Generates a random string of specified length.
    
    Args:
        size (int, optional): Length of string to generate. Defaults to 6
        lowercase (bool, optional): Whether to use lowercase letters only.
                                  If False, uses uppercase letters and digits
    
    Returns:
        str: Random string of specified length
    """
    if lowercase:
        chars = ascii_lowercase
    else:
        chars = string.ascii_uppercase + string.digits

    return ''.join(random.choice(chars) for _ in range(size))


def id_generator(size=18, chars=string.ascii_lowercase):
    """
    Generates a random string of specified size using the given characters.

    Parameters:
    size (int): The length of the random string. Default is 18.
    chars (str): The characters to use for generating the string. Default is lowercase letters.

    Returns:
    str: A randomly generated string.
    """
    return ''.join(random.choice(chars) for _ in range(size))


def rm_rf(location):
    """
    Uses the shell to forcefully and recursively remove a file or entire directory.

    Parameters:
    location (str): The file or directory path to remove.

    Returns:
    bool: True if the file or directory was successfully removed, False otherwise.
    """
    if not location:
        return False

    try:
        os.system(f"rm -rf {location} > /dev/null 2>&1")
        status = True
    except OSError:
        # If removal fails, set status to False
        status = False

    if status is False and os.path.exists(location):
        try:
            # If the file still exists, use shell command to forcefully remove it
            os.remove(location)
            return True
        except FileNotFoundError:
            print(f"problems with removing {location}")
            return False


def get_hash_from_string(_string):
    """
    Computes the MD5 hash of the given string.

    Parameters:
    _string (str): The input string to hash.

    Returns:
    str: The MD5 hash of the input string.
    """
    return hashlib.md5(_string.encode('utf-8')).hexdigest()