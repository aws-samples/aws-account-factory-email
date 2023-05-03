# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import os
import sys
from warnings import warn

file_dir = os.path.dirname(__file__)
sys.path.append(file_dir)
import utils
from schema import Schema, Optional as schema_Optional, Regex, Or, And, SchemaError
import ddb
import ses

SES_DOMAIN_NAME = os.getenv("SES_DOMAIN_NAME")
COUNTER_LENGTH = os.getenv("COUNTER_LENGTH", "3")  # Number of digits with leading zeros

# Constant values based on AWS documentation
# https://docs.aws.amazon.com/organizations/latest/APIReference/API_Account.html
AWS_ORGS_ACCT_NAME_REGEX = "[\u002d-\u007a]"
AWS_ORGS_EMAIL_ADDR_REGEX = r"[^\s@]+@[^\s@]+\.[^\s@]+"
AWS_ORGS_EMAIL_LENGTH_LIMIT = 64
AWS_ORGS_EMAIL_LENGTH_MIN = 6
AWS_ORGS_ACCT_NAME_LIMIT = 50

ENV_TRANSLATE_TABLE = {
    "DEVELOPMENT": "dev",
    "EVALUATION": "eval",
    "PRODUCTION": "prod",
    "QUALITYASSURANCE": "qa",
    "TRAINING": "trn",
    "VALIDATION": "val",
}

# This list should be adjusted to match what kind of account this is
# and could be used to match a new account with the right OU in AWS
# Organizations
VALID_ACCOUNT_TYPES = [
    "Sales",
    "Research",
    "IT",
    "DataEngineering",
]
DEFAULT_ENV = "eval"


def valid_acct_length(thing: str):
    return len(thing) <= AWS_ORGS_ACCT_NAME_LIMIT


def valid_email_length(address: str):
    return (
        len(address) <= AWS_ORGS_EMAIL_LENGTH_LIMIT
        and len(address) >= AWS_ORGS_EMAIL_LENGTH_MIN
    )


# Input format schema object
provision_aws_account_schema = Schema(
    {
        ddb.OWNER_ADDRESS: Regex(AWS_ORGS_EMAIL_ADDR_REGEX),
        ddb.ACCOUNT_TYPE: Or(*VALID_ACCOUNT_TYPES),
        ddb.TAGS: {
            schema_Optional("BusinessUnit"): str,
            schema_Optional("ApplicationName"): str,
            schema_Optional("Environment"): Or(*list(ENV_TRANSLATE_TABLE.keys())),
        },
        schema_Optional(ddb.ACCOUNT_NAME): And(
            Regex(AWS_ORGS_ACCT_NAME_REGEX), valid_acct_length
        ),
        schema_Optional(ddb.ACCOUNT_EMAIL): And(
            Regex(AWS_ORGS_EMAIL_ADDR_REGEX), valid_email_length
        ),
    },
    ignore_extra_keys=True,
)


def get_next_number(account_name):
    """Get all the records in the DB that match the account name
    Find the highest number of the Enum column and increment it by one"""
    records = ddb.get_records_by_account_prefix(account_name)
    if len(records) < 1:
        return format_number(1)
    counts = [int(r[ddb.COUNT]) for r in records]
    highest = int(sorted(counts)[-1])
    return format_number(highest + 1)


def format_number(input: int) -> str:
    return f"{input:0{COUNTER_LENGTH}d}"


def get_new_account_data(metadata: dict):
    """Function will generate a touple of (account name, account email)
    from the given `metadata` dictionary.  `metadata` should contain the following
    dictionary keys:  `BusinessUnit`, `ApplicationName`, `Environment`
    You can override the email address and account name by specifying
    `AccountName` and/or `AccountEmail` in the metadata"""

    BUS = metadata.get("BusinessUnit").lower()
    APP = metadata.get("ApplicationName").lower()
    ENV = ENV_TRANSLATE_TABLE.get(metadata.get("Environment"), DEFAULT_ENV)
    AN_OVERRIDE = metadata.get(ddb.ACCOUNT_NAME)
    AE_OVERRIDE = metadata.get(ddb.ACCOUNT_EMAIL)
    proposed_name = AN_OVERRIDE if AN_OVERRIDE else "-".join([BUS, APP, ENV])
    if not AN_OVERRIDE:
        # Some customers only want to enable counters for certain account types
        # here is where you would implement that functionality if needed
        counter = get_next_number(proposed_name)
        proposed_name = f"{proposed_name}-{counter}"
    proposed_email = (
        AE_OVERRIDE if AE_OVERRIDE else proposed_name + "@" + SES_DOMAIN_NAME
    )

    if not valid_acct_length(proposed_name):
        raise ValueError(
            f"The proposed account name is too long \
            ({proposed_name})"
        )
    if not valid_email_length(proposed_email):
        raise ValueError(
            f"The proposed email address is too long \
            ({proposed_email})"
        )
    return proposed_name, proposed_email


def lambda_handler(event, context):
    try:
        validated_request = provision_aws_account_schema.validate(event)
    except SchemaError as se:
        return utils.failed({"message": str(se)})
    tags = validated_request.get(ddb.TAGS)
    account_type = validated_request.get(ddb.ACCOUNT_TYPE)
    owner_email = validated_request.get(ddb.OWNER_ADDRESS)

    # Attempt to generate new account email and name
    try:
        account_name, account_email = get_new_account_data(tags)
    except ValueError as ve:
        return utils.failed({"message": str(ve)})

    # If either the account email or account name already exist, fail the process
    email_conflict = ddb.get_account_owner_address(account_email)
    if email_conflict:
        return utils.failed(
            {"message": f"An account with email {account_email} already exists"}
        )

    name_conflict = ddb.get_account_by_name(account_name)
    if name_conflict:
        return utils.failed(
            {"message": f"An account with name {account_name} already exists"}
        )

    # Store the record in the table
    ddb.store_account_record(
        account_name, account_email, account_type, owner_email, "NAME-ALLOCATED", tags
    )

    # Check if owner's email is verified and if not, send verification request
    # This is really only needed if your AWS account is still in SES sandbox mode
    verification_status = ses.verify_email_address(owner_email)

    # Return success
    return utils.success(
        {
            ddb.ACCOUNT_NAME: account_name,
            ddb.ACCOUNT_EMAIL: account_email,
            ddb.ACCOUNT_TYPE: account_type,
            "EmailVerification": verification_status,
        }
    )
