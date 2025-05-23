#!/bin/bash

export DOCKER_TEMP_IMAGE=${DOCKER_TEMP_IMAGE:=temp-lambda-pkg}
export PYTHON_VERSION=${PYTHON_VERSION:=3.8}
export CODEBUILD_ENV=${CODEBUILD_ENV:=true}

export MAJOR_VERSION=$(echo $PYTHON_VERSION | cut -d "." -f 1)
export MINOR_VERSION=$(echo $PYTHON_VERSION | cut -d "." -f 2)
export PYTHON_RELEASE="${MAJOR_VERSION}.${MINOR_VERSION}"

export SHARE_DIR=${SHARE_DIR:=/var/tmp/share}
export LAMBDA_PKG_NAME=${LAMBDA_PKG_NAME:=iac-ci-lambda_trigger_stepf}
export LAMBDA_PKG_DIR=${LAMBDA_PKG_DIR:=package/lambda}
export S3_BUCKET=${S3_BUCKET:=test-lambda-bucket}
export DOCKERFILE_LAMBDA=${DOCKERFILE_LAMBDA:=Dockerfile}

######################################################
# Main
######################################################

# Check if S3_KEY is set
if [ -z "${S3_KEY}" ]; then
    # If S3_KEY is not set, assign it the value of LAMBDA_NAME
    export S3_KEY="${LAMBDA_PKG_NAME}"
fi

echo "######################################################"
echo "# Variables"
echo "######################################################"
echo "LAMBDA_PKG_NAME => ${LAMBDA_PKG_NAME}"
echo "S3_BUCKET => ${S3_BUCKET}"
echo "S3_KEY => ${S3_KEY}"
echo "DOCKER_TEMP_IMAGE => ${DOCKER_TEMP_IMAGE}"
echo "######################################################"

docker build --build-arg pkg_name=$LAMBDA_PKG_NAME \
             --build-arg s3_bucket=$S3_BUCKET \
             --build-arg python_release=$PYTHON_RELEASE \
             --build-arg python_version=$PYTHON_VERSION \
             --build-arg share_dir=$SHARE_DIR \
             --build-arg lambda_pkg_dir=$LAMBDA_PKG_DIR \
             -t $DOCKER_TEMP_IMAGE . \
             -f $DOCKERFILE_LAMBDA || exit 9

docker rm -fv ${DOCKER_TEMP_IMAGE}-run > /dev/null > 2&1 || echo "tried to remove previous run image"

if [ "$CODEBUILD_ENV" = "true" ]; then
    docker create --name ${DOCKER_TEMP_IMAGE}-run $DOCKER_TEMP_IMAGE || exit 5
    docker cp ${DOCKER_TEMP_IMAGE}-run:${SHARE_DIR}/${LAMBDA_PKG_DIR}/${LAMBDA_PKG_NAME}.zip /tmp/${LAMBDA_PKG_NAME}.zip || exit 6
    aws s3 cp /tmp/${LAMBDA_PKG_NAME}.zip s3://${S3_BUCKET}/${S3_KEY}.zip || exit 7
    docker rm ${DOCKER_TEMP_IMAGE}-run
else
    echo "AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID" > .env
    echo "AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY" >> .env
    echo "AWS_SESSION_TOKEN=$AWS_SESSION_TOKEN" >> .env
    echo "LAMBDA_PKG_NAME=${LAMBDA_PKG_NAME}" >> .env
    echo "S3_BUCKET=${S3_BUCKET}" >> .env
    echo "S3_KEY=${S3_KEY}" >> .env
    echo "DOCKER_TEMP_IMAGE=${DOCKER_TEMP_IMAGE}" >> .env
    docker run --rm -i --env-file .env $DOCKER_TEMP_IMAGE cp ${SHARE_DIR}/${LAMBDA_PKG_DIR}/${LAMBDA_PKG_NAME}.zip s3://${S3_BUCKET}/${S3_KEY}.zip || exit 6
    rm -rf .env
fi