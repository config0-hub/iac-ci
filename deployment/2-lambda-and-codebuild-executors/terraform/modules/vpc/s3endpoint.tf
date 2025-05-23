# S3 VPC Endpoint
# This resource creates a VPC Endpoint that allows private access
# to the S3 service without traversing the public internet.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id  # ID of the VPC where the endpoint will be created
  service_name      = "com.amazonaws.${var.aws_default_region}.s3"  # S3 service name including the region
  vpc_endpoint_type = "Gateway"  # Type of VPC endpoint (Gateway for S3)
}
