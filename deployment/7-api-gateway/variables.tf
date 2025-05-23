variable "stage" {
  description = "Deployment stage identifier"
  type        = string
  default     = "v1"
}

variable "resource_name" {
  description = "Name for the CodeBuild resource"
  type        = string
  default     = "codebuild"
}

variable "lambda_name" {
  description = "Name of the Lambda function"
  type        = string
}

variable "apigateway_name" {
  description = "Name of the API Gateway"
  type        = string
  default     = "api-test"
}

variable "aws_default_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "eu-west-1"
}

variable "cloud_tags" {
  description = "Additional tags as a map"
  type        = map(string)
  default     = {}
}