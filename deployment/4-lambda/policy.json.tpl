{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": ["ssm:*"],
      "Resource": "*",
      "Effect": "Allow"
    },
    {
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams",
        "logs:PutLogEvents",
        "logs:GetLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*",
      "Effect": "Allow"
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:DescribeTable",
        "dynamodb:PartiQLInsert",
        "dynamodb:GetItem",
        "dynamodb:BatchGetItem",
        "dynamodb:BatchWriteItem",
        "dynamodb:UpdateTimeToLive",
        "dynamodb:PutItem",
        "dynamodb:PartiQLUpdate",
        "dynamodb:Scan",
        "dynamodb:UpdateItem",
        "dynamodb:UpdateTable",
        "dynamodb:GetRecords",
        "dynamodb:ListTables",
        "dynamodb:DeleteItem",
        "dynamodb:ListTagsOfResource",
        "dynamodb:PartiQLSelect",
        "dynamodb:ConditionCheckItem",
        "dynamodb:Query",
        "dynamodb:DescribeTimeToLive",
        "dynamodb:ListStreams",
        "dynamodb:PartiQLDelete"
      ],
      "Resource": [
        "arn:aws:dynamodb:us-east-1:${aws_account_id}:table/iac-ci-runs",
        "arn:aws:dynamodb:us-east-1:${aws_account_id}:table/iac-ci-settings"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        ${bucket_resources}
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["ssm:*"],
      "Resource": "*"
    },
    {
      "Action": [
        "lambda:TagResource",
        "lambda:GetFunctionConfiguration",
        "lambda:ListProvisionedConcurrencyConfigs",
        "lambda:GetProvisionedConcurrencyConfig",
        "lambda:ListLayerVersions",
        "lambda:ListLayers",
        "lambda:ListCodeSigningConfigs",
        "lambda:GetAlias",
        "lambda:ListFunctions",
        "lambda:GetEventSourceMapping",
        "lambda:InvokeFunction",
        "lambda:ListAliases",
        "lambda:GetFunctionCodeSigningConfig",
        "lambda:ListFunctionEventInvokeConfigs",
        "lambda:ListFunctionsByCodeSigningConfig",
        "lambda:GetFunctionConcurrency",
        "lambda:ListEventSourceMappings",
        "lambda:ListVersionsByFunction",
        "lambda:GetLayerVersion",
        "lambda:InvokeAsync",
        "lambda:GetAccountSettings",
        "lambda:GetLayerVersionPolicy",
        "lambda:UntagResource",
        "lambda:ListTags",
        "lambda:GetFunction",
        "lambda:GetFunctionEventInvokeConfig",
        "lambda:GetCodeSigningConfig",
        "lambda:GetPolicy"
      ],
      "Resource": "*",
      "Effect": "Allow"
    },
    {
      "Action": [
        "codebuild:ListReportsForReportGroup",
        "codebuild:ListBuildsForProject",
        "codebuild:BatchGetBuilds",
        "codebuild:StopBuildBatch",
        "codebuild:ListReports",
        "codebuild:DeleteBuildBatch",
        "codebuild:BatchGetReports",
        "codebuild:ListCuratedEnvironmentImages",
        "codebuild:ListBuildBatches",
        "codebuild:ListBuilds",
        "codebuild:BatchDeleteBuilds",
        "codebuild:StartBuild",
        "codebuild:BatchGetBuildBatches",
        "codebuild:GetResourcePolicy",
        "codebuild:StopBuild",
        "codebuild:RetryBuild",
        "codebuild:ImportSourceCredentials",
        "codebuild:BatchGetReportGroups",
        "codebuild:BatchGetProjects",
        "codebuild:RetryBuildBatch",
        "codebuild:StartBuildBatch"
      ],
      "Resource": "*",
      "Effect": "Allow"
    }
  ]
}