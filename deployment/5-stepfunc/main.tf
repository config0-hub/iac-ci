# Data source to get AWS account information
data "aws_caller_identity" "current" {}

#-----------------------------------------
# Variables
#-----------------------------------------

variable "aws_default_region" {
  description = "The AWS region where resources will be deployed"
  default     = "eu-west-1"
  type        = string
}

# Step Function configuration
variable "step_function_name" {
  description = "Name of the AWS Step Function state machine"
  default     = "apigw-codebuild-ci"
  type        = string
}

variable "app_name" {
  description = "Base name used for all resources"
  default     = "iac-ci"
  type        = string
}

# Lambda function names
variable "process_webhook" {
  description = "Name of the Lambda function that processes webhooks"
  default     = "process-webhook"
  type        = string
}

variable "pkgcode_to_s3" {
  description = "Name of the Lambda function that packages code to S3"
  default     = "pkgcode-to-s3"
  type        = string
}

variable "trigger_lambda" {
  description = "Name of the Lambda function that triggers other Lambda functions"
  default     = "trigger-lambda"
  type        = string
}

variable "update_pr" {
  description = "Name of the Lambda function that updates pull requests"
  default     = "update-pr"
  type        = string
}

variable "check_codebuild" {
  description = "Name of the Lambda function that checks CodeBuild status"
  default     = "check-codebuild"
  type        = string
}

variable "trigger_codebuild" {
  description = "Name of the Lambda function that triggers CodeBuild projects"
  default     = "trigger-codebuild"
  type        = string
}

variable "cloud_tags" {
  description = "Additional tags as a map"
  type        = map(string)
  default     = {}
}

#-----------------------------------------
# Resources
#-----------------------------------------

# IAM role for the Step Function
resource "aws_iam_role" "default" {
  name = "${var.step_function_name}-role"
  
  assume_role_policy = <<-EOF
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Action": "sts:AssumeRole",
        "Principal": {
          "Service": "states.amazonaws.com"
        },
        "Effect": "Allow",
        "Sid": "StepFunctionAssumeRole"
      }
    ]
  }
  EOF
}

# Step Function state machine definition
resource "aws_sfn_state_machine" "sfn_state_machine" {
  name     = var.step_function_name
  role_arn = aws_iam_role.default.arn

  definition = <<EOF
{
  "Comment": "The state machine processes webhook from code repo, executes codebuild, and checks results",
  "StartAt": "ProcessWebhook",
  "States": {
    "CheckCodebuild": {
      "InputPath": "$.body",
      "Next": "ChkCheckCodebuild",
      "Resource": "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:iac-ci-check-codebuild",
      "Type": "Task"
    },
    "ChkCheckCodebuild": {
      "Choices": [
        {
          "BooleanEquals": true,
          "Next": "CheckCodebuild",
          "Variable": "$.continue"
        }
      ],
      "Default": "Done",
      "Type": "Choice"
    },
    "ChkPkgCodeToS3": {
      "Choices": [
        {
          "IsPresent": true,
          "Next": "EvaluatePr",
          "Variable": "$.failure_s3_key"
        },
        {
          "BooleanEquals": true,
          "Next": "TriggerLambda",
          "Variable": "$.continue"
        }
      ],
      "Default": "Done",
      "Type": "Choice"
    },
    "ChkProcessWebhook": {
      "Choices": [
        {
          "And": [
            {
              "BooleanEquals": true,
              "Variable": "$.apply"
            },
            {
              "BooleanEquals": true,
              "Variable": "$.continue"
            }
          ],
          "Next": "TriggerCodebuild"
        },
        {
          "And": [
            {
              "BooleanEquals": true,
              "Variable": "$.destroy"
            },
            {
              "BooleanEquals": true,
              "Variable": "$.continue"
            }
          ],
          "Next": "TriggerCodebuild"
        },
        {
          "And": [
            {
              "BooleanEquals": true,
              "Variable": "$.check"
            },
            {
              "BooleanEquals": true,
              "Variable": "$.continue"
            }
          ],
          "Next": "PkgCodeToS3"
        }
      ],
      "Default": "Done",
      "Type": "Choice"
    },
    "ChkTriggerCodebuild": {
      "Choices": [
        {
          "BooleanEquals": true,
          "Next": "WaitCodebuildCheck",
          "Variable": "$.continue"
        }
      ],
      "Default": "Done",
      "Type": "Choice"
    },
    "ChkTriggerLambda": {
      "Choices": [
        {
          "BooleanEquals": true,
          "Next": "EvaluatePr",
          "Variable": "$.continue"
        }
      ],
      "Default": "Done",
      "Type": "Choice"
    },
    "Done": {
      "End": true,
      "Type": "Pass"
    },
    "EvaluatePr": {
      "End": true,
      "InputPath": "$.body",
      "Resource": "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:iac-ci-update-pr",
      "Type": "Task"
    },
    "PkgCodeToS3": {
      "InputPath": "$.body",
      "Next": "ChkPkgCodeToS3",
      "Resource": "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:iac-ci-pkgcode-to-s3",
      "Type": "Task"
    },
    "ProcessWebhook": {
      "Next": "ChkProcessWebhook",
      "Resource": "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:iac-ci-process-webhook",
      "Type": "Task"
    },
    "TriggerCodebuild": {
      "InputPath": "$.body",
      "Next": "ChkTriggerCodebuild",
      "Resource": "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:iac-ci-trigger-codebuild",
      "Type": "Task"
    },
    "TriggerLambda": {
      "InputPath": "$.body",
      "Next": "ChkTriggerLambda",
      "Resource": "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:iac-ci-trigger-lambda",
      "Type": "Task"
    },
    "WaitCodebuildCheck": {
      "Comment": "Wait to Check CodeBuild completion",
      "Next": "CheckCodebuild",
      "Seconds": 30,
      "Type": "Wait"
    }
  }
}
EOF
}

# IAM policy for the Step Function to invoke Lambda functions
resource "aws_iam_role_policy" "step_function_policy" {
  name = "${var.step_function_name}-policy"
  role = aws_iam_role.default.id

  policy = <<-EOF
  {
    "Version": "2012-10-17",
    "Statement": [
      {
        "Action": [
          "lambda:InvokeFunction"
        ],
        "Effect": "Allow",
        "Resource": [
          "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:${var.app_name}-${var.process_webhook}",
          "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:${var.app_name}-${var.pkgcode_to_s3}",
          "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:${var.app_name}-${var.trigger_codebuild}",
          "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:${var.app_name}-${var.trigger_lambda}",
          "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:${var.app_name}-${var.update_pr}",
          "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:${var.app_name}-${var.check_codebuild}"
        ]
      }
    ]
  }
  EOF
}
