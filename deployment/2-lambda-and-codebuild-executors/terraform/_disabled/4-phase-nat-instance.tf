#----------------------------------------
# Input Variables
#----------------------------------------

variable "instance_types" {
  description = "List of EC2 instance types for the NAT instance mixed instances policy. Smaller, cost-effective instances are preferred."
  type        = list(string)
  default     = ["t3.nano", "t3a.nano", "t3.micro", "t3a.micro", "t3.small", "t3a.small"]
}

variable "use_spot_instance" {
  description = "Whether to use spot instances (true) or on-demand EC2 instances (false) for the NAT instance."
  type        = bool
  default     = true
}

variable "user_data_write_files" {
  description = "Additional files to write via cloud-init in the write_files section."
  type        = list(any)
  default     = []
}

variable "user_data_runcmd" {
  description = "Additional commands to run via cloud-init in the runcmd section."
  type        = list(list(string))
  default     = []
}

variable "ssm_policy_arn" {
  description = "ARN of the SSM policy to attach to the NAT instance's IAM role for management access."
  type        = string
  default     = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

#----------------------------------------
# Local Variables
#----------------------------------------

locals {
  common_tags = {
    Name = "nat-instance-${var.environment_name}"
  }
  
  # Common dependencies for resources
  common_dependencies = [
    aws_vpc.main,
    module.log-bucket,
    module.cache-bucket,
    module.codebuild-log-bucket,
    aws_codebuild_project.codebuild,
    aws_lambda_function.default
  ]
}

#----------------------------------------
# Data Sources
#----------------------------------------

# Get the latest Amazon Linux 2 AMI for the NAT instance
data "aws_ami" "nat" {
  most_recent = true
  owners      = ["amazon"]
  
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
  
  filter {
    name   = "root-device-type"
    values = ["ebs"]
  }
  
  filter {
    name   = "name"
    values = ["amzn2-ami-hvm-*"]
  }
  
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
  
  filter {
    name   = "block-device-mapping.volume-type"
    values = ["gp2"]
  }
}

data "aws_subnet" "selected" {
  id = aws_subnet.public[0].id
}

#----------------------------------------
# Security Group Configuration
#----------------------------------------

resource "aws_security_group" "nat" {
  depends_on = [local.common_dependencies]

  name        = "${var.environment_name}-nat"
  vpc_id      = aws_vpc.main.id
  description = "Security group for NAT instance ${var.environment_name}"
  tags        = local.common_tags
}

resource "aws_security_group_rule" "egress" {
  security_group_id = aws_security_group.nat.id
  type              = "egress"
  cidr_blocks       = ["0.0.0.0/0"]
  from_port         = 0
  to_port           = 65535
  protocol          = "tcp"
}

resource "aws_security_group_rule" "ingress_any" {
  security_group_id = aws_security_group.nat.id
  type              = "ingress"
  cidr_blocks       = [var.main_cidr]
  from_port         = 0
  to_port           = 65535
  protocol          = "all"
}

resource "aws_security_group_rule" "ssh" {
  security_group_id = aws_security_group.nat.id
  type              = "ingress"
  cidr_blocks       = ["0.0.0.0/0"]
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
}

#----------------------------------------
# IAM Configuration for NAT Instance
#----------------------------------------

resource "aws_iam_role" "nat" {
  depends_on = [local.common_dependencies]

  name               = "${var.environment_name}-nat"
  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

  tags = local.common_tags
}

resource "aws_iam_role_policy_attachment" "ssm" {
  policy_arn = var.ssm_policy_arn
  role       = aws_iam_role.nat.name
}

resource "aws_iam_role_policy" "ec2" {
  role   = aws_iam_role.nat.name
  name   = "${var.environment_name}-nat"
  policy = <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:AttachNetworkInterface",
                "ec2:ModifyInstanceAttribute"
            ],
            "Resource": [ "arn:aws:ec2:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:instance/*" ]
        },
        {
            "Sid": "EC2RouteManagement",
            "Effect": "Allow",
            "Action": [
                "ec2:CreateRoute",
                "ec2:ReplaceRoute",
                "ec2:DescribeRouteTables",
                "ec2:DescribeInstances"
            ],
            "Resource": [ "arn:aws:ec2:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:route-table/${aws_route_table.private.id}" ]
        }
    ]
}
EOF
}

resource "aws_iam_instance_profile" "nat" {
  name = "${var.environment_name}-nat"
  role = aws_iam_role.nat.name
  tags = local.common_tags
}

#----------------------------------------
# NAT Instance Configuration
#----------------------------------------

resource "aws_launch_template" "nat" {
  depends_on = [
    aws_security_group.nat,
    aws_iam_instance_profile.nat
  ]

  name        = "${var.environment_name}-nat"
  image_id    = data.aws_ami.nat.id
  description = "Launch template for NAT instance ${var.environment_name}"
  
  iam_instance_profile {
    arn = aws_iam_instance_profile.nat.arn
  }

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"  # IMDSv2 required for security
  }

  network_interfaces {
    associate_public_ip_address = true
    security_groups             = [aws_security_group.nat.id]
    delete_on_termination       = true
  }

  tag_specifications {
    resource_type = "instance"
    tags          = local.common_tags
  }

  # Configure NAT instance using cloud-init
  user_data = base64encode(join("\n", [
    "#cloud-config",
    yamlencode({
      # https://cloudinit.readthedocs.io/en/latest/topics/modules.html
      write_files : concat([
        {
          path : "/opt/nat/configure.sh",
          content : templatefile("${path.module}/configure.sh", { route_table_id = aws_route_table.private.id }),
          permissions : "0755",
        }
      ], var.user_data_write_files),
      runcmd : concat([
        ["/opt/nat/configure.sh"],
      ], var.user_data_runcmd),
    })
  ]))

  tags = local.common_tags
}

resource "aws_autoscaling_group" "nat" {
  depends_on = [aws_launch_template.nat]

  name                = "${var.environment_name}-nat"
  desired_capacity    = 1
  min_size            = 1
  max_size            = 1
  vpc_zone_identifier = [aws_subnet.public[0].id]

  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = var.use_spot_instance ? 0 : 1
      on_demand_percentage_above_base_capacity = var.use_spot_instance ? 0 : 100
    }
    
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.nat.id
        version            = "$Latest"
      }
      
      dynamic "override" {
        for_each = var.instance_types
        content {
          instance_type = override.value
        }
      }
    }
  }

  dynamic "tag" {
    for_each = local.common_tags
    content {
      key                 = tag.key
      value               = tag.value
      propagate_at_launch = false
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

#----------------------------------------
# Outputs
#----------------------------------------

output "nat_security_group_id" {
  description = "ID of the security group attached to the NAT instance"
  value       = aws_security_group.nat.id
}

output "nat_instance_role_name" {
  description = "Name of the IAM role used by the NAT instance"
  value       = aws_iam_role.nat.name
}

output "nat_autoscaling_group_name" {
  description = "Name of the Auto Scaling Group managing the NAT instance"
  value       = aws_autoscaling_group.nat.name
}