#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AWS Lambda handler module for Terraform operations.
This module processes incoming Lambda events and executes Terraform operations using TF_Lambda.
"""

import os
import json
from iac_ci.tf import TF_Lambda


def handler(event, context):
    """
    AWS Lambda handler function for processing Terraform operations.

    This function initializes a TF_Lambda instance with the provided event data,
    executes the Terraform operations, and returns the results in a formatted response.

    Args:
        event (dict): AWS Lambda event containing configuration and parameters
                     for Terraform operations
        context (LambdaContext): AWS Lambda context object containing runtime information

    Returns:
        dict: Response object containing:
            - statusCode (int): HTTP status code (200 for success)
            - body (str): JSON-encoded string containing operation results

    Example:
        Event structure:
        {
            "terraform_vars": {...},
            "workspace": "dev",
            ...
        }

        Response structure:
        {
            "statusCode": 200,
            "body": "{"status": "success", ...}"
        }
    """
    # Initialize TF_Lambda with event parameters and run operations
    tf_lambda = TF_Lambda(**event)
    results = tf_lambda.run()

    # Format response
    response = {
        'statusCode': 200,
        'body': json.dumps(results),
    }

    # Print execution summary
    print("-" * 32)
    print(f'- Finished with results {results.get("status")} ')
    print("-" * 32)

    return response
