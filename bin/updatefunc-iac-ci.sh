#!/bin/bash

# Default environment variables
DEFAULT_CREDENTIALS_FILE="/tmp/.credentials/aws/iam.txt"
DEFAULT_S3_BUCKET="default-bucket-name"
DEFAULT_S3_KEY="iac-ci.zip"
DEFAULT_SLEEP_SECONDS=2

# Use environment variables if set, otherwise use defaults
CREDENTIALS_FILE=${CREDENTIALS_FILE:-$DEFAULT_CREDENTIALS_FILE}
S3_BUCKET=${S3_BUCKET:-$DEFAULT_S3_BUCKET}
S3_KEY=${S3_KEY:-$DEFAULT_S3_KEY}
SLEEP_SECONDS=${SLEEP_SECONDS:-$DEFAULT_SLEEP_SECONDS}

# Source credentials file if it exists
if [ -f "$CREDENTIALS_FILE" ]; then
    source "$CREDENTIALS_FILE"
    echo "Sourced credentials from $CREDENTIALS_FILE"
else
    echo "Warning: Credentials file not found at $CREDENTIALS_FILE"
fi

# Define list of functions to update
# Can be overridden by setting LAMBDA_FUNCTIONS as a space-separated string
DEFAULT_LAMBDA_FUNCTIONS=(
    "iac-ci-trigger-codebuild"
    "iac-ci-check-codebuild"
    "iac-ci-trigger-lambda"
    "iac-ci-pkgcode-to-s3"
    "iac-ci-process-webhook"
    "iac-ci-update-pr"
)

# Use provided functions if set, otherwise use defaults
if [ -z "$LAMBDA_FUNCTIONS" ]; then
    LAMBDA_FUNCTIONS=("${DEFAULT_LAMBDA_FUNCTIONS[@]}")
else
    # Convert space-separated string to array
    read -ra LAMBDA_FUNCTIONS <<< "$LAMBDA_FUNCTIONS"
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

# Update each Lambda function
for FUNC_NAME in "${LAMBDA_FUNCTIONS[@]}"
do
    echo ""
    echo "Updating function $FUNC_NAME"
    echo "Using S3 bucket: $S3_BUCKET"
    echo "Using S3 key: $S3_KEY"
    echo ""
    
    aws lambda update-function-code \
        --function-name "$FUNC_NAME" \
        --s3-key "$S3_KEY" \
        --s3-bucket "$S3_BUCKET" &
    
    # Wait a moment before starting the next update
    sleep "$SLEEP_SECONDS"
done

echo ""
echo "All function updates initiated. Use the AWS console or CLI to check status."
echo ""
