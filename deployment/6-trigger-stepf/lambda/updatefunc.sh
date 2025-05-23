source /tmp/.credentials/aws/iam-test-user-2.txt

export S3_BUCKET=app-env.lambda.williaumwu.3e5e8
export S3_KEY=iac-ci-trigger-lambda.zip

#s3://iac-ci-lambda-iacciexjtf/iac-ci-trigger-lambda.zip

for FUNC_NAME in iac-ci-lambda_trigger_stepf
do
   echo ""
   echo "updating function $FUNC_NAME"
   echo ""
   aws lambda update-function-code --function-name $FUNC_NAME \
   --s3-key $S3_KEY \
   --s3-bucket $S3_BUCKET &
   sleep 2
done
