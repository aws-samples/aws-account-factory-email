"""Library for managing the sending of email using SES"""
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import os
import boto3
import email
from botocore.exceptions import ClientError

region = os.getenv("AWS_REGION", "us-east-1")

# Create a new SES client.
client_ses = boto3.client("ses")
# Create a new S3 client.
s3 = boto3.resource("s3")


def get_message_from_s3(incoming_email_bucket, object_path):

    object_http_path = f"http://s3.console.aws.amazon.com/s3/object/{incoming_email_bucket}/{object_path}?region={region}"

    # Get the email object from the S3 bucket.
    object_s3 = s3.Object(incoming_email_bucket, object_path)
    meta = object_s3.get()["Metadata"]
    file = object_s3.get()["Body"].read()

    file_dict = {"file": file, "path": object_http_path}

    return file_dict


def create_message(address_from, address_to, file_dict):
    """Create multi-part MIME message"""

    # Parse the email body.
    mail_object = email.message_from_string(file_dict["file"].decode("utf-8"))

    # Adjust the from and to lines
    mail_object.__delitem__("From")
    mail_object.__delitem__("source")
    mail_object.__delitem__("Return-Path")
    mail_object.__delitem__("returnPath")
    # Replace the FROM address with one from the trusted domain
    mail_object["From"] = address_from
    # SES will not send on the email otherwise
    mail_object.__delitem__("To")
    mail_object["To"] = address_to

    message = {
        "Source": address_from,
        "Destinations": address_to,
        "Data": mail_object.as_string(),
    }

    return message


def send_email(message):
    """Use SES to send the `message`"""
    try:
        response = client_ses.send_raw_email(
            Source=message["Source"],
            Destinations=[message["Destinations"]],
            RawMessage={"Data": message["Data"]},
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "MessageRejected":
            if "not verified" in e.response["Error"]["Message"]:
                return f"Verification_Error: Address {message['Destinations']} is not verified"
        return e.response["Error"]["Message"]
    else:
        return "Email sent! Message ID: " + response["MessageId"]
