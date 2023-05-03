"""Library for managing SES"""
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import os
import boto3
from botocore.exceptions import ClientError

# Create a new SES client.
ses = boto3.client("ses")


def verify_email_address(email_address: str) -> str:
    """Returns a message about the state of email verification.
    If no verification request was ever sent, one will be sent"""
    try:
        response = ses.get_identity_verification_attributes(Identities=[email_address])
    except ClientError as ce:
        print(ce.response)
        message = f"An error was generated when attempting to get the state of verification {ce.response['Error']['Message']}"
    if "VerificationAttributes" in response:
        status = (
            response["VerificationAttributes"]
            .get(email_address, {})
            .get("VerificationStatus")
        )
        if status is None:
            send_verification_request(email_address)
            message = f"A request to verify {email_address} has been sent, please check your email."
        else:
            message = f"A request to verify {email_address} is in a {status} state."
    return message


def send_verification_request(email_address: str):
    try:
        response = ses.verify_email_identity(EmailAddress=email_address)
    except ClientError as ce:
        print(ce.response)
