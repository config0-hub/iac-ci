#!/usr/bin/env python
# 
# Copyright 2025 Gary Leong gary@config0.com
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import os
import boto3
import re

from iac_ci.common.utilities import get_hash_from_string
from iac_ci.common.github_pr import GitHubRepo
from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.orders import PlatformReporter


def format_terraform_init(init_output):
    """Format terraform init output for better readability"""
    clean_output = strip_ansi_codes(init_output)
    lines = clean_output.strip().split('\n')
    
    formatted = "\n"
    
    for line in lines:
        if "Initializing the backend" in line:
            formatted += "🔧 " + line + "\n"
        elif "Initializing provider plugins" in line:
            formatted += "🔌 " + line + "\n"
        elif "- Installing" in line or "- Using" in line:
            formatted += "  📦 " + line.strip("- ") + "\n"
        elif "Terraform has been successfully initialized" in line:
            formatted += "\n✅ " + line + "\n"
        elif "Warning" in line.lower():
            formatted += "⚠️ " + line + "\n"
        elif "Error" in line.lower():
            formatted += "❌ " + line + "\n"
        else:
            formatted += line + "\n"
    
    return formatted

def format_terraform_validate(validate_output):
    """Format terraform validate output with clear status"""
    clean_output = strip_ansi_codes(validate_output)
    
    if "Success!" in clean_output or "configuration is valid" in clean_output:
        return "\n✅ **Configuration is valid**\n"
    else:
        formatted = "\n❌ **Validation failed**\n\n"
        formatted += "```\n"
        formatted += clean_output
        formatted += "\n```"
        return formatted

def format_terraform_plan(plan_output):
    """
    Format Terraform plan output for insertion into a GitHub collapsible details section.
    
    Args:
        plan_output (str): Raw terraform plan output as a string
    
    Returns:
        str: Formatted content ready for insertion into <details> section
    """
    # Clean up any remaining ANSI escape codes (just in case)
    clean_output = strip_ansi_codes(plan_output)
    
    # Format the output for details section
    formatted_output = "\n```diff\n"
    formatted_output += clean_output
    formatted_output += "\n```\n"
    
    # Extract summary information
    summary = extract_plan_summary(clean_output)
    if summary:
        formatted_output += "\n**📊 Summary:**\n"
        formatted_output += f"- ✅ **{summary['add']} to add**\n"
        formatted_output += f"- 🔄 **{summary['change']} to change**\n"
        formatted_output += f"- ❌ **{summary['destroy']} to destroy**"
    
    return formatted_output

def format_tfsec_output(tfsec_output):
    """Format tfsec output with severity indicators and summary"""
    clean_output = strip_ansi_codes(tfsec_output)
    
    formatted = "\n🔒 **Security Scan Results**\n\n"
    
    # Count issues by severity
    high_count = clean_output.count("HIGH")
    medium_count = clean_output.count("MEDIUM") 
    low_count = clean_output.count("LOW")
    
    if high_count == 0 and medium_count == 0 and low_count == 0:
        if "No problems detected" in clean_output or len(clean_output.strip()) == 0:
            formatted += "✅ **No security issues found!**\n"
            return formatted
    
    # Summary
    formatted += "**Summary:**\n"
    if high_count > 0:
        formatted += f"- 🔴 **{high_count} HIGH** severity issues\n"
    if medium_count > 0:
        formatted += f"- 🟡 **{medium_count} MEDIUM** severity issues\n"
    if low_count > 0:
        formatted += f"- 🔵 **{low_count} LOW** severity issues\n"
    
    formatted += "\n```\n"
    formatted += clean_output
    formatted += "\n```"
    
    return formatted

def format_infracost_output(infracost_output):
    """Format infracost output with cost summary"""
    clean_output = strip_ansi_codes(infracost_output)
    
    formatted = "\n💰 **Cost Analysis**\n\n"
    
    # Look for cost summary patterns
    if "Monthly cost" in clean_output or "Total monthly cost" in clean_output:
        lines = clean_output.split('\n')
        summary_lines = []
        
        for line in lines:
            if "Monthly cost" in line or "Total monthly cost" in line:
                summary_lines.append(f"💸 {line.strip()}")
            elif "compared to" in line.lower():
                summary_lines.append(f"📊 {line.strip()}")
        
        if summary_lines:
            formatted += "**Summary:**\n"
            for summary in summary_lines:
                formatted += f"- {summary}\n"
            formatted += "\n"
    
    formatted += "```\n"
    formatted += clean_output
    formatted += "\n```"
    
    return formatted

def strip_ansi_codes(text):
    """
    Remove ANSI escape codes from text.
    
    Args:
        text (str): Text that may contain ANSI codes
        
    Returns:
        str: Text with ANSI codes removed
    """
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def extract_plan_summary(plan_output):
    """
    Extract the plan summary (add/change/destroy counts) from terraform output.
    
    Args:
        plan_output (str): Raw terraform plan output
        
    Returns:
        dict: Dictionary with 'add', 'change', 'destroy' counts or None if not found
    """
    pattern = r"Plan:\s+(\d+)\s+to\s+add,\s+(\d+)\s+to\s+change,\s+(\d+)\s+to\s+destroy"
    match = re.search(pattern, plan_output)
    
    if match:
        return {
            'add': match.group(1),
            'change': match.group(2),
            'destroy': match.group(3)
        }
    return None

class GitPr(PlatformReporter):

    def __init__(self, **kwargs):
        """
        This is the constructor for the GitPr class

        It is used to initialize a new instance of the class

        :param kwargs: a dictionary of keyword arguments to be passed to the parent class
        """
        self.classname = "TriggerLambda"
        self.logger = IaCLogger(self.classname)

        PlatformReporter.__init__(self, **kwargs)
        self.phase = "update-pr"

        self.s3 = boto3.resource('s3')
        self.search_tag = None
        self.failure_s3_key = None

        if kwargs.get("failure_s3_key"):
            self.failure_s3_key = kwargs["failure_s3_key"]

    def _get_s3_artifact(self, suffix_key):
        """
        Retrieves an artifact from an S3 bucket, given a suffix key.

        :param suffix_key: a string indicating the suffix key
        :return: the content of the file as a string
        """
        s3_key = os.path.join(self.stateful_id,
                              "cur",
                              suffix_key)

        return self._fetch_s3_artifact(s3_key)

    def _fetch_s3_artifact(self, s3_key):

        file_info = self.s3_file.exists_and_get(format="list",
                                                s3_bucket=self.tmp_bucket,
                                                s3_key=s3_key,
                                                stream=True)

        if file_info["status"] is False:
            self.logger.debug(f'Failed to retrieved file: s3_bucket: {self.tmp_bucket}/s3_key: {s3_key}')
            return False

        self.logger.debug(f'retrieved file: s3_bucket: {self.tmp_bucket}/s3_key: {s3_key}')

        indented_lines = ["    " + line for line in file_info["content"]]

        return ''.join(indented_lines)

    def _get_tfsec(self):
        """
        Retrieves a tfsec artifact from an S3 bucket.

        :return: the content of the artifact as a string
        """
        return self._get_s3_artifact(f"tfsec.{self.stateful_id}.out")

    def _get_infracost(self):
        """
        Retrieves an infracost artifact from an S3 bucket.

        :return: the content of the artifact as a string
        """
        return self._get_s3_artifact(f"infracost.{self.stateful_id}.out")

    def _get_tfplan(self):
        """
        Retrieves a Terraform plan artifact from an S3 bucket.

        :return: the content of the Terraform plan artifact as a string
        """
        return self._get_s3_artifact(f"terraform.{self.stateful_id}.tfplan.out")

    def _get_tfinit(self):
        """
        Retrieves a Terraform init artifact from an S3 bucket.

        :return: the content of the Terraform init artifact as a string
        """
        return self._get_s3_artifact(f"terraform.{self.stateful_id}.init")

    def _get_tffmt(self):
        """
        Retrieves a Terraform fmt artifact from an S3 bucket.

        :return: the content of the Terraform fmt artifact as a string
        """
        return self._get_s3_artifact(f"terraform.{self.stateful_id}.fmt")

    def _get_tfvalidate(self):
        """
        Retrieves a Terraform validate artifact from an S3 bucket.

        :return: the content of the Terraform validate artifact as a string
        """
        return self._get_s3_artifact(f"terraform.{self.stateful_id}.validate")

    def _set_order(self):
        """
        Sets the order for the current process with a human-readable description
        and a specified role. Constructs input arguments including a description
        of triggering a pull request update with the commit hash and assigns the
        order using the new_order method.
        """
        human_description = f"Trigger pr update commit_hash {self.commit_hash}"

        inputargs = {
            "human_description": human_description,
            "role": "lambda/build"
        }

        self.order = self.new_order(**inputargs)

    def _get_tf_md(self):
        """
        Generates a markdown string that summarizes the Terraform process steps:
        Initialization, Validation, and Plan. Each section provides details
        retrieved from corresponding S3 artifacts and is enclosed in collapsible
        sections for better readability.

        Sections are only added if their content is not False.

        :return: A markdown formatted string with Terraform process details.
        """
        content = "## 🏗️ Terraform\n\n"
        
        # Get section contents
        tf_init = self._get_tfinit()
        tf_validate = self._get_tfvalidate()
        tf_plan = self._get_tfplan()

        # Add Initialization section if content exists
        if tf_init:
            content += f'''### 1️⃣ Initialize

<details>
    <summary>show details</summary>
{format_terraform_init(tf_init)}
    
</details>

'''
        
        # Add Validation section if content exists
        if tf_validate:
            content += f'''### 2️⃣ Validate

<details>
    <summary>show details</summary>
{format_terraform_validate(tf_validate)}
    
</details>

'''
        
        # Add Plan section if content exists
        if tf_plan:
            content += f'''### 3️⃣ Plan

<details>
    <summary>show details</summary>
{format_terraform_plan(tf_plan)}
    
</details>
'''
        
        return content

    def _get_tfsec_md(self):
        """
        Generates a markdown string that summarizes the TFSec output:
        It retrieves the TFSec output from an S3 artifact and formats it
        with severity indicators and summary.

        :return: A markdown formatted string with TFSec output.
        """
        _log = self._get_tfsec()

        if not _log:
            return False

        content = f'''### 4️⃣ Security Scan
<details>
    <summary>show details</summary>
{format_tfsec_output(_log)}
    
</details>
        '''
        return content

    def _get_infracost_md(self):
        """
        Generates a markdown string that summarizes the Infracost output:
        It retrieves the Infracost output from an S3 artifact and formats it
        with cost analysis details.

        :return: A markdown formatted string with Infracost output.
        """
        _log = self._get_infracost()
        if not _log:
            return False

        content = f'''### 5️⃣ Cost Analysis
<details>
    <summary>show details</summary>
{format_infracost_output(_log)}
    
</details>
        '''
        return content

    def _ci_links(self):
        """
        Generates a markdown string containing CI details.

        This includes the commit hash and a link to the CI pipeline console URL
        if available. If the console URL is not present in run_info, the function
        returns None.

        :return: A markdown formatted string with CI details, or None if console_url is not available.
        """
        if not self.run_info.get("console_url"):
            return


        content = f'''\n## CI Details 
+ {self.webhook_info.get("commit_hash")}
+ [ci pipeline]({self.run_info["console_url"]})
+ {self.get_run_status()}
'''
        return content

    def _get_pr_md(self):
        """
        Generates a markdown string for the PR body that summarizes the Terraform process steps:
        Initialization, Validation, and Plan. Each section provides details
        retrieved from corresponding S3 artifacts and is enclosed in collapsible
        sections for better readability. Additionally, TFSec and Infracost outputs
        are included if available.

        :return: dictionary with two keys: "comment_body" and "md5sum". The former
        is a markdown formatted string with Terraform process details, TFSec output,
        Infracost output, and CI details. The latter is the md5sum of the comment body.
        """
        content = self._get_tf_md()

        try:
            tf_sec_content = self._get_tfsec_md()
        except Exception as e:
            self.logger.debug(f"Failed to get TFSec content: {str(e)}")
            tf_sec_content = None

        try:
            infracost_content = self._get_infracost_md()
        except Exception as e:
            self.logger.debug(f"Failed to get Infracost content: {str(e)}")
            infracost_content = None

        ci_link_content = self._ci_links()

        if tf_sec_content:
            content = content + "\n" + tf_sec_content

        if infracost_content:
            content = content + "\n" + infracost_content

        if ci_link_content:
            content = content + ci_link_content

        # Combine the table with tags for the comment body
        comment_body = f'{content}\n\n#{self.search_tag}'
        md5sum_str = get_hash_from_string(comment_body)

        return {
            "comment_body": comment_body,
            "md5sum": md5sum_str
        }

    def _get_pr_id(self):
        """
        Return a unique identifier for this PR given by its repo, branch and PR number.

        :return: a string hash of the unique identifier
        """
        _obj = f'{self.repo_name}.{self.branch}.{self.pr_number}.pr_info'

        return get_hash_from_string(_obj)

    def _update_comment(self, pr_md_info, existing_comments=None, overwrite=True):
        """
        Updates an existing comment in the PR with the latest comment body.

        :param pr_md_info: A dictionary with two keys: "comment_body" and "md5sum". The former
        is a markdown formatted string with Terraform process details, TFSec output,
        Infracost output, and CI details. The latter is the md5sum of the comment body.
        :param existing_comments: A list of existing comments in the PR.
        :param overwrite: This will not update the comment but write a new one - shows up on the bottom of PR comments
        :return: A dictionary with the comment ID and its URL if the comment was
        updated successfully, or False if the update failed.
        """
        if not existing_comments:
            return False

        if not len(existing_comments) == 1:
            return False

        comment_id = existing_comments[0]["id"]

        if overwrite:
            comment_info = {"status":False}
        else:
            self.logger.debug(f'overwriting existing comment_id: {comment_id}')
            comment_info = self.github_repo.update_pr_comment(comment_id,
                                                              pr_md_info["comment_body"])

        if not comment_info.get("status"):
            self.logger.debug(f"failed to update comment_id: {comment_id}.")
            self.github_repo.delete_pr_comment(comment_id)
            comment_info = self.github_repo.add_pr_comment(pr_md_info["comment_body"])

        return comment_info

    def _clean_all_pr_comments(self):
        """
        Clean out existing comments in the PR by deleting them.

        This includes any status comment created by this application, as well as
        any other comments that may have been created with the same search tag.
        """
        self.clean_pr_comments()
        self.clean_status_comment_id()

    def _delete_and_add_comment(self, pr_md_info, existing_comments=None):
        """
        Deletes existing comments in the PR and adds a new comment with the latest comment body.

        :param pr_md_info: A dictionary with two keys: "comment_body" and "md5sum". The former
        is a markdown formatted string with Terraform process details, TFSec output,
        Infracost output, and CI details. The latter is the md5sum of the comment body.
        :param existing_comments: A list of existing comments in the PR.
        :return: A dictionary with the comment ID and its URL if the comment was
        added successfully, or False if the add failed.
        """
        for comment in existing_comments:
            self.logger.debug(f'deleting comment_id {comment["id"]}')
            self.github_repo.delete_pr_comment(comment["id"])

        return self.github_repo.add_pr_comment(pr_md_info["comment_body"])

    def eval_pr(self):
        """
        Evaluate the PR and either add a new comment or update an existing one.

        The comment contains details about the Terraform plan, TFSec results, Infracost results,
        and CI details.

        If the PR is being destroyed, a new comment is always added. If the PR is not being
        destroyed, the comment is either added or updated depending on whether an existing
        comment with the same md5sum exists.

        :return: A dictionary with the comment ID and its URL if the comment was
        added successfully, or False if the add failed.
        """
        pr_md_info = self._get_pr_md()

        if not self.run_info.get("destroy"):
            comment_info = self._eval_pr(pr_md_info)
        else:
            self.logger.debug(f"Adding new comment comment_id for destroy.")
            comment_info = self.github_repo.add_pr_comment(pr_md_info["comment_body"])

        pr_md_info.update(comment_info)

        pr_md_info.update({
            "_id": self._get_pr_id(),
            "type": "pr_info"
        })

        self._clean_all_pr_comments()

        return pr_md_info

    def _eval_pr(self, pr_md_info):
        """
        Evaluate the PR and either update an existing comment or add a new one.

        If an existing comment with the same md5sum exists, the comment is updated.
        Otherwise, a new comment is added.

        :param pr_md_info: A dictionary with two keys: "comment_body" and "md5sum". The former
        is a markdown formatted string with Terraform process details, TFSec output,
        Infracost output, and CI details. The latter is the md5sum of the comment body.
        :return: A dictionary with the comment ID and its URL if the comment was
        added successfully, or False if the add failed.
        """
        existing_comments = self.github_repo.get_pr_comments(use_default_search_tag=True)

        if existing_comments:
            comment_info = self._update_comment(pr_md_info, existing_comments)
        else:
            self.logger.debug(f"Adding new comment comment_id.")
            comment_info = self.github_repo.add_pr_comment(pr_md_info["comment_body"])

        return comment_info

    def _save_run_info(self):
        """
        Save the run_info to the run_info table in DynamoDB.

        :return: None
        """
        self.db.table_runs.insert(self.run_info)
        msg = f"trigger_id: {self.trigger_id} saved"
        self.add_log(msg)

    def _init_vars(self):
        """
        Initialize variables from the trigger_info, webhook_info, and iac_ci_info
        dictionaries.

        These variables are used throughout the class and are initialized here for
        convenience.
        """
        self.commit_hash = self.run_info["commit_hash"]
        self.repo_name = self.trigger_info.get("repo_name")
        self.repo_owner = self.trigger_info.get("repo_owner")
        self.remote_stateful_bucket = self.trigger_info["remote_stateful_bucket"]
        self.stateful_id = self.iac_ci_info["stateful_id"]
        self.tmp_bucket = self.trigger_info["s3_bucket_tmp"]
        self.pr_number = self.webhook_info["pr_number"]
        self.branch = self.webhook_info["branch"]

        github_token_info = self.get_github_token()

        if github_token_info.get("status"):
            self.github_token = github_token_info["value"]
        else:
            self.github_token = False

        self.set_search_tag()

    def execute(self):
        """
        Executes the main process for handling a GitHub pull request event.

        This method initializes necessary variables, sets the order, and creates
        a GitHubRepo instance to interact with the pull request. It evaluates the
        pull request to add or update comments with details about the Terraform plan,
        TFSec results, Infracost results, and CI details. If successful, it updates
        the results to indicate the process is complete, logs a summary, and saves
        run information.

        :return: True if execution is successful.
        """

        self._init_vars()
        self._set_order()

        self.github_repo = GitHubRepo(self.repo_name,
                                      self.pr_number,
                                      search_tag=self.search_tag,
                                      token=self.github_token,
                                      owner=self.repo_owner)

        # successful at this point
        self.results["update"] = True
        self.results["close"] = True

        if self.failure_s3_key:
            status = self._exec_failure()
        else:
            status = self._exec_successful()

        if status:
            self.results["status"] = "successful"
        else:
            self.results["status"] = "failure"

        summary_msg = f"# Triggered \n# trigger_id: {self.trigger_id} \n# iac_ci_id: {self.iac_ci_id}\n"

        self.add_log("#" * 32)
        self.add_log("# Summary")
        self.add_log(summary_msg)
        self.add_log("#" * 32)

        self.insert_to_return()
        self.finalize_order()
        self._save_run_info()

        return True

    def _exec_successful(self):
        pr_info = self.eval_pr()
        self.results["notify"] = {
            "links": [{"github comment": pr_info["url"]}]
        }

        return True
    
    def _exec_failure(self):
        failure_log = self._fetch_s3_artifact(self.failure_s3_key)
        if not failure_log:
            failure_log = f'Failed to retrieved file: s3_bucket: {self.tmp_bucket}/s3_key: {self.failure_s3_key}'
        status_comment_info = self.get_cur_status_comment()
        content = f'''## Failure Log
<details>
    <summary>show</summary>
{failure_log}

</details>
        '''
        new_comment = f'{status_comment_info["body"]}\n\n{content}'
        self.github_repo.update_pr_comment(status_comment_info["id"],
                                           new_comment)
        self.results["notify"] = {
            "links": [{"github comment": status_comment_info["html_url"]}]
        }

        return True