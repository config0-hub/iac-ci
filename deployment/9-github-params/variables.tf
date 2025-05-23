variable "key_name" {
  description = "Name identifier for the deployment key"
  type        = string
}

variable "public_key_hash" {
  description = "Hash of the public key used for verification"
  type        = string
}

variable "read_only" {
  description = "Whether the integration has read-only access"
  type        = bool
  default     = true
}

variable "repository" {
  description = "Repository name for the webhook configuration"
  type        = string
  default     = "iac-ci"
}

variable "url" {
  description = "Webhook destination URL endpoint"
  type        = string
}

variable "secret" {
  description = "Secret token for webhook authentication"
  type        = string
  sensitive   = true
}

variable "insecure_ssl" {
  description = "Allow insecure SSL connections"
  type        = bool
  default     = true
}

variable "active" {
  description = "Enable or disable the webhook"
  type        = bool
  default     = true
}

variable "content_type" {
  description = "Content type of webhook payload"
  type        = string
  default     = "json"
}

variable "events" {
  description = "Events that trigger the webhook (comma-separated)"
  type        = string
  default     = "push,pull_request"
}