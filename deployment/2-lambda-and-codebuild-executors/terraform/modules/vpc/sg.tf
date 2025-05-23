# Security Group for Bastion hosts
# Allows SSH and HTTPS access from the internet and all outbound traffic
resource "aws_security_group" "bastion" {
  name        = "bastion"
  description = "Bastion Layer Group"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "https"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "ssh"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Rule to allow all TCP traffic between instances in the bastion security group
resource "aws_security_group_rule" "bastion_allow_tcp" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "tcp"
  security_group_id        = aws_security_group.bastion.id
  source_security_group_id = aws_security_group.bastion.id
}

# Rule to allow all UDP traffic between instances in the bastion security group
resource "aws_security_group_rule" "bastion_allow_udp" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "udp"
  security_group_id        = aws_security_group.bastion.id
  source_security_group_id = aws_security_group.bastion.id
}

# Output the Bastion Security Group ID for reference in other modules
output "bastion_sg_id" {
  value       = aws_security_group.bastion.id
  description = "ID of the Bastion Security Group"
}