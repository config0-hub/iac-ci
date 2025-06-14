#!/usr/bin/env python

import datetime

class DirectPrintLogger:
    """Logger implementation that uses print directly, for Lambda compatibility"""
    def __init__(self, execution_id):
        self.execution_id = execution_id
    
    def _format_message(self, level, message):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        return f"{timestamp} - {level} - {self.execution_id} {message}"
    
    def debug(self, message, prefix=""):
        if prefix:
            # If a prefix is provided, add it to each line with a space
            lines = message.split('\n')
            for line in lines:
                print(f"{prefix} {line}")
        else:
            # Regular formatting
            print(self._format_message("DEBUG", message))
    
    def info(self, message, prefix=""):
        if prefix:
            # If a prefix is provided, add it to each line with a space
            lines = message.split('\n')
            for line in lines:
                print(f"{prefix} {line}")
        else:
            # Regular formatting
            print(self._format_message("INFO", message))
    
    def warn(self, message, prefix=""):
        if prefix:
            # If a prefix is provided, add it to each line with a space
            lines = message.split('\n')
            for line in lines:
                print(f"{prefix} {line}")
        else:
            # Regular formatting
            print(self._format_message("WARNING", message))
    
    def warning(self, message, prefix=""):
        self.warn(message, prefix)
    
    def error(self, message, prefix=""):
        if prefix:
            # If a prefix is provided, add it to each line with a space
            lines = message.split('\n')
            for line in lines:
                print(f"{prefix} {line}")
        else:
            # Regular formatting
            print(self._format_message("ERROR", message))
    
    def critical(self, message, prefix=""):
        if prefix:
            # If a prefix is provided, add it to each line with a space
            lines = message.split('\n')
            for line in lines:
                print(f"{prefix} {line}")
        else:
            # Regular formatting
            print(self._format_message("CRITICAL", message))