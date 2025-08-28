#!/usr/bin/env python
"""
S3 File operations using boto3.

This module provides a class for handling S3 file operations.
"""

# Copyright 2025 Gary Leong gary@config0.com
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
from time import sleep
from botocore.exceptions import ClientError
from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.boto3_common import Boto3Common
from iac_ci.common.utilities import id_generator2


class S3FileBoto3(Boto3Common):
    """
    A class for handling S3 file operations using boto3.
    Inherits from Boto3Common for AWS connectivity.

    This class provides methods for common S3 operations including:
    - Checking if files exist
    - Uploading files
    - Downloading files
    - Removing files
    - Getting S3 URLs
    """

    def __init__(self, **kwargs):
        """
        Initialize S3FileBoto3 instance.

        Args:
            **kwargs: Arbitrary keyword arguments passed to parent class
        """
        self.classname = 'S3FileBoto3'
        self.logger = IaCLogger(self.classname)
        self.logger.debug(f"Instantiating {self.classname}")
        Boto3Common.__init__(self, 's3', **kwargs)

    @staticmethod
    def get_url(**kwargs):
        """
        Generate S3 URL from bucket and key.

        Args:
            **kwargs: Must contain:
                s3_bucket (str): Name of S3 bucket
                s3_key (str): S3 object key

        Returns:
            str: Formatted S3 URL
        """
        s3_bucket = kwargs["s3_bucket"]
        s3_key = kwargs["s3_key"]

        return f"s3://{os.path.join(s3_bucket, s3_key)}"

    def exists_and_get(self, format=None, **kwargs):
        """
        Check if S3 object exists and retrieve it.

        Args:
            format (str, optional): Format of returned content ('list' for line-by-line)
            **kwargs: Must contain:
                s3_key (str): S3 object key
                s3_bucket (str): S3 bucket name
                dstfile (str, optional): Destination file path
                stream (bool, optional): Whether to stream file content (default: True)

        Returns:
            dict/str: If stream=True, returns dict with status and content
                     If stream=False, returns destination file path
        """
        s3_key = kwargs.get("s3_key")
        s3_bucket = kwargs.get("s3_bucket")
        dstfile = kwargs.get("dstfile")
        stream = kwargs.get("stream", True)

        if not dstfile:
            dstfile = f'/tmp/{id_generator2()}'

        if not self.exists(s3_bucket, s3_key):
            failed_message = f"exists_and_get: NOT FOUND s3_bucket: {s3_bucket}, s3_key: {s3_key}"
            self.logger.debug(failed_message)
            return {
                "status": False,
                "failed_message": failed_message
            }

        self.get(s3_bucket=s3_bucket,
                 s3_key=s3_key,
                 dstfile=dstfile)

        if not os.path.exists(dstfile):
            failed_message = f"exists_and_get: file {dstfile} not found"
            self.logger.debug(failed_message)
            return {
                "status": False,
                "failed_message": failed_message
            }

        if not stream:
            return dstfile

        with open(dstfile, 'r') as file:
            if format == "list":
                content = file.readlines()
            else:
                content = file.read()

        return {
            "status": True,
            "content": content
        }

    def get(self, **kwargs):
        """
        Download file from S3.

        Args:
            **kwargs: Must contain:
                dstfile (str): Destination file path
                s3_key (str): S3 object key
                s3_bucket (str): S3 bucket name

        Returns:
            boto3 response object
        """
        dstfile = kwargs["dstfile"]
        s3_key = kwargs["s3_key"]
        s3_bucket = kwargs["s3_bucket"]

        return self.client.download_file(s3_bucket, s3_key, dstfile)

    def copy(self, src_s3_bucket, src_s3_key, dst_s3_bucket, dst_s3_key):

        copy_source = {
            'Bucket': src_s3_bucket,
            'Key': src_s3_key
        }

        obj = self.resource.Object(dst_s3_bucket, dst_s3_key)

        return obj.copy(copy_source)
        
    def exists(self, s3_bucket, s3_key):
        """
        Check if S3 object exists.

        Args:
            s3_bucket (str): S3 bucket name
            s3_key (str): S3 object key

        Returns:
            bool: True if object exists, False otherwise
        """
        try:
            self.client.head_object(Bucket=s3_bucket, Key=s3_key)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == '404':
                self.logger.debug(f's3 object bucket {s3_bucket} s3_key {s3_key} does not exists')
            else:
                self.logger.debug(f'Error checking s3 object: {e}')
            return False

        return True

    def verify(self, s3_bucket=None, s3_key=None, wait_int=1, retries=60):
        """
        Verify S3 object exists with retries.

        Args:
            s3_bucket (str): S3 bucket name
            s3_key (str): S3 object key
            wait_int (int, optional): Wait interval between retries in seconds (default: 1)
            retries (int, optional): Number of retry attempts (default: 60)

        Returns:
            bool: True if object exists within retry attempts, False otherwise
        """
        for retry in range(retries):
            if self.exists(s3_bucket, s3_key):
                return True
            sleep(wait_int)
        return False

    def insert(self, **kwargs):
        """
        Upload file to S3.

        Args:
            **kwargs: Must contain:
                srcfile (str): Source file path
                s3_bucket (str): S3 bucket name
                s3_key (str): S3 object key
                public (bool, optional): Make object public readable
                verify (bool, optional): Verify upload success

        Returns:
            boto3 response object or bool if verify=True
        """
        srcfile = kwargs["srcfile"]
        s3_bucket = kwargs["s3_bucket"]
        s3_key = kwargs["s3_key"]
        public = kwargs.get("public")
        verify = kwargs.get("verify")

        if not public:
            response = self.client.upload_file(srcfile, s3_bucket, s3_key)
        else:
            response = self.resource.meta.client.upload_file(srcfile,
                                                            s3_bucket,
                                                            s3_key,
                                                            ExtraArgs={'ACL': 'public-read'})

        if verify:
            self.logger.debug(f"VERIFIED: s3_bucket {s3_bucket}, s3_key {s3_key} to be inserted")
            return self.verify(s3_bucket, s3_key)

        return response

    def remove(self, s3_bucket, s3_key):
        """
        Remove object from S3.

        Args:
            s3_bucket (str): S3 bucket name
            s3_key (str): S3 object key

        Returns:
            boto3 response object or None if object doesn't exist
        """
        if not self.exists(s3_bucket, s3_key):
            return

        obj = self.resource.Object(s3_bucket, s3_key)

        return obj.delete()
