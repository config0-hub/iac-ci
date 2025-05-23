data "aws_caller_identity" "current" {}

locals {
    aws_account_id = data.aws_caller_identity.current.account_id
}

resource "aws_api_gateway_rest_api" "default" {
  description = "Config0/Terraform API gateway"
  body = jsonencode({
    openapi = "3.0.1"
    info = {
      title   = var.apigateway_name
      version = "1.0"
    }
    post = {
      x-amazon-apigateway-integration = {
        httpMethod           = "POST"
        payloadFormatVersion = "1.0"
        type                 = "HTTP_PROXY"
      }
    }
  })

  name        = var.apigateway_name

  tags = merge(
    var.cloud_tags,
    {
      Product = "apigateway"
    },
  )
  endpoint_configuration {
    types = ["REGIONAL"]
  }
}

resource "aws_api_gateway_resource" "default" {
  parent_id   = aws_api_gateway_rest_api.default.root_resource_id
  rest_api_id = aws_api_gateway_rest_api.default.id
  path_part   = "{${var.resource_name}+}"
}

resource "aws_api_gateway_method" "post" {
   rest_api_id   = aws_api_gateway_rest_api.default.id
   resource_id   = aws_api_gateway_resource.default.id
   http_method   = "POST"
   authorization = "NONE"
}

resource "aws_api_gateway_integration" "lambda_non_root" {
   rest_api_id = aws_api_gateway_rest_api.default.id
   resource_id = aws_api_gateway_method.post.resource_id
   http_method = aws_api_gateway_method.post.http_method

   integration_http_method = "POST"
   type                    = "AWS_PROXY"
   uri                     = "arn:aws:apigateway:${var.aws_default_region}:lambda:path/2015-03-31/functions/arn:aws:lambda:${var.aws_default_region}:${local.aws_account_id}:function:${var.lambda_name}/invocations"
}

resource "aws_api_gateway_method" "post_root" {
   rest_api_id   = aws_api_gateway_rest_api.default.id
   resource_id   = aws_api_gateway_rest_api.default.root_resource_id
   http_method   = "POST"
   authorization = "NONE"
}

resource "aws_api_gateway_integration" "lambda_root" {
   rest_api_id = aws_api_gateway_rest_api.default.id
   resource_id = aws_api_gateway_method.post_root.resource_id
   http_method = aws_api_gateway_method.post_root.http_method

   integration_http_method = "POST"
   type                    = "AWS_PROXY"
   uri                     = "arn:aws:apigateway:${var.aws_default_region}:lambda:path/2015-03-31/functions/arn:aws:lambda:${var.aws_default_region}:${local.aws_account_id}:function:${var.lambda_name}/invocations"
}

resource "aws_api_gateway_method_response" "response_200" {
 rest_api_id = aws_api_gateway_rest_api.default.id
 resource_id = aws_api_gateway_resource.default.id
 http_method = aws_api_gateway_method.post.http_method
 status_code = "200"
}

resource "aws_api_gateway_integration_response" "IntegrationResponse" {
  depends_on = [
     aws_api_gateway_integration.lambda_non_root,
     aws_api_gateway_integration.lambda_root,
  ]
  rest_api_id = aws_api_gateway_rest_api.default.id
  resource_id = aws_api_gateway_resource.default.id
  http_method = aws_api_gateway_method.post.http_method
  status_code = aws_api_gateway_method_response.response_200.status_code
  # Transforms the backend JSON response to json. The space is "A must have"
 response_templates = {
 "application/json" = <<EOF
 
 EOF
 }
}

resource "aws_lambda_permission" "apigw_lambda" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "arn:aws:execute-api:${var.aws_default_region}:${local.aws_account_id}:${aws_api_gateway_rest_api.default.id}/*/${aws_api_gateway_method.post.http_method}${aws_api_gateway_resource.default.path}"
}

resource "aws_api_gateway_deployment" "default" {
   depends_on = [
     aws_api_gateway_integration.lambda_non_root,
     aws_api_gateway_integration_response.IntegrationResponse,
   ]

   rest_api_id = aws_api_gateway_rest_api.default.id
   stage_name  = var.stage

}

output "base_url" {
  value = "${aws_api_gateway_deployment.default.invoke_url}/${var.resource_name}"
}
