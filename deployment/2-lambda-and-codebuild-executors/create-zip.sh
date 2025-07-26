#!/bin/bash

# Default environment variables
CURRENT_PWD=$(pwd)

TMPDIR=${TMPDIR:=/var/tmp}
BUILD_DIR=$BASE_DIR_EXECUTORS

LAMBDA_PKG_NAME=${LAMBDA_PKG_NAME:=base}
LAMBDA_PKG_DIR=${LAMBDA_PKG_DIR:=/var/tmp/build/package/lambda}
DOCKER_TEMP_IMAGE=${DOCKER_TEMP_IMAGE:=temp-lambda-pkg}
DOCKERFILE_LAMBDA=${DOCKERFILE_LAMBDA:=Dockerfile}
EXECUTORS_BUILD_ENV_VARS_FILE=${EXECUTORS_BUILD_ENV_VARS_FILE:=/tmp/.build_executors_vars.env}

# Source environment variables file if it exists
if [ -f "${EXECUTORS_BUILD_ENV_VARS_FILE}" ]; then
    echo "Sourcing environment variables from ${EXECUTORS_BUILD_ENV_VARS_FILE}"
    source "${EXECUTORS_BUILD_ENV_VARS_FILE}"
else
    echo "Environment variables file ${EXECUTORS_BUILD_ENV_VARS_FILE} not found, using defaults"
fi

# Setup build directory
setup_build_dir() {
    echo "Setting up BUILD_DIR ${BUILD_DIR}"
    echo "Making directory BUILD_DIR ${BUILD_DIR}"
    mkdir -p ${BUILD_DIR} || echo "Build directory already exists"
    echo "DONE: Setting up BUILD_DIR ${BUILD_DIR}"
}

# Build lambda package
build_lambda_package() {
    echo -e "\nBuilding lambda package\n"

    echo "Copying lambda to build dir"
    cp -rp lambda ${BUILD_DIR}/ || exit 4
    
    echo "Copying Dockerfile to build dir"
    cp -rp lambda/$DOCKERFILE_LAMBDA ${BUILD_DIR}/lambda/iac-ci-executors || exit 5
    
    cd ${BUILD_DIR}/lambda/iac-ci-executors || exit 6
    
    echo "Executing build of lambda function"
    echo "######################################################"
    echo "# Variables"
    echo "######################################################"
    echo "LAMBDA_PKG_NAME => ${LAMBDA_PKG_NAME}"
    echo "DOCKER_TEMP_IMAGE => ${DOCKER_TEMP_IMAGE}"
    echo "######################################################"

    # Build Docker image
    docker build --build-arg pkg_name=$LAMBDA_PKG_NAME -t $DOCKER_TEMP_IMAGE . -f $DOCKERFILE_LAMBDA || exit 9
    rm -rf $DOCKERFILE_LAMBDA

    # Create container and extract zip file
    docker create --name $DOCKER_TEMP_IMAGE $DOCKER_TEMP_IMAGE || { echo "Could not create docker image"; exit 9; }
    echo -e "\n"
    docker cp $DOCKER_TEMP_IMAGE:$LAMBDA_PKG_DIR/base.zip ./base.zip || { echo "Could not copy base.zip file from docker image"; exit 9; }
    echo -e "\n"
    docker rm $DOCKER_TEMP_IMAGE > /dev/null 2>&1

    # Process the zip file
    rm -rf temp
    mkdir temp || echo "directory may already exists"
    unzip base.zip -d temp || { echo "Could not unzip file"; exit 9; }
    cp -rp iac_ci temp/ || { echo "Could not copy iac-ci/* files"; exit 9; }
    cp -rp main.py temp/ || { echo "Could not copy main.py/* files"; exit 9; }
    
    cd temp || exit 9
    rm -rf ${TMPDIR}/iac-ci.zip || exit 9
    zip -r ${TMPDIR}/iac-ci.zip . || exit 9
    cp -rp ${TMPDIR}/iac-ci.zip /tmp/iac-ci-executors.zip || echo "copy failed"
    cd ..
    rm -rf temp || exit 9
    echo ""
}

# Print completion message
print_completion() {
    echo "#################################################################"
    echo ""
    echo "iac-ci-executors.zip found in /tmp"
    echo ""
    echo "#################################################################"
}

##############################################################
# Main script execution
##############################################################
main() {
    cd $CURRENT_PWD
    
    # Setup build directory
    setup_build_dir
    
    echo "Building lambda package"
    build_lambda_package

    print_completion
}

# Execute main function
main
