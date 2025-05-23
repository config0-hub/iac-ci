runtime 	        = "python3.9"
memory_size 	        = 256
lambda_timeout 	        = 900
lambda_layers 	        = "arn:aws:lambda:us-east-1:553035198032:layer:git-lambda2:8"

lambda_functions = {
  "process-webhook" = {
    handler = "app_webhook.handler"
  },
  "trigger-codebuild" = {
    handler = "app_codebuild.handler"
  },
  "pkgcode-to-s3" = {
    handler = "app_s3.handler"
  },
  "check-codebuild" = {
    handler = "app_check_build.handler"
  },
  "trigger-lambda" = {
    handler = "app_lambda.handler"
  },
  "update-pr" = {
    handler = "app_pr.handler"
  }
}
