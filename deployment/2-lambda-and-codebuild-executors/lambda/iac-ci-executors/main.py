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

def handler(event, context):
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
        timestamp = int(time.time())
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
            
        print(f"Setting PYTHONPATH: {env['PYTHONPATH']}")
        print(f"Setting TF_RESPONSE_PATH: {env['TF_RESPONSE_PATH']}")
        print(f"Lambda task root: {lambda_task_root}")
        
        # Build the command with shell redirection to capture stdout and stderr
        print(f"Executing main_tf.py with Python {sys.executable}")
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
        
        print(f"Terraform process completed with exit code: {return_code}")
        
        # Initialize response data
        response_data = {}
        
        # Try to read the JSON response if it exists
        if os.path.exists(response_path):
            try:
                with open(response_path, 'r') as f:
                    response_data = json.load(f)
                print(f"Successfully read response data from {response_path}")
                # Clean up the response file
                os.remove(response_path)
            except Exception as e:
                print(f"Error reading response file: {str(e)}")
        else:
            print(f"Response file {response_path} was not created")
        
        # Read the combined output from the output file
        combined_output = ""
        if os.path.exists(output_path):
            with open(output_path, 'r') as f:
                combined_output = f.read()
            
            # Print the complete output to the logs
            print("==================== TERRAFORM EXECUTION OUTPUT ====================")
            print(combined_output)
            print("==================================================================")
                
            # Don't remove the output file yet as we'll upload it to S3
        else:
            combined_output = f"ERROR: Output file {output_path} was not created"
            print(combined_output)
        
        # Upload the output to S3 if output_bucket and output_bucket_key are in the results
        if response_data and 'body' in response_data:
            try:
                body_dict = json.loads(response_data['body'])
                
                output_bucket = body_dict.get('output_bucket')
                output_bucket_key = body_dict.get('output_bucket_key')
                
                if output_bucket and output_bucket_key and os.path.exists(output_path):
                    # Upload the output log to S3
                    s3_client = boto3.client('s3')
                    
                    print(f"Uploading output to S3: s3://{output_bucket}/{output_bucket_key}")
                    
                    # Upload the file
                    s3_client.upload_file(
                        output_path,
                        output_bucket,
                        output_bucket_key,
                        ExtraArgs={'ContentType': 'text/plain'}
                    )
                    
                    print(f"Successfully uploaded output to S3: s3://{output_bucket}/{output_bucket_key}")
                    
                    # Add the upload info to the response
                    body_dict['tf_output_uploaded'] = True
                    body_dict['tf_output_location'] = f"s3://{output_bucket}/{output_bucket_key}"
                else:
                    print("Missing output_bucket or output_bucket_key in results, or output file doesn't exist")
                    if not output_bucket:
                        print("output_bucket is missing")
                    if not output_bucket_key:
                        print("output_bucket_key is missing")
                    if not os.path.exists(output_path):
                        print(f"Output file {output_path} doesn't exist")
                
                # Add the output to the response
                body_dict['tf_output'] = combined_output
                response_data['body'] = json.dumps(body_dict)
                
            except Exception as e:
                print(f"Error processing response or uploading to S3: {str(e)}")
                traceback_str = traceback.format_exc()
                print(traceback_str)
                
                # Add the error to the response
                if 'body' in response_data:
                    try:
                        body_dict = json.loads(response_data['body'])
                        body_dict['tf_output'] = combined_output
                        body_dict['tf_output_upload_error'] = str(e)
                        body_dict['tf_output_upload_traceback'] = traceback_str
                        response_data['body'] = json.dumps(body_dict)
                    except:
                        response_data['body'] = json.dumps({
                            'tf_output': combined_output,
                            'original_response': response_data.get('body', ''),
                            'tf_output_upload_error': str(e),
                            'tf_output_upload_traceback': traceback_str
                        })
        
        # Now clean up the output file
        if os.path.exists(output_path):
            os.remove(output_path)
            
        # If we have response data, return it; otherwise, build a response based on the return code
        if response_data:
            return response_data
        else:
            # Create a response based on the return code
            return {
                'statusCode': 200 if return_code == 0 else 400,
                'body': json.dumps({
                    'status': 'success' if return_code == 0 else 'error',
                    'tf_output': combined_output,
                    'return_code': return_code
                })
            }
        
    except Exception as e:
        error_traceback = traceback.format_exc()
        print(f"Error executing Terraform operation: {str(e)}")
        print(error_traceback)
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'error': str(e),
                'traceback': error_traceback
            })
        }