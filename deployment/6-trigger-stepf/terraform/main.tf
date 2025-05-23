#------------------------------------------------------------------
# This Terraform module creates an AWS Lambda function with associated IAM roles and policies.
# It configures permissions for S3 access and integrates with Step Functions.
#------------------------------------------------------------------

# Get current AWS account information
data "aws_caller_identity" "current" {}

# IAM role for Lambda execution
resource "aws_iam_role" "lambda" {
  name               = "${var.lambda_name}-lambda-role"
  assume_role_policy = var.assume_policy
}

# IAM policy for Lambda role permissions
resource "aws_iam_policy" "lambda" {
  name        = "${var.lambda_name}-lambda-iam-policy"
  path        = "/"
  description = "Policy for Lambda Role ${var.lambda_name}-lambda-role"
  
  policy = templatefile("policy.json.tpl", {
    aws_default_region = var.aws_default_region
    aws_account_id     = data.aws_caller_identity.current.account_id
    bucket_resources   = join(", ", flatten([
      for name in var.bucket_names : [
        "\"arn:aws:s3:::${name}\"",
        "\"arn:aws:s3:::${name}/*\""
      ]
    ]))
  })
}

# Attach IAM policy to Lambda role
resource "aws_iam_role_policy_attachment" "default" {
  role       = aws_iam_role.lambda.name
  policy_arn = aws_iam_policy.lambda.arn
}

# Lambda function resource
resource "aws_lambda_function" "default" {
  function_name = var.lambda_name
  layers        = var.lambda_layers != null ? split(",", var.lambda_layers) : []
  timeout       = var.lambda_timeout
  memory_size   = var.memory_size
  s3_bucket     = var.s3_bucket
  s3_key        = var.s3_key
  role          = aws_iam_role.lambda.arn
  handler       = var.handler
  runtime       = var.runtime
  publish       = "true"
  depends_on    = [aws_iam_role_policy_attachment.default]
  
  environment {
    variables = {
      DYNAMODB_TABLE    = "iac-ci-runs"
      STATE_MACHINE_ARN = "arn:aws:states:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:stateMachine:${var.step_function_name}"
    }
  }

  tags = merge(
    var.cloud_tags,
    {
      Product = var.product
    },
  )
}
