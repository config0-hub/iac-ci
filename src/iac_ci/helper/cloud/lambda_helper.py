#!/usr/bin/env python
"""
Module for handling AWS Lambda events and responses.
Provides utilities for processing Lambda event inputs and formatting responses.
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
import os


class LambdaHandler:
    """
    Handler class for AWS Lambda events.
    
    This class processes Lambda event inputs and provides utilities
    for handling both direct invocations and SNS triggered events.
    
    Attributes:
        sns_event (bool): Indicates if event is from SNS
        event (dict): Processed Lambda event
    """
    
    def __init__(self, event):
        """
        Initialize LambdaHandler with an event.
        
        Args:
            event (dict/str): Lambda event to process
        """
        self.sns_event = None

        try:
            self.event = json.loads(event)
        except (TypeError, ValueError):
            print("")
            print("event already a dictionary")
            self.event = event

    def get_init_msg(self):
        """
        Retrieve the initial message from the Lambda event.

        Handles both direct invocations and SNS-triggered events,
        extracting the core message based on the event structure.

        Returns:
            dict: Initial message extracted from the event
        """
        if "Records" in self.event:
            self.sns_event = True
            try:
                init_msg = json.loads(self.event['Records'][0]['Sns']['Message'])
            except (KeyError, ValueError, TypeError):
                init_msg = self.event
        else:
            init_msg = self.event

        if os.environ.get("DEBUG_IAC_CI"):
            print("")
            print(f"init_msg: {json.dumps(init_msg, indent=2)}")
            print("")

        return init_msg


def return_thru_lambda(sresults):
    """
    Format sresults for Lambda function return.
    
    Args:
        sresults (dict): Results to format for Lambda return
    
    Returns:
        dict: Formatted response with statusCode and body
    """
    if os.environ.get("DEBUG_IAC_CI"):
        print("*" * 32)
        print(json.dumps(sresults, indent=4))
        print("*" * 32)

    results = {
        'statusCode': 200,
        'continue': sresults["continue"],
        'body': json.dumps(sresults)
    }

    if sresults.get("failure_s3_key"):
        results["failure_s3_key"] = sresults["failure_s3_key"]

    return results