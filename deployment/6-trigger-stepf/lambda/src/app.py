#!/usr/bin/env python

import os
import json
import boto3
import random
import string
import hmac
import hashlib
import logging
from time import time
from time import sleep
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CI_APP_NAME = os.environ.get('CI_APP_NAME', 'iac_ci')

def _write_execution_arn_to_db(search_str, execution_arn):
    dynamodb = boto3.resource('dynamodb')
    table_name = os.environ['DYNAMODB_TABLE_RUNS']
    table = dynamodb.Table(table_name)

    item = {
        "_id": search_str,
        "execution_arn": execution_arn,
        "checkin": int(time()),
        "expire_at": int(time()) + 300
    }

    status = None

    for retry in range(10):
        try:
            table.put_item(Item=item)
            status = True
            break
        except ClientError as e:
            print(f"Error writing to DynamoDB: {e.response['Error']['Message']}")
        sleep(5)
        continue

    return status

def get_webhook_secret(trigger_id):

    dynamodb = boto3.resource('dynamodb')
    table_name = os.environ['DYNAMODB_TABLE_SETTINGS']
    table = dynamodb.Table(table_name)

    try:

        response = table.get_item(
            Key={'_id': trigger_id}
        )
        
        if 'Item' in response:
            return response['Item']['secret']
        else:
            logger.error(f"Secret not found in DynamoDB SETTINGS table for _id: {trigger_id}")
            return None
            
    except ClientError as e:
        logger.error(f"DynamoDB error table_name {table_name}: {e.response['Error']['Message']}")
        return None
    except Exception as e:
        logger.error(f"Error retrieving secret table_name {table_name}: {str(e)}")
        return None

def validate_github_webhook(event):
    try:
        trigger_id = event["path"].split("/")[-1]
        logger.info(f"Extracted trigger_id from URL: {trigger_id}")
        
        headers = event.get('headers', {})
        body = event.get('body', '')
        
        github_signature = headers.get('x-hub-signature-256') or headers.get('X-Hub-Signature-256')
        
        if not github_signature:
            logger.error("Missing GitHub signature header")
            return False
        
        if github_signature.startswith('sha256='):
            github_signature = github_signature[7:]
        
        secret = get_webhook_secret(trigger_id)
        if not secret:
            logger.error(f"Failed to retrieve webhook secret for trigger_id: {trigger_id}")
            return False
        
        return validate_signature(body, secret, github_signature)
        
    except Exception as e:
        logger.error(f"Error validating GitHub webhook: {str(e)}")
        return False

def validate_signature(payload, secret, signature):
    try:
        if isinstance(payload, str):
            payload = payload.encode('utf-8')
        
        if isinstance(secret, str):
            secret = secret.encode('utf-8')
        
        expected_signature = hmac.new(
            secret,
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
        
    except Exception as e:
        logger.error(f"Error validating signature: {str(e)}")
        return False

def generate_random_string(length):
    characters = string.ascii_lowercase
    random_string = ''.join(random.choice(characters) for _ in range(length))
    return random_string

def handler(event, context):
    try:
        if not validate_github_webhook(event):
            logger.error("GitHub webhook validation failed")
            return {
                'statusCode': 401,
                'body': json.dumps({
                    'error': 'Webhook validation failed'
                })
            }
        
        logger.info("GitHub webhook validated successfully")
        
        search_str = generate_random_string(20)

        event[CI_APP_NAME] = {
            "body": {
                "step_func": True,
                "search_str": search_str
            }
        }

        state_machine_arn = os.environ['STATE_MACHINE_ARN']

        stepfunctions = boto3.client('stepfunctions')

        response = stepfunctions.start_execution(
            stateMachineArn=state_machine_arn,
            input=json.dumps(event),
        )

        execution_arn = response['executionArn']
        request_id = event['requestContext']['requestId']

        _write_execution_arn_to_db(search_str, execution_arn)

        print("-" * 32)
        print(f'event forwarded to state_machine: "{state_machine_arn}" from api_gateway: "{request_id}"')
        print(f"#{CI_APP_NAME}:::api_to_stepf {search_str} {execution_arn}")
        print("-" * 32)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Step Function triggered successfully',
                'executionArn': execution_arn,
                'request_id': request_id
            })
        }
        
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error'
            })
        }