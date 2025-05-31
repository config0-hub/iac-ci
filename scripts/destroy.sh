#!/bin/bash

# Script to destroy all resources created by the setup script

# ===== UTILITY FUNCTIONS =====
check_env_file() {
  if [ ! -f "$ENV_FILE" ]; then
    echo "Error: Environment file $ENV_FILE not found."
    echo "Cannot proceed with destruction without knowing what resources were created."
    exit 1
  fi
}

run_terraform_destroy() {
  local directory=$1
  
  cd $directory || exit 8
  tofu init || exit 8
  tofu destroy -auto-approve
}

confirm_destruction() {
  if [ -z "$YES_TO_ALL" ]; then
      echo "WARNING: This script will destroy all resources created by the setup script."
      echo "This action is IRREVERSIBLE and will DELETE ALL DATA in the S3 buckets."
      echo ""
      read -p "Are you sure you want to proceed? (y/N): " confirmation
      if [[ $confirmation != "y" && $confirmation != "Y" ]]; then
        echo "Destruction cancelled."
        exit 0
      fi
  fi
}

confirm_destruction2() {
  if [ -z "$YES_TO_ALL" ]; then
      echo "WARNING: This script will finalize the destruction of the buckets."
      echo ""
      read -p "Are you sure you want to proceed? (y/N): " confirmation

      if [[ $confirmation != "y" && $confirmation != "Y" ]]; then
        echo "Destruction cancelled."
        exit 0
      fi
  fi
}

# ===== ENVIRONMENT SETUP =====
export IAC_BUILD_DIR=${IAC_BUILD_DIR:=/var/tmp/iac-ci}
export ENV_FILE=${IAC_BUILD_DIR}/build_env_vars.env
export BASE_DIR_EXECUTORS=${IAC_BUILD_DIR}/build/executors
check_env_file

echo "Loading environment variables from $ENV_FILE"
source "$ENV_FILE"

# Check if critical variables are set
if [ -z "$TF_VAR_random_str" ] || [ -z "$TF_VAR_stateful_bucket_name" ]; then
  echo "Error: Critical environment variables not found in $ENV_FILE"
  echo "Cannot proceed with destruction."
  exit 1
fi

# Set SRCDIR to current directory if not already set
if [ -z "$SRCDIR" ]; then
  SRCDIR=$(pwd)
fi
export SRCDIR

# ===== DESTRUCTION FUNCTIONS =====
empty_s3_buckets() {
  echo "Emptying S3 buckets before destruction..."

  # List of all bucket variables from the env file
  local bucket_vars=(
    TF_VAR_lambda_bucket_name
    TF_VAR_codebuild_cache_bucket_name
    TF_VAR_codebuild_log_bucket_name
    TF_VAR_tmp_bucket_name
    TF_VAR_stateful_bucket_name
    TF_VAR_log_bucket_name
    TF_VAR_runs_bucket_name
  )

  for var in "${bucket_vars[@]}"; do
    if [ ! -z "${!var}" ]; then
      echo "Emptying bucket ${!var}..."
      aws s3 rm s3://${!var} --recursive > /dev/null 2>&1 || echo "Warning: Could not empty bucket ${!var} completely"
    fi
  done
}

remove_ssm_parameters() {
  echo "Removing SSM parameters..."
  
  # List of SSM parameters to remove
  local ssm_params=(
    "$SSM_GITHUB_TOKEN"
    "$SSM_SSH_KEY"
    "$SSM_INFRACOST_API_KEY"
    "$SSM_SLACK_WEBHOOK_HASH"
  )
  
  for param in "${ssm_params[@]}"; do
    if [ ! -z "$param" ]; then
      echo "Removing SSM parameter: $param"
      aws ssm delete-parameter --name "$param" || echo "Warning: Could not delete SSM parameter $param"
    fi
  done
}

delete_dynamodb_items() {
  echo "Deleting DynamoDB items..."
  
  # If we have the TRIGGER_ID, we can delete the specific items
  if [ ! -z "$TRIGGER_ID" ]; then
    echo "Deleting items with trigger_id: $TRIGGER_ID from iac-ci-settings table..."
    
    # Create a filter expression to find items with our trigger_id
    aws dynamodb scan \
      --table-name iac-ci-settings \
      --filter-expression "trigger_id = :tid" \
      --expression-attribute-values '{":tid": {"S": "'"$TRIGGER_ID"'"}}' \
      --query "Items[*]._id.S" \
      --output text | while read id; do
        if [ ! -z "$id" ]; then
          echo "Deleting item with _id: $id"
          aws dynamodb delete-item --table-name iac-ci-settings --key '{"_id": {"S": "'"$id"'"}}' || echo "Warning: Could not delete item with _id $id"
        fi
      done
  fi
}
destroy_api_gateway() {
  echo "Destroying API Gateway..."
  export TF_VAR_lambda_name="iac-ci-lambda_trigger_stepf"
  export TF_VAR_stage="v1"
  export TF_VAR_resource_name="iac"
  create_backend_tf "$SRCDIR/deployment/7-api-gateway" "iac-ci-system/api-gateway"
  run_terraform_destroy "$SRCDIR/deployment/7-api-gateway"
}

destroy_sns_topic_subscription() {
  echo "Destroying SNS Topic Subscription..."
  export TF_VAR_topic_name="iac-ci-codebuild-complete-trigger"
  export TF_VAR_lambda_name="iac-ci-check-codebuild"
  create_backend_tf "$SRCDIR/deployment/8-sns_topic_subscription" "iac-ci-system/sns-topic-subscription"
  run_terraform_destroy "$SRCDIR/deployment/8-sns_topic_subscription"
}

destroy_trigger_lambda() {
  echo "Destroying Lambda to Trigger Step Function..."
  export TF_VAR_step_function_name="iac-ci-stepf-ci"
  export TF_VAR_lambda_name="iac-ci-lambda_trigger_stepf"
  export TF_VAR_handler="app.handler"
  export TF_VAR_s3_bucket="iac-ci-lambda-$TF_VAR_random_str"
  export TF_VAR_s3_key="iac-ci-lambda_trigger_stepf.zip"
  export TF_VAR_bucket_names="[\"iac-ci-lambda-$TF_VAR_random_str\",\"iac-ci-stateful-$TF_VAR_random_str\",\"iac-ci-tmp-$TF_VAR_random_str\",\"iac-ci-log-$TF_VAR_random_str\",\"iac-ci-runs-$TF_VAR_random_str\"]"
  create_backend_tf "$SRCDIR/deployment/6-trigger-stepf/terraform" "iac-ci-system/trigger-stepf"
  run_terraform_destroy "$SRCDIR/deployment/6-trigger-stepf/terraform"
}

destroy_step_functions() {
  echo "Destroying Step Functions..."
  create_backend_tf "$SRCDIR/deployment/5-stepfunc" "iac-ci-system/stepfunc"
  run_terraform_destroy "$SRCDIR/deployment/5-stepfunc"
}

destroy_lambda_functions() {
  echo "Destroying Lambda Functions..."
  export TF_VAR_s3_bucket="iac-ci-lambda-$TF_VAR_random_str"
  export TF_VAR_bucket_names="[\"iac-ci-lambda-$TF_VAR_random_str\",\"iac-ci-stateful-$TF_VAR_random_str\",\"iac-ci-tmp-$TF_VAR_random_str\",\"iac-ci-log-$TF_VAR_random_str\",\"iac-ci-runs-$TF_VAR_random_str\"]"
  create_backend_tf "$SRCDIR/deployment/4-lambda" "iac-ci-system/lambda-funcs"
  run_terraform_destroy "$SRCDIR/deployment/4-lambda"
}

destroy_dynamodb() {
  echo "Destroying DynamoDB Tables..."
  create_backend_tf "$SRCDIR/deployment/3-dynamodb" "iac-ci-system/dynamodb"
  run_terraform_destroy "$SRCDIR/deployment/3-dynamodb"
}

destroy_iac_ci_executors() {
  echo "Destroying IAC-CI Executors..."
  cd $SRCDIR/deployment/2-lambda-and-codebuild-executors/
  ./destroy.sh || echo "Warning: Executor destruction may not have been complete"
}

destroy_github_repo_params() {
  cd $SRCDIR
  export TF_VAR_url=${BASE_URL}/${TRIGGER_ID}
  export TF_VAR_secret=$SECRET
  export TF_VAR_public_key=$FIRST_REPO_TO_REGISTER_PUBLIC_SSH_KEY_HASH
  run_terraform_destroy "$SRCDIR/deployment/9-github-params"
}

destroy_s3_buckets() {
  echo "Destroying S3 Buckets..."
  cd $SRCDIR/deployment/1-s3-buckets
  tofu init || exit 8
  tofu destroy -auto-approve
}

create_backend_tf() {
  local directory=$1
  local key=$2
  
  cat <<EOL > $directory/backend.tf
terraform {
  backend "s3" {
    bucket         = "${TF_VAR_stateful_bucket_name}"
    key            = "$key"
    region         = "us-east-1"
  }
}
EOL
}

cleanup_local_files() {
  echo "Cleaning up local files..."
  
  # Remove SSH keys if they exist
  if [ -d "/var/tmp/github/ssh_keys" ]; then
    rm -rf /var/tmp/github/ssh_keys
    echo "Removed SSH keys directory"
  fi
  
  # Remove environment file
  if [ -f "$ENV_FILE" ]; then
    rm -f "$ENV_FILE"
    echo "Removed environment file: $ENV_FILE"
  fi
  
  # Remove temporary files
  rm -f /tmp/data.json 2>/dev/null
  rm -f /tmp/.exports.env 2>/dev/null
  rm -f /tmp/iac-ci-system.zip 2>/dev/null
  rm -rf /tmp/iac-ci-build 2>/dev/null
  
  echo "Local cleanup complete"
}

# ===== MAIN EXECUTION =====
main() {
  confirm_destruction
  destroy_github_repo_params

  destroy_sns_topic_subscription
  destroy_api_gateway
  destroy_trigger_lambda
  destroy_step_functions
  destroy_lambda_functions

  delete_dynamodb_items
  destroy_dynamodb

  destroy_iac_ci_executors || echo "expected to failure in initial delete"
  sleep 1800
  destroy_iac_ci_executors

  remove_ssm_parameters
  cleanup_local_files

  confirm_destruction2
  empty_s3_buckets
  destroy_s3_buckets

  echo "========================================================"
  echo "Destruction complete. All resources should be removed."
  echo "========================================================"
}

# Execute main function
main
