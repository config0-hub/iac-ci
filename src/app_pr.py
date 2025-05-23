#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
AWS Lambda handler for Git PR processing.

This module provides the AWS Lambda entry point for processing Git Pull Requests
through the GitPr class from the main_pr module.
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

from iac_ci.helper.cloud.lambda_helper import LambdaHandler, return_thru_lambda
from main_pr import GitPr as Main


def handler(event, context):

    lambda_handler = LambdaHandler(event)
    message = lambda_handler.get_init_msg()

    main = Main(**message)
    results = main.run()

    return return_thru_lambda(results)