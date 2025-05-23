resource "github_repository_webhook" "default" {
  # Name of the GitHub repository
  repository = var.repository

  configuration {
    # URL where webhook payloads will be sent
    url          = var.url
    # Whether to allow insecure SSL when delivering payloads
    insecure_ssl = var.insecure_ssl
    # Content type of the payload (json or form)
    content_type = var.content_type
    # Secret token for securing webhook deliveries
    secret       = var.secret
  }

  # Whether the webhook is active
  active = var.active
  # List of events to trigger the webhook
  events = split(",", var.events)
}

output "webhook_id" {
  description = "The ID of the created GitHub repository webhook"
  value       = github_repository_webhook.default.id
}

output "url" {
  description = "The URL of the webhook (sensitive value)"
  value       = github_repository_webhook.default.configuration[0].url
  sensitive   = true
}