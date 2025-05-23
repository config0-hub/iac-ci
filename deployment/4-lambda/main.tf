#------------------------------------------------------------------
# Infrastructure as Code CI/CD Pipeline Lambda Functions
# This configuration defines AWS Lambda functions that work together in a CI/CD pipeline

# Variables:
# s3_bucket          - S3 bucket where Lambda deployment packages are stored
# runtime            - Runtime environment for Lambda functions (e.g., python3.8)
# memory_size        - Memory allocation for Lambda functions in MB
# lambda_timeout     - Maximum execution time allowed for Lambda functions
# lambda_layers      - Lambda layers for shared code and dependencies
# aws_default_region - AWS region for resource deployment
# lambda_env_vars    - Environment variables for Lambda functions
# cloud_tags         - Resource tags for all Lambda functions
# bucket_names       - S3 bucket names used in the pipeline
#------------------------------------------------------------------

# Process webhook events from source control systems
module "process-webhook" {
  source             = "./modules/lambda"
  s3_key             = "iac-ci-process-webhook.zip"
  lambda_name        = "iac-ci-process-webhook"
  handler            = "app_webhook.handler"
  s3_bucket          = var.s3_bucket
  runtime            = var.runtime
  memory_size        = var.memory_size
  lambda_timeout     = var.lambda_timeout
  lambda_layers      = var.lambda_layers
  aws_default_region = var.aws_default_region
  lambda_env_vars    = var.lambda_env_vars
  cloud_tags         = var.cloud_tags
  bucket_names       = var.bucket_names
}

# Trigger AWS CodeBuild projects for infrastructure testing
module "trigger-codebuild" {
  source             = "./modules/lambda"
  s3_key             = "iac-ci-trigger-codebuild.zip"
  lambda_name        = "iac-ci-trigger-codebuild"
  handler            = "app_codebuild.handler"
  s3_bucket          = var.s3_bucket
  runtime            = var.runtime
  memory_size        = var.memory_size
  lambda_timeout     = var.lambda_timeout
  lambda_layers      = var.lambda_layers
  aws_default_region = var.aws_default_region
  lambda_env_vars    = var.lambda_env_vars
  cloud_tags         = var.cloud_tags
  bucket_names       = var.bucket_names
}

# Package code and upload to S3 for deployment
module "pkgcode-to-s3" {
  source             = "./modules/lambda"
  s3_key             = "iac-ci-pkgcode-to-s3.zip"
  lambda_name        = "iac-ci-pkgcode-to-s3"
  handler            = "app_s3.handler"
  s3_bucket          = var.s3_bucket
  runtime            = var.runtime
  memory_size        = var.memory_size
  lambda_timeout     = var.lambda_timeout
  lambda_layers      = var.lambda_layers
  aws_default_region = var.aws_default_region
  lambda_env_vars    = var.lambda_env_vars
  cloud_tags         = var.cloud_tags
  bucket_names       = var.bucket_names
}

# Monitor CodeBuild execution status and process results
module "check-codebuild" {
  source             = "./modules/lambda"
  s3_key             = "iac-ci-check-codebuild.zip"
  lambda_name        = "iac-ci-check-codebuild"
  handler            = "app_check_build.handler"
  s3_bucket          = var.s3_bucket
  runtime            = var.runtime
  memory_size        = var.memory_size
  lambda_timeout     = var.lambda_timeout
  lambda_layers      = var.lambda_layers
  aws_default_region = var.aws_default_region
  lambda_env_vars    = var.lambda_env_vars
  cloud_tags         = var.cloud_tags
  bucket_names       = var.bucket_names
}

# Trigger downstream Lambda functions in the pipeline
module "trigger-lambda" {
  source             = "./modules/lambda"
  s3_key             = "iac-ci-trigger-lambda.zip"
  lambda_name        = "iac-ci-trigger-lambda"
  handler            = "app_lambda.handler"
  s3_bucket          = var.s3_bucket
  runtime            = var.runtime
  memory_size        = var.memory_size
  lambda_timeout     = var.lambda_timeout
  lambda_layers      = var.lambda_layers
  aws_default_region = var.aws_default_region
  lambda_env_vars    = var.lambda_env_vars
  cloud_tags         = var.cloud_tags
  bucket_names       = var.bucket_names
}

# Update pull request status with pipeline results
module "update-pr" {
  source             = "./modules/lambda"
  s3_key             = "iac-ci-update-pr.zip"
  lambda_name        = "iac-ci-update-pr"
  handler            = "app_pr.handler"
  s3_bucket          = var.s3_bucket
  runtime            = var.runtime
  memory_size        = var.memory_size
  lambda_timeout     = var.lambda_timeout
  lambda_layers      = var.lambda_layers
  aws_default_region = var.aws_default_region
  lambda_env_vars    = var.lambda_env_vars
  cloud_tags         = var.cloud_tags
  bucket_names       = var.bucket_names
}