#!/bin/bash

# Enable strict mode for better error handling
set -e

# ===== UTILITY FUNCTIONS =====
log_info() {
    echo "[$(date '+%H:%M:%S')] $1"
}

generate_random_string() {
    local prefix="$1"
    local length="${2:-16}"
    
    # Generate lowercase random string using /dev/urandom
    local random_string=$(LC_ALL=C tr -dc 'a-z0-9' < /dev/urandom | head -c "$length")
    echo "${prefix}${random_string}"
}

check_required_env_var() {
    local var_name="$1"
    local error_message="${2:-Required environment variable $var_name is not set}"
    
    if [ -z "${!var_name:-}" ]; then
        log_info "ERROR: $error_message"
        exit 1
    fi
}

create_backend_tf() {
    local directory="$1"
    local key="$2"
    
    mkdir -p "$directory"
    cat > "$directory/backend.tf" <<EOL
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
    local directory="$1"
    local original_dir="$(pwd)"
    
    log_info "Running Terraform in $directory"
    cd "$directory"
    tofu init
    tofu plan
    tofu apply -auto-approve
    cd "$original_dir"
}

# ===== ENVIRONMENT SETUP =====
export SRCDIR="$(pwd)"
export IAC_BUILD_DIR="${IAC_BUILD_DIR:-/var/tmp/iac-ci}"
export ENV_FILE="${IAC_BUILD_DIR}/build_env_vars.env"
export IAC_REPO_SSH_KEYS_LOCAL_DIR="${IAC_BUILD_DIR}/github/ssh_keys"
export IAC_REPO_SSH_KEYS_EMAIL="iac-ci@iac-ci.com"

# Load existing environment
if [ ! -f "$ENV_FILE" ]; then
    log_info "ERROR: Environment file not found at $ENV_FILE"
    log_info "Please run the main installation script first."
    exit 1
fi

log_info "Loading environment from $ENV_FILE"
source "$ENV_FILE"

# ===== PARAMETER VALIDATION =====
usage() {
    echo "Usage: $0 <REPO_NAME>"
    echo ""
    echo "Register a new GitHub repository for IAC CI/CD"
    echo ""
    echo "Arguments:"
    echo "  REPO_NAME    Name of the GitHub repository to register"
    echo ""
    echo "Example:"
    echo "  $0 my-infrastructure-repo"
    exit 1
}

if [ $# -ne 1 ]; then
    usage
fi

export NEW_REPO_NAME="$1"

# Validate required environment variables from main installation
check_required_env_var "TF_VAR_stateful_bucket_name"
check_required_env_var "TF_VAR_tmp_bucket_name"
check_required_env_var "TF_VAR_lambda_bucket_name"
check_required_env_var "TF_VAR_log_bucket_name"
check_required_env_var "TF_VAR_runs_bucket_name"
check_required_env_var "BASE_URL"
check_required_env_var "SSM_GITHUB_TOKEN"
check_required_env_var "SSM_INFRACOST_API_KEY"
check_required_env_var "SSM_SLACK_WEBHOOK_HASH"
check_required_env_var "GITHUB_TOKEN"

# ===== MAIN FUNCTIONS =====
generate_repo_identifiers() {
    log_info "Generating identifiers for repository: $NEW_REPO_NAME"
    
    # Generate unique identifiers for this repository
    export NEW_WEBHOOK_SECRET=$(generate_random_string iac-ci- 20)
    
    # Generate TRIGGER_ID using the same logic as main script
    local SECRET_OBJ="${TF_VAR_tmp_bucket_name}.${TF_VAR_lambda_bucket_name}.${TF_VAR_stateful_bucket_name}.${NEW_REPO_NAME}"
    local SECRET=$(python3 -c "import hashlib; print(hashlib.md5('$SECRET_OBJ'.encode('utf-8')).hexdigest())")
    local TRIGGER_OBJ="${SECRET}.${NEW_REPO_NAME}"
    export NEW_TRIGGER_ID=$(python3 -c "import hashlib; print(hashlib.md5('$TRIGGER_OBJ'.encode('utf-8')).hexdigest())")
    
    # Generate SSM parameter path for this repo
    export NEW_SSM_SSH_KEY="/iac-ci/github/repo/${NEW_REPO_NAME}/private_key"
    
    log_info "Generated TRIGGER_ID: $NEW_TRIGGER_ID"
    log_info "Generated SSM SSH Key path: $NEW_SSM_SSH_KEY"
}

create_repo_ssh_keys() {
    log_info "Creating SSH keys for repository: $NEW_REPO_NAME"
    
    mkdir -p "$IAC_REPO_SSH_KEYS_LOCAL_DIR"
    
    local key_path="${IAC_REPO_SSH_KEYS_LOCAL_DIR}/${NEW_REPO_NAME}"
    
    # Check if keys already exist
    if [ -f "$key_path" ]; then
        log_info "SSH keys already exist for $NEW_REPO_NAME, using existing keys"
    else
        ssh-keygen -t rsa -b 2048 -C "$IAC_REPO_SSH_KEYS_EMAIL" -f "$key_path" -N ""
        log_info "Created new SSH key pair for $NEW_REPO_NAME"
    fi
    
    export NEW_PRIVATE_SSH_KEY_HASH=$(base64 -w0 "$key_path")
    export NEW_PUBLIC_SSH_KEY_HASH=$(base64 -w0 "${key_path}.pub")
}

upload_repo_ssm_parameters() {
    log_info "Uploading SSH key to SSM for repository: $NEW_REPO_NAME"
    
    aws ssm put-parameter \
        --name "$NEW_SSM_SSH_KEY" \
        --type "SecureString" \
        --value "$NEW_PRIVATE_SSH_KEY_HASH" \
        --description "SSH private key for repository $NEW_REPO_NAME" \
        --overwrite || {
        log_info "ERROR: Failed to upload SSH key to SSM: $NEW_SSM_SSH_KEY"
        exit 1
    }
}

configure_github_repo_params() {
    log_info "Configuring GitHub repository parameters for: $NEW_REPO_NAME"
    
    export TF_VAR_url="${BASE_URL}/${NEW_TRIGGER_ID}"
    export TF_VAR_secret="$NEW_WEBHOOK_SECRET"
    export TF_VAR_public_key_hash="$NEW_PUBLIC_SSH_KEY_HASH"
    export TF_VAR_repository="$NEW_REPO_NAME"
    
    local terraform_dir="$SRCDIR/deployment/9-github-params"
    local backend_key="iac-ci-system/repo/${NEW_REPO_NAME}/github-params"
    
    create_backend_tf "$terraform_dir" "$backend_key"
    run_terraform "$terraform_dir"
    
    log_info "Webhook URL for $NEW_REPO_NAME: ${BASE_URL}/${NEW_TRIGGER_ID}"
}

register_repo_in_dynamodb() {
    log_info "Registering repository in DynamoDB: $NEW_REPO_NAME"
    
    local json_file="/tmp/repo_data_${NEW_REPO_NAME}_$$.json"
    
    cat > "$json_file" <<EOF
{
  "_id": {
    "S": "$NEW_TRIGGER_ID"
  },
  "trigger_id": {
    "S": "$NEW_TRIGGER_ID"
  },
  "app_name_iac": {
    "S": "iac-ci"
  },
  "iac_ci_repo": {
    "S": "$NEW_REPO_NAME"
  },
  "repo_name": {
    "S": "$NEW_REPO_NAME"
  },
  "secret": {
    "S": "$NEW_WEBHOOK_SECRET"
  },
  "run_title": {
    "S": "iac-ci"
  },
  "ssm_ssh_key": {
    "S": "$NEW_SSM_SSH_KEY"
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

    aws dynamodb put-item --table-name iac-ci-settings --item "file://$json_file" || {
        log_info "ERROR: Failed to register repository in DynamoDB"
        rm -f "$json_file"
        exit 1
    }
    
    rm -f "$json_file"
    log_info "Successfully registered repository $NEW_REPO_NAME in DynamoDB"
}

save_repo_config() {
    log_info "Saving repository configuration"
    
    local repo_config_file="${IAC_BUILD_DIR}/repo_${NEW_REPO_NAME}_config.env"
    
    cat > "$repo_config_file" <<EOF
# Repository configuration for: $NEW_REPO_NAME
# Generated on: $(date)

export REPO_NAME="$NEW_REPO_NAME"
export TRIGGER_ID="$NEW_TRIGGER_ID"
export WEBHOOK_SECRET="$NEW_WEBHOOK_SECRET"
export SSM_SSH_KEY="$NEW_SSM_SSH_KEY"
export WEBHOOK_URL="${BASE_URL}/${NEW_TRIGGER_ID}"
export PRIVATE_SSH_KEY_HASH="$NEW_PRIVATE_SSH_KEY_HASH"
export PUBLIC_SSH_KEY_HASH="$NEW_PUBLIC_SSH_KEY_HASH"
EOF

    log_info "Repository configuration saved to: $repo_config_file"
}

# ===== MAIN EXECUTION =====
main() {
    log_info "Starting repository registration for: $NEW_REPO_NAME"
    
    generate_repo_identifiers
    create_repo_ssh_keys
    upload_repo_ssm_parameters
    configure_github_repo_params
    register_repo_in_dynamodb
    save_repo_config
    
    log_info "Successfully registered repository: $NEW_REPO_NAME"
    log_info "Webhook URL: ${BASE_URL}/${NEW_TRIGGER_ID}"
    log_info ""
    log_info "Next steps:"
    log_info "1. Add the webhook URL to your GitHub repository settings"
    log_info "2. Use add_iac_config.sh to configure IAC workflows for specific branches/folders"
}

# Execute main function
main
