#!/usr/bin/env python
"""
Lambda handler for processing webhooks in an Infrastructure as Code CI/CD pipeline.
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
import os
from copy import deepcopy

from main_webhook import WebhookProcess as Main
from iac_ci.common.loggerly import IaCLogger


def handler(event, context):

    classname = 'handler'
    logger = IaCLogger(classname)

    if not event["httpMethod"] == "POST":
        return {
            "statusCode": 405,
            "body": json.dumps(f"Invalid HTTP Method {event['httpMethod']} supplied")
        }

    body = event.get('body', '')
    
    if body and not isinstance(body, dict):
        try:
            event_body = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error(e)
            raise e
    elif body and isinstance(body, dict):
        event_body = body
    else:
        return {
            "statusCode": 400,
            "body": json.dumps("No json event_body provided...")
        }

    if os.environ.get("DEBUG_IAC_CI"):
        copy_event = deepcopy(event)
        copy_event["body"] = event_body
        logger.debug(f"\n{json.dumps(copy_event, indent=4)}\n")

    main = Main(event=event,
                event_body=event_body)

    results = main.run()

    return {
        'statusCode': 200,
        'continue': results["continue"],
        'apply': results.get("apply"),
        'destroy': results.get("destroy"),
        'check': results.get("check"),
        'body': json.dumps(results)
    }