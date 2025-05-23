#----------------------------------------------------
# This Terraform configuration creates an IAM user for CI/CD operations
# and attaches three policies to that user. Each policy grants different
# permissions needed for infrastructure automation.
#
# Variables:
# - var.environment_name: The environment name (e.g., dev, staging, prod)
#                         Used to name the IAM user and policies
#
# Local variables:
# - local.policies: A map containing policy documents

# IAM User resource for CI/CD operations
#----------------------------------------------------
resource "aws_iam_user" "iac-ci" {
  name = var.environment_name
}

# First IAM policy for the CI/CD user
resource "aws_iam_policy" "iac-ci-1" {
  depends_on = [
    aws_iam_user.iac-ci,
    aws_vpc.main,
    module.log-bucket,
    module.cache-bucket,
    module.codebuild-log-bucket,
    aws_codebuild_project.codebuild,
    aws_lambda_function.default
  ]

  name        = "${var.environment_name}-1"
  description = "${var.environment_name}-1 policy"
  policy      = local.policies["iac-ci-policy-1"]
}

# Second IAM policy for the CI/CD user
resource "aws_iam_policy" "iac-ci-2" {
  depends_on = [
    aws_iam_user.iac-ci,
    aws_vpc.main,
    module.log-bucket,
    module.cache-bucket,
    module.codebuild-log-bucket,
    aws_codebuild_project.codebuild,
    aws_lambda_function.default
  ]

  name        = "${var.environment_name}-2"
  description = "${var.environment_name}-2 policy"
  policy      = local.policies["iac-ci-policy-2"]
}

# Third IAM policy for the CI/CD user
resource "aws_iam_policy" "iac-ci-3" {
  depends_on = [
    aws_iam_user.iac-ci,
    aws_vpc.main,
    module.log-bucket,
    module.cache-bucket,
    module.codebuild-log-bucket,
    aws_codebuild_project.codebuild,
    aws_lambda_function.default
  ]

  name        = "${var.environment_name}-3"
  description = "${var.environment_name}-3 policy"
  policy      = local.policies["iac-ci-policy-3"]
}

# Attach the first policy to the IAM user
resource "aws_iam_user_policy_attachment" "iac-ci-1" {
  user       = aws_iam_user.iac-ci.name
  policy_arn = aws_iam_policy.iac-ci-1.arn
}

# Attach the second policy to the IAM user
resource "aws_iam_user_policy_attachment" "iac-ci-2" {
  user       = aws_iam_user.iac-ci.name
  policy_arn = aws_iam_policy.iac-ci-2.arn
}

# Attach the third policy to the IAM user
resource "aws_iam_user_policy_attachment" "iac-ci-3" {
  user       = aws_iam_user.iac-ci.name
  policy_arn = aws_iam_policy.iac-ci-3.arn
}