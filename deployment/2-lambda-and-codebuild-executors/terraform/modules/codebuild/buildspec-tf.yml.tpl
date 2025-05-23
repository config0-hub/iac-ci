version: 0.2

env:
  variables:
    TMPDIR: /tmp

phases:
  install:
    commands:
      - apt-get update
      - apt-get install -y unzip
      - curl -LO https://releases.hashicorp.com/terraform/1.5.4/terraform_1.5.4_linux_amd64.zip
      - unzip terraform_1.5.4_linux_amd64.zip
      - mv terraform /usr/local/bin/terraform

  pre_build:
    on-failure: ABORT
    commands:
      - aws s3 cp s3://$REMOTE_STATEFUL_BUCKET/$STATEFUL_ID $TMPDIR/$STATEFUL_ID.tar.gz --quiet
      - mkdir -p $TMPDIR/terraform
      - tar xfz $TMPDIR/$STATEFUL_ID.tar.gz -C $TMPDIR/terraform > /dev/null
      - rm -rf $TMPDIR/$STATEFUL_ID.tar.gz

  build:
    on-failure: ABORT
    commands:
      - cd $TMPDIR/terraform
      - /usr/local/bin/terraform init
      - /usr/local/bin/terraform plan -out=tfplan
      - /usr/local/bin/terraform apply tfplan || /usr/local/bin/terrform destroy -auto-approve

  post_build:
    commands:
      - cd $TMPDIR/terraform
      - tar cfz $TMPDIR/$STATEFUL_ID.tar.gz . > /dev/null
      - aws s3 cp $TMPDIR/$STATEFUL_ID.tar.gz s3://$REMOTE_STATEFUL_BUCKET/$STATEFUL_ID --quiet
      - rm -rf $TMPDIR/$STATEFUL_ID.tar.gz
      - echo "###############################################################"
      - echo "# uploaded s3://$REMOTE_STATEFUL_BUCKET/$STATEFUL_ID"
      - echo "###############################################################"
