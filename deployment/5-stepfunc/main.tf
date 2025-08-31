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
  "Comment": "Processes webhook, executes CodeBuild, supports optional parallel folder builds when report && parallel_folder_builds. No parsing of $.body.",
  "StartAt": "ProcessWebhook",
  "States": {
    "ProcessWebhook": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:iac-ci-process-webhook",
      "Next": "ChkProcessWebhook"
    },
    "ChkProcessWebhook": {
      "Type": "Choice",
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
              "Variable": "$.continue"
            },
            {
              "BooleanEquals": true,
              "Variable": "$.report"
            },
            {
              "IsPresent": true,
              "Variable": "$.parallel_folder_builds"
            }
          ],
          "Next": "PrepareParallelBody"
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
      "Default": "Done"
    },
    "PrepareParallelBody": {
      "Type": "Pass",
      "Parameters": {
        "parallelArray.$": "$.parallel_folder_builds",
        "original_body.$": "$.body"
      },
      "Next": "ParallelPkgCodeToS3"
    },
    "ParallelPkgCodeToS3": {
      "Type": "Map",
      "ItemsPath": "$.parallelArray",
      "ResultPath": "$.parallelResults",
      "MaxConcurrency": 0,
      "Parameters": {
        "iac_ci_folder.$": "$$.Map.Item.Value",
        "report": true,
        "body.$": "$.original_body",
        "_id.$": "$$.Map.Item.Value"
      },
      "Iterator": {
        "StartAt": "ChildPkgCodeToS3",
        "States": {
          "ChildPkgCodeToS3": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:iac-ci-pkgcode-to-s3",
            "Next": "ChildChkPkgCodeToS3"
          },
          "ChildChkPkgCodeToS3": {
            "Type": "Choice",
            "Choices": [
              {
                "IsPresent": true,
                "Variable": "$.failure_s3_key",
                "Next": "Done_Child"
              },
              {
                "BooleanEquals": true,
                "Variable": "$.continue",
                "Next": "ChildTriggerLambda"
              }
            ],
            "Default": "Done_Child"
          },
          "ChildTriggerLambda": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:iac-ci-trigger-lambda",
            "Next": "Done_Child"
          },
          "Done_Child": {
            "Type": "Pass",
            "End": true
          }
        }
      },
      "Next": "EvaluatePrParent"
    },
    "EvaluatePrParent": {
      "Type": "Task",
      "Comment": "Send final PR update using original string body; set continue=true inside your Lambda if needed.",
      "InputPath": "$.original_body",
      "Resource": "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:iac-ci-update-pr",
      "End": true
    },
    "PkgCodeToS3": {
      "Type": "Task",
      "InputPath": "$.body",
      "Resource": "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:iac-ci-pkgcode-to-s3",
      "Next": "ChkPkgCodeToS3"
    },
    "ChkPkgCodeToS3": {
      "Type": "Choice",
      "Choices": [
        {
          "IsPresent": true,
          "Variable": "$.failure_s3_key",
          "Next": "EvaluatePr"
        },
        {
          "BooleanEquals": true,
          "Variable": "$.continue",
          "Next": "TriggerLambda"
        }
      ],
      "Default": "Done"
    },
    "TriggerLambda": {
      "Type": "Task",
      "InputPath": "$.body",
      "Resource": "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:iac-ci-trigger-lambda",
      "Next": "ChkTriggerLambda"
    },
    "ChkTriggerLambda": {
      "Type": "Choice",
      "Choices": [
        {
          "BooleanEquals": true,
          "Variable": "$.continue",
          "Next": "EvaluatePr"
        }
      ],
      "Default": "Done"
    },
    "EvaluatePr": {
      "Type": "Task",
      "InputPath": "$.body",
      "Resource": "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:iac-ci-update-pr",
      "End": true
    },
    "TriggerCodebuild": {
      "Type": "Task",
      "InputPath": "$.body",
      "Resource": "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:iac-ci-trigger-codebuild",
      "Next": "ChkTriggerCodebuild"
    },
    "ChkTriggerCodebuild": {
      "Type": "Choice",
      "Choices": [
        {
          "BooleanEquals": true,
          "Variable": "$.continue",
          "Next": "WaitCodebuildCheck"
        }
      ],
      "Default": "Done"
    },
    "WaitCodebuildCheck": {
      "Type": "Wait",
      "Comment": "Wait to Check CodeBuild completion",
      "Seconds": 30,
      "Next": "CheckCodebuild"
    },
    "CheckCodebuild": {
      "Type": "Task",
      "InputPath": "$.body",
      "Resource": "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:iac-ci-check-codebuild",
      "Next": "ChkCheckCodebuild"
    },
    "ChkCheckCodebuild": {
      "Type": "Choice",
      "Choices": [
        {
          "BooleanEquals": true,
          "Variable": "$.continue",
          "Next": "CheckCodebuild"
        }
      ],
      "Default": "Done"
    },
    "Done": {
      "Type": "Pass",
      "End": true
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
