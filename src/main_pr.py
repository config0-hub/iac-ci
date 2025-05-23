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

from iac_ci.common.utilities import get_hash_from_string
from iac_ci.common.github_pr import GitHubRepo
from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.orders import OrdersStagesHelper as PlatformReporter


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

    def _get_s3_artifact(self, suffix_key):
        """
        Retrieves an artifact from an S3 bucket, given a suffix key.

        :param suffix_key: a string indicating the suffix key
        :return: the content of the file as a string
        """
        s3_key = os.path.join(self.stateful_id,
                              "cur",
                              suffix_key)

        file_info = self.s3_file.exists_and_get(format="list",
                                                s3_bucket=self.tmp_bucket,
                                                s3_key=s3_key,
                                                stream=True)

        if file_info["status"] is False:
            if file_info["failed_message"]:
                self.logger.error(file_info["failed_message"])
                return file_info["failed_message"]
            else:
                return f'Failed to retrieved file: s3_bucket: {self.tmp_bucket}/s3_key: {s3_key}'

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

        :return: A markdown formatted string with Terraform process details.
        """
        content = f'''## Terraform

__Initialization__

<details>
    <summary>show</summary>
{self._get_tfinit()}
    
</details>

__Validation__

<details>
    <summary>show</summary>
{self._get_tfvalidate()}
    
</details>

__Plan__

<details>
    <summary>show</summary>
{self._get_tfplan()}
    
</details>
        '''
    
        return content

    def _get_tfsec_md(self):
        """
        Generates a markdown string that summarizes the TFSec output:
        It retrieves the TFSec output from an S3 artifact and encloses it
        in a collapsible section for better readability.

        :return: A markdown formatted string with TFSec output.
        """
        content = f'''## TFSec
<details>
    <summary>show</summary>
{self._get_tfsec()}
    
</details>
        '''
        return content

    def _get_infracost_md(self):
        """
        Generates a markdown string that summarizes the Infracost output:
        It retrieves the Infracost output from an S3 artifact and encloses it
        in a collapsible section for better readability.

        :return: A markdown formatted string with Infracost output.
        """
        content = f'''## Infracost
<details>
    <summary>show</summary>
{self._get_infracost()}
    
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

        pr_info = self.eval_pr()

        self.results["notify"] = {
            "links": [{"github comment": pr_info["url"]}]
        }

        # successful at this point
        self.results["update"] = True
        self.results["close"] = True
        self.results["status"] = "successful"

        summary_msg = f"# Triggered \n# trigger_id: {self.trigger_id} \n# iac_ci_id: {self.iac_ci_id}\n"

        self.add_log("#" * 32)
        self.add_log("# Summary")
        self.add_log(summary_msg)
        self.add_log("#" * 32)

        self.insert_to_return()
        self.finalize_order()
        self._save_run_info()

        return True