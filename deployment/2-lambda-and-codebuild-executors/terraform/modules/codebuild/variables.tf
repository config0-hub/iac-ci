variable "aws_default_region" {
  type        = string
  description = "Default AWS region for resources"
  default     = "us-east-1"
}

variable "num_of_projects" {
  type        = number
  description = "Number of projects to create"
  default     = 5
}

variable "build_image" {
  type        = string
  description = "CodeBuild container image (7.0 is Ubuntu 22.04)"
  default     = "aws/codebuild/standard:7.0"
}

variable "image_type" {
  type        = string
  description = "Type of container image to use"
  default     = "LINUX_CONTAINER"
}

variable "s3_bucket" {
  type        = string
  description = "S3 bucket for project artifacts"
}

variable "s3_bucket_cache" {
  type        = string
  description = "S3 bucket for caching build artifacts"
}

variable "s3_bucket_log" {
  type        = string
  description = "S3 bucket for storing build logs"
}

variable "environment_name" {
  type        = string
  description = "Environment name (e.g., dev, prod, staging)"
}

variable "privileged_mode" {
  type        = bool
  description = "Whether to run the Docker daemon inside a Docker container"
  default     = true
}

variable "description" {
  type        = string
  description = "Description for the CodeBuild project"
  default     = "Codebuild project"
}

variable "build_timeout" {
  type        = string
  description = "Number of minutes before build times out"
  default     = "90"
}

variable "compute_type" {
  type        = string
  description = "CodeBuild instance type to use for build"
  default     = "BUILD_GENERAL1_SMALL"
}

variable "aws_account_id" {
  type        = string
  description = "AWS account ID where resources will be created"
}

variable "cloud_tags" {
  type        = map(string)
  description = "Tags to apply to all created resources"
}
