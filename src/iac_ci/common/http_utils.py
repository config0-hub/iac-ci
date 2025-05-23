#!/usr/bin/env python
"""
HTTP Request Utilities

A collection of utilities for making HTTP requests, evaluating responses,
and handling errors in a standardized way.

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

from time import sleep
import json
import requests


def eval_insert_failed(call_type, r, name, api_endpoint, data=None):
    """
    Evaluates the result of an API call and constructs an error message if it failed.

    Parameters:
    call_type (str): The type of API call (e.g., 'POST').
    r (requests.Response): The response object from the API call.
    name (str): The name of the API call.
    api_endpoint (str): The endpoint of the API call.
    data (optional): The data payload sent with the request.

    Returns:
    dict: A dictionary containing the evaluation results and any error messages.
    """
    desc = f"making {call_type} request {name}"
    eval_results = eval_request_results(name=name, req=r, description=desc)

    if eval_results["success"]:
        return eval_results

    # Insert failed_message
    eval_results["failed_message"] = f"{desc} failed at {api_endpoint}"

    if not data:
        return eval_results

    try:
        eval_results["failed_message"] = f'{eval_results["failed_message"]}\n{data}'
    except (TypeError, ValueError):
        eval_results["failed_message"] = f'{eval_results["failed_message"]}\ndata payload contains binary'

    return eval_results


def eval_request_results(**kwargs):
    """
    Evaluates the result of an API request and returns a summary.

    Parameters:
    **kwargs: Contains 'req' (requests.Response), 'name' (str), and 'description' (str).

    Returns:
    dict: A dictionary summarizing the request result, including status code and success flag.
    """
    req = kwargs["req"]
    name = kwargs["name"]
    description = kwargs["description"]

    success = True
    internal_error = None

    status_code = int(req.status_code)

    # Status code between 400 and 500 are failures.
    if 399 < status_code < 600:
        success = False

    if 500 < status_code < 600:
        internal_error = True

    results = {"status_code": status_code, "success": success, "api": {}}

    if name:
        results["name"] = name

    if description:
        results["description"] = description

    if internal_error:
        results["internal_error"] = True

    try:
        _json = dict(req.json())
        results["api"]["response"] = _json
    except (ValueError, TypeError, json.JSONDecodeError):
        try:
            results["api"]["response"] = req.json()
        except (ValueError, TypeError, json.JSONDecodeError):
            results["api"]["response"] = None

    return results


def execute_http_post(**kwargs):
    """
    Executes an HTTP POST request and handles retries in case of failure.

    Parameters:
    **kwargs: Contains 'name' (str), 'headers' (dict), 'api_endpoint' (str),
              'data' (optional), 'verify' (bool), 'timeout' (int),
              'retries' (int), and 'sleep_int' (int).

    Returns:
    dict: A dictionary with the results of the POST request.
    """
    name = kwargs["name"]
    headers = kwargs["headers"]
    api_endpoint = kwargs["api_endpoint"]
    data = kwargs.get("data")
    verify = kwargs.get("verify")

    timeout = int(kwargs.get("timeout", 120))
    retries = int(kwargs.get("retries", 1))
    sleep_int = int(kwargs.get("sleep_int", 2))

    inputargs = {"headers": headers, "timeout": timeout}

    if verify:
        inputargs["verify"] = True
    else:
        inputargs["verify"] = False

    if data:
        if isinstance(data, dict):
            data = json.dumps(data)
        inputargs["data"] = data

    for retry in range(retries):
        print(f"execute http post api_endpoint {api_endpoint} retry {retry}")

        r = requests.post(api_endpoint, **inputargs)

        results = eval_insert_failed('POST',
                                    r,
                                    name,
                                    api_endpoint,
                                    data=data)

        if not results.get("internal_error"):
            break

        if results["success"]:
            break

        sleep(sleep_int)

    return results