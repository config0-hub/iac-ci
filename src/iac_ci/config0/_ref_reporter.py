#!/usr/bin/env python

import os

from iac_ci.common.http_utils import execute_http_post
from iac_ci.common.loggerly import IaCLogger

"""
NOT being used but provided as reference to report 
results to a third party platform such as Config0
or some other API endpoint
"""

class Config0Reporter:

    def __init__(self,**kwargs):

        self.classname = "Config0Reporter"
        self.logger = IaCLogger(self.classname)
        self.disable_config0_report = kwargs.get("disable_config0_report",True)  # True by default

    def _set_report_url(self,**kwargs):
        """
        https://app.config0.com/williaumwu/debug-auto-04/598

        Sets the report URL.

        This method constructs and sets the report URL based on information
        received from the Config0 API response. It extracts the run sequence ID,
        nickname, and SaaS environment from the response and uses them to build
        the URL. If the necessary information is not found in the response,
        the method returns without setting the URL.

        Args:
            kwargs (dict): Keyword arguments containing the API response.

        Returns:
            str or None: The constructed report URL, or None if the URL could not be constructed.
        """
        try:
            run_seq_id = kwargs["api"]["response"]["results"]["run_seq_id"]
            nickname = kwargs["api"]["response"]["results"]["nickname"]
            saas_env = kwargs["api"]["response"]["results"]["saas_env"]
        except Exception:
            return

        self.report_url = f"https://{saas_env}.config0.com/{nickname}/{self.trigger_info['project']}/{run_seq_id}"

        return self.report_url

    def sent_to_config0(self):
        """
        Sends results to Config0.

        This method sends the collected run results to the Config0 platform
        via an HTTP POST request. It retrieves the necessary input arguments
        for the request using _get_inputargs_http, executes the request,
        logs the interaction, sets the report URL, and returns the results
        from the Config0 API. The reporting is skipped if disable_config0_report is True.

        Returns:
            dict: The results of the HTTP POST request to Config0.
       """
        if self.disable_config0_report:
            return

        if not self.callback_token and not self.ssm_callback_token:
            return

        if not self.user_endpoint:
            return

        inputargs = self._get_inputargs_http()
        results = execute_http_post(**inputargs)

        self.logger.debug("%"*32)
        self.logger.debug("")
        self.logger.debug(f"Sent results to {inputargs['api_endpoint']}")

        if os.environ.get("DEBUG"):
            self.logger.json(results)
        self.logger.debug("%"*32)

        self._set_report_url(**results)

        return results
