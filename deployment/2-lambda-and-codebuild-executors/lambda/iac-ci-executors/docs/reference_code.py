import subprocess
from time import time


def execute_logfile_and_s3(command, timeout=None, heartbeat_interval=None, to_s3=None):

    # Start the subprocess
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        shell=True  # Use shell=True to allow command as a string
    )

    start_time = time()
    last_output_time = time()

    try:
        while True:
            # Check if the process has finished
            if process.poll() is not None:
                break

            # Check for timeout if specified
            if timeout is not None and time() - start_time > timeout:
                msg = "Process timed out!"
                print(msg,end='')
                process.terminate()
                break

            # Read output line by line
            line = process.stdout.readline()
            if line:
                print(line)
                last_output_time = time()  # Update last output time
            else:
                # Check for heartbeat if specified
                if heartbeat_interval is not None and time() - last_output_time > heartbeat_interval:
                    msg = "No output received for a while, process may be stalled!"
                    print(msg,end='')
                    process.terminate()  # Terminate if stalled

            if to_s3 and time() - last_output_time > 30:
                try:
                    to_s3()
                except Exception:
                    print("trouble uploading logfile to s3")
    except KeyboardInterrupt:
        process.terminate()  # Terminate on keyboard interrupt
    finally:
        process.stdout.close()
        process.wait()  # Wait for the process to complete

    return process.returncode  # Get the exit code
