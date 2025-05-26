source /tmp/.credentials/aws/iam.txt
export S3_BUCKET=
export S3_KEY=iac-ci.zip

for FUNC_NAME in iac-ci-trigger-codebuild iac-ci-check-codebuild iac-ci-trigger-lambda iac-ci-pkgcode-to-s3 iac-ci-process-webhook iac-ci-update-pr
do
   echo ""
   echo "updating function $FUNC_NAME"
   echo ""
   aws lambda update-function-code --function-name $FUNC_NAME \
   --s3-key $S3_KEY \
   --s3-bucket $S3_BUCKET &
   sleep 2
done
