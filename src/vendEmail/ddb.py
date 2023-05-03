"""Library for managing operations with DynamoDB"""
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import boto3
import os
from boto3.dynamodb.conditions import Key
from utils import event_dt

CURRENT_REGION = os.getenv("AWS_REGION", "us-east-1")
TABLE_NAME = os.getenv("TABLE_NAME", "AWSAccountTable")
# Field Names
ACCOUNT_EMAIL = "AccountEmail"
OWNER_ADDRESS = "OwnerAddress"
ACCOUNT_NAME = "AccountName"
ACCOUNT_TYPE = "AccountType"
COUNT = "Enum"
TAGS = "Tags"
LAST_UPDATED = "LastUpdated"
STATUS = "Status"
ACCOUNT_ENUM_INDEX = "-".join([ACCOUNT_NAME, COUNT, "Index"])

ddb = boto3.resource("dynamodb", region_name=CURRENT_REGION)
account_table = ddb.Table(TABLE_NAME)


def get_account_owner_address(incoming_email_address):
    resp = account_table.get_item(Key={ACCOUNT_EMAIL: incoming_email_address})
    return resp.get("Item", {}).get(OWNER_ADDRESS)


def get_records_by_account_prefix(account_name):
    """Get all records matching `account_name`.  This function does not
    expect `account_name` to contain the counter at the end."""

    resp = account_table.query(
        IndexName=ACCOUNT_ENUM_INDEX,
        KeyConditionExpression=Key(ACCOUNT_NAME).eq(account_name),
    )
    if len(resp.get("Items")) < 1:
        resp = {"Items": []}
    print(
        f'Query DynamoDB table {TABLE_NAME} and returned {len(resp.get("Items"))} records'
    )
    return resp.get("Items")


def get_account_by_name(account_name):
    """Get account records matching the account name given
    This functions expects `account_name` to have a number at the
    end like '-001'. Function returns only the first record found."""
    name, count = account_name.rsplit("-", 1)
    resp = account_table.query(
        IndexName=ACCOUNT_ENUM_INDEX,
        KeyConditionExpression=Key(ACCOUNT_NAME).eq(name) & Key(COUNT).eq(count),
    )
    if len(resp.get("Items")) < 1:
        resp = {"Items": [{}]}
    print(
        f'Query DynamoDB table {TABLE_NAME} and returned {len(resp.get("Items"))} records'
    )
    # Only return the first item
    return resp.get("Items")[0]


def store_account_record(
    account_name: str,
    account_email: str,
    account_type: str,
    owner_email: str,
    status: str,
    tags: dict,
):
    """PUT record in the Account Table table. Will overwrite the record if \
        it exists"""
    # First split the account name from the counter at the end so we can \
    # store them separately
    name, count = account_name.rsplit("-", 1)
    update_ts = event_dt()
    resp = account_table.put_item(
        Item={
            STATUS: status,
            ACCOUNT_NAME: name,
            ACCOUNT_TYPE: account_type,
            COUNT: count,
            ACCOUNT_EMAIL: account_email,
            OWNER_ADDRESS: owner_email,
            TAGS: tags,
            LAST_UPDATED: update_ts,
        }
    )
    return resp
