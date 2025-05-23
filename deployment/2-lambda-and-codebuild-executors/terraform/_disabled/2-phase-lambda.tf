#####################################################
# Onboarding - phase 2b
#####################################################
resource "aws_lambda_function" "default" {
  depends_on = [aws_s3_bucket_object.lambda,
    aws_vpc.main,
    module.log-bucket,
    module.cache-bucket,
  module.codebuild-log-bucket]

  function_name = var.environment_name
  handler       = "main.handler"
  runtime       = "python3.9"
  timeout       = 800
  memory_size   = 1024
  s3_bucket     = var.lambda_bucket_name
  s3_key        = "${var.environment_name}.zip"
  role          = aws_iam_role.lambda.arn
  publish       = "true"

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.main.id]
  }
}

resource "aws_lambda_function_event_invoke_config" "retry" {
  depends_on                   = [aws_lambda_function.default]
  function_name                = aws_lambda_function.default.function_name
  maximum_event_age_in_seconds = 60
  maximum_retry_attempts       = 0
}

resource "aws_sqs_queue" "failed" {
  name = "${var.environment_name}-failed-queue"
}

resource "aws_sqs_queue" "success" {
  name = "${var.environment_name}-success-queue"
}


resource "aws_lambda_function_event_invoke_config" "default" {
  depends_on    = [aws_lambda_function.default]
  function_name = aws_lambda_function.default.function_name

  destination_config {
    on_failure {
      destination = aws_sqs_queue.failed.arn
    }

    on_success {
      destination = aws_sqs_queue.success.arn
    }
  }
}


# iam role
resource "aws_iam_role" "lambda" {
  name               = "${var.environment_name}-lambda-role"
  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    Name = var.environment_name
  }

  depends_on = [module.log-bucket,
  module.cache-bucket]
}

# iam policy permissions 
resource "aws_iam_policy" "lambda" {
  name   = "${var.environment_name}-lambda-policy"
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
        "arn:aws:s3:::${var.log_bucket_name}",
        "arn:aws:s3:::${var.stateful_bucket_name}/*",
        "arn:aws:s3:::${var.log_bucket_name}/*"
      ]
    }
  ]
}
EOF
}

resource "aws_iam_role_policy_attachment" "lambda" {
  role       = aws_iam_role.lambda.name
  policy_arn = aws_iam_policy.lambda.arn
}

output "lambda_role_arn" {
  value = aws_iam_role.lambda.arn
}
