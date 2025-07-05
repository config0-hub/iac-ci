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
import time
import boto3
import glob
import shutil
from iac_ci.loggerly import DirectPrintLogger

def s3_put_object(s3_client, bucket, key, body, content_type='text/plain', logger=None):
    """
    Put an object to S3, handling errors gracefully
    """
    if not bucket or not key:
        return False
    
    try:
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType=content_type
        )
        if logger:
            logger.debug(f"Successfully wrote to S3: s3://{bucket}/{key}")
        return True
    except Exception as e:
        if logger:
            logger.debug(f"Failed to write to S3: s3://{bucket}/{key} - {str(e)}")
        return False

def cleanup_tmp_directory(logger=None):
    """
    Clean up temporary files from previous runs
    """
    try:
        # List all files in /tmp/
        tmp_files = glob.glob("/tmp/*")
        for f in tmp_files:
            if os.path.isfile(f):
                os.remove(f)
            elif os.path.isdir(f):
                shutil.rmtree(f)
        if logger:
            logger.debug(f"Cleaned up {len(tmp_files)} files/directories from /tmp/")
    except Exception as e:
        if logger:
            logger.debug(f"Error cleaning up /tmp/ directory: {str(e)}")

def handler(event, context):
    # Initialize defaults
    output_bucket = None
    execution_id = None
    start_time = int(time.time())
    
    # Clean up /tmp/ directory from previous runs
    cleanup_tmp_directory()
    
    # Get execution_id from event or environment
    if event.get("execution_id"):
        execution_id = event["execution_id"]
    elif os.environ.get("EXECUTION_ID"):
        execution_id = os.environ["EXECUTION_ID"]

    # Initialize logger - we'll create it even without execution_id for initial logging
    logger = DirectPrintLogger(f'{execution_id if execution_id else "no_execution_id"}')
    
    # Error out if execution_id is not provided
    if not execution_id:
        error_msg = "execution_id must be provided in event or environment variables"
        logger.debug(f"ERROR: {error_msg}")

        cleanup_tmp_directory()

        # Return error response
        return {
            'statusCode': 400,
            'body': json.dumps({
                'status': False,
                'error': error_msg
            })
        }

    # Set execution_id in environment for child processes
    os.environ["EXECUTION_ID"] = execution_id
    logger.debug(f"Starting execution with ID: {execution_id}")
    
    # Get output bucket - critical for storing results
    if os.environ.get("OUTPUT_BUCKET"):
        output_bucket = os.environ["OUTPUT_BUCKET"]
    else:
        output_bucket = event.get("output_bucket")
        if output_bucket:
            os.environ["OUTPUT_BUCKET"] = output_bucket

    if not output_bucket:
        logger.debug('WARNING: No output bucket specified. Results will not be saved to S3.')
    
    # Initialize S3 client
    s3_client = boto3.client('s3')
    
    # Create initiated marker
    if output_bucket:
        s3_put_object(s3_client, output_bucket, f"executions/{execution_id}/initiated", str(start_time), logger=logger)
    
    try:
        # Convert the event to a base64 string
        event_json = json.dumps(event)
        event_base64 = base64.b64encode(event_json.encode()).decode()
        
        # Sanitize the input to prevent command injection
        safe_base64 = shlex.quote(event_base64)
        
        # Path to the main_tf.py script
        lambda_task_root = os.environ.get('LAMBDA_TASK_ROOT', '/var/task')
        script_path = os.path.join(lambda_task_root, "main_tf.py")
        
        # Create unique file paths for this execution
        request_id = context.aws_request_id if context else 'local'
        output_path = f"/tmp/tf_output_{start_time}_{request_id}.txt"
        response_path = f"/tmp/tf_response_{start_time}_{request_id}.json"

        # Set up environment with enhanced PYTHONPATH and response path
        env = os.environ.copy()
        current_path = os.environ.get('PYTHONPATH', '')
        
        if current_path:
            env['PYTHONPATH'] = f"{lambda_task_root}:{current_path}"
        else:
            env['PYTHONPATH'] = lambda_task_root
        
        # Pass the response path to main_tf.py
        env['TF_RESPONSE_PATH'] = response_path
            
        logger.debug(f"Setting PYTHONPATH: {env['PYTHONPATH']}")
        logger.debug(f"Setting TF_RESPONSE_PATH: {env['TF_RESPONSE_PATH']}")
        logger.debug(f"Executing main_tf.py with Python {sys.executable}")
        
        # Build the command with shell redirection to capture stdout and stderr
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
        
        # Read the JSON response if it exists
        if os.path.exists(response_path):
            with open(response_path, 'r') as f:
                response_data = json.load(f)
            logger.debug(f"Successfully read response data from {response_path}")
            os.remove(response_path)
        else:
            logger.debug(f"Response file {response_path} was not created")
        
        # Read the combined output from the output file
        combined_output = ""
        if os.path.exists(output_path):
            with open(output_path, 'r') as f:
                combined_output = f.read()
            
            logger.debug("==================== EXECUTION OUTPUT ====================")
            logger.debug(combined_output)
            logger.debug("==================================================================")
            os.remove(output_path)
        else:
            combined_output = f"ERROR: Output file {output_path} was not created"
            logger.debug(combined_output)
        
        # Prepare result data with execution details
        result_data = {
            'output_bucket': output_bucket,
            'execution_id': execution_id,
            'return_code': return_code,
            'status': 'success' if return_code == 0 else 'error',
            'function_name': context.function_name if context else 'unknown',
            'execution_time': f"{context.get_remaining_time_in_millis()/1000:.2f} seconds" if context else "unknown",
            'output': combined_output,
            'start_time': start_time,
            'done': True,
            'end_time': int(time.time())
        }
        
        # If we have response data, incorporate it into result_data
        if response_data and 'body' in response_data:
            if isinstance(response_data['body'], str):
                try:
                    body_dict = json.loads(response_data['body'])
                except json.JSONDecodeError:
                    body_dict = {"raw_body": response_data['body']}
            else:
                body_dict = response_data['body']
                
            # Transfer all body information to result data
            result_data.update(body_dict)
        
        # Upload result data to S3
        if output_bucket:
            result_key = f"executions/{execution_id}/result.json"
            s3_put_object(
                s3_client, 
                output_bucket, 
                result_key, 
                json.dumps(result_data),
                content_type='application/json',
                logger=logger
            )
            result_data['result_key'] = result_key
        
        # Prepare final response
        if response_data:
            # Add our tracking information to the response body
            if 'body' in response_data:
                if isinstance(response_data['body'], str):
                    try:
                        body_dict = json.loads(response_data['body'])
                    except json.JSONDecodeError:
                        body_dict = {"raw_body": response_data['body']}
                else:
                    body_dict = response_data['body']
                
                # Add tracking URLs and execution info
                if output_bucket:
                    body_dict['initiated_key'] = f"executions/{execution_id}/initiated"
                    body_dict['result_key'] = f"executions/{execution_id}/result.json"
                    body_dict['done_key'] = f"executions/{execution_id}/done"
                
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
        logger.debug(f"Error executing main_tf operation: {str(e)}")
        logger.debug(error_traceback)
        
        fresults = {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'error': str(e),
                'traceback': error_traceback,
                'execution_id': execution_id
            })
        }
        
        # Upload error info to result.json
        if output_bucket:
            error_data = {
                'execution_id': execution_id,
                'status': 'error',
                'error': str(e),
                'traceback': error_traceback,
                'start_time': start_time,
                'done': True,
                'end_time': int(time.time())
            }
            s3_put_object(
                s3_client,
                output_bucket,
                f"executions/{execution_id}/result.json",
                json.dumps(error_data),
                content_type='application/json',
                logger=logger
            )
    
    # Create done marker to indicate completion
    s3_put_object(
        s3_client, 
        output_bucket, 
        f"executions/{execution_id}/done", 
        str(int(time.time())),
        logger=logger
    )
    logger.debug("Lambda function execution complete")
    cleanup_tmp_directory()

    return fresults