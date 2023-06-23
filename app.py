#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import aws_cdk as cdk
from aws_mail_fwd.aws_mail_fwd_stack import AwsMailFwdStack
from cdk_nag import AwsSolutionsChecks

app = cdk.App()
app_stack = AwsMailFwdStack(app, "AwsMailFwdStack")
cdk.Aspects.of(app).add(AwsSolutionsChecks(verbose=True))
app.synth()
