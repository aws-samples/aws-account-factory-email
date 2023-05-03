"""Utility functions"""
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import time
import os
from datetime import datetime

API_VERSION = os.getenv(
    "API_VERSION", "<UNKNOWN>"
)  # What API version we are dealing with
HEADERS = {"x-api-version": API_VERSION}


def event_dt():
    """Returns timestamp"""
    return datetime.fromtimestamp(time.time()).isoformat()


def failed(body):
    return {"statusCode": 500, "body": body, "headers": HEADERS}


def success(body):
    return {"statusCode": 200, "body": body, "headers": HEADERS}
