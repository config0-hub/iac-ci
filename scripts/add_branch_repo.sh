#!/bin/bash

# Function to generate a random string
generate_random_string() {
    local prefix="$1"
    local length="${2:-16}"  # Default length is 16 if not specified
    local random_string=$(LC_ALL=C tr -dc 'a-z0-9' < /dev/urandom | head -c "$length")
    echo "${prefix}${random_string}"
}

# Function to display usage information
usage() {
    echo "Usage: $0 <branch> [options] [folder]"
    echo "Options:"
    echo "  --tf-runtime <runtime>    Specify Terraform/OpenTofu runtime (default: tofu:1.9.1)"
    echo ""
    echo "If folder is not specified, branch value will be used as the folder."
    exit 1
}

# Check for minimum arguments
if [ $# -lt 1 ]; then
    usage
fi

# Default values
TF_RUNTIME="tofu:1.9.1"
BRANCH=""
FOLDER=""

# Parse arguments
while [ "$1" != "" ]; do
    case $1 in
        --tf-runtime )       shift
                            TF_RUNTIME="$1"
                            ;;
        --help )            usage
                            ;;
        -* )                echo "Unknown option: $1"
                            usage
                            ;;
        * )                 if [ -z "$BRANCH" ]; then
                                BRANCH="$1"
                            elif [ -z "$FOLDER" ]; then
                                FOLDER="$1"
                            else
                                echo "Too many positional arguments."
                                usage
                            fi
                            ;;
    esac
    shift
done

# Validate required arguments
if [ -z "$BRANCH" ]; then
    echo "Error: Branch argument is required."
    usage
fi

# Set folder to branch if not provided
if [ -z "$FOLDER" ]; then
    FOLDER="$BRANCH"
fi

echo "Using branch: $BRANCH"
echo "Using folder: $FOLDER"
echo "Using TF runtime: $TF_RUNTIME"

# ===== ENVIRONMENT SETUP =====
IAC_BUILD_DIR=${IAC_BUILD_DIR:=/var/tmp/iac-ci}
ENV_FILE=${IAC_BUILD_DIR}/build_env_vars.env

# Check if env file exists and source it if it does
if [ -f "$ENV_FILE" ]; then
    echo "Found existing environment file. Loading variables from $ENV_FILE"
    source "$ENV_FILE"
    
    # Check for required variables
    if [ -z "$TRIGGER_ID" ]; then
        echo "Error: Required variable TRIGGER_ID not found in environment file."
        exit 1
    fi
    
    if [ -z "$REPO_NAME" ]; then
        echo "Error: Required variable REPO_NAME not found in environment file."
        exit 1
    fi
else
    echo "Error: Environment file not found at $ENV_FILE"
    echo "Please run the initialization script first to generate required variables."
    exit 1
fi

# Generate a new STATEFUL_ID for this run (only thing that changes each time)
STATEFUL_ID=$(generate_random_string "iac-ci-" 10)
echo "Generated new STATEFUL_ID: $STATEFUL_ID"

# ===== MAIN FUNCTION =====
configure_iac_code_information() {
    # Generate unique ID for this configuration
    local STRING_OBJECT="iac_ci.${TRIGGER_ID}.${BRANCH}"
    local _ID=$(echo -n "$STRING_OBJECT" | md5sum | awk '{print $1}')

    echo "Creating configuration with ID: $_ID"
    echo "TRIGGER_ID: $TRIGGER_ID"
    echo "STATEFUL_ID: $STATEFUL_ID"
    echo "REPO_NAME: $REPO_NAME"

    # Create the JSON data for DynamoDB
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
    "S": "$TF_RUNTIME"
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
  "iac_ci_branch": {
    "S": "$BRANCH"
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
    
    # Insert the data into DynamoDB
    echo "Uploading configuration to DynamoDB table: iac-ci-settings..."
    aws dynamodb put-item --table-name iac-ci-settings --item file:///tmp/iac-code-data.json
    
    if [ $? -eq 0 ]; then
        echo "✅ Successfully uploaded configuration for branch '$BRANCH' and folder '$FOLDER'"
        echo "💡 Use these values in your commands:"
        echo "   Branch: $BRANCH"
        echo "   Folder: $FOLDER"
        echo "   Stateful ID: $STATEFUL_ID"
    else
        echo "❌ Failed to upload configuration to DynamoDB"
        exit 1
    fi
    
    # Clean up
    rm -f /tmp/iac-code-data.json
}

# Execute main function
configure_iac_code_information