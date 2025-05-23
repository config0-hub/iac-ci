# GitHub Provider Configuration
# This Terraform configuration establishes the GitHub provider connection

terraform {
  required_version = ">= 1.1.0"  # Specifies the minimum compatible Terraform version
}

provider "github" {
  # The GitHub provider uses default authentication methods
  # Credentials are typically sourced from environment variables
}