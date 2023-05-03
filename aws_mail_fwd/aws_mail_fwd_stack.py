# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
from constructs import Construct
from aws_cdk import (
    RemovalPolicy,
    Duration,
    CfnOutput,
    Fn,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    Stack,
    aws_lambda,
    aws_s3 as s3,
    # aws_s3_notifications as s3_notify,
    aws_sns as sns,
    aws_lambda_event_sources as lambda_events,
    aws_kms as kms,
    aws_ses as ses,
    aws_ses_actions as ses_actions,
    custom_resources as custom_resource,
    BundlingOptions,
)


class AwsMailFwdStack(Stack):
    """SES Mail Forwarding Stack"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a kms key for storing emails
        self.mail_key = kms.Key(
            self, "KmsKey", enable_key_rotation=True, alias="alias/email-processing"
        )
        self.sns_key = kms.Key(
            self, "KmsKeySns", enable_key_rotation=True, alias="alias/sns-mail-receipt"
        )
        self.mail_key.grant_decrypt(iam.ServicePrincipal("ses.amazonaws.com"))
        self.sns_key.grant_encrypt_decrypt(iam.ServicePrincipal("ses.amazonaws.com"))
        # Allow SES to decrypt messages as per requirement
        # https://docs.aws.amazon.com/ses/latest/dg/receiving-email-permissions.html

        # Create a bucket to store emails
        destroy_bucket = self.node.try_get_context("REMOVE_BUCKET_ON_DESTROY")
        self.mail_bucket = s3.Bucket(
            self,
            "MailBucket",
            versioned=True,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.mail_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY
            if destroy_bucket
            else RemovalPolicy.RETAIN,
            auto_delete_objects=destroy_bucket,
            lifecycle_rules=[
                s3.LifecycleRule(
                    enabled=True,
                    expiration=Duration.days(90),
                    noncurrent_version_expiration=Duration.days(1),
                    id="RetentionRule",
                )
            ],
        )

        self.mail_bucket.grant_read_write(iam.ServicePrincipal("ses.amazonaws.com"))

        # create dynamo table
        self.account_table = dynamodb.Table(
            self,
            "AccountTable",
            partition_key=dynamodb.Attribute(
                name="AccountEmail", type=dynamodb.AttributeType.STRING
            ),
            table_name=self.node.try_get_context("ACCOUNT_TABLE_NAME"),
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery=True,
        )
        if self.node.try_get_context("REMOVE_TABLE_ON_DESTROY"):
            self.account_table.apply_removal_policy(RemovalPolicy.DESTROY)

        # Add a global secondary index
        self.account_table.add_global_secondary_index(
            partition_key=dynamodb.Attribute(
                name="AccountId", type=dynamodb.AttributeType.STRING
            ),
            index_name="AccountId-Index",
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # Add a global secondary index
        self.account_table.add_global_secondary_index(
            partition_key=dynamodb.Attribute(
                name="AccountName", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="Enum", type=dynamodb.AttributeType.STRING
            ),
            index_name="AccountName-Enum-Index",
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # Create lambda function for vending emails
        self.vend_email_function = aws_lambda.Function(
            self,
            "VendEmailFunction",
            runtime=aws_lambda.Runtime.PYTHON_3_9,
            handler="app.lambda_handler",
            code=aws_lambda.Code.from_asset(
                "src/vendEmail",
                bundling=BundlingOptions(
                    image=aws_lambda.Runtime.PYTHON_3_9.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            description="Function to vend AWS account names and email addresses",
            architecture=aws_lambda.Architecture.ARM_64,
        )

        # Create lambda function for forwarding emails
        self.ses_mail_fwd_function = aws_lambda.Function(
            self,
            "SesMailForwardFunction",
            runtime=aws_lambda.Runtime.PYTHON_3_9,
            handler="app.lambda_handler",
            code=aws_lambda.Code.from_asset("src/fwdEmail"),
            description="Function to forward email to the proper AWS account owner",
            architecture=aws_lambda.Architecture.ARM_64,
        )

        # Setup Lambda to receive events from an SNS topic
        self.sns_topic = sns.Topic(
            self, "SNSEmailReceivedTopic", topic_name="EmailReceivedTopic", master_key=self.sns_key
        )
        self.ses_mail_fwd_function.add_event_source(
            lambda_events.SnsEventSource(self.sns_topic)
        )
        self.sns_topic.grant_publish(iam.ServicePrincipal("ses.amazonaws.com"))

        # The following was commented out in favor of using SNS for invoking Lambda
        # # create s3 notification for lambda function
        # notification = s3_notify.LambdaDestination(self.ses_mail_fwd_function)

        # # assign notification for the s3 event type (ex: OBJECT_CREATED)
        # self.mail_bucket.add_event_notification(s3.EventType.OBJECT_CREATED, notification)

        # Set up environment variables for our functions
        self.ses_mail_fwd_function.add_environment(
            "SES_DOMAIN_NAME", self.node.try_get_context("SES_DOMAIN_NAME")
        )
        self.ses_mail_fwd_function.add_environment(
            "ADDRESS_FROM", self.node.try_get_context("ADDRESS_FROM")
        )
        self.ses_mail_fwd_function.add_environment(
            "ADDRESS_ADMIN", self.node.try_get_context("ADDRESS_ADMIN")
        )
        self.ses_mail_fwd_function.add_environment(
            "TABLE_NAME", self.account_table.table_name
        )
        self.vend_email_function.add_environment(
            "SES_DOMAIN_NAME", self.node.try_get_context("SES_DOMAIN_NAME")
        )
        self.vend_email_function.add_environment(
            "TABLE_NAME", self.account_table.table_name
        )
        self.vend_email_function.add_environment(
            "API_VERSION", self.node.try_get_context("API_VERSION")
        )
        self.vend_email_function.add_environment(
            "COUNTER_LENGTH", self.node.try_get_context("COUNTER_LENGTH")
        )

        # Grant permission to Lambda to write to account table and bucket
        self.account_table.grant_read_data(self.ses_mail_fwd_function)
        self.account_table.grant_read_write_data(self.vend_email_function)
        self.mail_bucket.grant_read(self.ses_mail_fwd_function)
        self.mail_key.grant_decrypt(self.ses_mail_fwd_function)
        self.sns_key.grant_encrypt_decrypt(self.ses_mail_fwd_function)

        # Grant permissions to Lambda to perform SES actions
        self.ses_mail_fwd_function.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=[
                    Fn.sub("arn:aws:ses:${AWS::Region}:${AWS::AccountId}:identity/*")
                    # Wildcard: Identities unknown prior to policy deployment
                ],
                actions=["ses:SendRawEmail"],
            )
        )
        self.vend_email_function.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=["*"], # Wildcard: Identities unknown prior to policy deployment
                actions=[
                    "ses:GetIdentityVerificationAttributes",
                    "ses:VerifyEmailIdentity",
                ],
            )
        )

        # Set up SES Ruleset
        self.rule_set = ses.ReceiptRuleSet(
            self,
            "SESRuleSet",
            rules=[
                ses.ReceiptRuleOptions(
                    receipt_rule_name="ProcessAWSAccountEmails",
                    recipients=[self.node.try_get_context("SES_DOMAIN_NAME")],
                    scan_enabled=True,
                    tls_policy=ses.TlsPolicy.REQUIRE,
                    actions=[
                        ses_actions.AddHeader(
                            name="X-Processed-By",
                            value=self.node.try_get_context("MAIL_HEADER_VALUE"),
                        ),
                        ses_actions.S3(
                            bucket=self.mail_bucket,
                            object_key_prefix="mail/",
                            # kms_key=self.mail_key,  # DO NOT specify the key here, this would pre-encrypt messages and require a special decryption routine in Lambda. The objects ARE being encrypted with the default KMS key assigned the bucket
                            topic=self.sns_topic,
                        ),
                    ],
                )
            ],
        )

        # Custom AWS Resource to mark the RuleSet as active.
        self.custom_ses_rule_set_activate = custom_resource.AwsCustomResource(
            self,
            "SesReceiptRuleActivate",
            on_create={
                "service": "SES",
                "action": "setActiveReceiptRuleSet",
                "parameters": {"RuleSetName": f"{self.rule_set.receipt_rule_set_name}"},
                "physical_resource_id": custom_resource.PhysicalResourceId.of("id"),
            },
            on_delete={
                "service": "SES",
                "action": "setActiveReceiptRuleSet",
                "physical_resource_id": custom_resource.PhysicalResourceId.of("id"),
            },
            policy=custom_resource.AwsCustomResourcePolicy.from_statements(
                statements=[
                    iam.PolicyStatement(
                        actions=[
                            "ses:SetActiveReceiptRuleSet",
                            "ses:DescribeReceiptRuleSet",
                            "ses:CreateReceiptRuleSet",
                        ],
                        resources=["*"], # Wildcard, resource ARNs do not exist prior to deployment of this policy
                    )
                ]
            ),
        )

        # Set some CFN stack outputs
        CfnOutput(
            self,
            "AccountTableName",
            value=self.account_table.table_name,
            description="DynamoDB table where account information will be stored",
        )
        CfnOutput(
            self,
            "MailBucketArn",
            value=self.mail_bucket.bucket_arn,
            description="ARN of S3 bucket where mail will be stored",
        )
