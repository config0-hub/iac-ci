#!/bin/bash

# GENERAL 
setup_environment() {
    # Default environment variables
    DEFAULT_CREDENTIALS_FILE="/tmp/.credentials/aws/iam.txt"
    DEFAULT_S3_BUCKET="default-bucket-name"
    
    # Use environment variables if set, otherwise use defaults
    CREDENTIALS_FILE=${CREDENTIALS_FILE:-$DEFAULT_CREDENTIALS_FILE}
    S3_BUCKET=${S3_BUCKET:-$DEFAULT_S3_BUCKET}
    
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
}

# COMMON FUNCTIONS 
# Function to upload file to S3 and update Lambda function
# Parameters:
# $1 - Source file path
# $2 - S3 key (destination filename)
# $3 - Lambda function name
upload_and_update_lambda() {
    local SOURCE_FILE="$1"
    local S3_KEY="$2"
    local FUNC_NAME="$3"
    
    echo "Uploading $SOURCE_FILE to s3://$S3_BUCKET/$S3_KEY"
    aws s3 cp "$SOURCE_FILE" "s3://$S3_BUCKET/$S3_KEY" || { echo "Failed to upload to S3"; return 1; }
    
    echo "Updating Lambda function: $FUNC_NAME"
    echo "Using S3 bucket: $S3_BUCKET"
    echo "Using S3 key: $S3_KEY"
    
    aws lambda update-function-code \
        --function-name "$FUNC_NAME" \
        --s3-key "$S3_KEY" \
        --s3-bucket "$S3_BUCKET" &
    
    return 0
}

# IAC_CI FUNCTIONS
update_iac_ci_functions() {
    echo "Updating IAC code"
    SOURCE_FILE="../artifacts/iac-ci.zip"
    
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
    
    # Update each Lambda function
    for FUNC_NAME in "${LAMBDA_FUNCTIONS[@]}"
    do
        upload_and_update_lambda "$SOURCE_FILE" "$FUNC_NAME.zip" "$FUNC_NAME"
        
        # Wait a moment before starting the next update
        sleep "${SLEEP_SECONDS:-1}"
    done
    
    echo "All IAC CI function updates initiated."
}

# LAMBDA TRIGGER FUNCTION
update_lambda_trigger_function() {
    echo "Updating trigger stepf code"
    
    FUNC_NAME="iac-ci-lambda_trigger_stepf"
    S3_KEY="$FUNC_NAME.zip"
    SOURCE_FILE="../artifacts/$FUNC_NAME.zip"
    
    upload_and_update_lambda "$SOURCE_FILE" "$S3_KEY" "$FUNC_NAME"
    
    LAMBDA_PID=$!
    echo "Lambda trigger update initiated with process ID: $LAMBDA_PID"
}

# IAC EXECUTOR 
update_iac_executor() {
    echo "Updating iac-ci executors"
    SOURCE_FILE="../artifacts/iac-ci-executors.zip"
    S3_KEY="iac-ci.zip"
    FUNC_NAME="iac-ci"
    
    upload_and_update_lambda "$SOURCE_FILE" "$S3_KEY" "$FUNC_NAME"
}

#########################################################
# MAIN 
#########################################################

main() {
    setup_environment
    update_iac_ci_functions
    update_lambda_trigger_function
    update_iac_executor
    echo "Script completed successfully"
}

# Execute main function
main
