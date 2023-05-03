"""Library for managing operations with DynamoDB"""
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import boto3
import os

CURRENT_REGION = os.getenv("AWS_REGION", "us-east-1")
TABLE_NAME = os.getenv("TABLE_NAME")
# Field Names
ACCOUNT_EMAIL = "AccountEmail"
OWNER_ADDRESS = "OwnerAddress"

ddb = boto3.resource("dynamodb", region_name=CURRENT_REGION)
account_table = ddb.Table(TABLE_NAME)


def get_account_owner_address(incoming_email_address):
    resp = account_table.get_item(Key={ACCOUNT_EMAIL: incoming_email_address})
    return resp.get("Item", {}).get(OWNER_ADDRESS)
