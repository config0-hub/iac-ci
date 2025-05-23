#!/usr/bin/env python
# 
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
from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.boto3_common import Boto3Common


class LambdaBoto3(Boto3Common):
    """
    A class for interacting with AWS Lambda functions using boto3.
    Inherits from Boto3Common for AWS connectivity.

    This class provides functionality to invoke Lambda functions asynchronously.
    """

    def __init__(self, **kwargs):
        """
        Initialize LambdaBoto3 instance.

        Args:
            **kwargs: Arbitrary keyword arguments passed to parent class
        """
        self.classname = 'LambdaBoto3'
        self.logger = IaCLogger(self.classname)
        self.logger.debug(f"Instantiating {self.classname}")
        Boto3Common.__init__(self, 'lambda', **kwargs)

    def run(self, **kwargs):
        """
        Invoke a Lambda function asynchronously.

        Args:
            **kwargs: Must contain:
                name (str): Name or ARN of the Lambda function
                message (dict): Payload to send to the Lambda function

        Returns:
            dict: AWS Lambda invoke response object

        Note:
            The function is invoked with 'Event' invocation type, 
            meaning it's asynchronous and doesn't wait for the function to complete.
        """
        name = kwargs["name"]
        message = kwargs["message"]

        return self.client.invoke(
            FunctionName=name,
            InvocationType='Event',
            Payload=json.dumps(message)
        )