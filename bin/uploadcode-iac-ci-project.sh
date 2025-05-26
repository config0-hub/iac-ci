source /tmp/.credentials/aws/iam.txt
export S3_BUCKET=
export S3_KEY=
aws s3 cp /tmp/iac-ci.zip s3://$S3_BUCKET/$S3_KEY
