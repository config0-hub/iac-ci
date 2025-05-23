# variables
variable "main_cidr" { default = "10.10.0.0/16" }
variable "public_subnet_a" { default = "10.10.101.0/24" }
variable "public_subnet_b" { default = "10.10.102.0/24" }
variable "private_subnet_a" { default = "10.10.201.0/24" }
variable "private_subnet_b" { default = "10.10.202.0/24" }

# vpc build below

resource "aws_security_group" "main" {
  name   = var.environment_name
  vpc_id = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  #ingress {
  #  from_port = 27017
  #  to_port = 27017
  #  protocol = "tcp"
  #  cidr_blocks = ["0.0.0.0/0"]
  #}

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.environment_name}-sg"
  }

}

locals {
  public_subnets = {
    "${var.aws_default_region}a" = var.public_subnet_a
    "${var.aws_default_region}b" = var.public_subnet_b
  }
  private_subnets = {
    "${var.aws_default_region}a" = var.private_subnet_a
    "${var.aws_default_region}b" = var.private_subnet_b
  }
}

resource "aws_vpc" "main" {
  cidr_block = var.main_cidr

  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.environment_name}"
  }
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.environment_name}-internet-gateway"
  }
}

resource "aws_subnet" "public" {
  count      = length(local.public_subnets)
  cidr_block = element(values(local.public_subnets), count.index)
  vpc_id     = aws_vpc.main.id

  map_public_ip_on_launch = true
  availability_zone       = element(keys(local.public_subnets), count.index)

  tags = {
    Name = "${var.environment_name}-service-public"
  }
}

resource "aws_subnet" "private" {
  count      = length(local.private_subnets)
  cidr_block = element(values(local.private_subnets), count.index)
  vpc_id     = aws_vpc.main.id

  map_public_ip_on_launch = true
  availability_zone       = element(keys(local.private_subnets), count.index)

  tags = {
    Name = "${var.environment_name}-service-private"
  }
}

resource "aws_default_route_table" "public" {
  default_route_table_id = aws_vpc.main.main_route_table_id

  tags = {
    Name = "${var.environment_name}-public"
  }
}

resource "aws_route" "public_internet_gateway" {
  count                  = length(local.public_subnets)
  route_table_id         = aws_default_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id

  timeouts {
    create = "5m"
  }
}

resource "aws_route_table_association" "public" {
  count          = length(local.public_subnets)
  subnet_id      = element(aws_subnet.public.*.id, count.index)
  route_table_id = aws_default_route_table.public.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.environment_name}-private"
  }
}

resource "aws_route_table_association" "private" {
  count          = length(local.private_subnets)
  subnet_id      = element(aws_subnet.private.*.id, count.index)
  route_table_id = aws_route_table.private.id
}

######################## default endpoints

resource "aws_vpc_endpoint" "s3" {
  depends_on      = [aws_vpc.main]
  vpc_id          = aws_vpc.main.id
  service_name    = "com.amazonaws.${var.aws_default_region}.s3"
  route_table_ids = [aws_route_table.private.id, aws_default_route_table.public.id]
  tags = {
    Product = "vpc_endpoint"
    Name    = "s3-gw-endpt-${var.environment_name}"
  }
}

resource "aws_vpc_endpoint" "dynamodb" {
  depends_on      = [aws_vpc.main]
  vpc_id          = aws_vpc.main.id
  service_name    = "com.amazonaws.${var.aws_default_region}.dynamodb"
  route_table_ids = [aws_route_table.private.id, aws_default_route_table.public.id]
  tags = {
    Product = "vpc_endpoint"
    Name    = "dynamodb-gw-endpt-${var.environment_name}"
  }
}

output "vpc_id" { value = aws_vpc.main.id }
output "private_subnet_id" { value = aws_subnet.private[0].id }
output "public_subnet_id" { value = aws_subnet.public[0].id }
output "public_subnet_ids" { value = aws_subnet.public[*].id }
output "private_subnet_ids" { value = aws_subnet.private[*].id }
output "private_table_id" { value = aws_route_table.private.id }