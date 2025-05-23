locals {
  # Policy definitions for AWS IAM roles used in the CI/CD pipeline
  policies = {
    # Runner execution policy with broad permissions for CI/CD operations
    # Grants access to various AWS services including logging, storage, compute, and networking
    runner_exec_policy = <<EOF
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
        "acm:*",
        "apigateway:*",
        "appmesh:*",
        "autoscaling:*",
        "aws-portal:*",
        "cloudformation:*",
        "cloudfront:*",
        "cloudtrail:*",
        "cloudwatch:*",
        "codebuild:*",
        "codepipeline:*",
        "devicefarm:*",
        "dynamodb:*",
        "ec2:*",
        "ecr:*",
        "ecs:*",
        "eks:*",
        "elasticfilesystem:*",
        "events:*",
        "glacier:*",
        "iam:*",
        "kafka:*",
        "kinesis:*",
        "kms:*",
        "lambda:*",
        "logs:*",
        "rds:*",
        "route53:*",
        "s3:*",
        "servicediscovery:*",
        "sns:*",
        "sqs:*",
        "ssm:*",
        "states:*",
        "xray:*"
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

    iac-ci-policy-1 = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:CancelSpotInstanceRequests",
        "ec2:CreateKeyPair",
        "ec2:CreateTags",
        "ec2:DeleteKeyPair",
        "ec2:DescribeImages",
        "ec2:DescribeInstances",
        "ec2:DescribeKeyPairs",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSpotPriceHistory",
        "ec2:RequestSpotInstances",
        "ec2:RunInstances",
        "ec2:TerminateInstances",
        "ecr:DescribeRegistry",
        "ecr:DescribeRepositories"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "lambda:GetFunction",
        "lambda:InvokeAsync",
        "lambda:InvokeFunction",
        "lambda:UpdateFunctionConfiguration"
      ],
      "Resource": "${aws_lambda_function.default.arn}"
    },
    {
      "Effect": "Allow",
      "Action": [
        "codebuild:BatchGetBuilds",
        "codebuild:ListBuilds",
        "codebuild:ListBuildsForProject",
        "codebuild:ListProjects",
        "codebuild:StartBuild",
        "codebuild:StartBuildBatch",
        "codebuild:StopBuild"
      ],
      "Resource": "${aws_codebuild_project.codebuild.arn}"
    }
  ]
}
EOF

    iac-ci-policy-2 = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:*"
      ],
      "Resource": [
        "arn:aws:s3:::${var.stateful_bucket_name}",
        "arn:aws:s3:::${var.stateful_bucket_name}/*",
        "arn:aws:s3:::${var.log_bucket_name}",
        "arn:aws:s3:::${var.log_bucket_name}/*",
        "arn:aws:s3:::${var.runs_bucket_name}",
        "arn:aws:s3:::${var.runs_bucket_name}/*",
        "arn:aws:s3:::${var.lambda_bucket_name}",
        "arn:aws:s3:::${var.lambda_bucket_name}/*",
        "arn:aws:s3:::${var.tmp_bucket_name}",
        "arn:aws:s3:::${var.tmp_bucket_name}/*",
        "arn:aws:s3:::${var.codebuild_cache_bucket_name}",
        "arn:aws:s3:::${var.codebuild_cache_bucket_name}/*",
        "arn:aws:s3:::${var.codebuild_log_bucket_name}",
        "arn:aws:s3:::${var.codebuild_log_bucket_name}/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetBucketLocation",
        "s3:ListAllMyBuckets"
      ],
      "Resource": "*"
    }
  ]
}
EOF

    iac-ci-policy-3 = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:DeleteParameter",
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:GetParametersByPath",
        "ssm:PutParameter"
      ],
      "Resource": [
        "arn:aws:ssm:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:parameter/iac-ci/*",
        "arn:aws:ssm:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:parameter/iac-ci",
        "arn:aws:ssm:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:parameter/iac_ci/statefuls/*",
        "arn:aws:ssm:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:parameter/iac_ci/statefuls"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "ssm:DescribeParameters"
      ],
      "Resource": [
        "arn:aws:ssm:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:*"
      ],
      "Resource": [
        "arn:aws:dynamodb:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:table/${var.environment_name}-tmp"
      ]
    }
  ]
}
EOF
  }
}