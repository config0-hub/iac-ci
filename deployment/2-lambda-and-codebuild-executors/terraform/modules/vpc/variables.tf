variable "aws_default_region" {
  type        = string
  default     = "us-east-1"
  description = "The default AWS region where resources will be created"
}

variable "vpc_name" {
  type        = string
  description = "The name to assign to the VPC resource"
}

variable "cloud_tags" {
  type        = map(string)
  description = "Map of cloud tags to apply to all resources"
}
