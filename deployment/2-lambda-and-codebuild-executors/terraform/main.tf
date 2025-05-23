# Retrieve current AWS account information
data "aws_caller_identity" "current" {}

# Local variables
locals {
  cloud_tags = {
    orchestrated_by = "iac-ci"
  }
}

# Environment name (e.g., dev, stage, prod)
variable "environment_name" {
  description = "Name of the environment being deployed"
  type        = string
}

# S3 bucket for CodeBuild cache storage
variable "codebuild_cache_bucket_name" {
  description = "Name of the S3 bucket for CodeBuild cache artifacts"
  type        = string
}

# S3 bucket for CodeBuild logs
variable "codebuild_log_bucket_name" {
  description = "Name of the S3 bucket for storing CodeBuild logs"
  type        = string
}

# S3 bucket for temporary file storage
variable "tmp_bucket_name" {
  description = "Name of the S3 bucket for temporary files"
  type        = string
}

# S3 bucket for Lambda artifacts
variable "lambda_bucket_name" {
  description = "Name of the S3 bucket for Lambda function code and artifacts"
  type        = string
}

# S3 bucket for stateful resources
variable "stateful_bucket_name" {
  description = "Name of the S3 bucket for storing stateful resources"
  type        = string
}

# S3 bucket for application logs
variable "log_bucket_name" {
  description = "Name of the S3 bucket for application logging"
  type        = string
}

# S3 bucket for run results
variable "runs_bucket_name" {
  description = "Name of the S3 bucket for storing run results"
  type        = string
}

# AWS region for resource deployment
variable "aws_default_region" {
  description = "AWS region where resources will be deployed"
  type        = string
}

variable "cloud_tags" {
  type        = map(string)
  description = "Tags to apply to all created resources"
}
