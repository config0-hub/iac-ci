#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Terraform CLI command module.
This module processes CLI arguments and executes Terraform operations using TF_Lambda.
"""

import os
import boto3
import json
import sys
import base64
import traceback
from time import time
from iac_ci.tf import TF_Lambda
from iac_ci.loggerly import DirectPrintLogger

# Initialize logger
logger = DirectPrintLogger(f'{os.environ["EXECUTION_ID"]}')

# Global response path
RESPONSE_PATH = os.environ.get('TF_RESPONSE_PATH')


def write_response_to_file(response):
    """
    Helper function to write a response to the designated file.

    Args:
        response (dict): Response object to write to file.
    """
    if RESPONSE_PATH:
        with open(RESPONSE_PATH, 'w') as f:
            json.dump(response, f)
        logger.debug(f"Response written to {RESPONSE_PATH}")

def run_terraform(config):
    """
    Core function to execute Terraform operations.

    This function initializes a TF_Lambda instance with the provided configuration,
    executes the Terraform operations, and returns the results.

    Args:
        config (dict): Configuration parameters for Terraform operations
                       Such as terraform_vars, workspace, etc.

    Returns:
        dict: Response object containing:
            - statusCode (int): HTTP status code (200 for success)
            - body (str): JSON-encoded string containing operation results

    Example:
        Config structure:
        {
            "terraform_vars": {...},
            "workspace": "dev",
            ...
        }
    """

    # Initialize TF_Lambda with configuration parameters and run operations
    tf_lambda = TF_Lambda(**config)
    tf_lambda.load_build_env_vars()

    try:
        build_expire_at = int(time()) + int(tf_lambda.build_env_vars.get("BUILD_TIMEOUT"))
    except:
        logger.debug("using default build expire at with 800s timeout")
        build_expire_at = int(time()) + 800

    output_bucket = os.environ["OUTPUT_BUCKET"]
    execution_id = os.environ["EXECUTION_ID"]
    s3_client = boto3.client('s3')
    bucket_key = f"executions/{execution_id}/expire_at"

    s3_client.put_object(
        Bucket=output_bucket,
        Key=bucket_key,
        Body=str(build_expire_at))

    results = tf_lambda.run(build_expire_at)

    results["tf_status"] = str(results["status"])
    results["tf_exitcode"] = str(results["exitcode"])

    for _delete_key in ["status", "exitcode"]:
        del results[_delete_key]

    # Format response
    response = {
        'statusCode': 200,
        'body': json.dumps(results)
    }

    # Print execution summary
    logger.debug("-" * 32)
    logger.debug(f'- Terraform operation completed with status: {results.get("status")} ')
    logger.debug("-" * 32)

    # Write response to the designated file
    write_response_to_file(response)

    return response

def cli_main():
    """
    CLI entry point.
    Expects a base64-encoded JSON configuration as the first argument.
    """
    try:
        # Check if we have the base64 argument
        if len(sys.argv) < 2:
            logger.debug("Error: Missing base64 configuration argument")
            logger.debug("Usage: python main_tf.py <base64_encoded_config>")
            sys.exit(1)

        # Get the base64-encoded config from command line
        base64_string = sys.argv[1]

        # Decode the base64 string to JSON string
        json_str = base64.b64decode(base64_string).decode()

        # Parse the JSON string to get the configuration object
        config = json.loads(json_str)

        # Call the terraform execution function
        result = run_terraform(config)

        # Return appropriate exit code based on status
        if result.get('statusCode', 500) >= 400:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        # Print the error and traceback
        error_msg = {
            "statusCode": 500,
            "body": json.dumps({
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc()
            })
        }

        # Write error response to the designated file
        write_response_to_file(error_msg)

        logger.debug(json.dumps(error_msg, default=str))
        sys.exit(1)


# When script is run directly, use the CLI main function
if __name__ == "__main__":
    cli_main()