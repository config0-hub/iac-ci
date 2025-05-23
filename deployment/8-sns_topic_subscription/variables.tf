variable "topic_name" {
  type        = string
  description = "The name of the SNS topic to which build notifications will be sent"
}

variable "aws_default_region" {
  type        = string
  description = "The AWS region where resources will be deployed"
  default     = "eu-west-1"
}

variable "cloud_tags" {
  type        = map(string)
  description = "Additional tags to apply to all created resources"
  default     = {}
}

variable "lambda_name" {
  type        = string
  description = "The name of the Lambda function to be created"
}
