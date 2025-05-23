variable "product" {
  description = "The product or service name for resource identification"
  type        = string
  default     = "lambda"
}

variable "aws_default_region" {
  description = "AWS region where resources will be deployed"
  type        = string
  default     = "eu-west-1"
}

# S3 Configuration
variable "s3_bucket" {
  description = "S3 bucket containing the Lambda deployment package"
  type        = string
}

variable "s3_key" {
  description = "S3 key (path) to the Lambda deployment package"
  type        = string
}

# Resource Naming
variable "lambda_name" {
  description = "Name of the Lambda function to be created"
  type        = string
}

variable "step_function_name" {
  description = "Name of the Step Function to be created"
  type        = string
}

# Lambda Configuration
variable "handler" {
  description = "Lambda function handler entry point"
  type        = string
  default     = "app.handler"
}

variable "runtime" {
  description = "Lambda runtime environment"
  type        = string
  default     = "python3.9"
}

variable "lambda_layers" {
  description = "ARN of Lambda layer to attach to the function"
  type        = string
  default     = null
}

variable "memory_size" {
  description = "Memory allocation for Lambda function in MB"
  type        = number
  default     = 128
}

variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 900
}

variable "lambda_env_vars" {
  description = "Environment variables for Lambda function"
  type        = map(string)
  default     = {}
}

# Access Configuration
variable "assume_policy" {
  description = "IAM assume role policy for Lambda execution"
  default = <<EOF
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

# Additional Resources
variable "bucket_names" {
  description = "List of S3 bucket names to grant Lambda access to"
  type        = list(string)
}

variable "cloud_tags" {
  description = "Additional tags to apply to the resources"
  type        = map(string)
  default     = {}
}