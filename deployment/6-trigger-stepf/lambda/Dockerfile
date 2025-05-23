ARG python_release=3.9
ARG python_version=3.9

FROM public.ecr.aws/docker/library/python:${python_version} as build

ARG python_release=3.9
ARG pkg_name=PleaseSetPkgName
ARG s3_bucket=PleaseSetS3Bucket
ARG share_dir=/var/tmp/share

ENV PYTHON_RELEASE=$python_release
ENV SHARE_DIR=$share_dir

RUN mkdir -p $SHARE_DIR

RUN /bin/bash -c "cd $SHARE_DIR && \
    python3 -m venv $SHARE_DIR/venv && \
    source $SHARE_DIR/venv/bin/activate && \
    pip install --upgrade pip"

RUN echo $PYTHON_VERSION

COPY requirements.txt /tmp/requirements.txt

WORKDIR $SHARE_DIR/venv/lib/python${PYTHON_RELEASE}/site-packages

RUN /bin/bash -c "source $SHARE_DIR/venv/bin/activate && \
    pip3 install --upgrade pip && \
    pip3 install setuptools_rust && \
    pip3 install -r /tmp/requirements.txt && \
    rm -rf /tmp/requirements.txt"

RUN mv $SHARE_DIR/venv/lib/python${PYTHON_RELEASE}/site-packages $SHARE_DIR/app

# create the upload container
FROM public.ecr.aws/docker/library/alpine:3.18.4

ARG python_release=3.9
ARG pkg_name=PleaseSetPkgName
ARG s3_bucket=PleaseSetS3Bucket
ARG share_dir=/var/tmp/share
ARG lambda_pkg_dir=package/lambda

ENV SHARE_DIR=$share_dir
ENV LAMBDA_PKG_NAME=$pkg_name
ENV S3_BUCKET=$s3_bucket
ENV LAMBDA_PKG_DIR=$lambda_pkg_dir

RUN apk add --no-cache python3 py3-pip zip tar gzip && \
    rm -rf /var/cache/apk/*

RUN pip3 install --upgrade pip 
RUN pip3 install --no-cache-dir awscli 

RUN mkdir -p $SHARE_DIR/$LAMBDA_PKG_DIR

COPY --from=build $SHARE_DIR/app $SHARE_DIR/app
ADD src.tar.gz $SHARE_DIR/app
RUN chown -R root:root $SHARE_DIR/app

RUN cd $SHARE_DIR/app && \
    zip -q -r9 $SHARE_DIR/$LAMBDA_PKG_DIR/$LAMBDA_PKG_NAME . && \
    echo "Lambda package found here: $SHARE_DIR/$LAMBDA_PKG_DIR/$LAMBDA_PKG_NAME.zip"

ENTRYPOINT ["aws", "s3" ]
