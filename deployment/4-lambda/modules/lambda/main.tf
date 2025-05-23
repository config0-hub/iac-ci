# Get the current AWS account identity
data "aws_caller_identity" "current" {}

# IAM role for the Lambda function
resource "aws_iam_role" "lambda" {
  name               = "${var.lambda_name}-lambda-role"
  assume_role_policy = var.assume_policy
}

# IAM policy for the Lambda role
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

# Attach the IAM policy to the Lambda role
resource "aws_iam_role_policy_attachment" "default" {
  role       = aws_iam_role.lambda.name
  policy_arn = aws_iam_policy.lambda.arn
}

# Lambda function configuration
resource "aws_lambda_function" "default" {
  function_name = var.lambda_name
  s3_bucket     = var.s3_bucket
  s3_key        = var.s3_key
  handler       = var.handler
  layers        = var.lambda_layers != null ? split(",", var.lambda_layers) : []
  timeout       = var.lambda_timeout
  memory_size   = var.memory_size
  role          = aws_iam_role.lambda.arn
  runtime       = var.runtime
  publish       = true
  depends_on    = [aws_iam_role_policy_attachment.default]
  
  # Conditionally add environment variables if any are provided
  dynamic "environment" {
    for_each = length(var.lambda_env_vars) > 0 ? [true] : []

    content {
      variables = var.lambda_env_vars
    }
  }

  tags = merge(
    var.cloud_tags,
    {
      Product = var.product
    },
  )
}

# Outputs
output "s3_key" {
  description = "The S3 key of the Lambda deployment package"
  value       = aws_lambda_function.default.s3_key
}

output "s3_bucket" {
  description = "The S3 bucket containing the Lambda deployment package"
  value       = aws_lambda_function.default.s3_bucket
}

output "memory_size" {
  description = "Amount of memory in MB allocated to the Lambda function"
  value       = aws_lambda_function.default.memory_size
}

output "role" {
  description = "IAM role ARN attached to the Lambda function"
  value       = aws_lambda_function.default.role
}

output "runtime" {
  description = "Runtime environment for the Lambda function"
  value       = aws_lambda_function.default.runtime
}

output "handler" {
  description = "Function entrypoint in the deployment package"
  value       = aws_lambda_function.default.handler
}

output "invoke_arn" {
  description = "ARN to be used for invoking Lambda from API Gateway"
  value       = aws_lambda_function.default.invoke_arn
}

output "function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.default.function_name
}

output "layers" {
  description = "List of Lambda Layer ARNs attached to the function"
  value       = aws_lambda_function.default.layers
}

output "timeout" {
  description = "Function execution timeout in seconds"
  value       = aws_lambda_function.default.timeout
}

output "arn" {
  description = "ARN identifying the Lambda function"
  value       = aws_lambda_function.default.arn
}