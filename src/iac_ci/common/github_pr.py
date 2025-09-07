#!/usr/bin/env python

"""
GitHub Repository API Client

A module for interacting with GitHub repositories and managing pull requests.
"""

# Copyright (C) 2025 Gary Leong <gary@config0.com>
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
import requests
import base64
import hashlib
from iac_ci.common.loggerly import IaCLogger


class GitHubRepo:
    """
    A class to interact with GitHub repositories and manage pull requests.
    """

    def __init__(self, repo_name, pr_number, **kwargs):
        """
        Initializes the GitHubRepo class with repository details.

        Args:
            repo_name (str): Name of the repository.
            pr_number (int): Number of the pull request.
            **kwargs: Additional arguments including 'token' and 'owner'.

        Raises:
            ValueError: If 'GITHUB_TOKEN' is not set.
        """
        self.classname = "GitHubRepo"
        self.logger = IaCLogger(self.classname)

        if kwargs.get('token'):
            self.github_token = kwargs["token"]
        else:
            self.github_token = os.getenv('GITHUB_TOKEN')

        if not self.github_token:
            raise ValueError("Environment variable 'GITHUB_TOKEN' not set.")

        self._set_base_urls()
        self._set_repo_urls(repo_name, pr_number, owner=kwargs.get("owner"))
        self.search_tag = kwargs.get("search_tag")

        if self.search_tag:
            self.logger.debug(f"GitHubRepo - search_tag set: {self.search_tag}")

        self.apply = None

    def _set_repo_urls(self, repo_name, pr_number, owner=None):
        """
        Sets the repository URLs based on the provided details.

        Args:
            repo_name (str): Name of the repository.
            pr_number (int): Number of the pull request.
            owner (str, optional): Owner of the repository.
        """
        self.pr_number = pr_number

        if owner:
            self.owner = owner
        elif os.getenv('GITHUB_OWNER'):
            self.owner = os.getenv('GITHUB_OWNER')
        else:
            self.owner = self.get_owner()

        self.repo_name = repo_name
        self.url_pr = f'https://api.github.com/repos/{self.owner}/{self.repo_name}/pulls'
    
    def get_file(self, commit_hash, file_path='.iac_ci/config.yml'):
        """
        Retrieves and parses a YAML file from a specific commit hash.

        Args:
            commit_hash (str): The commit hash to get the file from.
            file_path (str, optional): Path to the YAML file. Defaults to '.iac_ci/config.yml'.

        Returns:
            dict: The parsed YAML content as a dictionary, or None if the file
                  doesn't exist or there was an error.
        """

        url = f'https://github.com/{self.owner}/{self.repo_name}/raw/{commit_hash}/{file_path}'

        response = requests.get(url, headers=self.headers)

        if response.status_code != 200:
            self.logger.error(f"Failed to get file {file_path} at commit {commit_hash}: {response.status_code}")
            return None

        data = response.json()

        # GitHub API returns content as base64 encoded
        if 'content' in data:
            try:
                return base64.b64decode(data['content']).decode('utf-8')
            except Exception as e:
                self.logger.error(f"Error processing file: {e}")
                return None

        self.logger.error(f"No content found in {file_path} at commit {commit_hash}")
        return None

    def _set_base_urls(self):
        """
        Sets the base URLs for accessing GitHub API.
        """
        self.url_owner = 'https://api.github.com/user'
        self.url_repos = 'https://api.github.com/user/repos'
        self.headers = {'Authorization': f'token {self.github_token}'}

    def _get_delete_comment_url(self, comment_id):
        """
        Constructs the URL for deleting a comment.

        Args:
            comment_id (int): ID of the comment to delete.

        Returns:
            str: URL for the delete comment API.
        """
        return f'https://api.github.com/repos/{self.owner}/{self.repo_name}/issues/comments/{comment_id}'

    def _set_pr_urls(self):
        """
        Sets the URLs specific to the pull request.
        """
        self.url_reviews = f'https://api.github.com/repos/{self.owner}/{self.repo_name}/pulls/{self.pr_number}/reviews'
        self.url_issues_comments = f'https://api.github.com/repos/{self.owner}/{self.repo_name}/issues/{self.pr_number}/comments'
        self.url_pr_comment = f'https://api.github.com/repos/{self.owner}/{self.repo_name}/pulls/{self.pr_number}/comments'
        self.url_pr_comment_by_id = f"https://api.github.com/repos/{self.owner}/{self.repo_name}/pulls/comments"
        self.url_comment_by_id = f"https://api.github.com/repos/{self.owner}/{self.repo_name}/issues/comments"

    def get_comment_by_id(self, comment_id, review_comment=False):
        """
        Retrieves a GitHub comment directly by its unique comment ID.

        Args:
            comment_id (int): The unique ID of the GitHub comment.
            review_comment (bool): True if it's a line-specific PR review comment,
                                   False if it's a general PR comment.

        Returns:
            dict: Comment data if successful.
            None: If comment not found or other errors occur.
        """
        self._set_pr_urls()

        if review_comment:
            url = f"{self.url_pr_comment_by_id}/{comment_id}"
        else:
            url = f"{self.url_comment_by_id}/{comment_id}"

        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            self.logger.debug(f"Successfully fetched comment ID: {comment_id}")
            return response.json()

        elif response.status_code == 404:
            self.logger.warn(f"Comment with ID {comment_id} not found.")
            return None

        else:
            self.logger.error(f"Error fetching comment ID {comment_id}: {response.status_code}, {response.text}")
            return None

    def get_pr_comments(self, use_default_search_tag=True, search_tag=None):
        """
        Retrieves comments from the pull request.

        Args:
            use_default_search_tag (bool): Whether to use the default search tag.
            search_tag (str, optional): Custom search tag to filter comments.

        Returns:
            list: List of comments matching the search criteria.
        """
        self._set_pr_urls()
        comments = []
        page = 1

        while True:
            response = requests.get(
                self.url_issues_comments,
                params={'page': page, 'per_page': 30},
                headers=self.headers
            )
            response.raise_for_status()
            data = response.json()

            if not data:
                break
        
            comments.extend(data)
            page += 1

        if search_tag:
            return self._filter_comment_by_tag(comments, search_tag=search_tag)
        elif use_default_search_tag:
            return self._filter_comment_by_tag(comments, search_tag=self.search_tag)

        return comments

    def _filter_comment_by_tag(self, comments, search_tag=None):
        """
        Filters comments based on the specified search tag.

        Args:
            comments (list): List of comments to filter.
            search_tag (str, optional): Tag to filter comments by.

        Returns:
            list: Filtered list of comments.
        
        Raises:
            ValueError: If no search tag is provided.
        """
        if not search_tag:
            search_tag = self.search_tag

        if not search_tag:
            raise ValueError("Search tag is needed to parse through comments")

        results = []

        for comment in comments:
            if search_tag in comment['body']:
                results.append(comment)

        self.logger.debug(f"search tag #{search_tag} found {len(results)}")

        return results

    @staticmethod
    def _get_str_hash(str_obj):
        """
        Computes the MD5 hash of the base64 encoded string.

        Args:
            str_obj (str): Input string to hash.

        Returns:
            str: MD5 hash of the encoded string.
        """
        body_b64 = base64.b64encode(str_obj.encode())
        return hashlib.md5(body_b64).hexdigest()

    def issue_to_pr(self, pr_number=None):
        """
        Retrieves pull request details and checks its approval status.

        Args:
            pr_number (int, optional): The pull request number to check.

        Returns:
            dict: Details of the pull request, including approval status.

        Raises:
            ValueError: If pr_number is not set.
        """
        if not pr_number:
            pr_number = self.pr_number

        if not pr_number:
            raise ValueError("pr_number needs to be set")

        self._set_pr_urls()
        pull_request_url = f"https://api.github.com/repos/{self.owner}/{self.repo_name}/pulls/{pr_number}"

        response = requests.get(pull_request_url, headers=self.headers)
        pr_approved = True if self.is_pr_approved() else None
        
        if response.status_code == 200:
            pr_data = response.json()
            return {
                'pr_number': pr_number,
                'pr_approved': pr_approved,
                'src_branch': pr_data['head']['ref'],
                'dest_branch': pr_data['base']['ref'],
                'branch': pr_data['base']['ref'],
                'commit_hash': pr_data['head']['sha'],
                'ssh_url': pr_data['head']['repo']['ssh_url'],
                'git_url': pr_data['head']['repo']['git_url'],
                'clone_url': pr_data['head']['repo']['clone_url']
            }
        
        self.logger.warn(f"Failed to get pull request data: {response.status_code}")
        return

    def _get_pr_review_comments(self):
        """
        Fetches and logs comments for the pull request.

        Logs details of each comment or indicates if none are found.
        """
        response = requests.get(self.url_pr_comment, headers=self.headers)

        if response.status_code == 200:
            comments = response.json()
            if comments:
                self.logger.debug(f"Comments for Pull Request #{self.pr_number} in {self.repo_name}:")
                for comment in comments:
                    self.logger.debug(f"{comment['user']['login']} on line {comment['line']}: {comment['body']}")
            else:
                self.logger.debug("No comments for this pull request.")
        else:
            self.logger.debug(f"Failed to fetch comments: {response.status_code}, {response.text}")

    def _update_pr_comment(self, comment_id, comment):
        """
        Updates a specific comment by its ID.

        Args:
            comment_id (int): ID of the comment to update.
            comment (str): New comment text.

        Returns:
            Response object from the update request.
        """
        url = f'https://api.github.com/repos/{self.owner}/{self.repo_name}/issues/comments/{comment_id}'
        return requests.patch(
            url,
            headers=self.headers,
            json={'body': comment}
        )

    def _add_pr_comment(self, comment):
        """
        Adds a new comment to the pull request.

        Args:
            comment (str): Comment text to add.

        Returns:
            Response object from the add comment request.
        """
        return requests.post(
            self.url_issues_comments, 
            headers=self.headers, 
            json={'body': comment}
        )

    def get_changed_files(self, pr_num=None):
        """
        Retrieves the list of files changed in a pull request.

        Args:
            pr_num (int, optional): The pull request number. Defaults to the instance's pr_number.

        Returns:
            list: List of file objects containing information about changed files.
                  Each file object includes keys like:
                  - filename: path of the file
                  - status: 'added', 'modified', 'removed', etc.
                  - additions: number of lines added
                  - deletions: number of lines deleted
                  - changes: total changes
                  - patch: diff patch if available

        Raises:
            ValueError: If pr_num is not provided and not set in the instance.
        """
        if not pr_num:
            pr_num = self.pr_number

        if not pr_num:
            raise ValueError("Pull request number (pr_num) must be provided")

        url = f'https://api.github.com/repos/{self.owner}/{self.repo_name}/pulls/{pr_num}/files'

        files = []
        page = 1

        # GitHub API paginates results, so we need to fetch all pages
        while True:
            response = requests.get(
                url,
                params={'page': page, 'per_page': 100},  # 100 is the maximum per page
                headers=self.headers
            )

            if response.status_code != 200:
                self.logger.error(f"Failed to fetch changed files: {response.status_code}, {response.text}")
                return []

            data = response.json()

            if not data:  # No more pages
                break

            files.extend(data)
            page += 1

        self.logger.debug(f"Found {len(files)} changed files in PR #{pr_num}")
        return files

    def get_changed_dirs(self, pr_num=None, include_root=False):
        """
        Retrieves the list of unique directories containing changed files in a pull request.

        Args:
            pr_num (int, optional): The pull request number. Defaults to the instance's pr_number.
            include_root (bool, optional): Whether to include the root directory (".") in results.
                                          Defaults to False.

        Returns:
            list: Sorted list of unique directories containing changed files.

        Raises:
            ValueError: If pr_num is not provided and not set in the instance.
        """
        # Get all changed files
        changed_files = self.get_changed_files(pr_num=pr_num)

        # Extract directories from file paths
        dirs = set()
        for file_obj in changed_files:
            filepath = file_obj.get('filename', '')

            # Skip special files like "~" which might be temporary
            if filepath in ['~'] or filepath.startswith('.') and len(filepath) == 1:
                continue

            if '/' in filepath:
                # For files in subdirectories, extract the directory path
                dir_path = '/'.join(filepath.split('/')[:-1])
                dirs.add(dir_path)
            elif include_root and filepath:  # Only add root if file is valid
                # For files in the root directory, add "." if requested
                dirs.add(".")

        # Convert to sorted list
        return sorted(list(dirs))

    def get_owner(self):
        """
        Retrieves the GitHub username associated with the personal access token.

        Returns:
            str: GitHub username.

        Raises:
            ValueError: If user info cannot be fetched.
        """
        response = requests.get(self.url_owner, headers=self.headers)

        if response.status_code != 200:
            raise ValueError(f"Failed to fetch user info: {response.status_code}, {response.text}")

        user_info = response.json()
        return user_info['login']

    def list_repos(self):
        """
        Lists all repositories for the authenticated user.

        Returns:
            list: List of repositories.

        Raises:
            ValueError: If repositories cannot be fetched.
        """
        response = requests.get(self.url_repos, headers=self.headers)

        if response.status_code != 200:
            raise ValueError(f"Failed to fetch repositories: {response.status_code}, {response.text}")

        return response.json()

    def _pr_comment_common(self, comment):
        """
        Prepares the comment for adding or updating.

        Args:
            comment (str): Comment text to prepare.

        Returns:
            tuple: Encoded comment and its MD5 hash.

        Raises:
            ValueError: If 'GITHUB_PR_COMMENT_B64' is not set when comment is None.
        """
        self._set_pr_urls()

        if comment:
            encoded_comment = base64.b64encode(comment.encode())
        else:
            encoded_comment = os.getenv('GITHUB_PR_COMMENT_B64')

        if not encoded_comment:
            raise ValueError("Environment variable 'GITHUB_PR_COMMENT_B64' not set.")

        md5_hash = hashlib.md5(str(encoded_comment).encode()).hexdigest()
        return encoded_comment, md5_hash


    def update_pr_comment(self, comment_id, comment):
        """
        Updates an existing pull request comment.

        Args:
            comment_id (int): ID of the comment to update.
            comment (str): New comment text.

        Returns:
            dict: Result of the update operation containing comment details.
        """
        _, md5_hash = self._pr_comment_common(comment)
        response = self._update_pr_comment(comment_id, comment)

        if response.status_code == 200:
            url = f'https://github.com/{self.owner}/{self.repo_name}/pull/{self.pr_number}#issuecomment-{comment_id}'
            self.logger.debug(f"Comment updated successfully with ID: {comment_id}.")
            return {
                "comment_id": comment_id,
                "url": url,
                "comment": comment,
                "md5sum": md5_hash,
                "status": True
            }

        self.logger.warn(f"Failed to update comment: {comment_id}")
        return {"status": False}

    def add_pr_comment(self, comment):
        """
        Adds a new comment to the pull request.

        Args:
            comment (str): Comment text to add.

        Returns:
            dict: Result of the add operation containing comment details.
        """
        encoded_comment, md5_hash = self._pr_comment_common(comment)
        decoded_comment = base64.b64decode(encoded_comment).decode('utf-8')

        response = self._add_pr_comment(decoded_comment)

        if response.status_code == 201:
            comment_data = response.json()
            comment_id = comment_data['id']
            self.logger.debug(f"Comment added successfully with ID: {comment_id}.")
            
            url = f'https://github.com/{self.owner}/{self.repo_name}/pull/{self.pr_number}#issuecomment-{comment_id}'

            return {
                "id": comment_id,
                "comment_id": comment_id,
                "comment": decoded_comment,
                "url": url,
                "md5sum": md5_hash,
                "status": True
            }

        self.logger.debug(f"Failed to add comment: {response.status_code}, {response.text}")

        return {"status": False}
    
    def is_pr_approved(self):
        """
        Checks if the specified pull request is approved.

        Returns:
            bool: True if approved, False otherwise, or None if the check fails.
        """
        self._set_pr_urls()
        response = requests.get(self.url_reviews, headers=self.headers)

        if response.status_code == 200:
            reviews = response.json()
            for review in reviews:
                if review['state'] == 'APPROVED':
                    self.logger.debug(f"Pull Request #{self.pr_number} in {self.repo_name} is approved.")
                    return True
            self.logger.debug(f"Pull Request #{self.pr_number} in {self.repo_name} is not approved.")
            return False
        
        self.logger.debug(f"Failed to fetch reviews: {response.status_code}, {response.text}")
        return

    def delete_pr_comment(self, comment_id):
        """
        Deletes a specific comment by its ID.

        Args:
            comment_id (int): ID of the comment to delete.
        """
        response = requests.delete(self._get_delete_comment_url(comment_id), headers=self.headers)

        if response.status_code == 204:
            self.logger.debug(f"Comment {comment_id} deleted successfully.")
        else:
            self.logger.debug(f"Comment {comment_id} deletion failed.")