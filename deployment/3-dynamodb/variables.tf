variable "dynamodb_names" {
  description = "List of DynamoDB table names to be created"
  type        = list(string)
}

variable "product" {
  description = "Product identifier for resource naming and tagging"
  type        = string
  default     = "dynamodb"
}

variable "aws_default_region" {
  description = "AWS region where resources will be deployed"
  type        = string
  default     = "eu-west-1"
}

variable "billing_mode" {
  description = "DynamoDB billing mode (PAY_PER_REQUEST or PROVISIONED)"
  type        = string
  default     = "PAY_PER_REQUEST"
}

variable "hash_key" {
  description = "Name of the hash key attribute for DynamoDB tables"
  type        = string
  default     = "_id"
}

variable "cloud_tags" {
  description = "Additional tags to apply to all resources as a map"
  type        = map(string)
  default     = {}
}