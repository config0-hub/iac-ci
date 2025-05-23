variable "prefixes" {
  description = "List of prefixes for S3 bucket names (lambda, stateful, tmp)"
  type        = list(string)
  default     = ["lambda", "stateful", "tmp"]
}

variable "random_str" {
  description = "Optional random string for the bucket name (generates one if not provided)"
  type        = string
  default     = ""
}

resource "random_string" "bucket_name" {
  length  = 10
  special = false
  upper   = false
  lower   = true
  number  = false
}

resource "aws_s3_bucket" "default" {
  for_each = toset(var.prefixes)
  bucket   = "iac-ci-${each.key}-${var.random_str != "" ? var.random_str : random_string.bucket_name.result}"
  acl      = "private"

  lifecycle {
    prevent_destroy = false
  }

  lifecycle_rule {
    id      = "expire-objects"
    enabled = each.key == "tmp"

    expiration {
      days = 1
    }
  }

  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }

  tags = {
    Name = "iac-ci-${each.key}-${var.random_str != "" ? var.random_str : random_string.bucket_name.result}"
  }
}

output "bucket_names" {
  description = "List of all created S3 bucket IDs"
  value       = [for bucket in aws_s3_bucket.default : bucket.id]
}

output "random_str" {
  description = "Random string used in bucket names (user-provided or auto-generated)"
  value       = var.random_str != "" ? var.random_str : random_string.bucket_name.result
}