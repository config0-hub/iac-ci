data "aws_caller_identity" "current" {}

resource "aws_sns_topic" "builds" {
  name = var.topic_name

  delivery_policy = <<EOF
{
  "http": {
    "defaultHealthyRetryPolicy": {
      "minDelayTarget": 20,
      "maxDelayTarget": 20,
      "numRetries": 1,
      "numMaxDelayRetries": 0,
      "numNoDelayRetries": 0,
      "numMinDelayRetries": 0,
      "backoffFunction": "linear"
    },
    "disableSubscriptionOverrides": false,
    "defaultThrottlePolicy": {
      "maxReceivesPerSecond": 1
    }
  }
}
EOF
}

resource "aws_sns_topic_subscription" "sns" {
  topic_arn = aws_sns_topic.builds.arn
  protocol  = "lambda"
  endpoint  = "arn:aws:lambda:${var.aws_default_region}:${data.aws_caller_identity.current.account_id}:function:${var.lambda_name}"
}

resource "aws_lambda_permission" "allow_sns_invoke" {
  statement_id  = "AllowExecutionFromSNS"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.builds.arn
}

data "aws_iam_policy_document" "builds" {
  statement {
    sid       = "TrustCloudWatchEvents"
    effect    = "Allow"
    actions   = ["sns:Publish",
                 "sns:SetTopicAttributes",
                 "sns:GetTopicAttributes",
                 "sns:Subscribe" ]
    resources = [aws_sns_topic.builds.arn]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

resource "aws_sns_topic_policy" "builds_events" {
  arn    = aws_sns_topic.builds.arn
  policy = data.aws_iam_policy_document.builds.json
}

###########################################
# this project name does not work
# in the cloudwatch event rule below

#"project-name": [ "flask-sample-private" ],
###########################################

resource "aws_cloudwatch_event_rule" "builds" {
  name          = "codebuild-to-${var.topic_name}"
  event_pattern = <<EOF
{
    "source": ["aws.codebuild"],
    "detail-type": ["CodeBuild Build State Change"],
    "detail": {
      "build-status": ["STOPPED", "FAILED", "SUCCEEDED"]
    }
}
EOF
}

resource "aws_cloudwatch_event_target" "builds" {
  target_id = "codebuild-to-${var.topic_name}"
  rule      = aws_cloudwatch_event_rule.builds.name
  arn       = aws_sns_topic.builds.arn
}

output "sns_topic_arn" {
  value = aws_sns_topic.builds.arn
}

output "cloudwatch_name" {
  value = aws_cloudwatch_event_rule.builds.name
}

output "cloudwatch_arn" {
  value = aws_cloudwatch_event_rule.builds.arn
}

output "sns_topic_subscription" {
  value = "${aws_sns_topic_subscription.sns.topic_arn} -> ${aws_sns_topic_subscription.sns.endpoint}"
}

output "endpoint" {
  value = aws_sns_topic_subscription.sns.endpoint
}
