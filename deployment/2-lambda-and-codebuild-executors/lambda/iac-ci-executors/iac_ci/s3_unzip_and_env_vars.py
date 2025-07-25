#!/usr/bin/env python
"""
Module for handling S3 zip file extraction and environment variable loading.
Provides functionality to download and extract zip files from S3, and load environment variables from encrypted files and SSM parameters.
"""

import base64
import os
import tempfile
import zipfile
import boto3
import shutil
from io import BytesIO

class S3UnzipEnvVar:
    """
    A class to handle S3 zip file extraction and environment variable loading.

    Attributes:
        bucket_name (str): Name of the S3 bucket
        bucket_key (str): Key of the zip file in S3
        dest_dir (str): Destination directory for extraction
        app_dir (str): Application directory path
        env_vars (dict): Dictionary to store environment variables
        base_file_path (str): Base path for extracted files
    """

    def __init__(self, bucket_name, bucket_key, dest_dir=None, app_dir=None):
        """
        Initialize S3UnzipEnvVar with bucket and directory information.

        Args:
            bucket_name (str): Name of the S3 bucket
            bucket_key (str): Key of the zip file in S3
            dest_dir (str, optional): Destination directory for extraction
            app_dir (str, optional): Application directory path
        """
        self.ssm_client = boto3.client('ssm')

        self.bucket_name = bucket_name
        self.bucket_key = bucket_key
        self.env_vars = {}

        if dest_dir:
            self.dest_dir = dest_dir
        else:
            self.dest_dir = tempfile.mkdtemp(prefix='/tmp/unzip_')

        if app_dir:
            self.app_dir = app_dir
        elif os.environ.get("APP_DIR"):
            self.app_dir=os.environ["APP_DIR"]
        else:
            self.app_dir = 'var/tmp/terraform'

        if not os.path.exists(self.dest_dir):
            os.makedirs(self.dest_dir)

        self.base_file_path = os.path.join(self.dest_dir,
                                          self.app_dir)

    def _download_and_extract(self):
        """
        Download zip file from S3 and extract its contents.

        Downloads the specified zip file from S3 into memory and extracts it
        to the destination directory.
        """
        # Initialize S3 client
        s3 = boto3.client('s3')

        # Download zip file into memory
        zip_file_obj = BytesIO()

        s3.download_fileobj(self.bucket_name,
                            self.bucket_key,
                            zip_file_obj)

        zip_file_obj.seek(0)

        with zipfile.ZipFile(zip_file_obj, 'r') as zip_ref:
            zip_ref.extractall(self.dest_dir)

    def _load_env_vars(self):
        """
        Load environment variables from encrypted files.

        Reads and decodes environment variables from build_env_vars.env.enc
        and ssm.env.enc files in the extracted directory.
        """
        build_file_path = f'{self.base_file_path}/build_env_vars.env.enc'
        ssm_file_path = f'{self.base_file_path}/ssm.env.enc'

        for _file in [ build_file_path, ssm_file_path ]:
            if not os.path.exists(_file):
                print(f'env_var file: "{_file}" does not exists')
                continue

            with open(_file, 'rb') as enc_file:
                encoded_content = enc_file.read()
                decoded_content = base64.b64decode(encoded_content)
                env_var_lines = decoded_content.decode('utf-8').strip().splitlines()

                for line in env_var_lines:
                    if '=' in line:
                        key, value = line.split('=', 1)
                        self.env_vars[key.strip()] = value.strip()

    def _load_ssm_parameters(self):
        """
        Load SSM parameters from AWS Systems Manager.

        Retrieves and processes SSM parameters specified in environment variables
        or previously loaded environment variables.
        """
        ssm_names = os.environ.get("SSM_NAMES")
        ssm_name = os.environ.get("SSM_NAME")

        if not ssm_names:
            ssm_names = self.env_vars.get("SSM_NAMES")

        if not ssm_name:
            ssm_name = self.env_vars.get("SSM_NAME")

        if ssm_names:
            # Split the comma-delimited string into a list
            parameter_names = [name.strip() for name in ssm_names.split(',')]
        elif ssm_name:
            parameter_names = [ssm_name]
        else:
            parameter_names = None

        if parameter_names:
            self._retrieve_ssm_parameters(parameter_names)

    def _insert_env_var_lines(self, env_var_lines):
        """
        Process and insert environment variable lines into env_vars dictionary.

        Args:
            env_var_lines (list): List of environment variable lines to process

        Returns:
            dict: Updated environment variables dictionary
        """
        for line in env_var_lines:
            # Strip whitespace and ignore empty lines or comments
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Remove 'export ' if it exists
            if line.startswith('export '):
                line = line[len('export '):]
            
            # Ensure the line contains an '=' character
            if '=' in line:
                try:
                    key_value = line.split('=', 1)
                except Exception:
                    print('WARN: could not split the line by "="')
                    key_value = None

                if not key_value:
                    continue

                try:
                    key = key_value[0].strip()
                except Exception:
                    print('WARN: could not strip or get "key" for env var')
                    continue

                try:
                    value = key_value[1].strip().strip('\"')  # Remove quotes if present
                except Exception:
                    print('WARN: could not strip or get "value" for env var')
                    continue

                print(f'added env variable "{key}" to env_vars')
                self.env_vars[key] = value

        return self.env_vars

    def _get_and_parse_ssm_param(self, name):
        """
        Retrieve and parse a single SSM parameter.

        Args:
            name (str): Name of the SSM parameter to retrieve
        """
        response = self.ssm_client.get_parameter(Name=name,
                                                 WithDecryption=True)
        # Decode the base64 encoded value
        decoded_value = base64.b64decode(response['Parameter']['Value'])

        # Convert bytes to string and split into lines
        env_var_lines = decoded_value.decode('utf-8').strip().splitlines()

        # Add to env_vars dictionary
        self._insert_env_var_lines(env_var_lines)

    def _retrieve_ssm_parameters(self, parameter_names):
        """
        Retrieve multiple SSM parameters.

        Args:
            parameter_names (list): List of SSM parameter names to retrieve
        """
        for name in parameter_names:
            print("#"*32)
            print(f'# Looking to retrieve ssm_name: "{name}"')
            print("#"*32)
            try:
                self._get_and_parse_ssm_param(name)
            except Exception as e:
                print("#" * 32)
                print(f"# Error retrieving parameter {name}: {e}")
                print("#"*32)

    def _get_env_vars(self):
        """
        Get the loaded environment variables.

        Returns:
            dict: Dictionary of loaded environment variables
        """
        return self.env_vars

    def run(self):
        """
        Execute the complete workflow of downloading, extracting, and loading variables.

        Returns:
            dict: Dictionary of all loaded environment variables
        """
        self._download_and_extract()
        self._load_env_vars()
        self._load_ssm_parameters()

        return self._get_env_vars()
