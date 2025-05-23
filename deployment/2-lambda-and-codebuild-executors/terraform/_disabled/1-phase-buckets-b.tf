#----------------------------------------------------
# S3 Resources
#----------------------------------------------------

# Lambda deployment package
# Stores the Lambda function ZIP file in S3
resource "aws_s3_bucket_object" "lambda" {
  bucket     = var.lambda_bucket_name     # S3 bucket for Lambda code storage
  key        = "${var.environment_name}.zip"  # Object key with environment name
  source     = "./lambda/iac-ci.zip"      # Path to local Lambda deployment package
  acl        = "private"                  # Access control setting
}

# Log bucket - stores application logs with retention policy
module "log-bucket" {
  source             = "./modules/bucket-lc"
  aws_default_region = var.aws_default_region  # AWS region for resource deployment
  bucket             = var.log_bucket_name     # Name of the logs bucket
  cloud_tags         = local.cloud_tags      # Resource tagging
  expire_days        = 365                     # Log retention period (1 year)
}

# Runs bucket - stores pipeline execution data
module "runs-bucket" {
  source             = "./modules/bucket-lc"
  aws_default_region = var.aws_default_region
  bucket             = var.runs_bucket_name    # Name of the execution data bucket
  cloud_tags         = local.cloud_tags
  expire_days        = 365                     # Data retention period (1 year)
}

# CodeBuild cache bucket - improves build performance
module "cache-bucket" {
  source             = "./modules/bucket-lc"
  aws_default_region = var.aws_default_region
  bucket             = var.codebuild_cache_bucket_name  # Cache storage bucket name
  cloud_tags         = local.cloud_tags
  expire_days        = 1                               # Short cache retention (1 day)
}

# CodeBuild log bucket - stores build logs
module "codebuild-log-bucket" {
  source             = "./modules/bucket-lc"
  aws_default_region = var.aws_default_region
  bucket             = var.codebuild_log_bucket_name   # Build logs bucket name
  cloud_tags         = local.cloud_tags
  expire_days        = 1                               # Log retention period (1 day)
}
