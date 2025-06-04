#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Terraform CLI command module.
This module processes CLI arguments and executes Terraform operations using TF_Lambda.
"""

import os
import json
import sys
import base64
import traceback
from iac_ci.tf import TF_Lambda


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
    try:
        # Initialize TF_Lambda with configuration parameters and run operations
        tf_lambda = TF_Lambda(**config)
        results = tf_lambda.run()

        results["output_bucket"] = os.environ["OUTPUT_BUCKET"]
        results["output_bucket_key"] = os.environ["OUTPUT_BUCKET_KEY"]

        # Format response
        response = {
            'statusCode': 200,
            'body': json.dumps(results),
        }

        # Print execution summary
        print("-" * 32)
        print(f'- Terraform operation completed with status: {results.get("status")} ')
        print("-" * 32)

        # Write response to the designated file if environment variable is set
        response_path = os.environ.get('TF_RESPONSE_PATH')
        if response_path:
            try:
                with open(response_path, 'w') as f:
                    json.dump(response, f)
                print(f"Response written to {response_path}")
            except Exception as e:
                print(f"Error writing response to {response_path}: {str(e)}")

        return response
    
    except Exception as e:
        # Handle exceptions
        error_response = {
            "output_bucket": os.environ["OUTPUT_BUCKET"],
            "output_bucket_key": os.environ["OUTPUT_BUCKET_KEY"],
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'error': str(e),
                'traceback': traceback.format_exc()
            })
        }
        
        # Print error summary
        print("-" * 32)
        print(f'- Terraform operation failed: {str(e)}')
        print("-" * 32)
        
        # Write error response to the designated file if environment variable is set
        response_path = os.environ.get('TF_RESPONSE_PATH')
        if response_path:
            try:
                with open(response_path, 'w') as f:
                    json.dump(error_response, f)
                print(f"Error response written to {response_path}")
            except Exception as write_err:
                print(f"Error writing response to {response_path}: {str(write_err)}")
        
        return error_response


def cli_main():
    """
    CLI entry point.
    Expects a base64-encoded JSON configuration as the first argument.
    """
    try:
        # Check if we have the base64 argument
        if len(sys.argv) < 2:
            print("Error: Missing base64 configuration argument")
            print("Usage: python main_tf.py <base64_encoded_config>")
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
        
        # Write error response to the designated file if environment variable is set
        response_path = os.environ.get('TF_RESPONSE_PATH')
        if response_path:
            try:
                with open(response_path, 'w') as f:
                    json.dump(error_msg, f)
                print(f"Error response written to {response_path}")
            except Exception as write_err:
                print(f"Error writing response to {response_path}: {str(write_err)}")
        
        print(json.dumps(error_msg, default=str))
        sys.exit(1)


# When script is run directly, use the CLI main function
if __name__ == "__main__":
    cli_main()