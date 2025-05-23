#!/usr/bin/env python

import os
import json
import boto3
import random
import string
from time import time
from time import sleep
from botocore.exceptions import ClientError

def _write_execution_arn_to_db(search_str,execution_arn):

    dynamodb = boto3.resource('dynamodb')
    table_name = os.environ['DYNAMODB_TABLE']
    table = dynamodb.Table(table_name)

    item = {
        "_id": search_str,
        "execution_arn": execution_arn,
        "checkin":int(time()),
        "expire_at":int(time()) + 300
    }

    status = None

    for retry in range(10):
        try:
            # Put the item into the DynamoDB table
            table.put_item(Item=item)
            status = True
            break
        except ClientError as e:
            print(f"Error writing to DynamoDB: {e.response['Error']['Message']}")
        sleep(5)
        continue

    return status

def generate_random_string(length):
    characters = string.ascii_lowercase  # Only lowercase letters
    random_string = ''.join(random.choice(characters) for _ in range(length))
    return random_string

def handler(event, context):

    search_str = generate_random_string(20)

    event["iac_ci"] = {
        "body": {
            "step_func":True,
            "search_str":search_str
        }
    }

    # Get the Step Function ARN from the environment variable
    state_machine_arn = os.environ['STATE_MACHINE_ARN']

    # Create a Step Functions client
    stepfunctions = boto3.client('stepfunctions')

    # Start the Step Function with the payload
    response = stepfunctions.start_execution(
        stateMachineArn=state_machine_arn,
        input=json.dumps(event),
    )

    execution_arn = response['executionArn']
    request_id = event['requestContext']['requestId']

    _write_execution_arn_to_db(search_str,execution_arn)

    print("-"*32)
    print(f'event forwarded to state_machine: "{state_machine_arn}" from api_gateway: "{request_id}"')
    print(f"#iac-ci:::api_to_stepf {search_str} {execution_arn}")
    print("-"*32)

    # Return a response
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Step Function triggered successfully',
            'executionArn': execution_arn,
            'request_id': request_id
        })
    }
