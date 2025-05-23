#!/usr/bin/env python

import os
from iac_ci.exec_log_s3 import ShellOutToS3
from get_aws_creds_frm_file import load_aws_credentials
from iac_ci.s3_unzip_and_env_vars import S3UnzipEnvVar

# Usage example
if __name__ == "__main__":


    stateful_id = "change"
    infracost_api_key = "change"

    bucket_name = f"app-env.stateful.iac.change.change"
    bucket_key = f"{stateful_id}/state/src.{stateful_id}.zip"

    os.environ["STATEFUL_ID"] = stateful_id
    os.environ["INFRACOST_API_KEY"] = infracost_api_key

    # Load credentials
    aws_credentials_path = '/tmp/aws.env'
    load_aws_credentials(aws_credentials_path)

    s3_env_vars = S3UnzipEnvVar(bucket_name,
                                bucket_key)

    env_vars = s3_env_vars.run()

    executor = ShellOutToS3(env_vars,
                            bucket_name,
                           f"{stateful_id}/last_run.log",
                            exec_dir=f"/tmp/{stateful_id}/var/tmp/terraform")

    commands_to_execute=[
        "echo 'Hello World'",
        "ls -al",
        "infracost breakdown --path ."
    ]

    executor.exec_cmds(commands_to_execute)