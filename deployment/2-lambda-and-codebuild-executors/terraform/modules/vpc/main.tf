locals {
  # Define public subnets across availability zones
  public_subnets = {
    "${var.aws_default_region}a" = "10.10.71.0/24"
    "${var.aws_default_region}b" = "10.10.72.0/24"
  }
  
  # Define private subnets across availability zones
  private_subnets = {
    "${var.aws_default_region}a" = "10.10.81.0/24"
    "${var.aws_default_region}b" = "10.10.82.0/24"
  }
}

# Main VPC with DNS support enabled
resource "aws_vpc" "main" {
  cidr_block           = "10.10.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
}

# Internet Gateway for public internet access
resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.main.id
}

# Public subnets with auto-assigned public IPs
resource "aws_subnet" "public" {
  count                   = length(local.public_subnets)
  cidr_block              = element(values(local.public_subnets), count.index)
  vpc_id                  = aws_vpc.main.id
  map_public_ip_on_launch = true
  availability_zone       = element(keys(local.public_subnets), count.index)
}

# Private subnets
resource "aws_subnet" "private" {
  count                   = length(local.private_subnets)
  cidr_block              = element(values(local.private_subnets), count.index)
  vpc_id                  = aws_vpc.main.id
  map_public_ip_on_launch = true
  availability_zone       = element(keys(local.private_subnets), count.index)
}

#-------------------------------------------------
# Routing
#-------------------------------------------------

# Use default route table for public routes
resource "aws_default_route_table" "public" {
  default_route_table_id = aws_vpc.main.main_route_table_id
}

# Add internet gateway route to public route table
resource "aws_route" "public_internet_gateway" {
  count                  = length(local.public_subnets)
  route_table_id         = aws_default_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id

  timeouts {
    create = "5m"
  }
}

# Associate public subnets with public route table
resource "aws_route_table_association" "public" {
  count          = length(local.public_subnets)
  subnet_id      = element(aws_subnet.public.*.id, count.index)
  route_table_id = aws_default_route_table.public.id
}

# Create separate route table for private subnets
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
}

# Associate private subnets with private route table
resource "aws_route_table_association" "private" {
  count          = length(local.private_subnets)
  subnet_id      = element(aws_subnet.private.*.id, count.index)
  route_table_id = aws_route_table.private.id
}

# S3 VPC endpoint for private access to S3
resource "aws_vpc_endpoint" "s3_endpoint" {
  vpc_id          = aws_vpc.main.id
  service_name    = "com.amazonaws.${var.aws_default_region}.s3"
  route_table_ids = [aws_route_table.private.id, aws_default_route_table.public.id]
}

# DynamoDB VPC endpoint for private access to DynamoDB
resource "aws_vpc_endpoint" "dynamodb_endpoint" {
  vpc_id          = aws_vpc.main.id
  service_name    = "com.amazonaws.${var.aws_default_region}.dynamodb"
  route_table_ids = [aws_route_table.private.id, aws_default_route_table.public.id]
}

#-------------------------------------------------
# Create NAT Gateway (commented out)
#-------------------------------------------------
#
# resource "aws_nat_gateway" "default" {
#   allocation_id = aws_eip.default.id
#   subnet_id     = aws_subnet.private[0].id
# }
#
# resource "aws_eip" "default" {
#   vpc = true
# }
#

#-------------------------------------------------
# Outputs
#-------------------------------------------------

# VPC ID for reference by other resources
output "vpc_id" {
  value       = aws_vpc.main.id
  description = "The ID of the VPC"
}

# First private subnet ID
output "private_subnet_id" {
  value       = aws_subnet.private[0].id
  description = "The ID of the first private subnet"
}

# List of all public subnet IDs
output "public_subnet_ids" {
  value       = aws_subnet.public[*].id
  description = "List of all public subnet IDs"
}
