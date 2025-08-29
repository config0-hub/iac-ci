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
import json

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
    Format Terraform plan output with improved readability and visual cues.
    
    Args:
        plan_output (str): Raw terraform plan output as a string
    
    Returns:
        str: Formatted content with enhanced visual indicators
    """
    # Clean up any ANSI escape codes
    clean_output = strip_ansi_codes(plan_output)
    
    # Format the output with syntax highlighting and visual indicators
    formatted_output = "\n```diff\n"
    
    # Process line by line to add visual enhancements
    lines = clean_output.split('\n')
    for line in lines:
        # Highlight resource changes
        if line.strip().startswith("+ resource"):
            formatted_output += "+ 🟢 " + line + "\n"
        elif line.strip().startswith("- resource"):
            formatted_output += "- 🔴 " + line + "\n"
        elif line.strip().startswith("~ resource") or line.strip().startswith("# resource"):
            formatted_output += "! 🟠 " + line + "\n"
        # Regular lines
        else:
            formatted_output += line + "\n"
            
    formatted_output += "```\n"
    
    # Extract summary information
    summary = extract_plan_summary(clean_output)
    if summary:
        formatted_output += "\n**📊 Plan Summary:**\n"
        formatted_output += f"- 🟢 **{summary['add']} to add**\n"
        formatted_output += f"- 🟠 **{summary['change']} to change**\n"
        formatted_output += f"- 🔴 **{summary['destroy']} to destroy**\n"
    
    return formatted_output

def format_tfsec_output(tfsec_output):
    """Format tfsec output with severity indicators and summary"""
    clean_output = strip_ansi_codes(tfsec_output)
    
    formatted = "\n🔒 **Security Scan Results**\n\n"
    
    # Count issues by severity - more robust counting
    high_count = len(re.findall(r"(CRITICAL|HIGH)", clean_output, re.IGNORECASE))
    medium_count = len(re.findall(r"MEDIUM", clean_output, re.IGNORECASE))
    low_count = len(re.findall(r"LOW", clean_output, re.IGNORECASE))
    
    if high_count == 0 and medium_count == 0 and low_count == 0:
        if "No problems detected" in clean_output or len(clean_output.strip()) == 0:
            formatted += "✅ **No security issues found!**\n"
            return formatted
    
    # Summary
    formatted += "**Summary:**\n"
    if high_count > 0:
        formatted += f"- 🔴 **{high_count} HIGH/CRITICAL** severity issues\n"
    if medium_count > 0:
        formatted += f"- 🟠 **{medium_count} MEDIUM** severity issues\n"
    if low_count > 0:
        formatted += f"- 🟡 **{low_count} LOW** severity issues\n"
    
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
    if not plan_output:
        return None
        
    clean_output = strip_ansi_codes(plan_output)
    pattern = r"Plan:\s+(\d+)\s+to\s+add,\s+(\d+)\s+to\s+change,\s+(\d+)\s+to\s+destroy"
    match = re.search(pattern, clean_output)
    
    if match:
        return {
            'add': match.group(1),
            'change': match.group(2),
            'destroy': match.group(3)
        }
    
    # Check for "No changes" pattern
    if "No changes." in clean_output or "No changes to infrastructure" in clean_output:
        return {
            'add': '0',
            'change': '0',
            'destroy': '0'
        }
        
    return None

def extract_infracost_monthly(infracost_data):
    """
    Extract the monthly cost from infracost JSON data.
    
    :param infracost_data: JSON string from infracost output
    :return: str: The monthly cost formatted as a string
    """
    if not infracost_data:
        return "N/A"

    # Parse the JSON data
    try:
        data = json.loads(infracost_data)
    except Exception as e:
        print(f"Failed to parse infracost JSON: {str(e)}")
        return "N/A"

    # Get the total monthly cost from the top level
    try:
        monthly_cost = data.get("totalMonthlyCost", "0")
    except Exception as e:
        print(f"Failed to extract totalMonthlyCost: {str(e)}")
        return "N/A"

    # Check if there's a difference in cost
    diff_cost = data.get("diffTotalMonthlyCost", "0")

    # Format the cost
    if float(monthly_cost) > 0:
        formatted_cost = f"${float(monthly_cost):.2f}"
    else:
        formatted_cost = "$0"

    # Add diff if it exists and is not zero
    if diff_cost and float(diff_cost) != 0:
        diff_prefix = "+" if float(diff_cost) > 0 else ""
        formatted_cost += f" ({diff_prefix}${float(diff_cost):.2f})"

    return formatted_cost
        
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
        self.base_report_tag = "iac-ci:::tag::report"
        self.failure_s3_key = None

        if kwargs.get("failure_s3_key"):
            self.failure_s3_key = kwargs["failure_s3_key"]

    def _analyze_tfplan_for_summary(self, plan_output):
        """
        Analyze terraform plan output to determine if there are changes.
        Returns True if no changes (success), False if changes (drift).

        :param plan_output: Raw terraform plan output
        :return: True if no changes, False if changes
        """
        if not plan_output:
            return False

        clean_output = strip_ansi_codes(plan_output)

        # Check for "No changes" statement - this is the success case
        if "No changes" in clean_output:
            return True

        # Any of these patterns indicate changes
        change_indicators = [
            "Plan: ",
            "to add",
            "to change",
            "to destroy",
            "will be created",
            "will be destroyed",
            "will be updated",
            "+ resource",
            "- resource"
        ]

        for indicator in change_indicators:
            if indicator in clean_output:
                return False

        # If we can't definitively detect changes, assume there are none
        return True

    def _analyze_tfsec_for_summary(self, tfsec_output):
        """
        Analyze tfsec output to determine security issue severity.
        Returns "high" for critical/high, "medium", "low", or "success" if no issues.

        :param tfsec_output: Raw tfsec output
        :return: String indicating severity or success
        """
        if not tfsec_output:
            return "success"

        clean_output = strip_ansi_codes(tfsec_output)

        # Look for the results section - more flexible regex pattern
        results_match = re.search(r"(?:results|Results).*?(?:passed|Passed).*?(\d+).*?(?:critical|Critical).*?(\d+).*?(?:high|High).*?(\d+).*?(?:medium|Medium).*?(\d+).*?(?:low|Low).*?(\d+)", 
                                clean_output, 
                                re.MULTILINE | re.DOTALL | re.IGNORECASE)

        if results_match:
            critical = int(results_match.group(1))
            high = int(results_match.group(2))
            medium = int(results_match.group(3))
            low = int(results_match.group(4))

            # Group critical and high together
            if critical > 0 or high > 0:
                return "high"
            elif medium > 0:
                return "medium"
            elif low > 0:
                return "low"
            else:
                return "success"

        # Alternative check for critical/high/medium/low issues
        if re.search(r"(CRITICAL|HIGH)", clean_output, re.IGNORECASE):
            return "high"
        elif re.search(r"MEDIUM", clean_output, re.IGNORECASE):
            return "medium"
        elif re.search(r"LOW", clean_output, re.IGNORECASE):
            return "low"
        elif "No problems detected" in clean_output or not clean_output.strip():
            return "success"

        # Default to success if no issues detected
        return "success"

    def _get_s3_artifact(self, suffix_key, ref_id=None):
        """
        Retrieves an artifact from an S3 bucket, given a suffix key.

        :param suffix_key: a string indicating the suffix key
        :param ref_id: Optional reference ID to use instead of stateful_id
        :return: the content of the file as a string
        """

        if not ref_id:
            ref_id = self.stateful_id

        s3_key = f"{ref_id}/cur/{suffix_key}"

        return self._fetch_s3_artifact(s3_key)

    def _fetch_s3_artifact(self, s3_key):
        """
        Fetch a file from S3 with improved error handling and logging.
        
        :param s3_key: S3 key of the file to fetch
        :return: File content as string or False if retrieval failed
        """
        self.logger.debug(f'Attempting to retrieve file: s3_bucket: {self.tmp_bucket}/s3_key: {s3_key}')
        
        file_info = self.s3_file.exists_and_get(format="list",
                                                s3_bucket=self.tmp_bucket,
                                                s3_key=s3_key,
                                                stream=True)

        if file_info["status"] is False:
            self.logger.debug(f'Failed to retrieve file: s3_bucket: {self.tmp_bucket}/s3_key: {s3_key}')
            return False

        self.logger.debug(f'Successfully retrieved file: s3_bucket: {self.tmp_bucket}/s3_key: {s3_key}')

        indented_lines = ["    " + line for line in file_info["content"]]

        return ''.join(indented_lines)

    def _get_tfsec(self, ref_id=None):
        """
        Retrieves a tfsec artifact from an S3 bucket.

        :return: the content of the artifact as a string
        """

        if not ref_id:
            ref_id = self.stateful_id

        return self._get_s3_artifact(f"tfsec.{ref_id}.out", ref_id=ref_id)

    def _get_infracost(self, ref_id=None, filetype=None):
        """
        Retrieves an infracost artifact from an S3 bucket.

        :return: the content of the artifact as a string
        """
        if not ref_id:
            ref_id = self.stateful_id

        if filetype == "json":
            return self._get_s3_artifact(f"infracost.{ref_id}.json", ref_id=ref_id)

        return self._get_s3_artifact(f"infracost.{ref_id}.out", ref_id=ref_id)

    def _get_tfplan(self, ref_id=None):
        """
        Retrieves a Terraform plan artifact from an S3 bucket.

        :return: the content of the Terraform plan artifact as a string
        """
        if not ref_id:
            ref_id = self.stateful_id

        return self._get_s3_artifact(f"terraform.{ref_id}.tfplan.out", ref_id=ref_id)

    def _get_tfinit(self, ref_id=None):
        """
        Retrieves a Terraform init artifact from an S3 bucket.

        :return: the content of the Terraform init artifact as a string
        """
        if not ref_id:
            ref_id = self.stateful_id

        return self._get_s3_artifact(f"terraform.{ref_id}.init", ref_id=ref_id)

    def _get_tffmt(self, ref_id=None):
        """
        Retrieves a Terraform fmt artifact from an S3 bucket.

        :return: the content of the Terraform fmt artifact as a string
        """
        if not ref_id:
            ref_id = self.stateful_id

        return self._get_s3_artifact(f"terraform.{ref_id}.fmt", ref_id=ref_id)

    def _get_tfvalidate(self, ref_id=None):
        """
        Retrieves a Terraform validate artifact from an S3 bucket.

        :return: the content of the Terraform validate artifact as a string
        """
        if not ref_id:
            ref_id = self.stateful_id

        return self._get_s3_artifact(f"terraform.{ref_id}.validate", ref_id=ref_id)

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

    def _get_tf_md(self, ref_id=None):
        """
        Generates a markdown string that summarizes the Terraform process steps:
        Initialization, Validation, and Plan. Each section provides details
        retrieved from corresponding S3 artifacts and is enclosed in collapsible
        sections for better readability.

        Sections are only added if their content is not False.

        :param ref_id: Optional reference ID to use for retrieving artifacts
        :return: A markdown formatted string with Terraform process details.
        """
        content = "## 🏗️ Terraform\n\n"

        # Get section contents
        if self.report:
            tf_init = None
            tf_validate = None
        else:
            tf_init = self._get_tfinit(ref_id=ref_id)
            tf_validate = self._get_tfvalidate(ref_id=ref_id)

        tf_plan = self._get_tfplan(ref_id=ref_id)
        plan_summary = extract_plan_summary(tf_plan) if tf_plan else None

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
        
        return {
            "content": content,
            "plan_summary": plan_summary
        }

    def _get_tfsec_md(self, ref_id=None):
        """
        Generates a markdown string that summarizes the TFSec output:
        It retrieves the TFSec output from an S3 artifact and formats it
        with severity indicators and summary.

        :param ref_id: Optional reference ID to use for retrieving artifacts
        :return: A markdown formatted string with TFSec output.
        """
        # Get tfsec data and analyze
        _log = self._get_tfsec(ref_id=ref_id)

        if not _log:
            return False

        content = f'''### 4️⃣ Security Scan
<details>
    <summary>show details</summary>
{format_tfsec_output(_log)}
    
</details>
        '''

        tfsec_severity = self._analyze_tfsec_for_summary(_log)

        return {
            "content":content,
            "tfsec_severity": tfsec_severity
        }

    def _get_infracost_md(self, ref_id=None):
        """
        Generates a markdown string that summarizes the Infracost output:
        It retrieves the Infracost output from an S3 artifact and formats it
        with cost analysis details.

        :param ref_id: Optional reference ID to use for retrieving artifacts
        :return: A markdown formatted string with Infracost output.
        """
        _log = self._get_infracost(ref_id=ref_id)
        infracost_data = self._get_infracost(ref_id=ref_id, filetype="json")
        monthly_cost = extract_infracost_monthly(infracost_data) if infracost_data else "N/A"

        if not _log:
            return {
                "content":False,
                "monthly_cost": monthly_cost
            }

        content = f'''### 5️⃣ Cost Analysis
<details>
    <summary>show details</summary>
{format_infracost_output(_log)}
    
</details>
        '''

        return {
            "content":content,
            "monthly_cost": monthly_cost
        }

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

    def _get_pr_md(self, ref_id=None):
        """
        Generates a markdown string for the PR body that summarizes the Terraform process steps:
        Initialization, Validation, and Plan. Each section provides details
        retrieved from corresponding S3 artifacts and is enclosed in collapsible
        sections for better readability. Additionally, TFSec and Infracost outputs
        are included if available.

        :param ref_id: Optional reference ID to use for retrieving artifacts
        :return: dictionary with two keys: "comment_body" and "md5sum". The former
        is a markdown formatted string with Terraform process details, TFSec output,
        Infracost output, and CI details. The latter is the md5sum of the comment body.
        """
        _tf_md_info = self._get_tf_md(ref_id=ref_id)
        content = _tf_md_info["content"]
        plan_summary = _tf_md_info["plan_summary"]

        try:
            tf_sec_info = self._get_tfsec_md(ref_id=ref_id)
            tf_sec_content = tf_sec_info["content"]
            tfsec_severity = tf_sec_info["tfsec_severity"]
        except Exception as e:
            self.logger.debug(f"Failed to get TFSec content: {str(e)}")
            tf_sec_content = None
            tfsec_severity = None

        if tf_sec_content:
            content = content + "\n" + tf_sec_content

        try:
            infracost_info = self._get_infracost_md(ref_id=ref_id)
            infracost_content = infracost_info["content"]
            monthly_cost = infracost_info["monthly_cost"]
        except Exception as e:
            self.logger.debug(f"Failed to get Infracost content: {str(e)}")
            infracost_content = None
            monthly_cost = None

        if infracost_content:
            content = content + "\n" + infracost_content

        if not self.report:
            ci_link_content = self._ci_links()
            if ci_link_content:
                content = content + ci_link_content

        return {
            "content": content,
            "plan_summary": plan_summary,
            "monthly_cost": monthly_cost if monthly_cost else "N/A",
            "tfsec_severity": tfsec_severity if tfsec_severity else "N/A"
        }

    def _get_pr_id(self):
        """
        Return a unique identifier for this PR given by its repo, branch and PR number.

        :return: a string hash of the unique identifier
        """
        _obj = f'{self.repo_name}.{self.branch}.{self.pr_number}.pr_info'

        return get_hash_from_string(_obj)

    def _upsert_comment(self, pr_md_info, existing_comments=None, overwrite=True):
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
        if not existing_comments or len(existing_comments) == 1:
            self.logger.debug('Adding new comment - no existing comments found.')
            return self.github_repo.add_pr_comment(pr_md_info["comment_body"])

        try:
            comment_id = existing_comments[0]["id"]
        except:
            comment_id = None

        if not overwrite:
            self.logger.debug(f'Updating existing comment_id: {comment_id}')

            comment_info = self.github_repo.update_pr_comment(comment_id,
                                                              pr_md_info["comment_body"])

        if overwrite or not comment_info.get("status"):
            if comment_id:
                self.github_repo.delete_pr_comment(comment_id)
            self.logger.debug('Adding new comment instead.')
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

    def _exec_successful(self, ref_id=None):
        """
        Evaluate the PR and either add a new comment or update an existing one.

        The comment contains details about the Terraform plan, TFSec results, Infracost results,
        and CI details.

        If the PR is being destroyed, a new comment is always added. If the PR is not being
        destroyed, the comment is either added or updated depending on whether an existing
        comment with the same md5sum exists.

        :param ref_id: Optional reference ID to use for retrieving artifacts
        :return: A dictionary with the comment ID and its URL if the comment was
        added successfully, or False if the add failed.
        """
        content = self._get_pr_md(ref_id=ref_id)["content"]

        # Combine the table with tags for the comment body
        comment_body = f'{content}\n\n#{self.search_tag}'
        md5sum_str = get_hash_from_string(comment_body)

        pr_md_info = {
            "comment_body": comment_body,
            "md5sum": md5sum_str
        }

        if not self.run_info.get("destroy"):
            existing_comments = self.github_repo.get_pr_comments(use_default_search_tag=True)
            comment_info = self._upsert_comment(pr_md_info, existing_comments, overwrite=True)
        else:
            self.logger.debug(f"Adding new comment comment_id for destroy.")
            comment_info = self.github_repo.add_pr_comment(pr_md_info["comment_body"])

        self._clean_all_pr_comments()

        try:
            pr_md_info.update(comment_info)

            pr_md_info.update({
                "_id": self._get_pr_id(),
                "type": "pr_info"
            })

            self.results["notify"] = {
                "links": [{"github comment": pr_md_info["url"]}]
            }
        except Exception as e:
            self.logger.debug(f'Failed to update pr_md_info with comment_info: {str(e)}')
            return False

        return True

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
        self.remote_stateful_bucket = self.trigger_info["remote_stateful_bucket"]
        self.stateful_id = self.iac_ci_info["stateful_id"]
        self.tmp_bucket = self.trigger_info["s3_bucket_tmp"]
        self.pr_number = self.webhook_info["pr_number"]
        self.branch = self.webhook_info["branch"]
        self.repo_owner = self.webhook_info["owner"]

        github_token_info = self.get_github_token()

        if github_token_info.get("status"):
            self.github_token = github_token_info["value"]
        else:
            self.github_token = False

        self.set_search_tag()

    def _get_parallel_run_summary(self, run_id):
        """
        Get summary information for a single run with improved error handling.
        
        :param run_id: ID of the run to summarize
        :return: Dictionary containing summary information for the run
        """
        try:
            results = self.db.table_runs.search_key(key="_id", value=run_id)
            if not results.get("Items") or len(results["Items"]) == 0:
                self.logger.debug(f"No data found for run_id: {run_id}")
                return {
                    "iac_ci_folder": "N/A",
                    "run_id": run_id,
                    "status": "unknown"
                }
                
            values = results["Items"][0]
            return {
                "iac_ci_folder": values.get("iac_ci_folder", "N/A"),
                "run_id": run_id,
                "status": values.get("status", "unknown")
            }
        except Exception as e:
            self.logger.debug(f"Error retrieving run data for {run_id}: {str(e)}")
            return {
                "iac_ci_folder": "Error",
                "run_id": run_id,
                "status": "error"
            }

    def _get_parallel_runs_summary(self, run_ids):
        """
        Get summary information for multiple runs.
        
        :param run_ids: List of run IDs to summarize
        :return: List of dictionaries containing summary information for each run
        """
        results = []

        for run_id in run_ids:
            results.append(self._get_parallel_run_summary(run_id))

        return results

    def _get_s3_link_url(self, ref_id, iac_ci_folder, file_type):
        """
        Generate a clickable S3 URL for accessing artifacts.
        
        Creates a properly formatted s3:// URL that can be used with AWS CLI.
        
        :param ref_id: Reference ID (could be stateful_id or another ID) 
                      used to locate the file
        :param file_type: The type of file (tfplan, tfsec, infracost)
        :return: A properly formatted S3 URL string
        """
        s3_base_ref_path = f'{self.repo_name}/{self.branch}/{str(self.pr_number)}/{iac_ci_folder}'

        if file_type == "tfplan":
            src_key = f"{ref_id}/cur/terraform.{ref_id}.tfplan.out"
            dest_key = f"{s3_base_ref_path}/cur/terraform.{ref_id}.tfplan.out"
        elif file_type == "tfsec":
            src_key = f"{ref_id}/cur/tfsec.{ref_id}.out"
            dest_key = f"{s3_base_ref_path}/cur/tfsec.{ref_id}.out"
        elif file_type == "infracost":
            src_key = f"{ref_id}/cur/infracost.{ref_id}.out"
            dest_key = f"{s3_base_ref_path}/cur/infracost.{ref_id}.out"
        else:
            return "#"

        # Copy the file within the same bucket
        try:
            self.s3_file.copy(self.tmp_bucket, src_key, self.tmp_bucket, dest_key)
            self.logger.debug(f"File copied from {src_key} to {dest_key} within the same bucket.")
            s3_url = f"s3://{self.tmp_bucket}/{dest_key}"
        except Exception as e:
            self.logger.debug(f"Error occurred while copying: {e}")
            s3_url = f"s3://{self.tmp_bucket}/{src_key}"

        return s3_url
    
    def _get_pr_md_parallel_runs(self, runs_summary):
        """
        Generate a markdown table summarizing multiple runs with enhanced plan details
        and a collapsible with all S3 file locations.

        :param runs_summary: List of dictionaries containing summary information for each run
        :return: Dictionary with comment_body and md5sum
        """
        # Initialize the content with a header
        content = "## 🏗️ Terraform Multi-Folder Summary\n\n"

        # Initialize the table header with original columns
        table = "| Folder | Drift Check | Security | Cost |\n"
        table += "|--------|------------|----------|------|\n"

        comment_folders = {}

        # Process each run and add to the table
        for run in runs_summary:
            run_id = run["run_id"]
            folder = run.get("iac_ci_folder", "N/A")
            folder_anchor = folder.replace("/", "-").replace(" ", "-").lower()

            # testtest456
            pr_md_results = self._get_pr_md(run_id)
            content_folder = pr_md_results["content"]
            plan_summary = pr_md_results["plan_summary"]
            tfsec_severity = pr_md_results["tfsec_severity"]
            monthly_cost = pr_md_results["monthly_cost"]

            # Generate S3 links
            tf_plan_link = self._get_s3_link_url(run_id, folder, "tfplan")
            tfsec_link = self._get_s3_link_url(run_id, folder, "tfsec")
            infracost_link = self._get_s3_link_url(run_id, folder, "infracost")

            # Add these links to the content_folder
            content_folder += f"\n\n**S3 Links:**\n- Terraform Plan: `{tf_plan_link}`\n- Security Report: `{tfsec_link}`\n- Cost Report: `{infracost_link}`"

            # Update the comment with the added S3 links
            comment_body_folder = f'{content_folder}\n\n#{self.base_report_tag} {folder}'
            comment_info_folder = self.github_repo.add_pr_comment(comment_body_folder)

            if not comment_info_folder.get("status"):
                self.logger.debug(f"Failed to add comment for folder report {folder}.")
            else:
                comment_id = comment_info_folder["comment_id"]
                url = comment_info_folder["url"]
                comment_folders[folder] = url
                self.logger.debug(f"Adding new comment comment_id {comment_id} for folder report {folder}.")

            # Format the terraform plan cell with drift indicators
            if plan_summary:
                add_count = int(plan_summary.get('add', '0'))
                change_count = int(plan_summary.get('change', '0'))
                destroy_count = int(plan_summary.get('destroy', '0'))

                if add_count == 0 and change_count == 0 and destroy_count == 0:
                    tf_plan_cell = "✅ No Drift"
                else:
                    # Show counts with color-coded indicators (red X for drift)
                    changes = []
                    if add_count > 0:
                        changes.append(f"❌/🟣+{add_count}")
                    if change_count > 0:
                        changes.append(f"❌/🟠~{change_count}")
                    if destroy_count > 0:
                        changes.append(f"❌/🔴-{destroy_count}")

                    tf_plan_cell = f"{' '.join(changes)}"
            else:
                tf_plan_cell = "❓ Unknown"

            # Format the tfsec cell with icon based on severity
            if tfsec_severity == "success":
                tfsec_cell = "✅"
            elif tfsec_severity == "high":
                tfsec_cell = "❌"
            elif tfsec_severity == "medium":
                tfsec_cell = "⚠️"
            elif tfsec_severity == "low":
                tfsec_cell = "ℹ️"
            else:
                tfsec_cell = "❓"

            # Format the infracost cell
            infracost_cell = monthly_cost

            # Add row to the table with link to the folder's comment
            table += f"| [`{folder}`]({url}) | {tf_plan_cell} | {tfsec_cell} | {infracost_cell} |\n"

        # Add the table to the content
        content += table

        # Add legend for quick reference
        content += "\n**Legend:** ❌ Drift Detected | 🟣 Add | 🟠 Change | 🔴 Delete | ✅ No Drift/Issues | ❌ Critical/High | ⚠️ Medium | ℹ️ Low\n"

        # Add CI details if available
        ci_link_content = self._ci_links()
        if ci_link_content:
            content += "\n" + ci_link_content

        # Create the comment body
        comment_body = f'{content}\n\n#{self.base_report_tag} summary'
        md5sum_str = get_hash_from_string(comment_body)

        return {
            "comment_body": comment_body,
            "md5sum": md5sum_str
        }

    def _clear_report_all_comments(self):

        if not hasattr(self, "github_repo") or not self.github_repo:
            return False

        search_tag = "report all tf"

        comments = self.github_repo.get_pr_comments(search_tag=search_tag)
        report_comments = self.github_repo.get_pr_comments(search_tag=f'#{self.base_report_tag}')

        if comments and len(comments) > 1:
            comments.sort(key=lambda comment: comment["id"])
            for comment in comments[:-1]:
                comment_id = comment["id"]
                self.logger.debug(f'deleting "report all tf" comment {comment_id}')
                self.github_repo.delete_pr_comment(comment_id)

        if report_comments:
            for comment in report_comments:
                comment_id = comment["id"]
                self.logger.debug(f'deleting report related comment {comment_id}')
                self.github_repo.delete_pr_comment(comment_id)

    def _exec_parallel_runs(self, run_ids=None):
        """
        Execute parallel runs analysis and create summary PR comment.
        
        :param run_ids: List of run IDs to include in the summary
        :return: True if successful, False otherwise
        """

        if not run_ids:
            self.logger.debug("No run IDs provided for parallel runs")
            return False

        self.logger.debug("#" * 32)
        self.logger.debug('# Executing parallel runs analysis for run_ids')
        self.logger.json(run_ids)
        self.logger.debug("#" * 32)

        self._clear_report_all_comments()
        self._clean_all_pr_comments()

        runs_summary = self._get_parallel_runs_summary(run_ids)
        pr_md_info = self._get_pr_md_parallel_runs(runs_summary)

        existing_comments = self.github_repo.get_pr_comments(use_default_search_tag=True)
        comment_info = self._upsert_comment(pr_md_info, existing_comments, overwrite=True)

        if comment_info and comment_info.get("status"):
            self.results["notify"] = {
                "links": [{"github comment": comment_info.get("url", "")}]
            }
            return True

        return False

    def execute(self, ref_id=None):
        """
        Executes the main process for handling a GitHub pull request event.

        This method initializes necessary variables, sets the order, and creates
        a GitHubRepo instance to interact with the pull request. It evaluates the
        pull request to add or update comments with details about the Terraform plan,
        TFSec results, Infracost results, and CI details. If successful, it updates
        the results to indicate the process is complete, logs a summary, and saves
        run information.

        :param ref_id: Optional reference ID to use for retrieving artifacts
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

        parallel_folder_builds = self.run_info.get("parallel_folder_builds")

        if self.report and parallel_folder_builds:
            status = self._exec_parallel_runs(run_ids=parallel_folder_builds)
        else:
            if self.failure_s3_key:
                status = self._exec_failure(ref_id=ref_id)
            else:
                status = self._exec_successful(ref_id=ref_id)

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

    def _exec_failure(self, ref_id=None):
        # Retrieve failure log from S3
        failure_log = self._fetch_s3_artifact(self.failure_s3_key)
        if not failure_log:
            failure_log = f'Failed to retrieved file: s3_bucket: {self.tmp_bucket}/s3_key: {(self.failure_s3_key)}'

        # Get current status comment information
        status_comment_info = self.get_cur_status_comment()

        # Format markdown content with enhanced styling
        content = f'''## ❌ Failure Log

<details>
<summary style="color: #d73a49; cursor: pointer; font-weight: bold;">Click to expand error details</summary>

```
{failure_log}
```

</details>
'''
        self._clean_all_pr_comments()

        # Update PR comment with new content
        new_comment = f'{status_comment_info["body"]}\n\n{content}'
        self.github_repo.add_pr_comment(new_comment)

        # Set notification links in results
        self.results["notify"] = {
            "links": [{"github comment": status_comment_info["html_url"]}]
        }

        return True