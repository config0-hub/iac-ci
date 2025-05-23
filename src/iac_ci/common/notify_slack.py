#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
SlackNotify

A utility for sending richly formatted notifications to Slack.

Copyright 2025 Gary Leong <gary@config0.com>
License: GNU General Public License v3.0
"""

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
import sys
import requests
from iac_ci.common.serialization import b64_decode
from iac_ci.common.loggerly import IaCLogger


class SlackNotify:
    """
    A class for sending richly formatted notifications to Slack.

    This class supports constructing and sending Slack messages with various
    components like headers, titles, payloads, links, and a message body. It
    integrates with the IaCLogger for logging and uses a base64-decoded webhook
    URL to send the notification.

    Attributes:
        username (str): The username to display in the Slack notification.
        header_text (str): The header text for the Slack message.
        divider (dict): A default divider block for Slack messages.
        classname (str): The name of the class ('SlackNotify').
        logger (IaCLogger): Logger instance for debugging and error reporting.
        slack_data (dict): The base Slack message structure.
        inputargs (dict): Input arguments containing message details.
        url (str): The Slack incoming webhook URL.
        title (dict): The title block of the message.
        payload (list): Payload sections of the Slack message.
        message (list): Message body sections of the Slack message.
        links (list): List of link sections for the Slack message.
        icon_emoji (str): Emoji icon for the Slack message.
        channel (str): Slack channel to send the message to.
    """

    def __init__(self, **kwargs):
        """
        Initializes the SlackNotify instance.

        Parameters:
            **kwargs: Keyword arguments containing 'username' and 'header_text' for the message.
        """
        self.username = kwargs["username"]
        self.header_text = kwargs["header_text"]
        self.divider = {"type": "divider"}
        self.classname = "SlackNotify"
        self.logger = IaCLogger(self.classname, logcategory="cloudprovider")
        self._set_base()

    def _setup(self, inputargs):
        """
        Prepares the Slack notification by setting up configuration parameters.

        Parameters:
            inputargs (dict): Input arguments containing configuration details like
                              'slack_webhook_b64', 'payload', 'message', 'links', etc.

        Returns:
            bool: True if the setup is successful, False otherwise.
        """
        self.inputargs = inputargs

        slack_webhook_b64 = inputargs.get("slack_webhook_b64")

        if not slack_webhook_b64:
            slack_webhook_b64 = os.environ.get("SLACK_WEBHOOK_B64")

        if not slack_webhook_b64:
            slack_webhook_b64 = inputargs.get("slack_webhook_hash")

        if not slack_webhook_b64:
            slack_webhook_b64 = os.environ.get("SLACK_WEBHOOK_HASH")

        # These variables need to be set
        try:
            self.url = b64_decode(slack_webhook_b64)
        except (TypeError, ValueError) as e:
            self.logger.error(f"Failed to decode webhook URL: {e}")
            self.url = None

        if not self.url:
            return False

        self.title = None
        self.payload = []
        self.message = []
        self.links = []

        return True

    def _set_misc(self):
        """
        Sets miscellaneous parameters like the icon emoji and Slack channel.
        """
        self.icon_emoji = self.inputargs.get("icon_emoji", ":arrows_counterclockwise:")
        self.channel = self.inputargs.get("slack_channel")

    def _set_base(self):
        """
        Initializes the base structure for the Slack message.
        """
        self.slack_data = {"username": self.username, "blocks": []}

    def _set_headers(self):
        """
        Sets the header block for the Slack message.
        """
        self.header = {
            "type": "header",
            "text": {"type": "plain_text", "text": self.header_text, "emoji": True},
        }

    def _set_title(self):
        """
        Sets the title block for the Slack message.
        """
        text = self.inputargs.get("title") or "This is the summary"

        self.title = {
            "type": "section",
            "text": {"type": "plain_text", "text": text, "emoji": True},
        }

    def _set_payload(self):
        """
        Sets the payload block for the Slack message.
        """
        payload = self.inputargs.get("payload")
        if not payload:
            return

        self.payload.append(self.divider)
        self.payload.append(
            {
                "type": "section",
                "text": {
                    "type": "plain_text",
                    "text": json.dumps(payload, indent=4),
                    "emoji": True,
                },
            }
        )

    def _set_links(self):
        """
        Sets the links block for the Slack message.

        The links are provided as a list of dictionaries, where each dictionary
        maps a title to a URL.
        """
        links = self.inputargs.get("links")
        
        if not links:
            return
            
        for link in links:
            for _title, _link in link.items():
                self.links.append(
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": f"<{_link}|{_title}>"},
                    }
                )

    def _set_message(self):
        """
        Sets the main message block for the Slack message.
        """
        message = self.inputargs.get("message")

        if not message:
            return

        self.message.append(self.divider)
        self.message.append(
            {
                "type": "section",
                "text": {"type": "plain_text", "text": message},
            }
        )

    def _assemble(self):
        """
        Assembles the complete Slack message by combining all blocks.
        """
        self._set_headers()
        self._set_title()
        self._set_payload()
        self._set_message()
        self._set_links()
        self._set_misc()

        if self.channel:
            self.slack_data["channel"] = self.channel
            
        self.slack_data["icon_emoji"] = self.icon_emoji
        
        if self.header:
            self.slack_data["blocks"].append(self.header)
            
        self.slack_data["blocks"].append(self.divider)
        
        if self.title:
            self.slack_data["blocks"].append(self.title)
            
        if self.payload:
            self.slack_data["blocks"].extend(self.payload)
            
        if self.message:
            self.slack_data["blocks"].extend(self.message)
            
        if self.links:
            self.slack_data["blocks"].extend(self.links)

        self.slack_data["blocks"].append(self.divider)

    def _send_message(self):
        """
        Sends the assembled Slack message to the configured webhook URL.

        Returns:
            bool: True if the message was sent successfully, False otherwise.
        """
        byte_length = str(sys.getsizeof(self.slack_data))
        headers = {"Content-Type": "application/json", "Content-Length": byte_length}

        try:
            response = requests.post(self.url, data=json.dumps(self.slack_data), headers=headers)
        except requests.RequestException as e:
            self.logger.error(f"Failed to send Slack message: {e}")
            return False

        if response.status_code == 200:
            return True

        self.logger.error(
            f"_send_message status_code: {response.status_code}\ntrace: {response.text}"
        )
        return False
            

    def run(self, inputargs):
        """
        Executes the Slack notification process.

        Parameters:
            inputargs (dict): Input arguments containing details for the Slack message.
        """
        status = self._setup(inputargs=inputargs)

        if not status:
            return

        self._assemble()
        self._send_message()


if __name__ == "__main__":
    try:
        main = SlackNotify(username="IaC Notification", header_text="Notification")
        main.run(inputargs=b64_decode(os.environ["SLACK_INPUTARGS"]))
    except KeyError as e:
        print(f"Missing required environment variable: {e}")
    except Exception as e:
        print(f"Error running SlackNotify: {e}")