# Installation - Overview

```
+----------------------------+
|   Install "iac-ci" system  |
+----------------------------+
              |
              v
+-------------------------------+
|   Register GitOps Repository  |
|   into "iac-ci" system        |
+-------------------------------+
              |
              v
+---------------------------------------+
|   Register Specific IaC Code          |
|   - Specify Branch                    |
|   - Specify Folder in that Branch     |
+---------------------------------------+
```
I. Install the **"iac-ci"** system.  
II. Register a GitOps repository into the **"iac-ci"** system.  
III. Register a specific IaC code to perform CI on. This will involve:  
   - Specifying a branch.  
   - Specifying a folder in that branch.
   
### Laptop Access and Tools
- Ensure you have access to AWS by exporting the necessary variables.
- Install the AWS CLI if it's not already installed.
- Install the GitHub CLI (gh) if it's not already installed.
- Install Terraform/OpenTofu (tofu) if it's not already installed.

### I. Install the **"iac-ci"** System

#### Third Party Requirements
##### Required
1. **Create GitOps Repo for IaC Code**
   - Recommended name for the first repository: `iac-ci`
2. **Generate SSH Key and insert into repository from Step #1**
    - Details: [Upload SSH_KEY to GitHub Repo](GITHUB_DEPLOY_KEY.md).
3. **Generate GitHub Token for GitOps Repo**
   - Suggest using a classic token with the following permissions:
   - **Required:**
       - `repo`: Grants full control of private repositories.
       - `gist`: Allows you to create and manage gists.
       - `write:discussion`: Allows writing to discussions.
   - **Optional:**
       - `write:deploy_keys`: Allows adding and removing SSH deploy keys.
       - `admin:repo_hook`: To manage webhook configurations.
   - Details: [Generate a GitHub Token](GITHUB_TOKEN.md).

##### Optional (For Full Functionality)
4. **Sign Up for Infracost and Get API Token**
    - Details: [Get Infracost API token](INFRACOST.md).
5. **Create Slack App and Get Webhook URL for Notifications**
    - Details: [Get Slack App Webhook Url](SLACK_WEBHOOK_URL.md).