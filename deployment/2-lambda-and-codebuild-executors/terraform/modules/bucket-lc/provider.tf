# AWS Infrastructure Configuration

# Local block to sort tags for consistent ordering
locals {
  # Convert user-provided tags map to sorted list
  sorted_cloud_tags = [
    for k in sort(keys(var.cloud_tags)) : {
      key   = k
      value = var.cloud_tags[k]
    }
  ]
  
  # Create a sorted and consistent map of all tags
  all_tags = merge(
    # Convert sorted list back to map
    { for item in local.sorted_cloud_tags : item.key => item.value },
    {
      # Tag indicating infrastructure is managed by CI pipeline
      orchestrated_by = "iac-ci"
    }
  )
}

# AWS Provider Configuration
provider "aws" {
  # The AWS region where resources will be deployed
  region = var.aws_default_region
  
  # Default tags applied to all AWS resources with consistent ordering
  default_tags {
    tags = local.all_tags
  }
  
  # Optional configuration for tags to ignore during operations
  ignore_tags {}
}

# Terraform Configuration Block
terraform {
  # Minimum required Terraform version
  required_version = ">= 1.1.0"

  # Required provider specifications
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}