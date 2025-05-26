#----------------------------------------------------
# Onboarding - Phase 2
#----------------------------------------------------

variable "build_image" {
  type        = string
  description = "CodeBuild container image to use - standard:7.0 is Ubuntu 22.04"
  default     = "aws/codebuild/standard:7.0"
}

variable "image_type" {
  type        = string
  description = "Type of build environment to use for builds"
  default     = "LINUX_CONTAINER"
}

variable "privileged_mode" {
  type        = bool
  description = "Whether to enable privileged mode for Docker containers"
  default     = true
}

variable "description" {
  type        = string
  description = "Description for the CodeBuild project"
  default     = "Codebuild project"
}

variable "build_timeout" {
  type        = string
  description = "Number of minutes before build times out"
  default     = "90"
}

variable "compute_type" {
  type        = string
  description = "Instance type of the CodeBuild environment"
  default     = "BUILD_GENERAL1_SMALL"
}

#----------------------------------------------------
# Template and IAM Configuration
#----------------------------------------------------

# IAM role for CodeBuild service
resource "aws_iam_role" "codebuild" {
  name = "${var.environment_name}-codebuild-role"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "codebuild.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

  lifecycle {
    create_before_destroy = true
  }
}

# CodeBuild project definition
resource "aws_codebuild_project" "codebuild" {
  name          = var.environment_name
  description   = var.description
  build_timeout = var.build_timeout
  service_role  = aws_iam_role.codebuild.arn

  artifacts {
    type = "NO_ARTIFACTS"
  }

  cache {
    type     = "S3"
    location = var.codebuild_cache_bucket_name
  }

  vpc_config {
    vpc_id             = aws_vpc.main.id
    subnets            = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.main.id]
  }

  environment {
    compute_type    = var.compute_type
    image           = var.build_image
    type            = var.image_type
    privileged_mode = var.privileged_mode
  }

  source {
    type = "NO_SOURCE"
    buildspec = base64decode("dmVyc2lvbjogMC4yCgpwaGFzZXM6CiAgYnVpbGQ6CiAgICBjb21tYW5kczoKICAgICAgLSBlY2hvICJTdGFydGluZyBidWlsZCBvbiAkKGRhdGUpIgogICAgICAtIGVjaG8gIkJ1aWxkIGNvbXBsZXRlZCBzdWNjZXNzZnVsbHkiCgphcnRpZmFjdHM6CiAgZmlsZXM6CiAgICAtICcqKi8qJw==")
  }

  logs_config {
    cloudwatch_logs {
      group_name  = "log-group"
      stream_name = "log-stream"
    }

    s3_logs {
      status   = "ENABLED"
      location = "${var.log_bucket_name}/codebuild/logs"
    }
  }

  tags = {
    Name = var.environment_name
  }

  depends_on = [
    aws_vpc.main,
    module.log-bucket,
    module.cache-bucket,
    module.codebuild-log-bucket
  ]
}

# IAM permissions policy for CodeBuild role
resource "aws_iam_role_policy" "default" {
  role = aws_iam_role.codebuild.name

  policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Resource": [
        "*"
      ],
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "rds:*",
        "kafka:*",
        "logs:*",
        "cloudtrail:*",
        "dynamodb:*",
        "sqs:*",
        "codebuild:*",
        "appmesh:*",
        "servicediscovery:*",
        "cloudfront:*",
        "kms:*",
        "kinesis:*",
        "xray:*",
        "events:*",
        "sns:*",
        "elasticfilesystem:*",
        "states:*",
        "apigateway:*",
        "s3:*",
        "cloudformation:*",
        "iam:*",
        "devicefarm:*",
        "glacier:*",
        "cloudwatch:*",
        "ssm:*",
        "aws-portal:*",
        "route53:*",
        "lambda:*",
        "ecs:*",
        "ecr:*",
        "codepipeline:*",
        "ec2:*",
        "eks:*",
        "acm:*",
        "autoscaling:*"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:*"
      ],
      "Resource": [
        "arn:aws:s3:::${var.stateful_bucket_name}",
        "arn:aws:s3:::${var.codebuild_cache_bucket_name}",
        "arn:aws:s3:::${var.log_bucket_name}",
        "arn:aws:s3:::${var.stateful_bucket_name}/*",
        "arn:aws:s3:::${var.codebuild_cache_bucket_name}/*",
        "arn:aws:s3:::${var.log_bucket_name}/*"
      ]
    }
  ]
}
EOF
}

#----------------------------------------------------
# Outputs
#----------------------------------------------------

output "codebuild_role_arn" {
  description = "ARN of the IAM role assigned to the CodeBuild project"
  value       = aws_iam_role.codebuild.arn
}
