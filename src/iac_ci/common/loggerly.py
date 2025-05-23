#!/usr/bin/env python
#
# Copyright 2025 Gary Leong <gary@config0.com>
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
import json
import logging


class IaCLogger(object):
    """
    A custom logger class designed for Infrastructure-as-Code (IaC) platforms.
    
    This class provides enhanced logging functionality, including support for
    JSON-formatted logs, message aggregation, and specialized logging for
    debugging, informational, warning, error, and critical messages. It also
    ensures that verbose logging from libraries like Boto3 is suppressed.

    Attributes:
        classname: The name of the class ('IaCLogger').
        iac_platform: The IaC platform, derived from the environment variable `IAC_PLATFORM`.
        direct: The direct logging instance for the logger.
        aggregate_msg: A buffer for aggregating messages before logging them.
    """

    def __init__(self, name, **kwargs):
        """
        Initializes the IaCLogger instance.

        Parameters:
            name (str): The name of the logger instance.
            **kwargs: Additional keyword arguments (currently unused).

        The constructor sets up the logger to write logs to a file in the `/tmp/{IAC_PLATFORM}/log` directory.
        It also suppresses verbose logging from Boto3-related libraries.
        """
        self.classname = 'IaCLogger'
        self.iac_platform = os.environ.get("IAC_PLATFORM", "config0")

        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)

        try:
            # Suppress verbose logging from Boto3 and related libraries
            logging.getLogger().setLevel(logging.WARNING)
            logging.getLogger('boto3').setLevel(logging.WARNING)
            logging.getLogger('botocore').setLevel(logging.WARNING)
            logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
            logging.getLogger('s3transfer.utils').setLevel(logging.WARNING)
            logging.getLogger('s3transfer.tasks').setLevel(logging.WARNING)
            logging.getLogger('s3transfer.futures').setLevel(logging.WARNING)
        except (AttributeError, ValueError) as e:
            logger.warn(f"Could not complete disabling verbose logging for Boto3 related activities: {str(e)}")

        # Create a log directory and file
        logdir = f"/tmp/{self.iac_platform}/log"
        os.system(f"mkdir -p {logdir}")
        logfile = f"{logdir}/{self.iac_platform}_main.log"

        fh = logging.FileHandler(logfile)
        fh.setLevel(logging.DEBUG)

        # Set up a formatter for the log messages
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(formatter)
        logger.addHandler(fh)

        self.direct = logger
        self.aggregate_msg = None

    def json(self, message):
        """
        Logs a JSON-formatted message.

        Parameters:
            message (dict): The message to log in JSON format.
        """
        try:
            self.debug(f"\n{json.dumps(message, indent=4)}\n")
        except (TypeError, ValueError) as e:
            self.debug(f"Failed to serialize to JSON: {message} (Error: {str(e)})")

    def aggmsg(self, message, new=False, prt=None, cmethod="debug"):
        """
        Aggregates messages for collective logging.

        Parameters:
            message (str): The message to aggregate.
            new (bool): Whether to start a new aggregated message.
            prt (bool): Whether to print the aggregated message.
            cmethod (str): The logging method to use (e.g., 'debug', 'info').

        Returns:
            str: The current aggregated message.
        """
        if not self.aggregate_msg:
            new = True

        if not new:
            self.aggregate_msg = f"{self.aggregate_msg}\n{message}"
        else:
            self.aggregate_msg = f"\n{message}"

        if not prt:
            return self.aggregate_msg

        msg = self.aggregate_msg
        self.print_aggmsg(cmethod)

        return msg

    def print_aggmsg(self, cmethod="debug"):
        """
        Prints the aggregated message using the specified logging method.

        Parameters:
            cmethod (str): The logging method to use (e.g., 'debug', 'info').
        """
        _method = f'self.{cmethod}(self.aggregate_msg)'
        eval(_method)
        self.aggregate_msg = ""

    def debug_highlight(self, message):
        """
        Logs a debug message with visual highlighting.

        Parameters:
            message (str): The message to log.
        """
        self.direct.debug("+" * 32)
        self.direct.debug(message)
        self.direct.debug("+" * 32)

    def info(self, message):
        """
        Logs an informational message.

        Parameters:
            message (str): The message to log.
        """
        self.direct.info(message)

    def debug(self, message):
        """
        Logs a debug message.

        Parameters:
            message (str): The message to log.
        """
        self.direct.debug(message)

    def critical(self, message):
        """
        Logs a critical message with visual emphasis.

        Parameters:
            message (str): The message to log.
        """
        self.direct.critical("!" * 32)
        self.direct.critical(message)
        self.direct.critical("!" * 32)

    def error(self, message):
        """
        Logs an error message with visual emphasis.

        Parameters:
            message (str): The message to log.
        """
        self.direct.error("*" * 32)
        self.direct.error(message)
        self.direct.error("*" * 32)

    def warn(self, message):
        """
        Logs a warning message with visual emphasis.

        Parameters:
            message (str): The message to log.
        """
        self.direct.warn("-" * 32)
        self.direct.warn(message)
        self.direct.warn("-" * 32)