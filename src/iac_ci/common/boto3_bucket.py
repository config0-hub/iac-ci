#!/usr/bin/env python
"""
S3 bucket management functionality using boto3.

Copyright (C) 2025 Gary Leong <gary@config0.com>
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import json
from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.boto3_common import Boto3Common


class S3BucketBoto3(Boto3Common):

    def __init__(self, **kwargs):
        """
        Instantiate an instance of the S3BucketBoto3 class.

        This class provides methods for interacting with AWS S3 buckets using the boto3 library.

        Parameters
        ----------
        **kwargs : dict
            A dictionary of keyword arguments.
        """
        self.classname = 'S3BucketBoto3'
        self.logger = IaCLogger(self.classname)
        self.logger.debug(f"Instantiating {self.classname}")
        Boto3Common.__init__(self, 's3', **kwargs)

    def exists(self, **kwargs):
        """
        Check if an S3 bucket exists.

        This method checks if a given S3 bucket exists.
        """
        name = kwargs["name"]

        try:
            if self.resource.Bucket(name).creation_date is not None:
                return True
            return False
        except Exception as e:
            self.logger.debug(f"Error checking if bucket {name} exists: {str(e)}")
            return False

    def enable_encryption(self, **kwargs):
        """
        Enable encryption on an S3 bucket.

        This method enables default server-side encryption using AES256 for a given S3 bucket.
        """
        name = kwargs["name"]
        server_side_encryption_configuration = {
            'Rules': [
                {
                    'ApplyServerSideEncryptionByDefault': {
                        'SSEAlgorithm': 'AES256'
                    }
                },
            ]
        }

        return self.client.put_bucket_encryption(
            Bucket=name,
            ServerSideEncryptionConfiguration=server_side_encryption_configuration,
        )

    def set_expire_days(self, **kwargs):
        """
        Set expiry days for objects in an S3 bucket.

        This method sets a lifecycle policy on a given S3 bucket to expire objects after a specified number of days.
        """
        name = kwargs["name"]
        expire_days = kwargs.get("expire_days")

        expire = {
            "Rules": [
                {
                    "Status": "Enabled",
                    "Prefix": "",
                    "Expiration": {
                        "Days": expire_days
                    }
                }
            ]
        }

        return self.client.put_bucket_lifecycle(
            Bucket=name, 
            LifecycleConfiguration=expire
        )

    def create(self, **kwargs):
        """
        Create an S3 bucket.

        This method creates an S3 bucket with optional encryption, expiry days, and location constraints.
        """
        name = kwargs["name"]
        encryption = kwargs.get("encryption")
        clobber = kwargs.get("clobber")
        expire_days = kwargs.get("expire_days")
        location_contraint = kwargs.get("location_contraint")

        if self.exists(**kwargs):
            self.logger.debug(f'bucket name = {name} already exists')
            if not clobber:
                return
            self.destroy(force=True, **kwargs)

        if location_contraint:
            location = {'LocationConstraint': self.aws_default_region}
            self.client.create_bucket(
                Bucket=name,
                CreateBucketConfiguration=location
            )
        else:
            self.client.create_bucket(Bucket=name)

        if encryption:
            self.enable_encryption(**kwargs)
            
        if expire_days:
            self.set_expire_days(**kwargs)

        results = {"name": name}

        if location_contraint:
            results["location_contraint"] = location_contraint
            results["region"] = self.aws_default_region

        if kwargs.get("encryption"):
            results["encryption"] = True
            
        if kwargs.get("expire_days"):
            results["expire_days"] = expire_days

        return results

    def destroy(self, **kwargs):
        """
        Destroy an S3 bucket.

        This method destroys a given S3 bucket, optionally forcing the deletion of all objects within the bucket first.
        """
        name = kwargs["name"]
        force = kwargs.get("force", True)

        if not self.exists(**kwargs):
            self.logger.debug(f'bucket name = {name} does not exists')
            return

        if force:
            bucket = self.resource.Bucket(name)
            bucket.objects.all().delete()

        self.client.delete_bucket(Bucket=name)

        return True

    def list(self, **kwargs):
        """
        List all S3 buckets.

        This method lists all available S3 buckets, optionally returning the raw output or printing it as JSON.
        """
        try:
            response = self.client.list_buckets()
            output = [bucket["Name"] for bucket in response['Buckets']]
        except Exception as e:
            self.logger.error(f"Error listing buckets: {str(e)}")
            return

        if not output:
            return

        if kwargs.get('raw'):
            return output

        print(json.dumps(output, indent=4))