data "template_file" "buildspec" {
  template = base64decode(var.buildspec_hash)
  vars = {
      s3_bucket=var.s3_bucket
      aws_default_region=var.aws_default_region
      aws_account_id=var.aws_account_id
  }
}

# iam role
resource "aws_iam_role" "default" {
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

# the codebuild
resource "aws_codebuild_project" "codebuild" {
  count         = var.num_of_projects
  name          = "${var.environment_name}_${count.index + 1}"
  description   = var.description
  build_timeout = var.build_timeout
  service_role  = aws_iam_role.codebuild.arn

  artifacts {
    type        = "NO_ARTIFACTS"
  }

  cache {
    type     = "S3"
    location = var.s3_bucket_cache
  }

  environment {
    compute_type    = var.compute_type
    image           = var.build_image
    type            = var.image_type
    privileged_mode = var.privileged_mode
  }

  source {
    buildspec           = data.template_file.buildspec.rendered
    type                = "NO_SOURCE"
  }

  logs_config {
    cloudwatch_logs {
      group_name  = "log-group"
      stream_name = "log-stream"
    }

    s3_logs {
      status   = "ENABLED"
      location = "${var.s3_bucket_log}/codebuild/logs"
    }
  }

  tags = {
    Name          = var.environment_name
  }

}

# iam policy permissions 
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
        "acm:*"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:*"
      ],
      "Resource": [
        "arn:aws:s3:::${var.s3_bucket}",
        "arn:aws:s3:::${var.s3_bucket_cache}",
        "arn:aws:s3:::${var.s3_bucket_log}",
        "arn:aws:s3:::${var.s3_bucket}/*",
        "arn:aws:s3:::${var.s3_bucket_cache}/*",
        "arn:aws:s3:::${var.s3_bucket_log}/*"
      ]
    }
  ]
}
EOF
}

output "codebuild_role_arn" {
  value = aws_iam_role.codebuild.arn
}
