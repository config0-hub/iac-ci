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

variable "buildspec_hash" {
  type        = string
  description = "Buildspec template as a base64 hash"
  default     = "dmVyc2lvbjogMC4yCgplbnY6CiAgdmFyaWFibGVzOgogICAgVE1QRElSOiAvdG1wCgpwaGFzZXM6CiAgaW5zdGFsbDoKICAgIGNvbW1hbmRzOgogICAgICAtIGFwdC1nZXQgdXBkYXRlCiAgICAgIC0gYXB0LWdldCBpbnN0YWxsIC15IHVuemlwCiAgICAgIC0gY3VybCAtTE8gaHR0cHM6Ly9yZWxlYXNlcy5oYXNoaWNvcnAuY29tL3RlcnJhZm9ybS8xLjUuNC90ZXJyYWZvcm1fMS41LjRfbGludXhfYW1kNjQuemlwCiAgICAgIC0gdW56aXAgdGVycmFmb3JtXzEuNS40X2xpbnV4X2FtZDY0LnppcAogICAgICAtIG12IHRlcnJhZm9ybSAvdXNyL2xvY2FsL2Jpbi90ZXJyYWZvcm0KCiAgcHJlX2J1aWxkOgogICAgb24tZmFpbHVyZTogQUJPUlQKICAgIGNvbW1hbmRzOgogICAgICAtIGF3cyBzMyBjcCBzMzovLyRSRU1PVEVfU1RBVEVGVUxfQlVDS0VULyRTVEFURUZVTF9JRCAkVE1QRElSLyRTVEFURUZVTF9JRC50YXIuZ3ogLS1xdWlldAogICAgICAtIG1rZGlyIC1wICRUTVBESVIvdGVycmFmb3JtCiAgICAgIC0gdGFyIHhmeiAkVE1QRElSLyRTVEFURUZVTF9JRC50YXIuZ3ogLUMgJFRNUERJUi90ZXJyYWZvcm0KICAgICAgLSBybSAtcmYgJFRNUERJUi8kU1RBVEVGVUxfSUQudGFyLmd6CgogIGJ1aWxkOgogICAgb24tZmFpbHVyZTogQUJPUlQKICAgIGNvbW1hbmRzOgogICAgICAtIGNkICRUTVBESVIvdGVycmFmb3JtCiAgICAgIC0gL3Vzci9sb2NhbC9iaW4vdGVycmFmb3JtIGluaXQKICAgICAgLSAvdXNyL2xvY2FsL2Jpbi90ZXJyYWZvcm0gcGxhbiAtb3V0PXRmcGxhbgogICAgICAtIC91c3IvbG9jYWwvYmluL3RlcnJhZm9ybSBhcHBseSB0ZnBsYW4gfHwgL3Vzci9sb2NhbC9iaW4vdGVycmZvcm0gZGVzdHJveSAtYXV0by1hcHByb3ZlCgogIHBvc3RfYnVpbGQ6CiAgICBjb21tYW5kczoKICAgICAgLSBjZCAkVE1QRElSL3RlcnJhZm9ybQogICAgICAtIHRhciBjZnogJFRNUERJUi8kU1RBVEVGVUxfSUQudGFyLmd6IC4KICAgICAgLSBhd3MgczMgY3AgJFRNUERJUi8kU1RBVEVGVUxfSUQudGFyLmd6IHMzOi8vJFJFTU9URV9TVEFURUZVTF9CVUNLRVQvJFNUQVRFRlVMX0lEIC0tcXVpZXQKICAgICAgLSBybSAtcmYgJFRNUERJUi8kU1RBVEVGVUxfSUQudGFyLmd6CiAgICAgIC0gZWNobyAiIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIgogICAgICAtIGVjaG8gIiMgdXBsb2FkZWQgczM6Ly8kUkVNT1RFX1NUQVRFRlVMX0JVQ0tFVC8kU1RBVEVGVUxfSUQiCiAgICAgIC0gZWNobyAiIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIgo="
}