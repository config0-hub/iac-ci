#!/bin/bash

# Add basic error handling
set -e

# ===== UTILITY FUNCTIONS =====
log_info() {
    echo "[$(date '+%H:%M:%S')] $1"
}

generate_random_string() {
    local prefix="$1"
    local length="${2:-16}"  # Default length is 16 if not specified

    # Generate lowercase random string using /dev/urandom
    local random_string=$(LC_ALL=C tr -dc 'a-z0-9' < /dev/urandom | head -c "$length")

    # Return the prefix + random string
    echo "${prefix}${random_string}"
}

check_optional_env_var() {
    local var_name="$1"

    if [ -z "${!var_name}" ]; then
        log_info "WARNING: Environment variable '$var_name' is not set."

        if [ -z "$YES_TO_ALL" ]; then
            read -p "Do you want to continue anyway? (y/N): " response
            case "$response" in
                [yY][eE][sS]|[yY])
                    return 0
                    ;;
                *)
                    log_info "Aborting."
                    return 1
                    ;;
            esac
        else
            log_info "Continuing without '$var_name' because YES_TO_ALL is set."
            return 0
        fi
    fi

    return 0
}

check_required_env_var() {
  local var_name=$1
  local error_message=$2
  
  if [ -z "${!var_name}" ]; then
    log_info "$error_message"
    exit 8
  fi
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

run_terraform() {
  local directory=$1
  
  cd $directory || exit 8
  tofu init || exit 8
  tofu plan || exit 8
  tofu apply -auto-approve
}

# ===== ENVIRONMENT SETUP =====
# Centralize environmental variables that don't change
readonly SRCDIR=$(pwd)
export SRCDIR
readonly IAC_BUILD_DIR=${IAC_BUILD_DIR:=/var/tmp/iac-ci}
readonly IAC_FIRST_REPO_TO_REGISTER=${IAC_FIRST_REPO_TO_REGISTER:=iac-ci}
readonly IAC_REPO_SSH_KEYS_LOCAL_DIR=${IAC_BUILD_DIR}/github/ssh_keys
readonly IAC_REPO_SSH_KEYS_EMAIL="iac-ci@iac-ci.com"
readonly ENV_FILE=${IAC_BUILD_DIR}/build_env_vars.env
readonly EXECUTORS_TF_BACKEND=${EXECUTORS_TF_BACKEND:=/tmp/backend.tf}
readonly EXECUTORS_BUILD_ENV_VARS_FILE=${EXECUTORS_BUILD_ENV_VARS_FILE:=/tmp/.build_executors_vars.env}

# Check if env file exists and source it if it does
if [ -f "$ENV_FILE" ]; then
  log_info "Found existing environment file. Loading variables from $ENV_FILE"
  source "$ENV_FILE"
  
  # Check if TF_VAR_random_str is set in the file
  if [ -z "$TF_VAR_random_str" ]; then
    log_info "TF_VAR_random_str not found in environment file. Will generate a new one."
    NEEDS_INITIALIZATION=true
  else
    log_info "Using existing TF_VAR_random_str: $TF_VAR_random_str"
    NEEDS_INITIALIZATION=false
  fi
else
  log_info "No existing environment file found. Will create one."
  NEEDS_INITIALIZATION=true
  
  # Create directory for env file
  mkdir -p $IAC_BUILD_DIR
  
  # Write unchanging environment variables to file
  cat <<EOL > "$ENV_FILE"
# SSM parameter paths
export SSM_GITHUB_TOKEN="/iac-ci/github/token"
export SSM_SSH_KEY="/iac-ci/github/repo/${IAC_FIRST_REPO_TO_REGISTER}/private_key"
export SSM_INFRACOST_API_KEY="/iac-ci/infracost/api_key"
export SSM_SLACK_WEBHOOK_HASH="/iac-ci/slack/webhook/url"

# Application names and settings
export REPO_NAME="${IAC_FIRST_REPO_TO_REGISTER}"
export APP_NAME_IAC="iac-ci"
export TF_VAR_aws_default_region="us-east-1"
export BASE_DIR_EXECUTORS="${IAC_BUILD_DIR}/build/executors"
export IAC_BUILD_DIR="${IAC_BUILD_DIR}"
export IAC_REPO_SSH_KEYS_EMAIL="$IAC_REPO_SSH_KEYS_EMAIL"
export IAC_REPO_SSH_KEYS_LOCAL_DIR="$IAC_REPO_SSH_KEYS_LOCAL_DIR"
export TF_VAR_environment_name="iac-ci"

# Constant AWS settings
export TF_VAR_hash_key="_id"
export TF_VAR_resource_name="iac-ci"
export TF_VAR_key_name="iac-ci"
export TF_VAR_billing_mode="PAY_PER_REQUEST"
export TF_VAR_step_function_name="iac-ci-stepf-ci"
export TF_VAR_handler="app.handler"
export TF_VAR_lambda_env_vars='{"ENV": "build", "IAC_PLATFORM":"iac-ci", "DEBUG_IAC_CI":"true"}'
export TF_VAR_cloud_tags='{"environment": "iac-ci", "purpose": "iac-ci"}'
export TF_VAR_dynamodb_names='[ "iac-ci-runs", "iac-ci-settings" ]'
export TF_VAR_topic_name="iac-ci-codebuild-complete-trigger"
export TF_VAR_events="push,pull_request,issue_comment"
export TF_VAR_repository="${IAC_FIRST_REPO_TO_REGISTER}"
EOL

  # Source the new environment file
  source "$ENV_FILE"
fi

# ===== MAIN FUNCTIONS =====
initialize_variables() {
  if [ "$NEEDS_INITIALIZATION" = true ]; then
    # Generate random string and IDs
    [ -z "${TF_VAR_random_str}" ] && export TF_VAR_random_str=$(generate_random_string iacci 5)
    export WEBHOOK_SECRET=$(generate_random_string iac-ci- 20)
    export STATEFUL_ID=$(generate_random_string iac-ci- 10)
    
    # Generate bucket names
    export TF_VAR_lambda_bucket_name="iac-ci-lambda-$TF_VAR_random_str"
    export TF_VAR_codebuild_cache_bucket_name="iac-ci-codebuild-cache-$TF_VAR_random_str"
    export TF_VAR_codebuild_log_bucket_name="iac-ci-codebuild-log-$TF_VAR_random_str"
    export TF_VAR_tmp_bucket_name="iac-ci-tmp-$TF_VAR_random_str"
    export TF_VAR_stateful_bucket_name="iac-ci-stateful-$TF_VAR_random_str"
    export TF_VAR_log_bucket_name="iac-ci-log-$TF_VAR_random_str"
    export TF_VAR_runs_bucket_name="iac-ci-runs-$TF_VAR_random_str"
    
    # TRIGGER_ID generation
    local SECRET_OBJ="${TF_VAR_tmp_bucket_name}.${TF_VAR_lambda_bucket_name}.${TF_VAR_stateful_bucket_name}"
    local SECRET=$(python3 -c "import hashlib; print(hashlib.md5('$SECRET_OBJ'.encode('utf-8')).hexdigest())")
    local TRIGGER_OBJ="${SECRET}.${APP_NAME_IAC}"
    export TRIGGER_ID=$(python3 -c "import hashlib; print(hashlib.md5('$TRIGGER_OBJ'.encode('utf-8')).hexdigest())")
    
    # Add the generated variables to the environment file
    cat <<EOL >> "$ENV_FILE"

# Dynamically generated variables
export TF_VAR_random_str="$TF_VAR_random_str"
export WEBHOOK_SECRET="$WEBHOOK_SECRET"
export STATEFUL_ID="$STATEFUL_ID"
export TRIGGER_ID="$TRIGGER_ID"

# Generated bucket names
export TF_VAR_lambda_bucket_name="$TF_VAR_lambda_bucket_name"
export TF_VAR_codebuild_cache_bucket_name="$TF_VAR_codebuild_cache_bucket_name"
export TF_VAR_codebuild_log_bucket_name="$TF_VAR_codebuild_log_bucket_name"
export TF_VAR_tmp_bucket_name="$TF_VAR_tmp_bucket_name"
export TF_VAR_stateful_bucket_name="$TF_VAR_stateful_bucket_name"
export TF_VAR_log_bucket_name="$TF_VAR_log_bucket_name"
export TF_VAR_runs_bucket_name="$TF_VAR_runs_bucket_name"
EOL
  fi
}

authenticate_and_check_prerequisites() {
  # Check required environment variables
  check_required_env_var "GITHUB_TOKEN"
  check_optional_env_var "INFRACOST_API_KEY"
  check_optional_env_var "SLACK_WEBHOOK_HASH"

  # Authenticate to github
  gh auth login
}

create_ssh_keys() {
  # Check if FIRST_REPO_TO_REGISTER_PRIVATE_SSH_KEY_HASH is already set in the environment file
  if grep -q "FIRST_REPO_TO_REGISTER_PRIVATE_SSH_KEY_HASH" "$ENV_FILE"; then
    log_info "SSH keys already created. Using existing FIRST_REPO_TO_REGISTER_PRIVATE_SSH_KEY_HASH."
    return
  fi

  mkdir -p $IAC_REPO_SSH_KEYS_LOCAL_DIR
  ssh-keygen -t rsa -b 2048 -C "$IAC_REPO_SSH_KEYS_EMAIL" -f $IAC_REPO_SSH_KEYS_LOCAL_DIR/${IAC_FIRST_REPO_TO_REGISTER} -N ""
  export FIRST_REPO_TO_REGISTER_PRIVATE_SSH_KEY_HASH=$(base64  $IAC_REPO_SSH_KEYS_LOCAL_DIR/${IAC_FIRST_REPO_TO_REGISTER} -w0)
  export FIRST_REPO_TO_REGISTER_PUBLIC_SSH_KEY_HASH=$(base64  $IAC_REPO_SSH_KEYS_LOCAL_DIR/${IAC_FIRST_REPO_TO_REGISTER}.pub -w0)

  echo -e "\n# SSH Keys\nexport FIRST_REPO_TO_REGISTER_PRIVATE_SSH_KEY_HASH=\"$FIRST_REPO_TO_REGISTER_PRIVATE_SSH_KEY_HASH\"" >> "$ENV_FILE"
  echo -e "\n# SSH Keys\nexport FIRST_REPO_TO_REGISTER_PUBLIC_SSH_KEY_HASH=\"$FIRST_REPO_TO_REGISTER_PUBLIC_SSH_KEY_HASH\"" >> "$ENV_FILE"
  echo -e "\n# SSH Keys\nexport TF_VAR_public_key_hash=\"$FIRST_REPO_TO_REGISTER_PUBLIC_SSH_KEY_HASH\"" >> "$ENV_FILE"
}

create_s3_buckets() {
  cd $SRCDIR/deployment/1-s3-buckets
  tofu init
  tofu plan
  tofu apply -auto-approve
}

upload_lambda_function() {
  cd $SRCDIR
  local S3_BUCKET=$TF_VAR_lambda_bucket_name
  local TMP_BUILD_DIR="/tmp/iac-ci-build"
  
  rm -rf $TMP_BUILD_DIR
  mkdir -p $TMP_BUILD_DIR || exit 9
  unzip artifacts/base.iac-ci-system-lambda.zip -d $TMP_BUILD_DIR || exit 9
  cp -rp src/* $TMP_BUILD_DIR/ || exit 9
  rm -rf /tmp/iac-ci-system.zip  || exit 9
  cd $TMP_BUILD_DIR || exit 9
  zip -r /tmp/iac-ci-system.zip . || exit 9
  cd .. || exit 9
  rm -rf $TMP_BUILD_DIR || exit 9
  
  aws s3 cp /tmp/iac-ci-system.zip s3://$S3_BUCKET/iac-ci-system.zip
  
  log_info "# isolating functions with a copy of code"
  
  for S3_KEY_COPY in iac-ci-pkgcode-to-s3.zip iac-ci-process-webhook.zip iac-ci-trigger-codebuild.zip iac-ci-trigger-lambda.zip iac-ci-update-pr.zip iac-ci-check-codebuild.zip 
  do
      aws s3 cp s3://$S3_BUCKET/iac-ci-system.zip s3://$S3_BUCKET/$S3_KEY_COPY
  done
}

install_iac_ci_executors() {
  cd $SRCDIR
  log_info "creating ${EXECUTORS_BUILD_ENV_VARS_FILE} file"
  cat <<EOL > $EXECUTORS_BUILD_ENV_VARS_FILE
export BASE_DIR_EXECUTORS="${IAC_BUILD_DIR}/build/executors"
export TF_VAR_environment_name="$TF_VAR_environment_name"
export TF_VAR_codebuild_cache_bucket_name="$TF_VAR_codebuild_cache_bucket_name"
export TF_VAR_codebuild_log_bucket_name="$TF_VAR_codebuild_log_bucket_name"
export TF_VAR_tmp_bucket_name="$TF_VAR_tmp_bucket_name"
export TF_VAR_lambda_bucket_name="$TF_VAR_lambda_bucket_name"
export TF_VAR_stateful_bucket_name="$TF_VAR_stateful_bucket_name"
export TF_VAR_log_bucket_name="$TF_VAR_log_bucket_name"
export TF_VAR_runs_bucket_name="$TF_VAR_runs_bucket_name"
export TF_VAR_aws_default_region="us-east-1"
EOL

  source $EXECUTORS_BUILD_ENV_VARS_FILE

  BACKEND_BASE_DIR_EXECUTORS="$(dirname "$BASE_DIR_EXECUTORS")"
  mkdir -p ${IAC_BUILD_DIR}/build/executors
  create_backend_tf "$BASE_DIR_EXECUTORS" "iac-ci"
  
  cd deployment/2-lambda-and-codebuild-executors/
  ./create.sh
}

install_dynamodb() {
  cd $SRCDIR
  create_backend_tf "$SRCDIR/deployment/3-dynamodb" "iac-ci-system/dynamodb"
  run_terraform "$SRCDIR/deployment/3-dynamodb"
}

install_lambda_functions() {
  cd $SRCDIR
  export TF_VAR_s3_bucket=$TF_VAR_lambda_bucket_name
  export TF_VAR_bucket_names="[\"$TF_VAR_lambda_bucket_name\",\"$TF_VAR_stateful_bucket_name\",\"$TF_VAR_tmp_bucket_name\",\"$TF_VAR_log_bucket_name\",\"$TF_VAR_runs_bucket_name\"]"
  create_backend_tf "$SRCDIR/deployment/4-lambda" "iac-ci-system/lambda-funcs"
  run_terraform "$SRCDIR/deployment/4-lambda"
}

install_step_functions() {
  cd $SRCDIR
  create_backend_tf "$SRCDIR/deployment/5-stepfunc" "iac-ci-system/stepfunc"
  run_terraform "$SRCDIR/deployment/5-stepfunc"
}

install_trigger_lambda() {
  cd $SRCDIR
  export S3_BUCKET=$TF_VAR_lambda_bucket_name
  export TF_VAR_s3_bucket=$TF_VAR_lambda_bucket_name
  export TF_VAR_lambda_name="iac-ci-lambda_trigger_stepf"
  export TF_VAR_s3_key="iac-ci-lambda_trigger_stepf.zip"
  export TF_VAR_bucket_names="[\"$TF_VAR_lambda_bucket_name\",\"$TF_VAR_stateful_bucket_name\",\"$TF_VAR_tmp_bucket_name\",\"$TF_VAR_log_bucket_name\",\"$TF_VAR_runs_bucket_name\"]"
  
  cd deployment/6-trigger-stepf/lambda/
  ./docker-to-lambda.sh || exit 9
  cd -
  
  create_backend_tf "$SRCDIR/deployment/6-trigger-stepf/terraform" "iac-ci-system/trigger-stepf"
  run_terraform "$SRCDIR/deployment/6-trigger-stepf/terraform"
}

install_github_repo_params() {
  cd $SRCDIR
  export TF_VAR_url=${BASE_URL}/${TRIGGER_ID}
  export TF_VAR_secret=$WEBHOOK_SECRET
  export TF_VAR_public_key_hash=$FIRST_REPO_TO_REGISTER_PUBLIC_SSH_KEY_HASH
  create_backend_tf "$SRCDIR/deployment/9-github-params" "iac-ci-system/repo/${IAC_FIRST_REPO_TO_REGISTER}/github-params"
  run_terraform "$SRCDIR/deployment/9-github-params"
  log_info "webhook url \"${BASE_URL}/${TRIGGER_ID}\""
}

install_api_gateway() {
  cd $SRCDIR

  export TF_VAR_lambda_name="iac-ci-lambda_trigger_stepf"
  create_backend_tf "$SRCDIR/deployment/7-api-gateway" "iac-ci-system/api-gateway"
  run_terraform "$SRCDIR/deployment/7-api-gateway"

  # Capture the base_url from Terraform output
  BASE_URL=$(cd $SRCDIR/deployment/7-api-gateway && tofu output -raw base_url)

  if [ ! -z "$BASE_URL" ]; then
    log_info "API Gateway URL: $BASE_URL"
    export BASE_URL

    # Add BASE_URL to environment file if not already there
    if ! grep -q "BASE_URL" "$ENV_FILE"; then
      echo -e "\n# API Gateway URL\nexport BASE_URL=\"$BASE_URL\"" >> "$ENV_FILE"
    else
      # Update existing BASE_URL in environment file
      sed -i "s|export BASE_URL=.*|export BASE_URL=\"$BASE_URL\"|" "$ENV_FILE"
    fi
  else
    log_info "Warning: Could not capture base_url from Terraform output"
  fi
}

install_sns_topic_subscription() {
  cd $SRCDIR
  
  export TF_VAR_lambda_name="iac-ci-check-codebuild"
  
  create_backend_tf "$SRCDIR/deployment/8-sns_topic_subscription" "iac-ci-system/sns-topic-subscription"
  run_terraform "$SRCDIR/deployment/8-sns_topic_subscription"
}

upload_ssm_parameters() {
  cd $SRCDIR
  
  aws ssm put-parameter \
    --name $SSM_GITHUB_TOKEN \
    --type "SecureString" \
    --value $GITHUB_TOKEN \
    --overwrite || (log_info "cannot upload $SSM_GITHUB_TOKEN to ssm" && exit 2)
  
  aws ssm put-parameter \
    --name $SSM_SSH_KEY \
    --type "SecureString" \
    --value $FIRST_REPO_TO_REGISTER_PRIVATE_SSH_KEY_HASH \
    --overwrite || (log_info "cannot upload $SSM_SSH_KEY to ssm" && exit 2)

  aws ssm put-parameter \
    --name $SSM_INFRACOST_API_KEY \
    --type "SecureString" \
    --value $INFRACOST_API_KEY \
    --overwrite || (log_info "cannot upload $SSM_SSM_INFRACOST_API_KEY to ssm" && exit 2)

  aws ssm put-parameter \
    --name $SSM_SLACK_WEBHOOK_HASH \
    --type "SecureString" \
    --value $SLACK_WEBHOOK_HASH \
    --overwrite || (log_info "cannot upload $SSM_SLACK_WEBHOOK_HASH to ssm" && exit 2)
}

configure_repo_information() {
  cd $SRCDIR
  
  export TF_VAR_url="$BASE_URL/$TRIGGER_ID"
  export TF_VAR_secret=$WEBHOOK_SECRET

  cat <<EOF > /tmp/repo_data_dynamodb.json
{
  "_id": {
    "S": "$TRIGGER_ID"
  },
  "trigger_id": {
    "S": "$TRIGGER_ID"
  },
  "app_name_iac": {
    "S": "iac-ci"
  },
  "iac_ci_repo": {
    "S": "$REPO_NAME"
  },
  "repo_name": {
    "S": "$REPO_NAME"
  },
  "secret": {
    "S": "$WEBHOOK_SECRET"
  },
  "run_title": {
    "S": "iac-ci"
  },
  "ssm_ssh_key": {
    "S": "$SSM_SSH_KEY"
  },
  "ssm_iac_ci_github_token": {
    "S": "$SSM_GITHUB_TOKEN"
  },
  "s3_bucket_tmp": {
    "S": "$TF_VAR_tmp_bucket_name"
  },
  "remote_stateful_bucket": {
    "S": "$TF_VAR_stateful_bucket_name"
  },
  "type": {
    "S": "registered_repo"
  },
  "ssm_slack_webhook_hash": {
    "S": "$SSM_SLACK_WEBHOOK_HASH"
  },
  "ssm_infracost_api_key": {
    "S": "$SSM_INFRACOST_API_KEY"
  }
}
EOF
  aws dynamodb put-item --table-name iac-ci-settings --item file:///tmp/repo_data_dynamodb.json && log_info "repo data uploaded"
  rm -rf /tmp/repo_data_dynamodb.json
}

configure_iac_code_information() {
  cd $SRCDIR

  local BRANCH="test"
  local FOLDER="test"
  local STRING_OBJECT="iac_ci.${TRIGGER_ID}.${BRANCH}"
  local _ID=$(echo -n "$STRING_OBJECT" | md5sum | awk '{print $1}')

  cat <<EOF > /tmp/iac-code-data.json
{
  "_id": {
    "S": "$_ID"
  },
  "iac_ci_repo": {
    "S": "$REPO_NAME"
  },
  "repo_name": {
    "S": "$REPO_NAME"
  },
  "trigger_id": {
    "S": "$TRIGGER_ID"
  },
  "run_title": {
    "S": "iac-ci"
  },
  "source_method": {
    "S": "terraform"
  },
  "stateful_id": {
    "S": "$STATEFUL_ID"
  },
  "tf_runtime": {
    "S": "tofu:1.9.1"
  },
  "app_name": {
    "S": "terraform"
  },
  "app_dir": {
    "S": "var/tmp/terraform"
  },
  "run_share_dir": {
    "S": "var/tmp/$STATEFUL_ID"
  },
  "type": {
    "S": "iac_setting"
  },
  "require_approval": {
    "S": "False"
  },
  "iac_ci_folder": {
    "S": "$FOLDER"
  },
  "apply_str": {
    "S": "apply tf"
  },
  "check_str": {
    "S": "check tf"
  },
  "destroy_str": {
    "S": "destroy tf"
  }
}
EOF
  
  aws dynamodb put-item --table-name iac-ci-settings --item file:///tmp/iac-code-data.json && log_info "iac code data uploaded"
  rm -rf /tmp/iac-code-data.json
}

# ===== MAIN EXECUTION =====
main() {
  initialize_variables
  authenticate_and_check_prerequisites
  create_ssh_keys
  create_s3_buckets
  upload_lambda_function
  install_iac_ci_executors
  install_dynamodb
  install_lambda_functions
  install_step_functions
  install_trigger_lambda
  install_api_gateway
  install_sns_topic_subscription
  upload_ssm_parameters
  configure_repo_information
  configure_iac_code_information
  install_github_repo_params
}

# Execute main function
main