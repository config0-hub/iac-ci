# General AWS Configuration
variable "product" {
  description = "Name of the product/service being deployed"
  type        = string
  default     = "lambda"
}

variable "aws_default_region" {
  description = "AWS region where resources will be deployed"
  type        = string
  default     = "eu-west-1"
}

variable "cloud_tags" {
  description = "Additional tags as a map to be applied to all resources"
  type        = map(string)
  default     = {}
}

# S3 Configuration
variable "s3_bucket" {
  description = "Name of the S3 bucket containing the Lambda deployment package"
  type        = string
}

variable "s3_key" {
  description = "S3 key (path) of the Lambda deployment package"
  type        = string
}

variable "bucket_names" {
  description = "List of S3 bucket names that Lambda will have access to"
  type        = list(string)
}

# Lambda Configuration
variable "lambda_name" {
  description = "Name of the Lambda function to be created"
  type        = string
}

variable "handler" {
  description = "Lambda function handler entry point (e.g., file.function_name)"
  type        = string
  default     = "app.handler"
}

variable "runtime" {
  description = "Lambda function runtime environment"
  type        = string
  default     = "python3.9"
}

variable "lambda_layers" {
  description = "ARN of Lambda layer(s) to attach to the function"
  type        = string
  default     = null
}

variable "memory_size" {
  description = "Memory allocation for Lambda function in MB"
  type        = number
  default     = 128
}

variable "lambda_timeout" {
  description = "Lambda function execution timeout in seconds"
  type        = number
  default     = 900
}

variable "lambda_env_vars" {
  description = "Environmental variables for Lambda function as a map"
  type        = map(string)
  default     = {}
}

variable "assume_policy" {
  description = "IAM policy document for Lambda execution role"
  default     = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
  ]
}
EOF
}