#!/usr/bin/env python
"""
A collection of utility functions and CLI tools for file operations, encryption, and AWS interactions.
"""

import base64
import json
import os
import traceback


def str_to_py_obj(str_obj):
    """
    Decode a base64 encoded string and convert it to a Python object.

    Args:
        str_obj (str): Base64 encoded string

    Returns:
        dict: Decoded Python object
    """
    decoded_string = base64.b64decode(str_obj).decode('utf-8')
    return json.loads(decoded_string)


def execute(cmd):
    """
    Execute a shell command and return its status.

    Args:
        cmd (str): Command to execute

    Returns:
        dict: Execution result containing:
            - output: Command output (None)
            - exitcode: Command exit code
            - status: Boolean indicating success
            - failed_msg: Error message if failed (optional)
    """
    failed_msg = None
    print(f'executing cmd = {cmd}')

    try:
        exitcode = os.system(cmd)
    except Exception:
        exitcode = "89"
        failed_msg = traceback.format_exc()

    if exitcode == 0:
        return {
            "output": None,
            "exitcode": exitcode,
            "status": True
        }

    print(f'## FAILED: cmd = {cmd}')
    return {
        "output": None,
        "exitcode": exitcode,
        "status": False,
        "failed_msg": failed_msg
    }


def write_get_ssm_cli():
    """Create a CLI tool for retrieving AWS SSM parameters."""
    contents = '''#!/usr/bin/env python

import argparse
import boto3
import base64
import fileinput

def retrieve_ssm_parameter(parameter_name):
    # Create a Boto3 SSM client
    ssm_client = boto3.client('ssm')

    # Retrieve the parameter value
    response = ssm_client.get_parameter(Name=parameter_name, WithDecryption=True)

    # Extract the value from the response
    parameter_value = response['Parameter']['Value']

    return parameter_value

def decode_from_base64(value):
    decoded_value = base64.b64decode(value).decode('utf-8')
    return decoded_value

def concatenate_to_file(file_path, content):
    with open(file_path, 'a') as file:
        file.write(content)

def remove_export_prefix(file_path):
    with fileinput.FileInput(file_path, inplace=True, backup='.bak') as file:
        for line in file:
            line = line.strip()
            if line.startswith('export '):
                line = line[len('export '):]
            print(line)

def add_export_prefix(file_path):
    with fileinput.FileInput(file_path, inplace=True, backup='.bak') as file:
        for line in file:
            line = line.strip()
            if not line.startswith('export '):
                line = 'export ' + line
            print(line)

if __name__ == '__main__':
    # Create an argument parser
    parser = argparse.ArgumentParser(description='Retrieve an SSM parameter value from the Parameter Store and concatenate it to a file')

    # Add the parameter name argument
    parser.add_argument('-name', type=str, help='Name of the parameter in the Parameter Store')

    # Add the file path argument
    parser.add_argument('-file', type=str, help='Path to the file to concatenate the parameter value')

    # Parse the command-line arguments
    args = parser.parse_args()

    # Retrieve the parameter value
    value = retrieve_ssm_parameter(args.name)
    
    # Decode the parameter value from Base64
    decoded_value = decode_from_base64(value)

    # Concatenate the decoded value to the file
    concatenate_to_file(args.file, decoded_value)
    
    # remove export prefix all lines
    remove_export_prefix(args.file)
    
    # add export prefix to all lines
    #add_export_prefix(args.file)
    
'''

    # Write contents to the file
    with open("/tmp/ssm_get", 'w') as file:
        file.write(contents)
    os.chmod("/tmp/ssm_get", 0o755)


def write_curl_cli():
    """Create a Python-based curl utility CLI tool."""
    contents = '''#!/usr/bin/env python
    
import sys
import os

sys.path = [
   '/var/task', 
   '/opt/python/lib/python3.9/site-packages', 
   '/opt/python', 
   '/var/runtime', 
   '/var/lang/lib/python39.zip', 
   '/var/lang/lib/python3.9', 
   '/var/lang/lib/python3.9/lib-dynload', 
   '/var/lang/lib/python3.9/site-packages', 
   '/opt/python/lib/python3.9/site-packages', 
   '/opt/python']

import argparse
import requests

def main():
    parser = argparse.ArgumentParser(description='Python curl utility with -L -s -o options')
    parser.add_argument('url', help='URL to retrieve')
    parser.add_argument('-L', '--location', action='store_true', help='Follow redirects')
    parser.add_argument('-s', '--silent', action='store_true', help='Silent mode')
    parser.add_argument('-o', '--output', help='Output file path')

    args = parser.parse_args()

    response = requests.get(args.url, allow_redirects=args.location)
    content = response.content

    if args.output:
        with open(args.output, 'wb') as file:
            file.write(content)
    elif not args.silent:
        print(content.decode('utf-8'))

if __name__ == '__main__':
    main()
'''

    # Write contents to the file
    with open("/tmp/curl", 'w') as file:
        file.write(contents)
    os.chmod("/tmp/curl", 0o755)


def write_untar():
    """Create a Python-based tar extraction utility."""
    contents = '''#!/usr/bin/env python

import argparse
import tarfile
import os
import sys

def extract_tar_gz(file_path, output_dir='.'):
    """Extract a tar.gz file to the specified output directory."""
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"The file '{file_path}' does not exist.")

    with tarfile.open(file_path, 'r:gz') as tar:
        tar.extractall(path=output_dir)
        print(f"Extracted {file_path} to {output_dir}")

def main():
    # Check for the correct number of arguments
    if len(sys.argv) < 3:
        print("Usage: python extract_tar_gz.py xfz <file> -C <directory>")
        sys.exit(1)

    # Check if the first argument is 'xfz'
    if sys.argv[1] != 'xfz':
        print("Error: First argument must be 'xfz'")
        sys.exit(1)

    # Set up argument parser
    parser = argparse.ArgumentParser(description='Extract a tar.gz file using xfz options.')
    parser.add_argument('file', help='The tar.gz file to extract')
    parser.add_argument('-C', '--directory', default='.',
                        help='Directory to extract to (default: current directory)')

    # Parse arguments
    args = parser.parse_args(sys.argv[2:])  # Skip the first two arguments

    try:
        # Extract the tar.gz file
        extract_tar_gz(args.file, args.directory)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
    '''

    # Write contents to the file
    with open("/tmp/tar",'w') as file:
        file.write(contents)
    os.chmod("/tmp/tar", 0o755)


def write_b64_decode():
    """Create a base64 decoding utility."""
    contents = '''#!/usr/bin/env python

import argparse
import base64
import sys
import os

sys.path = [
   '/var/task', 
   '/opt/python/lib/python3.9/site-packages', 
   '/opt/python', 
   '/var/runtime', 
   '/var/lang/lib/python39.zip', 
   '/var/lang/lib/python3.9', 
   '/var/lang/lib/python3.9/lib-dynload', 
   '/var/lang/lib/python3.9/site-packages', 
   '/opt/python/lib/python3.9/site-packages', 
   '/opt/python']

def decode_file(input_file, output_file):

    # Read the encoded content from the input file
    with open(input_file, 'r') as file:
        _file_content = file.read()

    # Convert the decoded content from base64
    try:
        base64_content = base64.b64decode(_file_content).decode()
    except Exception:
        base64_content = _file_content

    # Write the decoded content to the output file
    with open(output_file, 'w') as file:
        file.write(base64_content)

def main():
    parser = argparse.ArgumentParser(description='Base64 utility')
    parser.add_argument('-e', '--encoded_file', help='Path to the encoded file')
    parser.add_argument('-d', '--decoded_file', help='decoded_file destination')

    args = parser.parse_args()

    encoded_file = args.encoded_file
    decoded_file = args.decoded_file

    decode_file(encoded_file, decoded_file)

if __name__ == '__main__':
    main()
    '''

    # Write contents to the file
    with open("/tmp/decode_file",'w') as file:
        file.write(contents)
    os.chmod("/tmp/decode_file", 0o755)


def write_decrypt_cli():
    """Create a Fernet decryption utility."""
    contents = '''#!/usr/bin/env python
    
import argparse
import base64
import sys
import os

sys.path = [
   '/var/task', 
   '/opt/python/lib/python3.9/site-packages', 
   '/opt/python', 
   '/var/runtime', 
   '/var/lang/lib/python39.zip', 
   '/var/lang/lib/python3.9', 
   '/var/lang/lib/python3.9/lib-dynload', 
   '/var/lang/lib/python3.9/site-packages', 
   '/opt/python/lib/python3.9/site-packages', 
   '/opt/python']
   
from cryptography.fernet import Fernet

def convert_to_fernet_key(key):

    # Pad the key with zeros to make it 32 bytes long
    padded_key = key.ljust(32, "\\x00")

    # Convert the padded key to bytes
    key_bytes = padded_key.encode()

    # Encode the key bytes using base64
    base64_key = base64.urlsafe_b64encode(key_bytes)

    return base64_key

def decrypt_file(input_file, output_file, secret):

    passphrase = convert_to_fernet_key(secret)

    # Read the encrypted content from the input file
    with open(input_file, 'rb') as file:
        encrypted_content = file.read()

    # Decrypt the encrypted content
    cipher_suite = Fernet(passphrase)
    decrypted_content = cipher_suite.decrypt(encrypted_content)

    # Convert the decrypted content from base64
    base64_content = base64.b64decode(base64.b64decode(decrypted_content))

    # Write the decrypted content to the output file
    with open(output_file, 'wb') as file:
        file.write(base64_content)
    
def main():
    parser = argparse.ArgumentParser(description='Fernet Decrypt utility')
    parser.add_argument('-e', '--encrypted_file', help='Path to the encrypted file')
    parser.add_argument('-s', '--secret', help='Secret for decrypting')
    parser.add_argument('-d', '--decrypted_file', help='decrypted_file destination')

    args = parser.parse_args()

    encrypted_file = args.encrypted_file
    decrypted_file = args.decrypted_file
    secret = args.secret
    
    #print(f'Encrypted file {encrypted_file}')
    #print(f'Decrypted file {decrypted_file}')
    #print(f'Secret file {secret}')
    
    decrypt_file(encrypted_file, decrypted_file, secret)

if __name__ == '__main__':
    main()
    
    '''

    # Write contents to the file
    with open("/tmp/decrypt", 'w') as file:
        file.write(contents)
    os.chmod("/tmp/decrypt", 0o755)


def write_zip_cli():
    """Create a ZIP file creation utility."""
    contents = '''#!/usr/bin/env python

import argparse
import zipfile
import os

def zip_files(zip_file_path, source_directory, recursive):
    source_directory = os.path.abspath(source_directory)
    
    with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
        if recursive:
            for root, dirs, files in os.walk(source_directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    zip_ref.write(file_path, os.path.relpath(file_path, source_directory))
        else:
            for file in os.listdir(source_directory):
                file_path = os.path.join(source_directory, file)
                if os.path.isfile(file_path):
                    zip_ref.write(file_path, file)

    print(f"ZIP file created: {zip_file_path}")

def main():
    parser = argparse.ArgumentParser(description='Zip utility')
    parser.add_argument('zip_file', help='Path to the ZIP file')
    parser.add_argument('-r', '--recursive', action='store_true', help='Include subdirectories and files recursively')
    parser.add_argument('source_directory', nargs='?', default='.', help='Source directory for zipping')

    args = parser.parse_args()

    source_directory = os.getcwd() if args.source_directory == '.' else args.source_directory
    zip_file_path = args.zip_file
    recursive = args.recursive

    zip_files(zip_file_path, source_directory, recursive)

if __name__ == '__main__':
    main()

'''

    # Write contents to the file
    with open("/tmp/zip", 'w') as file:
        file.write(contents)
    os.chmod("/tmp/zip", 0o755)


def write_unzip_cli():
    """Create a ZIP file extraction utility."""
    contents = '''#!/usr/bin/env python

import argparse
import zipfile
import os

def unzip_file(zip_file_path, destination_directory, overwrite):
    with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
        zip_ref.extractall(destination_directory)
        if overwrite:
            for member in zip_ref.infolist():
                extracted_path = zip_ref.extract(member, destination_directory)
        else:
            zip_ref.extractall(destination_directory)

def main():
    parser = argparse.ArgumentParser(description='Unzip utility')
    parser.add_argument('zip_file', help='Path to the ZIP file')
    parser.add_argument('-o', '--overwrite', action='store_true', help='Overwrite files if they exist')
    parser.add_argument('-d', '--destination', default='.', help='Destination directory for extraction')

    args = parser.parse_args()

    zip_file_path = args.zip_file
    destination_directory = args.destination
    overwrite = args.overwrite

    unzip_file(zip_file_path, destination_directory, overwrite)

if __name__ == '__main__':
    main()
    
'''

    # Write contents to the file
    with open("/tmp/unzip", 'w') as file:
        file.write(contents)
    os.chmod("/tmp/unzip", 0o755)


def write_awscli_entrypt():
    """Create an AWS CLI wrapper."""
    contents = '''#!/usr/bin/env python
    
import sys
import os

sys.path = [
   '/var/task', 
   '/opt/python/lib/python3.9/site-packages', 
   '/opt/python', 
   '/var/runtime', 
   '/var/lang/lib/python39.zip', 
   '/var/lang/lib/python3.9', 
   '/var/lang/lib/python3.9/lib-dynload', 
   '/var/lang/lib/python3.9/site-packages', 
   '/opt/python/lib/python3.9/site-packages', 
   '/opt/python']

if os.environ.get('LC_CTYPE', '') == 'UTF-8':
    os.environ['LC_CTYPE'] = 'en_US.UTF-8'
import awscli.clidriver

def main():
    return awscli.clidriver.main()

if __name__ == '__main__':
    sys.exit(main())
'''
    # Write contents to the file
    with open("/tmp/aws", 'w') as file:
        file.write(contents)
    os.chmod("/tmp/aws", 0o755)


def append_to_log(log_file, msgs):
    """
    Append messages to a log file.

    Args:
        log_file (str): Path to the log file
        msgs (str or list): Message or list of messages to append

    Returns:
        None
    """
    log_dir = os.path.dirname(log_file)

    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    if not os.path.exists(log_file):
        open(log_file,'a').close()

    if not msgs:
        return

    if isinstance(msgs,list):
        _msgs = msgs
    else:
        _msgs = [ msgs ]

    with open(log_file,'a') as log:
        for _msg in _msgs:
            log.write(_msg.strip() + '\n')
