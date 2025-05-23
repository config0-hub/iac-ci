"""
Module for loading AWS credentials from environment files.
Provides functionality to safely load AWS credentials from .env files.
"""

import os
from dotenv import load_dotenv


def load_aws_credentials(env_file_path):
    """
    Load AWS credentials from a specified environment file.

    This function attempts to load environment variables from a .env file,
    which typically contains AWS credentials and configuration.

    Args:
        env_file_path (str): Path to the environment file containing AWS credentials

    Raises:
        FileNotFoundError: If the specified environment file does not exist

    Returns:
        None

    Example:
        >>> load_aws_credentials('.env')
        # Successfully loads AWS credentials from .env file
        
        >>> load_aws_credentials('non_existent.env')
        # Raises FileNotFoundError
    """
    if os.path.exists(env_file_path):
        load_dotenv(env_file_path)
    else:
        raise FileNotFoundError(f"{env_file_path} not found.")
