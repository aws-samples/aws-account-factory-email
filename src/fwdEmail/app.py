# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import json
import os, sys, logging

file_dir = os.path.dirname(__file__)
sys.path.append(file_dir)
import ses, ddb

ADDRESS_FROM = os.getenv("ADDRESS_FROM")
ADDRESS_ADMIN = os.getenv("ADDRESS_ADMIN")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger = logging.getLogger("FWD-EMAIL")
logging.getLogger().setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))


def lambda_handler(event, context):
    # Get the unique ID of the message. This corresponds to the name of the file
    # in S3.
    logger.debug(json.dumps(event))
    for record in event.get("Records"):
        if record.get("EventSource") == "aws:sns":
            decoded_message = json.loads(record.get("Sns").get("Message"))
            if decoded_message.get("notificationType") == "Received":
                # Extract Message Properties
                logger.info(
                    f"Received message ID {decoded_message.get('mail').get('messageId')}"
                )
                mail_bucket = (
                    decoded_message.get("receipt").get("action").get("bucketName")
                )
                object_path = (
                    decoded_message.get("receipt").get("action").get("objectKey")
                )
                mail_to = decoded_message.get("receipt").get("recipients")[0]

                # Retrieve the file from the S3 bucket.
                file_dict = ses.get_message_from_s3(mail_bucket, object_path)

                # Determine who to send the email to
                if mail_to == ADDRESS_FROM:
                    # Forward emails for the solution's FROM address to the admin
                    send_to = ADDRESS_ADMIN
                else:
                    account_owner = ddb.get_account_owner_address(mail_to)
                    send_to = account_owner if account_owner else ADDRESS_ADMIN

                # Create the message.
                message = ses.create_message(ADDRESS_FROM, send_to, file_dict)

                # Send the email and print the result.
                result = ses.send_email(message)
                if "Verification_Error" in result:
                    # Instead send the email to the admin account
                    logger.warn(
                        f"It appears {send_to} is not a verified email.  Will now attempt to send the message to the admin at {ADDRESS_ADMIN}"
                    )
                    msg_2 = ses.create_message(ADDRESS_FROM, ADDRESS_ADMIN, file_dict)
                    result = ses.send_email(msg_2)
                logger.info(result)
