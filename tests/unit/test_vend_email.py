"""Unit tests for vend email function"""
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
import os
from unittest import TestCase
from src.vendEmail import app
from schema import SchemaError

os.environ["SES_DOMAIN_NAME"] = "example.com"

valid_account_names = [
    "this-is-a-sample-account-name",
    "this-account-name-should-be-valid",
]
invalid_account_names = [
    {
        "AccountName": "this-account-name-shouldnot-workà",
        "AccountEmail": "user@example.com",
        "AccountType": "Sales",
        "OwnerAddress": "user@sample.example.com",
    },
    {
        "AccountName": "this-one-is-really-long-but has '!@#$%^&*()_+_)(*&^%$#@!~' issues",
        "AccountEmail": "user@example.com",
        "AccountType": "Sales",
        "OwnerAddress": "user@sample.example.com",
    },
]

invalid_email_addresses = [
    {
        "AccountName": "this-account-name-should-work",
        "AccountEmail": "user@example",
        "AccountType": "Sales",
        "OwnerAddress": "user@sample.example.com",
    },
    {
        "AccountName": "this-one-is-valid-name",
        "AccountEmail": "user@domainthatisreallylong@anotherdomain.example.com",
        "AccountType": "Sales",
        "OwnerAddress": "user@sample.example.com",
    },
]

invalid_account_length_names = [
    "this-account-name-length-is-really-long-and-should-cause-a-failure",
    "this-account-name-length-is-really-long-and-should-----------------=123456789=",
    "this-account-name-length-is-really-long-and-should-123456789",
]
valid_email_address_lengths = [
    "user@example.com",
    "user@domainthatisreallylonganotherdomain.example.com",
]
invalid_email_address_lengths = [
    "short",
    "user_namethatisreally_realy_really_really_LONG_again@another_domain.example.com",
    "user_namethatisreally_realy_really_really_REAAAAALLLY_LONG@anotherdomain.example.com",
    "user@domainthatisreallylongandanotherdomainandanotherdomainandanotherdomain.example.com",
]


class test_vend_email(TestCase):
    def test_invalid_account_name(self):
        for test_name in invalid_account_names:
            with self.subTest(test_name=test_name["AccountName"]):
                with self.assertRaises(SchemaError):
                    app.provision_aws_account_schema.validate(test_name)

    def test_invalid_email_addresses(self):
        for test_name in invalid_email_addresses:
            with self.subTest(test_name=test_name["AccountEmail"]):
                with self.assertRaises(SchemaError):
                    app.provision_aws_account_schema.validate(test_name)

    def test_valid_account_length(self):
        for test_name in valid_account_names:
            with self.subTest(
                test_name=test_name,
                description=f"Testing validity of account name length for '{test_name}' length={len(test_name)}",
            ):
                self.assertTrue(app.valid_acct_length(test_name))

    def test_invalid_account_length(self):
        for test_name in invalid_account_length_names:
            with self.subTest(
                test_name=test_name,
                description=f"Testing failure of account name length for '{test_name}' length={len(test_name)}",
            ):
                self.assertFalse(app.valid_acct_length(test_name))

    def test_valid_email_length(self):
        for test_name in valid_email_address_lengths:
            with self.subTest(
                test_name=test_name,
                description=f"Testing validity of email length for '{test_name}' length={len(test_name)}",
            ):
                self.assertTrue(app.valid_email_length(test_name))

    def test_invalid_email_length(self):
        for test_name in invalid_email_address_lengths:
            with self.subTest(
                test_name=test_name,
                description=f"Testing failure of email length for '{test_name}' length={len(test_name)}",
            ):
                self.assertFalse(app.valid_email_length(test_name))

    def test_get_new_account_data_returns_overrides(self):
        """Test that get_new_account_data() returns override values when provided"""
        from unittest.mock import patch

        base_metadata = {"BusinessUnit": "finance", "ApplicationName": "billing", "Environment": "PRODUCTION"}
        test_cases = [
            # Both overrides provided - uses both overrides directly
            ({**base_metadata, "AccountName": "my-custom-account", "AccountEmail": "my-custom-account@example.com"},
             "my-custom-account", "my-custom-account@example.com"),
            # Only AccountName override - email derived from name + SES_DOMAIN_NAME
            ({**base_metadata, "AccountName": "my-custom-account"},
             "my-custom-account", "my-custom-account@example.com"),
            # Only AccountEmail override - name auto-generated with counter
            ({**base_metadata, "AccountEmail": "custom-email@example.com"},
             "finance-billing-prod-001", "custom-email@example.com"),
            # No overrides - both auto-generated
            ({**base_metadata},
             "finance-billing-prod-001", "finance-billing-prod-001@example.com"),
        ]

        for metadata, expected_name, expected_email in test_cases:
            with self.subTest(metadata=metadata):
                with patch.object(app, 'get_next_number', return_value="001"):
                    with patch.object(app, 'SES_DOMAIN_NAME', "example.com"):
                        account_name, account_email = app.get_new_account_data(metadata)
                        self.assertEqual(account_name, expected_name)
                        self.assertEqual(account_email, expected_email)
