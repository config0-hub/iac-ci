#!/bin/bash

# Source credentials
source /tmp/.credentials/aws/iam-test-user-2.txt

# Check if S3_BUCKET is set
if [ -z "${S3_BUCKET}" ]; then
    echo "ERROR: S3_BUCKET environment variable is required but not set."
    echo "Please set S3_BUCKET before running this script."
    exit 1
fi

# Set S3_KEY with a default if not provided
export S3_KEY=${S3_KEY:-iac-ci-trigger-lambda.zip}

echo "Using S3 bucket: ${S3_BUCKET}"
echo "Using S3 key: ${S3_KEY}"

#s3://iac-ci-lambda-iacciexjtf/iac-ci-trigger-lambda.zip

for FUNC_NAME in iac-ci-lambda_trigger_stepf
do
   echo ""
   echo "updating function $FUNC_NAME"
   echo ""
   aws lambda update-function-code --function-name $FUNC_NAME \
   --s3-key $S3_KEY \
   --s3-bucket $S3_BUCKET &
   sleep 2
done

echo "Update requests submitted. Functions are being updated in the background."