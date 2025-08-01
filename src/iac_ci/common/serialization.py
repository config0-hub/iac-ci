#!/usr/bin/env python
"""
Base64 encoding and decoding utilities.

This module provides functions for encoding objects to base64 and decoding base64 strings.
"""

# Copyright (C) 2025 Gary Leong <gary@config0.com>
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

import json
import base64
from typing import Any, Dict, Union

def b64_encode(obj: Any) -> str:
    """
    Encode an object or string to base64.

    Args:
        obj: Input object to encode. Can be a dictionary or any object that can be JSON serialized,
             or a string.

    Returns:
        str: ASCII-encoded base64 string.

    Notes:
        - If input is a dictionary, it is first converted to JSON string
        - For non-string/dict inputs, attempts JSON serialization
        - Converts input to ASCII bytes before base64 encoding
    """
    if isinstance(obj, dict):
        obj = json.dumps(obj)
    elif not isinstance(obj, str):
        try:
            obj = json.dumps(obj)
        except OverflowError as e:
            print(f"Warning: could not JSON serialize object for b64: {e}")

    input_bytes = obj.encode('ascii')
    base64_bytes = base64.b64encode(input_bytes)

    # decode the b64 binary into a b64 string
    return base64_bytes.decode('ascii')


def b64_decode(token: str) -> Union[Dict, str]:
    """
    Decode a base64 string back to its original form.

    Args:
        token (str): Base64 encoded string to decode.

    Returns:
        Union[Dict, str]: Decoded data, either as:
            - JSON-parsed dictionary/object if valid JSON
            - ASCII string if decodable as ASCII
            - UTF-8 string as fallback

    Notes:
        - Attempts multiple decode strategies in order:
            1. JSON decode from ASCII
            2. Plain ASCII decode
            3. Default string decode
            4. UTF-8 decode as final fallback
    """
    base64_bytes = token.encode('ascii')
    decoded_bytes = base64.b64decode(base64_bytes)

    # Try to decode as JSON
    try:
        return json.loads(decoded_bytes.decode('ascii'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass

    # Try to decode as ASCII
    try:
        return decoded_bytes.decode('ascii')
    except UnicodeDecodeError:
        pass

    # Try default decoding
    try:
        return decoded_bytes.decode()
    except UnicodeDecodeError:
        pass

    # Final fallback to UTF-8
    return decoded_bytes.decode("utf-8")