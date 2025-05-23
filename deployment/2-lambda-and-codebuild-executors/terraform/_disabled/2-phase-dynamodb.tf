resource "aws_dynamodb_table" "iac-ci-tmp" {
  name             = "${var.environment_name}-tmp"
  billing_mode     = "PAY_PER_REQUEST"  # On-demand capacity
  hash_key         = "_id"              # Partition key

  attribute {
    name = "_id"
    type = "S"    # String type
  }

  ttl {
    attribute_name = "expire_at"  # TTL attribute for automatic item deletion
    enabled        = true
  }

  tags = {
    Name = "${var.environment_name}-tmp"
  }
}