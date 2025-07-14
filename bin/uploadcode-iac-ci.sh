#!/bin/bash

# Default environment variables
DEFAULT_CREDENTIALS_FILE="/tmp/.credentials/aws/iam.txt"
DEFAULT_S3_BUCKET="default-bucket-name"
DEFAULT_S3_KEY="iac-ci.zip"
DEFAULT_SOURCE_FILE="/tmp/iac-ci.zip"

# Use environment variables if set, otherwise use defaults
CREDENTIALS_FILE=${CREDENTIALS_FILE:-$DEFAULT_CREDENTIALS_FILE}
S3_BUCKET=${S3_BUCKET:-$DEFAULT_S3_BUCKET}
S3_KEY=${S3_KEY:-$DEFAULT_S3_KEY}

# Source credentials file if it exists
if [ -f "$CREDENTIALS_FILE" ]; then
    source "$CREDENTIALS_FILE"
    echo "Sourced credentials from $CREDENTIALS_FILE"
else
    echo "Warning: Credentials file not found at $CREDENTIALS_FILE"
fi

# Validate that required variables are set
if [ -z "$S3_BUCKET" ]; then
    echo "Error: S3_BUCKET is not set"
    exit 1
fi

if [ -z "$S3_KEY" ]; then
    echo "Error: S3_KEY is not set"
    exit 1
fi

# Check if source file exists
if [ ! -f "$DEFAULT_SOURCE_FILE" ]; then
    echo "Error: Source file $DEFAULT_SOURCE_FILE does not exist"
    exit 1
fi

# Upload file to S3
echo "Uploading $DEFAULT_SOURCE_FILE to s3://$S3_BUCKET/$S3_KEY"
echo "aws s3 cp $DEFAULT_SOURCE_FILE s3://$S3_BUCKET/$S3_KEY"
aws s3 cp $DEFAULT_SOURCE_FILE "s3://$S3_BUCKET/$S3_KEY"
UPLOAD_STATUS=$?

if [ $UPLOAD_STATUS -eq 0 ]; then
    echo "Upload successful"
else
    echo "Upload failed with status $UPLOAD_STATUS"
    exit $UPLOAD_STATUS
fi
