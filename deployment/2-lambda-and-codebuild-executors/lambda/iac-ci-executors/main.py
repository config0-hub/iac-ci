#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
AWS Lambda handler that executes main_tf.py as a CLI command with a base64-encoded configuration.
"""

import base64
import json
import subprocess
import sys
import shlex
import os
import traceback
from time import time
import boto3
import uuid
from iac_ci.loggerly import DirectPrintLogger

def handler(event, context):

    output_bucket = None
    execution_id = None

    try:
        # Convert the event to a base64 string
        event_json = json.dumps(event)

        if not os.environ.get("EXECUTION_ID"):
            execution_id = event.get("execution_id")
            if not execution_id:
                execution_id = uuid.uuid4().hex
            else:
                print(f"using the provided in event execution id: {execution_id}")
            os.environ["EXECUTION_ID"] = execution_id
        else:
            print(f'using the provided in env var execution id: {os.environ["EXECUTION_ID"]}')

        execution_id = os.environ["EXECUTION_ID"]
        logger = DirectPrintLogger(f'{execution_id}')

        # Get output bucket information - critical for storing results
        try:
            output_bucket = event["output_bucket"]
        except:
            output_bucket = None

        if not output_bucket:
            logger.debug('WARNING: No output bucket specified. Results will not be saved to S3.')

        # Initialize S3 client
        s3_client = boto3.client('s3')
        s3_client.put_object(Bucket=output_bucket, Key=f"executions/{execution_id}/initiated", Body=str(time.time()))

        event_base64 = base64.b64encode(event_json.encode()).decode()
        
        # Sanitize the input to prevent command injection
        safe_base64 = shlex.quote(event_base64)
        
        # Path to the main_tf.py script
        lambda_task_root = os.environ.get('LAMBDA_TASK_ROOT', '/var/task')
        script_path = os.path.join(lambda_task_root, "main_tf.py")
        
        # Create unique file paths for this execution
        timestamp = int(time())
        request_id = context.aws_request_id if context else 'local'
        output_path = f"/tmp/tf_output_{timestamp}_{request_id}.txt"
        response_path = f"/tmp/tf_response_{timestamp}_{request_id}.json"

        # Get the current Python path
        current_path = os.environ.get('PYTHONPATH', '')
        
        # Set up environment with enhanced PYTHONPATH and response path
        env = os.environ.copy()
        if current_path:
            env['PYTHONPATH'] = f"{lambda_task_root}:{current_path}"
        else:
            env['PYTHONPATH'] = lambda_task_root
        
        # Pass the response path to main_tf.py
        env['TF_RESPONSE_PATH'] = response_path
            
        logger.debug(f"Setting PYTHONPATH: {env['PYTHONPATH']}")
        logger.debug(f"Setting TF_RESPONSE_PATH: {env['TF_RESPONSE_PATH']}")
        logger.debug(f"Lambda task root: {lambda_task_root}")
        
        # Build the command with shell redirection to capture stdout and stderr
        logger.debug(f"Executing main_tf.py with Python {sys.executable}")
        command = f"cd {lambda_task_root} && {sys.executable} {script_path} {safe_base64} > {output_path} 2>&1"

        # Run the command with shell=True to enable redirection and the modified environment
        process = subprocess.run(
            command,
            shell=True,
            env=env,
            check=False  # Don't raise exception on non-zero exit
        )
        
        # Get the return code
        return_code = process.returncode

        # if 0, this does not mean the actual main_tf execution succeeded
        logger.debug(f"main_tf cli execution exit code: {return_code}")
        
        # Initialize response data
        response_data = {}
        
        # Try to read the JSON response if it exists
        if os.path.exists(response_path):
            with open(response_path, 'r') as f:
                response_data = json.load(f)
            logger.debug(f"Successfully read response data from {response_path}")
            # Clean up the response file
            os.remove(response_path)
        else:
            logger.debug(f"Response file {response_path} was not created")
        
        # Read the combined output from the output file
        combined_output = ""
        if os.path.exists(output_path):
            with open(output_path, 'r') as f:
                combined_output = f.read()
            
            # Print the complete output to the logs
            logger.debug("==================== EXECUTION OUTPUT ====================")
            logger.debug(combined_output)
            logger.debug("==================================================================")
        else:
            combined_output = f"ERROR: Output file {output_path} was not created"
            logger.debug(combined_output)
        
        # Prepare result data that will be saved to S3
        result_data = {}
        if response_data and 'body' in response_data:
            if isinstance(response_data['body'], str):
                body_dict = json.loads(response_data['body'])
            else:
                body_dict = response_data['body']

            # Transfer all body information to result data
            result_data.update(body_dict)

        # Add execution information to result data
        result_data['execution_id'] = execution_id
        result_data['return_code'] = return_code
        result_data['status'] = 'success' if return_code == 0 else 'error'
        result_data['function_name'] = context.function_name if context else 'unknown'
        result_data['execution_time'] = f"{context.get_remaining_time_in_millis()/1000:.2f} seconds" if context else "unknown"
        result_data['logs'] = combined_output
        
        # Upload the result data to the path aws_executor.py expects
        if output_bucket:
            result_key = f"executions/{execution_id}/result.json"

            s3_client.put_object(
                Bucket=output_bucket,
                Key=result_key,
                Body=json.dumps(result_data),
                ContentType='application/json'
            )

            logger.debug(f"Successfully uploaded result to S3: s3://{output_bucket}/{result_key}")
            result_data['result_url'] = f"s3://{output_bucket}/{result_key}"

        # Now clean up the output file
        if os.path.exists(output_path):
            os.remove(output_path)
            
        # If we have response data, return it; otherwise, build a response based on the result_data
        if response_data:
            # Add our tracking information to the response
            if 'body' in response_data:
                if isinstance(response_data['body'], str):
                    body_dict = json.loads(response_data['body'])
                else:
                    body_dict = response_data['body']

                # Add tracking URLs
                if output_bucket:
                    body_dict['initiated_url'] = f"s3://{output_bucket}/executions/{execution_id}/initiated"
                    body_dict['result_url'] = f"s3://{output_bucket}/executions/{execution_id}/result.json"
                    body_dict['done_url'] = f"s3://{output_bucket}/executions/{execution_id}/done"

                # Add function info and execution time
                body_dict['function_name'] = context.function_name if context else 'unknown'
                body_dict['execution_time'] = f"{context.get_remaining_time_in_millis()/1000:.2f} seconds" if context else "unknown"

                # Update the response body
                response_data['body'] = json.dumps(body_dict)

            fresults = response_data
        else:
            # Create a response based on the result data
            fresults = {
                'statusCode': 200 if return_code == 0 else 400,
                'body': json.dumps(result_data)
            }
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        logger = DirectPrintLogger('error')
        logger.debug(f"Error executing main_tf operation: {str(e)}")
        logger.debug(error_traceback)
        
        fresults = {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'error': str(e),
                'traceback': error_traceback
            })
        }
    
    # Create done marker to indicate completion - with success/failure info
    if output_bucket:
        s3_client.put_object(Bucket=output_bucket, Key=f"executions/{execution_id}/done", Body=str(time.time()))
        logger.debug(f"Lambda function complete with done marker in S3 bucket")

    return fresults