# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
from constructs import Construct
from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    CfnOutput,
    Fn,
    BundlingOptions,
    custom_resources,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda,
    aws_s3 as s3,
    aws_sns as sns,
    aws_lambda_event_sources as lambda_events,
    aws_kms as kms,
    aws_ses as ses,
    aws_ses_actions as ses_actions,
    aws_logs,
)
from cdk_nag import NagSuppressions

ACCOUNT_TABLE_GSI_NAME = "AccountName-Enum-Index"

class AwsMailFwdStack(Stack):
    """SES Mail Forwarding Stack"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a kms key for storing emails
        mail_key = kms.Key(
            self, "KmsKey", enable_key_rotation=True, alias="alias/email-processing"
        )
        sns_key = kms.Key(
            self, "KmsKeySns", enable_key_rotation=True, alias="alias/sns-mail-receipt"
        )
        mail_key.grant_decrypt(iam.ServicePrincipal("ses.amazonaws.com"))
        sns_key.grant_encrypt_decrypt(iam.ServicePrincipal("ses.amazonaws.com"))
        # Allow SES to decrypt messages as per requirement
        # https://docs.aws.amazon.com/ses/latest/dg/receiving-email-permissions.html

        # Create a bucket to store emails
        destroy_bucket = self.node.try_get_context("REMOVE_BUCKET_ON_DESTROY")
        mail_bucket = s3.Bucket(
            self,
            "MailBucket",
            versioned=True,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=mail_key,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            # For production use, set up server access logs:
            # server_access_logs_bucket=central_access_log_bucket,
            # server_access_logs_prefix='logs',
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

        mail_bucket.grant_read_write(iam.ServicePrincipal("ses.amazonaws.com"))

        # create dynamo table
        account_table = dynamodb.Table(
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
            account_table.apply_removal_policy(RemovalPolicy.DESTROY)

        # Add a global secondary index
        account_table.add_global_secondary_index(
            partition_key=dynamodb.Attribute(
                name="AccountName", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="Enum", type=dynamodb.AttributeType.STRING
            ),
            index_name=ACCOUNT_TABLE_GSI_NAME,
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # Create Vend Email Lambda Log Groups
        vend_email_log_group = aws_logs.LogGroup(
            self,
            "VendEmailLogGroup",
            removal_policy=RemovalPolicy.DESTROY,
            retention=aws_logs.RetentionDays.ONE_MONTH,
        )

        # Create Vend Email Lambda IAM Role
        vend_email_role = iam.Role(
            self,
            "VendEmailFunctionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="AwsMailFwd Vend Email Lambda Function role",
        )
        vend_email_log_group.grant_write(vend_email_role)

        # Create lambda function for vending emails
        vend_email_function = aws_lambda.Function(
            self,
            "VendEmailFunction",
            runtime=aws_lambda.Runtime.PYTHON_3_10,
            runtime_management_mode=aws_lambda.RuntimeManagementMode.AUTO,
            handler="app.lambda_handler",
            code=aws_lambda.Code.from_asset(
                "src/vendEmail",
                bundling=BundlingOptions(
                    image=aws_lambda.Runtime.PYTHON_3_10.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            description="Function to vend AWS account names and email addresses",
            architecture=aws_lambda.Architecture.ARM_64,
            role=vend_email_role,
        )
        

        # Create SES Mail Fwd Function Lambda Log Groups
        ses_fwd_function_log_group = aws_logs.LogGroup(
            self,
            "SesMailForwardLogGroup",
            removal_policy=RemovalPolicy.DESTROY,
            retention=aws_logs.RetentionDays.ONE_MONTH,
        )
        ses_fwd_function_role = iam.Role(
            self,
            "SesMailForwardLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="AwsMailFwd SES Mail Forwarding Lambda Function role",
        )
        ses_fwd_function_log_group.grant_write(ses_fwd_function_role)

        # Create lambda function for forwarding emails
        ses_fwd_function = aws_lambda.Function(
            self,
            "SesMailForwardFunction",
            runtime=aws_lambda.Runtime.PYTHON_3_10,
            runtime_management_mode=aws_lambda.RuntimeManagementMode.AUTO,
            handler="app.lambda_handler",
            code=aws_lambda.Code.from_asset("src/fwdEmail"),
            description="Function to forward email to the proper AWS account owner",
            architecture=aws_lambda.Architecture.ARM_64,
            role=ses_fwd_function_role,
        )

        # Setup Lambda to receive events from an SNS topic
        sns_topic = sns.Topic(
            self, "SNSEmailReceivedTopic", topic_name="EmailReceivedTopic", master_key=sns_key
        )
        ses_fwd_function.add_event_source(
            lambda_events.SnsEventSource(sns_topic)
        )
        sns_topic.grant_publish(iam.ServicePrincipal("ses.amazonaws.com"))
        sns_topic.add_to_resource_policy(
            iam.PolicyStatement(
                actions=[
                    "SNS:Publish"
                ],
                effect=iam.Effect.DENY,
                resources=[sns_topic.topic_arn],
                conditions={
                    "Bool": {
                        "aws:SecureTransport": "false"
                    }
                },
                principals=[iam.ArnPrincipal("*")]
            )
        )
        # The following was commented out in favor of using SNS for invoking Lambda
        # # create s3 notification for lambda function
        # notification = s3_notify.LambdaDestination(ses_mail_fwd_function)

        # # assign notification for the s3 event type (ex: OBJECT_CREATED)
        # mail_bucket.add_event_notification(s3.EventType.OBJECT_CREATED, notification)

        # Set up environment variables for our functions
        ses_fwd_function.add_environment(
            "SES_DOMAIN_NAME", self.node.try_get_context("SES_DOMAIN_NAME")
        )
        ses_fwd_function.add_environment(
            "ADDRESS_FROM", self.node.try_get_context("ADDRESS_FROM")
        )
        ses_fwd_function.add_environment(
            "ADDRESS_ADMIN", self.node.try_get_context("ADDRESS_ADMIN")
        )
        ses_fwd_function.add_environment(
            "TABLE_NAME", account_table.table_name
        )
        vend_email_function.add_environment(
            "SES_DOMAIN_NAME", self.node.try_get_context("SES_DOMAIN_NAME")
        )
        vend_email_function.add_environment(
            "TABLE_NAME", account_table.table_name
        )
        vend_email_function.add_environment(
            "API_VERSION", self.node.try_get_context("API_VERSION")
        )
        vend_email_function.add_environment(
            "COUNTER_LENGTH", self.node.try_get_context("COUNTER_LENGTH")
        )

        # Grant permission to Lambda to write to account table and bucket
        ses_fwd_function_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "dynamodb:BatchGetItem",
                    "dynamodb:GetRecords",
                    "dynamodb:GetShardIterator",
                    "dynamodb:Query",
                    "dynamodb:GetItem",
                    "dynamodb:Scan",
                    "dynamodb:ConditionCheckItem",
                    "dynamodb:DescribeTable"
                ],
                effect=iam.Effect.ALLOW,
                resources=[
                    account_table.table_arn,
                    account_table.table_arn + "/index/" + ACCOUNT_TABLE_GSI_NAME   
                ]
            )
        )
        vend_email_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "dynamodb:BatchGetItem",
                    "dynamodb:GetRecords",
                    "dynamodb:GetShardIterator",
                    "dynamodb:Query",
                    "dynamodb:GetItem",
                    "dynamodb:Scan",
                    "dynamodb:ConditionCheckItem",
                    "dynamodb:BatchWriteItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem",
                    "dynamodb:DescribeTable"
                ],
                effect=iam.Effect.ALLOW,
                resources=[
                    account_table.table_arn,
                    account_table.table_arn + "/index/" + ACCOUNT_TABLE_GSI_NAME   
                ]
            )
        )
        mail_bucket.grant_read(ses_fwd_function_role)
        mail_key.grant_decrypt(ses_fwd_function_role)
        sns_key.grant_encrypt_decrypt(ses_fwd_function_role)

        # Grant permissions to Lambda to perform SES actions
        ses_fwd_function_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=[
                    Fn.sub("arn:${AWS::Partition}:ses:${AWS::Region}:${AWS::AccountId}:identity/*")
                ],
                actions=["ses:SendRawEmail"],
            )
        )

        vend_email_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=["*"],
                actions=[
                    "ses:GetIdentityVerificationAttributes",
                    "ses:VerifyEmailIdentity",
                ],
            )
        )

        # Set up SES RuleSet
        rule_set = ses.ReceiptRuleSet(
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
                            bucket=mail_bucket,
                            object_key_prefix="mail/",
                            # kms_key=mail_key,  # DO NOT specify the key here, this would pre-encrypt messages and require a special decryption routine in Lambda. The objects ARE being encrypted with the default KMS key assigned the bucket
                            topic=sns_topic,
                        ),
                    ],
                )
            ],
        )

        # Create a role for the custom resource which will mark the RuleSet active
        custom_resource_role = iam.Role(
            self,
            "SesReceiptRuleActivateRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="AwsMailFwd SES Mail Forwarding Rule Activator Function Role",
            inline_policies={
                "GrantAttachRights":
                iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "ses:SetActiveReceiptRuleSet",
                                "ses:DescribeReceiptRuleSet",
                                "ses:CreateReceiptRuleSet",
                            ],
                            resources=["*"],
                        )
                    ]
                )
            }
        )

        # Custom AWS Resource to mark the RuleSet as active.
        custom_ses_rule_set_activate = custom_resources.AwsCustomResource(
            self,
            "SesReceiptRuleActivate",
            install_latest_aws_sdk=True,
            on_create={
                "service": "SES",
                "action": "setActiveReceiptRuleSet",
                "parameters": {"RuleSetName": f"{rule_set.receipt_rule_set_name}"},
                "physical_resource_id": custom_resources.PhysicalResourceId.of("id"),
            },
            on_delete={
                "service": "SES",
                "action": "setActiveReceiptRuleSet",
                "physical_resource_id": custom_resources.PhysicalResourceId.of("id"),
            },
            role=custom_resource_role,
        )
        # Set some CFN stack outputs
        CfnOutput(
            self,
            "AccountTableName",
            value=account_table.table_name,
            description="DynamoDB table where account information will be stored",
        )
        CfnOutput(
            self,
            "MailBucketArn",
            value=mail_bucket.bucket_arn,
            description="ARN of S3 bucket where mail will be stored",
        )

        # --------------------------------------------------------------------
        # CDK NAG Suppressions
        # --------------------------------------------------------------------
        NagSuppressions.add_resource_suppressions(
            mail_bucket,
            [
                {
                    "id": "AwsSolutions-S1",
                    "reason": "POC Deployment. For production use, follow best practices and enable bucket server access logs to a central S3 bucket."
                }
            ]
        )
        NagSuppressions.add_resource_suppressions(
            vend_email_function,
            [
                {
                    "id": "AwsSolutions-L1",
                    "reason": "Currently Python 3.10 is the latest supported release."
                }
            ]
        )
        NagSuppressions.add_resource_suppressions(
            ses_fwd_function,
            [
                {
                    "id": "AwsSolutions-L1",
                    "reason": "Currently Python 3.10 is the latest supported release."
                }
            ]
        )
        NagSuppressions.add_resource_suppressions(
            ses_fwd_function_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "appliesTo": [
                        "Action::s3:GetObject*",
                        "Action::s3:GetBucket*",
                        "Action::s3:List*"
                    ],
                    "reason": "Wildcard present to maintain a concise policy document"
                }
            ],
            True
        )
        mail_bucket_cfn_res = self.get_logical_id(mail_bucket.node.default_child)
        NagSuppressions.add_resource_suppressions(
            ses_fwd_function_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "appliesTo": [
                        f"Resource::<{mail_bucket_cfn_res}.Arn>/*",
                    ],
                    "reason": "Solution must access any and all objects in the bucket"
                }
            ],
            True
        )
        NagSuppressions.add_resource_suppressions(
            ses_fwd_function_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "The role must be allowed to send email to all identities",
                    "appliesTo": ["Resource::arn:<AWS::Partition>:ses:<AWS::Region>:<AWS::AccountId>:identity/*"],
                }
            ],
            True
        )
        NagSuppressions.add_resource_suppressions(
            ses_fwd_function_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "All the KMS actions are needed for the role to encrypt and decrypt messages",
                    "appliesTo": [
                        "Action::kms:GenerateDataKey*",
                        "Action::kms:ReEncrypt*"
                    ],
                }
            ],
            True
        )
        NagSuppressions.add_resource_suppressions(
            vend_email_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "appliesTo": ["Resource::*"],
                    "reason": "The solution must process any identity that could exist"
                }
            ],
            True
        )
        NagSuppressions.add_resource_suppressions(
            custom_resource_role,
            [
                {
                    "id": "AwsSolutions-IAM5",
                    "reason": "Only wildcard resources are supported for SES rule sets"
                }
            ]
        )
