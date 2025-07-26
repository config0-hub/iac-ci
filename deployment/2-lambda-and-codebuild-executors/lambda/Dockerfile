FROM public.ecr.aws/docker/library/python:3.10 AS build

ENV PYTHON_RELEASE=3.10
ENV BUILD_DIR=/var/tmp/build

RUN mkdir -p $BUILD_DIR

RUN /bin/bash -c "cd $BUILD_DIR && \
    python3 -m venv $BUILD_DIR/venv && \
    source $BUILD_DIR/venv/bin/activate && \
    pip install --upgrade pip"

RUN echo $PYTHON_VERSION

COPY requirements.txt /tmp/requirements.txt

WORKDIR $BUILD_DIR/venv/lib/python${PYTHON_RELEASE}/site-packages

RUN /bin/bash -c "source $BUILD_DIR/venv/bin/activate && \
    pip3 install --upgrade pip && \
    pip3 install setuptools_rust && \
    pip3 install -r /tmp/requirements.txt && \
    rm -rf /tmp/requirements.txt"

RUN mv $BUILD_DIR/venv/lib/python${PYTHON_RELEASE}/site-packages $BUILD_DIR/app

FROM public.ecr.aws/docker/library/alpine:3.18.4

ARG pkg_name=PleaseSetPkgName
ARG s3_bucket=PleaseSetS3Bucket

ENV LAMBDA_PKG_NAME=$pkg_name
ENV S3_BUCKET=$s3_bucket
ENV LAMBDA_PKG_DIR=package/lambda
ENV BUILD_DIR=/var/tmp/build

RUN apk add --no-cache python3 py3-pip zip && \
    rm -rf /var/cache/apk/*

RUN pip3 install --upgrade pip
RUN pip3 install --no-cache-dir awscli

RUN mkdir -p $BUILD_DIR/$LAMBDA_PKG_DIR

COPY --from=build $BUILD_DIR/app $BUILD_DIR/app
ADD main.py $BUILD_DIR/app
ADD main_tf.py $BUILD_DIR/app
RUN chown -R root:root $BUILD_DIR/app

RUN cd $BUILD_DIR/app && \
    zip -q -r9 $BUILD_DIR/$LAMBDA_PKG_DIR/$LAMBDA_PKG_NAME . && \
    echo "Lambda package found here: $BUILD_DIR/$LAMBDA_PKG_DIR/$LAMBDA_PKG_NAME.zip"
