#!/bin/bash

# Default environment variables
DEFAULT_SRC_DIR="../deployment/6-trigger-stepf/lambda/src"
DEFAULT_TMP_DIR="/tmp"
DEFAULT_OUTPUT_ZIP="${DEFAULT_TMP_DIR}/trigger_stepf.zip"
DEFAULT_OUTPUT_TAR="${DEFAULT_TMP_DIR}/trigger_stepf.tar.gz"
DEFAULT_S3_BUCKET="changeme-bucket"
DEFAULT_S3_KEY="iac-ci-lambda_trigger_stepf.zip"
DEFAULT_FUNC_NAME="iac-ci-lambda_trigger_stepf"
DEFAULT_INITIAL_DIR=$(pwd)

# Use environment variables if set, otherwise use defaults
SRC_DIR=${SRC_DIR:-$DEFAULT_SRC_DIR}
TMP_DIR=${TMP_DIR:-$DEFAULT_TMP_DIR}
OUTPUT_ZIP=${OUTPUT_ZIP:-$DEFAULT_OUTPUT_ZIP}
OUTPUT_TAR=${OUTPUT_TAR:-$DEFAULT_OUTPUT_TAR}
S3_BUCKET=${S3_BUCKET:-$DEFAULT_S3_BUCKET}
S3_KEY=${S3_KEY:-$DEFAULT_S3_KEY}
FUNC_NAME=${FUNC_NAME:-$DEFAULT_FUNC_NAME}
INITIAL_DIR=${INITIAL_DIR:-$DEFAULT_INITIAL_DIR}

# Make sure source directory exists
if [ ! -d "$SRC_DIR" ]; then
    echo "Error: Source directory $SRC_DIR does not exist"
    exit 1
fi

# Change to source directory
echo "Changing to source directory: $SRC_DIR"
cd "$SRC_DIR" || { echo "Failed to change to source directory"; exit 1; }

# Clean up any existing output files
echo "Cleaning up previous build artifacts"
rm -rf "$OUTPUT_ZIP" "$OUTPUT_TAR"

# Create archives
echo "Creating zip archive: $OUTPUT_ZIP"
zip -r "$OUTPUT_ZIP" . || { echo "Failed to create zip archive"; exit 9; }

echo "Creating tar archive: $OUTPUT_TAR"
tar cvfz "$OUTPUT_TAR" . || { echo "Failed to create tar archive"; exit 9; }

# Return to initial directory
echo "Returning to initial directory"
cd "$INITIAL_DIR" || { echo "Failed to return to initial directory"; exit 1; }

# Upload to S3
echo "Uploading $OUTPUT_ZIP to s3://$S3_BUCKET/$S3_KEY"
aws s3 cp "$OUTPUT_ZIP" "s3://$S3_BUCKET/$S3_KEY" || { echo "Failed to upload to S3"; exit 1; }

# Update Lambda function
echo "Updating Lambda function: $FUNC_NAME"
aws lambda update-function-code \
    --function-name "$FUNC_NAME" \
    --s3-key "$S3_KEY" \
    --s3-bucket "$S3_BUCKET" &

LAMBDA_PID=$!
echo "Lambda update initiated with process ID: $LAMBDA_PID"
echo "Script completed successfully"
