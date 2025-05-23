#!/usr/bin/env python
#
# Copyright (C) 2025 Gary Leong gary@config0.com
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

from time import sleep
from botocore.errorfactory import ClientError
from boto3.dynamodb.conditions import Key

from iac_ci.common.loggerly import IaCLogger
from iac_ci.common.boto3_common import Boto3Common


class DynamodbHelper(Boto3Common):
    """
    A helper class for interacting with DynamoDB tables.
    """

    def __init__(self, **kwargs):
        """
        Initialize the DynamodbHelper class.
        
        Parameters:
        kwargs (dict): A dictionary of keyword arguments including 'table' (required).
        """
        self.classname = 'DynamodbHelper'
        self.logger = IaCLogger(self.classname)
        self.logger.debug(f"Instantiating {self.classname}")
        Boto3Common.__init__(self, 'dynamodb', **kwargs)

        self.table_name = kwargs["table"]
        self.table = self.resource.Table(self.table_name)

        self.retry_exceptions = ('ProvisionedThroughputExceededException',
                                 'ThrottlingException')

        self.wait_int = 3
        self.total_retries = 20

    def get_single_item(self, primary_value, primary_key="_id"):
        """
        Retrieves a single item from the DynamoDB table based on the primary key.

        Parameters:
        primary_value: The value of the primary key to search for in the table.
        primary_key: The name of the primary key attribute. Defaults to "_id".

        Returns:
        dict: A dictionary containing the status of the operation and the retrieved values.
              If the item is found, 'status' is True and 'values' contains the item data.
              If the item is not found, 'status' is None and 'failed_message' contains an error message.
              If the item is not retrievable, 'status' is False and 'failed_message' contains an error message.
        """
        match = {primary_key: primary_value}
        self.logger.debug(f"looking for match {match} in table {self.table_name}")
        query = self.get(match, raise_on_error=None)

        if not query or not query.get("Item"):
            return {
                "status": None,
                "failed_message": f"match {match} not found in {self.table_name}"
            }

        try:
            values = query["Item"]
        except KeyError:
            return {
                "status": False,
                "failed_message": f"match {match} not retrievable in {self.table_name}"
            }

        self.logger.debug(f"found match {match} in table {self.table_name}")

        return {
            "status": True,
            "values": values
        }

    def get(self, match, total_retries=None, wait_int=None, raise_on_error=True):
        """
        Retrieves an item from the DynamoDB table based on the provided key.

        Parameters:
        match (dict): A dictionary representing the key of the item to retrieve.
        total_retries (int, optional): The maximum number of retry attempts if the operation is throttled. Defaults to the class attribute total_retries.
        wait_int (int, optional): The wait interval in seconds between retry attempts. Defaults to the class attribute wait_int.
        raise_on_error (bool, optional): If True, raises an exception on non-retryable errors. If False, returns False on non-retryable errors. Defaults to True.

        Returns:
        dict: The response from the DynamoDB get_item operation if successful.
        False: If a non-retryable error occurs and raise_on_error is False.
        
        Raises:
        Exception: If a non-retryable error occurs and raise_on_error is True, or if the maximum number of retries is exceeded.
        """
        # Use default retry settings if none are provided
        if not total_retries:
            total_retries = self.total_retries

        if not wait_int:
            wait_int = self.wait_int

        retry = 0

        while True:
            try:
                # Attempt to retrieve the item from the table
                return self.table.get_item(Key=match)
            except ClientError as err:
                # Check if the error is retryable
                if err.response['Error']['Code'] not in self.retry_exceptions:
                    # If not retryable, raise an exception or return False depending on raise_on_error
                    if raise_on_error:
                        raise Exception(err.response['Error']) from err
                    return False

                # Log the retry attempt and wait before retrying
                self.logger.debug(f'Retry dynamodb get retry={retry} - need to wait for thread to free up')
                sleep(wait_int)
                retry += 1

                # Raise an exception if the maximum number of retries is exceeded
                if retry > total_retries:
                    if raise_on_error:
                        msg = f'FAILED dynamodb get with retry={retry} - need to wait for thread to free up'
                        raise Exception(msg) from err
                    return False

    def upsert(self, values, primary_key="_id"):
        """
        Upserts an item to the DynamoDB table based on the provided primary key.

        Parameters:
        values (dict): A dictionary containing the key-value pairs to upsert.
        primary_key (str): The name of the primary key attribute. Defaults to "_id".

        Returns:
        dict: The response from the DynamoDB upsert operation if successful.
        """
        # Retrieve the existing item in the table based on the primary key
        db_results = self.get_single_item(primary_key=primary_key,
                                          primary_value=values[primary_key])

        # If the item already exists in the table, delete it first
        if db_results.get("status"):
            self.delete({"_id": values["_id"]}, raise_on_error=False)

        # Insert the new item into the table
        return self.insert(values)

    def insert(self, values, total_retries=None, wait_int=None):
        """
        Inserts an item into the DynamoDB table.

        Parameters:
        values (dict): A dictionary representing the item to insert.
        total_retries (int, optional): The maximum number of retry attempts if the operation is throttled. Defaults to the class attribute total_retries.
        wait_int (int, optional): The wait interval in seconds between retry attempts. Defaults to the class attribute wait_int.

        Returns:
        dict: The response from the DynamoDB put_item operation if successful.

        Raises:
        Exception: If a non-retryable error occurs or if the maximum number of retries is exceeded.
        """
        # Use default retry settings if none are provided
        if not total_retries:
            total_retries = self.total_retries

        if not wait_int:
            wait_int = self.wait_int

        retry = 0

        while True:
            try:
                # Attempt to insert the item into the table
                return self.table.put_item(Item=values)
            except ClientError as err:
                # Check if the error is retryable
                if err.response['Error']['Code'] not in self.retry_exceptions:
                    raise Exception(err.response['Error']) from err

                # Log the retry attempt and wait before retrying
                self.logger.debug(f'Retry dynamodb write/update/insert retry={retry} - need to wait for thread to free up')
                sleep(wait_int)
                retry += 1

                # Raise an exception if the maximum number of retries is exceeded
                if retry > total_retries:
                    msg = f'FAILED dynamodb write/update/insert with retry={retry} - need to wait for thread to free up'
                    raise Exception(msg) from err

    def search_key(self, key, value, total_retries=None, wait_int=None):
        """
        Searches the DynamoDB table for an item with the specified key and value.

        Parameters:
        key (str): The name of the key to search for.
        value (str): The value of the key to search for.
        total_retries (int, optional): The maximum number of retry attempts if the operation is throttled. Defaults to the class attribute total_retries.
        wait_int (int, optional): The wait interval in seconds between retry attempts. Defaults to the class attribute wait_int.

        Returns:
        dict: The response from the DynamoDB scan operation if successful.

        Raises:
        Exception: If a non-retryable error occurs or if the maximum number of retries is exceeded.
        """
        if not total_retries:
            total_retries = self.total_retries

        if not wait_int:
            wait_int = self.wait_int

        retry = 0

        while True:
            self.logger.debug(f'scanning key "{key}" value "{value}"')

            try:
                return self.table.scan(FilterExpression=Key(key).eq(value))
            except ClientError as err:
                if err.response['Error']['Code'] not in self.retry_exceptions:
                    raise Exception(err.response['Error']) from err
                    
                self.logger.debug(f'Retry dynamodb search_key retry={retry} - need to wait for thread to free up')
                sleep(wait_int)
                retry += 1
                
                if retry > total_retries:
                    msg = f'FAILED dynamodb search_key with retry={retry} - need to wait for thread to free up'
                    raise Exception(msg) from err

    def search(self, total_retries=None, wait_int=None):
        """
        Scans the DynamoDB table.

        This method scans the entire DynamoDB table and returns the results as a list of dictionaries.

        Parameters:
        total_retries (int, optional): The maximum number of retry attempts if the operation is throttled. Defaults to the class attribute total_retries.
        wait_int (int, optional): The wait interval in seconds between retry attempts. Defaults to the class attribute wait_int.

        Returns:
        list: A list of dictionaries, where each dictionary represents an item in the DynamoDB table.

        Raises:
        Exception: If a non-retryable error occurs or if the maximum number of retries is exceeded.
        """
        if not total_retries:
            total_retries = self.total_retries

        if not wait_int:
            wait_int = self.wait_int

        retry = 0

        while True:
            self.logger.debug('scanning the table')

            try:
                # Attempt to scan the table
                return self.table.scan()
            except ClientError as err:
                # Check if the error is retryable
                if err.response['Error']['Code'] not in self.retry_exceptions:
                    raise Exception(err.response['Error']) from err

                # Log the retry attempt and wait before retrying
                self.logger.debug(f'Retry dynamodb search retry={retry} - need to wait for thread to free up')
                sleep(wait_int)
                retry += 1

                # Raise an exception if the maximum number of retries is exceeded
                if retry > total_retries:
                    msg = f'FAILED dynamodb search with retry={retry} - need to wait for thread to free up'
                    raise Exception(msg) from err

    def update(self, match, update_expression, expression_attribute_values, total_retries=None, wait_int=None):
        """
        Updates an item in the DynamoDB table.

        Parameters:
        match (dict): A dictionary representing the key of the item to update.
        update_expression (str): A string representing the update expression for the update_item operation.
        expression_attribute_values (dict): A dictionary of attribute values for the update expression.
        total_retries (int, optional): The maximum number of retry attempts if the operation is throttled. Defaults to the class attribute total_retries.
        wait_int (int, optional): The wait interval in seconds between retry attempts. Defaults to the class attribute wait_int.

        Returns:
        dict: The response from the DynamoDB update_item operation if successful.

        Raises:
        Exception: If a non-retryable error occurs or if the maximum number of retries is exceeded.
        """
        # Use default retry settings if none are provided
        if not total_retries:
            total_retries = self.total_retries
            
        if not wait_int:
            wait_int = self.wait_int

        retry = 0

        while True:
            try:
                return self.table.update_item(
                    Key=match,
                    UpdateExpression=update_expression,
                    ExpressionAttributeValues=expression_attribute_values,
                    ReturnValues="UPDATED_NEW",
                )
            except ClientError as err:
                # Check if the error is retryable
                if err.response['Error']['Code'] not in self.retry_exceptions:
                    raise Exception(err.response['Error']) from err

                # Log the retry attempt and wait before retrying
                self.logger.debug(f'Retry dynamodb update retry={retry} - need to wait for thread to free up')
                sleep(wait_int)
                retry += 1

                # Raise an exception if the maximum number of retries is exceeded
                if retry > total_retries:
                    msg = f'FAILED dynamodb update with retry={retry} - need to wait for thread to free up'
                    raise Exception(msg) from err

    def delete(self, match, total_retries=None, wait_int=None, raise_on_error=True):
        """
        Deletes an item from the DynamoDB table.

        Parameters:
        match (dict): A dictionary representing the key of the item to delete.
        total_retries (int, optional): The maximum number of retry attempts if the operation is throttled. Defaults to the class attribute total_retries.
        wait_int (int, optional): The wait interval in seconds between retry attempts. Defaults to the class attribute wait_int.
        raise_on_error (bool, optional): If True, raises an exception on non-retryable errors. If False, returns False on non-retryable errors. Defaults to True.

        Returns:
        dict: The response from the DynamoDB delete_item operation if successful.
        False: If a non-retryable error occurs and raise_on_error is False.

        Raises:
        Exception: If a non-retryable error occurs and raise_on_error is True, or if the maximum number of retries is exceeded.
        """
        if not total_retries:
            total_retries = self.total_retries

        if not wait_int:
            wait_int = self.wait_int
            
        retry = 0

        while True:
            try:
                return self.table.delete_item(Key=match)
            except ClientError as err:
                if err.response['Error']['Code'] not in self.retry_exceptions:
                    if not raise_on_error:
                        return False
                    raise Exception(err.response['Error']) from err
                    
                self.logger.debug(f'Retry dynamodb delete retry={retry} - need to wait for thread to free up')
                sleep(wait_int)
                retry += 1
                
                if retry > total_retries:
                    if not raise_on_error:
                        return False
                    msg = f'FAILED dynamodb delete with retry={retry} - need to wait for thread to free up'
                    raise Exception(msg) from err

    def raw(self):
        """
        Returns the DynamoDB table object.

        This method provides direct access to the DynamoDB table object associated with this instance.

        Returns:
        boto3.resources.factory.dynamodb.Table: The DynamoDB table object.
        """
        return self.table


class Dynamodb_boto3(Boto3Common):
    """
    A class for interacting with AWS DynamoDB using boto3.
    """

    def __init__(self, **kwargs):
        """
        Initialize the Dynamodb_boto3 class.
        
        Parameters:
        kwargs (dict): A dictionary of keyword arguments.
        """
        self.classname = 'Dynamodb_boto3'
        self.logger = IaCLogger(self.classname, logcategory="cloudprovider")
        self.logger.debug(f"Instantiating {self.classname}")

        Boto3Common.__init__(self, 'dynamodb', **kwargs)
        self.get_creds_frm_role = None

        if kwargs.get("get_creds_frm_role"):
            self.get_creds_frm_role = True

    def set(self, **kwargs):
        """
        Creates and returns a DynamodbHelper instance.
        
        Parameters:
        kwargs (dict): A dictionary of keyword arguments including 'table' (required).
        
        Returns:
        DynamodbHelper: An instance of the DynamodbHelper class.
        """
        return DynamodbHelper(
            resource=self.resource,
            table=kwargs["table"],
            get_creds_frm_role=self.get_creds_frm_role,
        )