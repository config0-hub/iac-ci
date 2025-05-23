
`terraform init`

<details>
  <summary>expand</summary>

```
Initializing the backend...

Initializing provider plugins...
- Reusing previous version of hashicorp/github from the dependency lock file
- Using previously-installed hashicorp/github v6.2.1

OpenTofu has been successfully initialized!

You may now begin working with OpenTofu. Try running "tofu plan" to see
any changes that are required for your infrastructure. All OpenTofu commands
should now work.

If you ever set or change modules or backend configuration for OpenTofu,
rerun this command to reinitialize your working directory. If you forget, other
commands will detect it and remind you to do so if necessary.
```
</details>

`terraform fmt`

<details>
  <summary>expand</summary>

```
```

</details>

`terraform validate`

<details>
  <summary>expand</summary>

```
Success! The configuration is valid.
```

</details>

`terraform plan`

<details>
  <summary>expand</summary>

```
OpenTofu used the selected providers to generate the following execution
plan. Resource actions are indicated with the following symbols:
  + create

OpenTofu will perform the following actions:

  # github_branch.default will be created
  + resource "github_branch" "default" {
      + branch        = "main"
      + etag          = (known after apply)
      + id            = (known after apply)
      + ref           = (known after apply)
      + repository    = "private-test"
      + sha           = (known after apply)
      + source_branch = "main"
      + source_sha    = (known after apply)
    }

  # github_branch_default.default will be created
  + resource "github_branch_default" "default" {
      + branch     = "main"
      + etag       = (known after apply)
      + id         = (known after apply)
      + rename     = false
      + repository = "private-test"
    }

  # github_repository.default will be created
  + resource "github_repository" "default" {
      + allow_auto_merge            = false
      + allow_merge_commit          = true
      + allow_rebase_merge          = true
      + allow_squash_merge          = true
      + archived                    = false
      + auto_init                   = true
      + default_branch              = (known after apply)
      + delete_branch_on_merge      = true
      + description                 = "This is a repo private-test created using Terraform"
      + etag                        = (known after apply)
      + full_name                   = (known after apply)
      + git_clone_url               = (known after apply)
      + has_issues                  = true
      + has_projects                = false
      + has_wiki                    = false
      + html_url                    = (known after apply)
      + http_clone_url              = (known after apply)
      + id                          = (known after apply)
      + merge_commit_message        = "PR_TITLE"
      + merge_commit_title          = "MERGE_MESSAGE"
      + name                        = "private-test"
      + node_id                     = (known after apply)
      + primary_language            = (known after apply)
      + private                     = (known after apply)
      + repo_id                     = (known after apply)
      + squash_merge_commit_message = "COMMIT_MESSAGES"
      + squash_merge_commit_title   = "COMMIT_OR_PR_TITLE"
      + ssh_clone_url               = (known after apply)
      + svn_url                     = (known after apply)
      + topics                      = (known after apply)
      + visibility                  = "private"
      + web_commit_signoff_required = false
    }

Plan: 3 to add, 0 to change, 0 to destroy.

─────────────────────────────────────────────────────────────────────────────

Note: You didn't use the -out option to save this plan, so OpenTofu can't
guarantee to take exactly these actions if you run "tofu apply" now.
```

</details>
