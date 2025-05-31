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

# ===== ENVIRONMENT SETUP =====
readonly SRCDIR="$(pwd)"
readonly IAC_BUILD_DIR="${IAC_BUILD_DIR:-/var/tmp/iac-ci}"
readonly ENV_FILE="${IAC_BUILD_DIR}/build_env_vars.env"

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
    echo "Usage: $0 <REPO_NAME> <BRANCH> <IAC_FOLDER> [OPTIONS]"
    echo ""
    echo "Add IAC configuration to a registered repository"
    echo ""
    echo "Arguments:"
    echo "  REPO_NAME     Name of the registered repository"
    echo "  BRANCH        Branch to monitor for changes"
    echo "  IAC_FOLDER    Folder containing IAC code"
    echo ""
    echo "Options:"
    echo "  --source-method METHOD    IAC tool (default: terraform)"
    echo "  --runtime VERSION         Runtime version (default: tofu:1.9.1)"
    echo "  --app-name NAME          Application name (default: terraform)"
    echo "  --app-dir DIR            Working directory (default: var/tmp/terraform)"
    echo "  --require-approval BOOL   Require approval (default: False)"
    echo "  --apply-str STRING       Apply command string (default: 'apply tf')"
    echo "  --check-str STRING       Check command string (default: 'check tf')"
    echo "  --destroy-str STRING     Destroy command string (default: 'destroy tf')"
    echo ""
    echo "Example:"
    echo "  $0 my-infrastructure-repo main infrastructure"
    echo "  $0 my-app-repo develop terraform --source-method pulumi --runtime pulumi:3.0"
    exit 1
}

if [ $# -lt 3 ]; then
    usage
fi

readonly REPO_NAME="$1"
readonly BRANCH="$2"
readonly IAC_FOLDER="$3"
shift 3

# Default values
SOURCE_METHOD="terraform"
RUNTIME="tofu:1.9.1"
APP_NAME="terraform"
APP_DIR="var/tmp/terraform"
REQUIRE_APPROVAL="False"
APPLY_STR="apply tf"
CHECK_STR="check tf"
DESTROY_STR="destroy tf"

# Parse optional arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --source-method)
            SOURCE_METHOD="$2"
            shift 2
            ;;
        --runtime)
            RUNTIME="$2"
            shift 2
            ;;
        --app-name)
            APP_NAME="$2"
            shift 2
            ;;
        --app-dir)
            APP_DIR="$2"
            shift 2
            ;;
        --require-approval)
            REQUIRE_APPROVAL="$2"
            shift 2
            ;;
        --apply-str)
            APPLY_STR="$2"
            shift 2
            ;;
        --check-str)
            CHECK_STR="$2"
            shift 2
            ;;
        --destroy-str)
            DESTROY_STR="$2"
            shift 2
            ;;
        *)
            log_info "ERROR: Unknown option $1"
            usage
            ;;
    esac
done

log_info "Configuring IAC for repository: $REPO_NAME"
log_info "Branch: $BRANCH"
log_info "IAC Folder: $IAC_FOLDER"
log_info "Source Method: $SOURCE_METHOD"
log_info "Runtime: $RUNTIME"

# ===== MAIN FUNCTIONS =====
verify_repo_registered() {
    log_info "Verifying repository is registered: $REPO_NAME"
    
    # Try to load repo configuration
    local repo_config_file="${IAC_BUILD_DIR}/repo_${REPO_NAME}_config.env"
    
    if [ ! -f "$repo_config_file" ]; then
        log_info "ERROR: Repository configuration not found: $repo_config_file"
        log_info "Please register the repository first using register_repo.sh"
        exit 1
    fi
    
    source "$repo_config_file"
    
    # Verify required variables are loaded
    check_required_env_var "TRIGGER_ID" "TRIGGER_ID not found in repository configuration"
    
    log_info "Repository $REPO_NAME is registered with TRIGGER_ID: $TRIGGER_ID"
}

generate_iac_identifiers() {
    log_info "Generating IAC configuration identifiers"
    
    # Generate unique STATEFUL_ID for this IAC configuration
    export STATEFUL_ID=$(generate_random_string iac-ci- 10)
    
    # Generate unique _ID for DynamoDB entry
    local STRING_OBJECT="iac_ci.${TRIGGER_ID}.${BRANCH}"
    export IAC_CONFIG_ID=$(echo -n "$STRING_OBJECT" | md5sum | awk '{print $1}')
    
    # Generate run share directory
    export RUN_SHARE_DIR="var/tmp/$STATEFUL_ID"
    
    log_info "Generated STATEFUL_ID: $STATEFUL_ID"
    log_info "Generated IAC_CONFIG_ID: $IAC_CONFIG_ID"
}

add_iac_config_to_dynamodb() {
    log_info "Adding IAC configuration to DynamoDB"
    
    local json_file="/tmp/iac_config_${REPO_NAME}_${BRANCH}_$$.json"
    
    cat > "$json_file" <<EOF
{
  "_id": {
    "S": "$IAC_CONFIG_ID"
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
    "S": "$SOURCE_METHOD"
  },
  "stateful_id": {
    "S": "$STATEFUL_ID"
  },
  "tf_runtime": {
    "S": "$RUNTIME"
  },
  "app_name": {
    "S": "$APP_NAME"
  },
  "app_dir": {
    "S": "$APP_DIR"
  },
  "run_share_dir": {
    "S": "$RUN_SHARE_DIR"
  },
  "type": {
    "S": "iac_setting"
  },
  "require_approval": {
    "S": "$REQUIRE_APPROVAL"
  },
  "iac_ci_folder": {
    "S": "$IAC_FOLDER"
  },
  "apply_str": {
    "S": "$APPLY_STR"
  },
  "check_str": {
    "S": "$CHECK_STR"
  },
  "destroy_str": {
    "S": "$DESTROY_STR"
  },
  "branch": {
    "S": "$BRANCH"
  }
}
EOF

    aws dynamodb put-item --table-name iac-ci-settings --item "file://$json_file" || {
        log_info "ERROR: Failed to add IAC configuration to DynamoDB"
        rm -f "$json_file"
        exit 1
    }
    
    rm -f "$json_file"
    log_info "Successfully added IAC configuration to DynamoDB"
}

save_iac_config() {
    log_info "Saving IAC configuration"
    
    local iac_config_file="${IAC_BUILD_DIR}/iac_${REPO_NAME}_${BRANCH}_${IAC_FOLDER//\//_}_config.env"
    
    cat > "$iac_config_file" <<EOF
# IAC configuration for: $REPO_NAME/$BRANCH/$IAC_FOLDER
# Generated on: $(date)

export REPO_NAME="$REPO_NAME"
export BRANCH="$BRANCH"
export IAC_FOLDER="$IAC_FOLDER"
export TRIGGER_ID="$TRIGGER_ID"
export STATEFUL_ID="$STATEFUL_ID"
export IAC_CONFIG_ID="$IAC_CONFIG_ID"
export SOURCE_METHOD="$SOURCE_METHOD"
export RUNTIME="$RUNTIME"
export APP_NAME="$APP_NAME"
export APP_DIR="$APP_DIR"
export RUN_SHARE_DIR="$RUN_SHARE_DIR"
export REQUIRE_APPROVAL="$REQUIRE_APPROVAL"
export APPLY_STR="$APPLY_STR"
export CHECK_STR="$CHECK_STR"
export DESTROY_STR="$DESTROY_STR"
EOF

    log_info "IAC configuration saved to: $iac_config_file"
}

# ===== MAIN EXECUTION =====
main() {
    log_info "Starting IAC configuration for: $REPO_NAME/$BRANCH/$IAC_FOLDER"
    
    verify_repo_registered
    generate_iac_identifiers
    add_iac_config_to_dynamodb
    save_iac_config
    
    log_info "Successfully configured IAC workflow for: $REPO_NAME/$BRANCH/$IAC_FOLDER"
    log_info ""
    log_info "Configuration details:"
    log_info "  Repository: $REPO_NAME"
    log_info "  Branch: $BRANCH"
    log_info "  IAC Folder: $IAC_FOLDER"
    log_info "  Source Method: $SOURCE_METHOD"
    log_info "  Runtime: $RUNTIME"
    log_info "  Requires Approval: $REQUIRE_APPROVAL"
    log_info ""
    log_info "The repository will now monitor changes to the '$BRANCH' branch"
    log_info "in the '$IAC_FOLDER' folder for IAC deployments."
}

# Execute main function
main "$@"