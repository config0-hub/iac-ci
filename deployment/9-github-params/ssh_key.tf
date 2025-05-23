# GitHub Repository Deploy Key Resource
#
# This resource creates a deploy key for a GitHub repository, allowing external services
# to securely access the repository through SSH. Deploy keys are ideal for automation
# and CI/CD pipelines that need repository access.

resource "github_repository_deploy_key" "default" {
  # The name/title of the deploy key as it will appear in GitHub's UI
  # Using key_name for consistency with general SSH key naming conventions
  title      = var.key_name
  
  # The GitHub repository to add the deploy key to (format: "owner/repo")
  repository = var.repository
  
  # The deploy key content (SSH public key), base64-decoded from the provided hash
  key        = base64decode(var.public_key_hash)
  
  # Whether this key has read-only access (true) or read-write access (false)
  # Read-only is recommended for security unless write access is specifically needed
  read_only  = var.read_only
}