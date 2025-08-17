#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Copyright (C) 2025 Gary Leong gary@config0.com

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import base64
import os
import json
import boto3
import random
import string
import hmac
import hashlib
import logging
from time import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CI_APP_NAME = os.environ.get("CI_APP_NAME", "iac_ci")


def _load_list_from_b64_env(var_name, default_list):
    val = os.environ.get(var_name)
    if not val:
        return list(default_list)
    try:
        decoded = base64.b64decode(val).decode("utf-8").strip()
        # Try JSON first (preferred: '["push","apply"]')
        try:
            parsed = json.loads(decoded)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except Exception:
            pass
        # Fallback: comma/space separated string
        if "," in decoded:
            return [x.strip() for x in decoded.split(",") if x.strip()]
        return [x.strip() for x in decoded.split() if x.strip()]
    except Exception as e:
        logger.warning("Failed to parse %s: %s. Falling back to default.", var_name, e)
        return list(default_list)


BASIC_EVENTS = _load_list_from_b64_env(
    "BASIC_EVENTS_B64",
    ["push", "apply", "pull_request", "issue_comment"],
)

VALID_ACTIONS = _load_list_from_b64_env(
    "VALID_ACTIONS_B64",  # fixed env var name
    ["plan", "check", "destroy", "apply", "validate", "report"],
)


def _write_execution_arn_to_db(search_str, execution_arn):
    dynamodb = boto3.resource("dynamodb")
    table_name = os.environ.get("DYNAMODB_TABLE_RUNS", "iac-ci-runs")
    table = dynamodb.Table(table_name)
    now = int(time())
    item = {
        "_id": search_str,
        "execution_arn": execution_arn,
        "checkin": now,
        "expire_at": now + 300,
    }
    # Simple write with minimal retries
    for _ in range(3):
        try:
            table.put_item(Item=item)
            return True
        except Exception as e:
            logger.warning("Retrying put_item due to error: %s", e)
    return False


def get_webhook_secret(trigger_id):
    dynamodb = boto3.resource("dynamodb")
    table_name = os.environ.get("DYNAMODB_TABLE_SETTINGS", "iac-ci-settings")
    table = dynamodb.Table(table_name)
    try:
        response = table.get_item(Key={"_id": trigger_id})
    except Exception as e:
        logger.error("DynamoDB get_item failed: %s", e)
        return None
    item = response.get("Item")
    if item and "secret" in item:
        return item["secret"]
    logger.error("Secret not found in SETTINGS table for _id: %s", trigger_id)
    return None


def _get_header_case_insensitive(headers, key):
    if not headers:
        return None
    if key in headers:
        return headers[key]
    # normalize
    lower = {str(k).lower(): v for k, v in headers.items()}
    return lower.get(key.lower())


def validate_github_webhook(event):
    path = event.get("path") or ""
    trigger_id = path.split("/")[-1] if path else None
    if not trigger_id:
        logger.error("No trigger_id found in request path")
        return False

    logger.info("Extracted trigger_id from URL: %s", trigger_id)

    headers = event.get("headers") or {}
    body = event.get("body", "")

    # API Gateway can base64-encode bodies
    if event.get("isBase64Encoded"):
        try:
            body = base64.b64decode(body)
        except Exception as e:
            logger.error("Failed to base64-decode body: %s", e)
            return False

    sig_header = (
        _get_header_case_insensitive(headers, "x-hub-signature-256")
        or _get_header_case_insensitive(headers, "X-Hub-Signature-256")
    )
    if not sig_header:
        logger.error("Missing GitHub signature header")
        return False

    github_signature = sig_header
    if github_signature.startswith("sha256="):
        github_signature = github_signature[7:]

    secret = get_webhook_secret(trigger_id)
    if not secret:
        logger.error("Failed to retrieve webhook secret for trigger_id: %s", trigger_id)
        return False

    return validate_signature(body, secret, github_signature)


def validate_signature(payload, secret, signature):
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def generate_random_string(length):
    characters = string.ascii_lowercase
    return "".join(random.choice(characters) for _ in range(length))


def _parse_json_body_maybe(body):
    if isinstance(body, (bytes, bytearray)):
        try:
            body = body.decode("utf-8")
        except Exception:
            pass
    if isinstance(body, str):
        try:
            return json.loads(body)
        except Exception:
            return {}
    return body if isinstance(body, dict) else {}


def check_event(headers, body):
    """
    Validates event type and comment commands for issue_comment.
    Returns (status: bool, message: str).
    """
    headers = headers or {}
    user_agent = str(_get_header_case_insensitive(headers, "User-Agent") or "").lower()

    if "bitbucket" in user_agent:
        event_type = str(_get_header_case_insensitive(headers, "X-Event-Key") or "")
    else:
        event_type = str(_get_header_case_insensitive(headers, "X-GitHub-Event") or "")

    if event_type == "ping":
        return False, "event is ping - nothing done"

    if event_type == "issue_comment":
        payload = _parse_json_body_maybe(body)
        if payload.get("action") != "created":
            return False, 'issue_comment needs to have action == "created"'
        comment = str(payload.get("comment", {}).get("body", "")).strip().split("\n")[0].strip()
        if comment:
            first = comment.split(" ", 1)[0].strip()
            logger.info(f'evaluating first command string "{first}"')
            if first not in VALID_ACTIONS:
                return False, f'Command "{first}" not recognized. Must be one of: {VALID_ACTIONS}'
            else:
                logger.info(f'Command "{first}" recognized')

    if event_type in BASIC_EVENTS:
        return True, f'Event type "{event_type}" is valid'

    return False, f'event = "{event_type}" must be one of {BASIC_EVENTS}'


def handler(event, context):
    try:
        if not validate_github_webhook(event):
            logger.error("GitHub webhook validation failed")
            return {
                "statusCode": 401,
                "body": json.dumps({"error": "Webhook validation failed"}),
            }

        logger.info("GitHub webhook validated successfully")

        headers = event.get("headers") or {}
        body = event.get("body", "")

        if event.get("isBase64Encoded"):
            try:
                body = base64.b64decode(body)
            except Exception as e:
                logger.error("Failed to base64-decode body in handler: %s", e)
                return {
                    "statusCode": 400,
                    "body": json.dumps({"error": "Invalid base64 body"}),
                }

        ok, msg = check_event(headers, body)
        if not ok:
            logger.info("Event check result: %s", msg)
            if "ping" in msg:
                return {"statusCode": 200, "body": json.dumps({"message": msg})}
            return {"statusCode": 400, "body": json.dumps({"error": msg})}

        logger.info("Event check passed: %s", msg)

        search_str = generate_random_string(20)

        event[CI_APP_NAME] = {"body": {"step_func": True, "search_str": search_str}}

        state_machine_arn = os.environ["STATE_MACHINE_ARN"]

        stepfunctions = boto3.client("stepfunctions")
        response = stepfunctions.start_execution(
            stateMachineArn=state_machine_arn, input=json.dumps(event)
        )

        execution_arn = response["executionArn"]
        request_context = event.get("requestContext") or {}
        request_id = request_context.get("requestId") or generate_random_string(12)

        _write_execution_arn_to_db(search_str, execution_arn)

        logger.info(
            'event forwarded to state_machine: "%s" from api_gateway: "%s"',
            state_machine_arn,
            request_id,
        )
        print("-" * 32)
        print(f'#{CI_APP_NAME}:::api_to_stepf {search_str} {execution_arn}')
        print("-" * 32)

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": "Step Function triggered successfully",
                    "executionArn": execution_arn,
                    "request_id": request_id,
                }
            ),
        }
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        return {"statusCode": 500, "body": json.dumps({"error": "Internal server error"})}
