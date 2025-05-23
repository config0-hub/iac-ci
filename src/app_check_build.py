#!/usr/bin/env python
"""
AWS Lambda handler for processing build check events.

This module provides a Lambda handler that processes AWS CodeBuild events
and routes them to the appropriate build check logic.
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

import json
from iac_ci.helper.cloud.lambda_helper import LambdaHandler
from iac_ci.helper.cloud.lambda_helper import return_thru_lambda
from main_check_build import CheckBuild as Main


def handler(event, context):

    lambda_handler = LambdaHandler(event)

    if "body" in lambda_handler.event:
        try:
            message = json.loads(lambda_handler.event['body'])
        except json.JSONDecodeError:
            # Fallback to using the raw event if JSON parsing fails
            message = event
    else:
        _init_msg = lambda_handler.get_init_msg()
        if lambda_handler.sns_event:
            message = {
                "phase": "check_build",
                "build_status": _init_msg["detail"]["build-status"],
                "build_arn": _init_msg["detail"]["build-id"]
            }
            # Extract build ID from the ARN
            message["build_id"] = message["build_arn"].split("/")[-1]
        else:
            message = _init_msg

    main = Main(**message)
    results = main.run()

    return return_thru_lambda(results)