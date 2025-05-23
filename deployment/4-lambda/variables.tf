# AWS Configuration
variable "aws_default_region" {
  description = "The default AWS region where resources will be created"
  type        = string
  default     = "eu-west-1"
}

variable "s3_bucket" {
  description = "The name of the S3 bucket to use for Lambda function code storage"
  type        = string
}

# Lambda Configuration
variable "runtime" {
  description = "The runtime environment for the Lambda function"
  type        = string
  default     = "python3.9"
}

variable "lambda_layers" {
  description = "ARN of the Lambda Layer to use with the Lambda function"
  type        = string
  default     = null
}

variable "memory_size" {
  description = "Amount of memory in MB allocated to the Lambda function"
  type        = number
  default     = 128
}

variable "lambda_timeout" {
  description = "Timeout in seconds for the Lambda function"
  type        = number
  default     = 900
}

variable "lambda_env_vars" {
  description = "Environmental variables for Lambda functions as a map"
  type        = map(string)
  default     = {}
}

variable "lambda_functions" {
  description = "Map of Lambda functions with their configurations"
  type        = map(object({
    handler = string
  }))
}

# S3 Configuration
variable "bucket_names" {
  description = "List of S3 bucket names to be created or referenced"
  type        = list(string)
}

# Resource Tagging
variable "cloud_tags" {
  description = "Additional tags as a map to be applied to all resources"
  type        = map(string)
  default     = {}
}