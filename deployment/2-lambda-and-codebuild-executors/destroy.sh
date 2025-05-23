#!/bin/bash

# Global variables
CURRENT_PWD=$(pwd)

TMPDIR=${TMPDIR:=/var/tmp}
BUILD_DIR=$BASE_DIR_EXECUTORS

# Destroy Terraform resources
destroy_tf() {
    echo "Destroying Terraform resources"
    
    cd "${BUILD_DIR}/terraform" || { 
        echo "Failed to change directory to ${BUILD_DIR}/terraform"
        exit 8
    }
    
    tofu init || {
        echo "Failed to initialize Terraform"
        exit 9
    }
    
    if ! tofu destroy -auto-approve; then
        local _STATUS=$?
        echo "Terraform destroy failed with exit status: $_STATUS"
        exit $_STATUS
    fi
    
    echo "Terraform destroy completed successfully"
}

# Print status messages
print_status() {
    echo "#################################################################"
    echo "$1"
    echo "#################################################################"
}

##############################################################
# Main script execution
##############################################################
main() {
    # Export variables to make them available to subprocesses
    export CURRENT_PWD
    export TMPDIR
    export BUILD_DIR
    destroy_tf
    print_status "Terraform destroy process completed"
}

# Execute main function
main