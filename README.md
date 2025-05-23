# What is "iac-ci"?

"iac-ci" is a standalone system built on AWS that provides continuous integration for Infrastructure as Code (IaC). It serves as an alternative to Atlantis, offering several key benefits:

- **Open Source**: Fully belongs to the open-source community.
- **24/7 Availability**: Users can install it and have it running around the clock.
- **Cost-Effective**: Pay only for what you use.
- **No Scaling Concerns**: No need to manage and scale runners or workers.
- **No Third-Party API Gateway**: Eliminates the need for external services to manage APIs.

## How It Works

"iac-ci" system utilizes:

- **Two DynamoDB Tables**:
  - `iac-ci-settings`: Stores permanent configuration settings for each registered GitOps repository for IaC.
  - `iac-ci-runs`: A temporary table that records CI runs.

- **Lambda Functions**: Several Lambda functions are interconnected in a pipeline managed by a Step Function called `iac-ci-stepf-ci`.

- **API Gateway**: Acts as an entry point to receive webhooks.

"iac-ci" relies on executors:
- **"iac-ci" lambda executor**: Lambda function with elevated privileges to execute the IAC code
- **"iac-ci" codebuild project executor**: Codebuild project with elevated privileges to execute IAC apply/destroy

### General Workflow

#### Diagram

<pre>
                     <span style="color: teal;">+---------------------+</span>
                     <span style="color: teal;">|     API Gateway     |</span>
                     <span style="color: teal;">|  <span style="color: white;">(Receives Webhook)</span> |</span>
                     <span style="color: teal;">+----------+----------+</span>
                    <span style="color: green;">           |</span>
                    <span style="color: green;">           v</span>
                <span style="color: teal;">+-------------------------------+</span>
                <span style="color: teal;">|  iac-ci-lambda_trigger_stepf  |</span>
                <span style="color: teal;">|    <span style="color: white;">(Triggers Step Function)</span>   |</span>
                <span style="color: teal;">+---------------+---------------+</span>
                <span style="color: green;">                |</span>
                <span style="color: green;">                v</span>
                <span style="color: teal;">+-------------------------------+</span>
                <span style="color: teal;">|     iac-ci-process_webhook    |</span>
                <span style="color: teal;">| <span style="color: white;">      (Validates Webhook)</span>     |</span>
                <span style="color: teal;">+---------------+---------------+</span>
    <span style="color: green;">                            |</span>
<span style="color: green;">             +---------------------------------+</span>
<span style="color: green;">             |                                 |</span>
<span style="color: green;">             v                                 v</span>
<span style="color: teal;">+----------------------------+    +----------------------------+</span>
<span style="color: teal;">|           CD Run           |    |          CI Run            |</span>
<span style="color: teal;">|     <span style="color: white;">(TF apply/destroy)</span>     |    | <span style="color: white;"> (TF plan/Tfsec/Infracost)</span> |</span>
<span style="color: teal;">+----------------------------+    +----------------------------+</span>
<span style="color: green;">             |                                 |</span>
<span style="color: green;">             v                                 v</span>
<span style="color: teal;">+----------------------------+    +----------------------------+</span>
<span style="color: teal;">|   iac-ci-trigger_codebuild |    |      iac-ci-pkg_to_s3      |</span>
<span style="color: teal;">|     <span style="color: white;">(Triggers Build)</span>       |    |  <span style="color: white;">(Pkg Code & Upload to s3)</span> |</span>
<span style="color: teal;">+----------------------------+    +----------------------------+</span>
       <span style="color: green;">      |                                 |</span>
       <span style="color: green;">      v                                 v</span>
<span style="color: teal;">+----------------------------+    +----------------------------+</span>
<span style="color: teal;">|    iac-ci-check_codebuild  |    |    iac-ci-trigger_lambda   |</span>
<span style="color: teal;">|      <span style="color: white;">(Monitors Build)</span>      |    |      <span style="color: white;">(Executes CI Run)</span>     |</span>
<span style="color: teal;">+----------------------------+    +----------------------------+</span>
               <span style="color: green;">      |                   |</span>
               <span style="color: green;">      v                   v</span>
              <span style="color: teal;">+-------------------------------+</span>
              <span style="color: teal;">|         iac-ci-update_pr      |</span>
              <span style="color: teal;">| <span style="color: white;">(Updates PR & Slack Notify)</span>   |</span>
              <span style="color: teal;">+-------------------------------+</span>
</pre>

1. **Webhook Reception**: The API Gateway receives a webhook.
2. **Triggering Step Function**: The API Gateway forwards the webhook to a Lambda function, `iac-ci-lambda_trigger_stepf`, which triggers the Step Function `iac-ci-stepf` with the webhook payload.
3. **Processing the Webhook**:
   - The first Lambda function in the Step Function, `iac-ci-process-webhook`, checks if the webhook is valid by matching it against entries in the `iac-ci-settings` DynamoDB table.
   - It processes only specific webhook types: push, pull request, or PR comments; all others are ignored.
   - If the webhook is valid, `iac-ci-process-webhook` determines whether it's a general CI run OR a Terraform apply/destroy action.
     - **For Apply or Destroy**:
       - The function passes the webhook information to `iac-ci-trigger_codebuild`.
       - `iac-ci-trigger_codebuild` triggers the specified CodeBuild project (e.g., `iac-ci`) with elevated privileges to execute the IaC code and update the cloud infrastructure.
       - The next function, `iac-ci-check_codebuild`, monitors the progress of the IAC execution in the Codebuild project.
       - Once the Apply/Destroy is finishes, `iac-ci-check_codebuild` summarizes the build results and updates the PR comment if applicable, also posting summary links to a designated Slack channel.
     - **For CI Run**:
       - The function passes the webhook information to `iac-ci-pkg_to_s3`, which packages the correct code repository and uploads it to a temporary S3 bucket with automatic expiration.
       - Once packaged, `iac-ci-trigger_lambda` activates a Lambda function (e.g., `iac-ci`) to execute the CI run for IaC.
       - After completion, the `iac-ci-update_pr` function updates the PR and notifies users through Slack.

## Installation

The easiest way to install the "iac-ci" system is through [config0.com](https://www.config0.com). You simply need to sign up and execute two workflows. However, you will still need to complete all manual prerequisites, such as:

- Generating a GitHub token
- Obtaining an Infracost API token
- Creating a Slack app and getting the Webhook URL

Alternatively, you can install the system manually.
- Details: [Install "iac-ci" system manually](docs/INSTALL.md).
