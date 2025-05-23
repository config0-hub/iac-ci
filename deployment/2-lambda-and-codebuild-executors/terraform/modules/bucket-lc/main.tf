# Variables
variable "aws_default_region" {
  description = "AWS region for the S3 bucket"
  type        = string
}

variable "bucket" {
  description = "Name of the S3 bucket to create"
  type        = string
}

variable "expire_days" {
  description = "Number of days after which objects expire"
  type        = number
}

variable "cloud_tags" {
  description = "Map of cloud tags to apply to resources"
  type        = map(string)
}

# S3 Bucket Resource
resource "aws_s3_bucket" "default" {
  bucket        = var.bucket
  acl           = "private"
  force_destroy = true

  # Merge default_tags with the bucket-specific Name tag
  tags = merge(
    var.cloud_tags,
    {
      Name = var.bucket
    }
  )

  lifecycle_rule {
    enabled = true

    expiration {
      days = var.expire_days
    }

    noncurrent_version_expiration {
      days = var.expire_days
    }
  }

  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }
}

# Outputs
output "bucket_arn" {
  description = "ARN of the created S3 bucket"
  value       = aws_s3_bucket.default.arn
}

output "bucket_name" {
  description = "Name of the created S3 bucket"
  value       = aws_s3_bucket.default.bucket
}
