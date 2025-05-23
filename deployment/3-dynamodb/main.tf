resource "aws_dynamodb_table" "default" {
  for_each = toset(var.dynamodb_names)  # Convert list to a set for unique values

  name         = each.key                 # Use the current item from the list as the table name
  billing_mode = var.billing_mode         # Use the same billing mode for all tables
  hash_key     = var.hash_key             # Use the same hash key for all tables

  attribute {
    name = var.hash_key                   # Attribute definition for the hash key
    type = "S"                            # Type of the attribute (String)
  }

  ttl {
    attribute_name = "expire_at"         # TTL attribute name
    enabled        = true                  # Enable TTL
  }

  tags = merge(
    var.cloud_tags,                       # Merge user-defined tags
    {
      Product = var.product               # Additional tag for product
    },
  )
}
