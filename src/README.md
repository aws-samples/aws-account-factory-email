# Lambda Source Code
The sub-folders in this folder represent individual Lambda functions

The code for these functions is zipped up (one per folder), uploaded to S3 and then referenced during Lambda function deployment.  The AWS CDK handles this whole process as part of `cdk deploy`.

# /vendEmail
This function does the work of vending a valid AWS account and email address from given input. The process is as follows:
1. Event JSON is sent to the function (invocation method TBD). See example event in `events/sample_vend_request.json`
2. Generates an email address and account name based on some rules and on the input data  
3. Checks to see if the account name or email already exists
    1. If the email or account name already exist in the system, a response with 'statusCode' 500 is returned. Also with this response is body.message field with a text explanation of the issue.
4. Writes the information to a new record in DynamoDB
5. Checks to see if the account owner's email address has been verified by SES.  If not, the verification request is sent.  Until the email has been verified, the account owner will not receive these emails but rather then ADDRESS_ADMIN will.  Note that if your AWS account is not in the SES sandbox, this step could be commented out as it is not needed. See the /fwdEmail section below for more details on how emails are sent.
6. Returns a 'statusCode' 200. The response will also contain a 'body' element with the new 'AccountType', 'AccountName' and 'AccountEmail' fields which could then be used to register a new AWS account. Also returned is 'EmailVerification' field which indicates the status of the user's SES email verification status.  See `events/sample_vend_response.json` for an example response.

## Environment Vars for vendEmail
|Env Var|Source|
|--|--|
|SES_DOMAIN_NAME | cdk.json context.SES_DOMAIN_NAME
|TABLE_NAME | cdk.json context.ACCOUNT_TABLE_NAME
|API_VERSION | cdk.json context.API_VERSION

# /fwEmail
This function delivers incoming message to the proper recipient.  The process is as follows:
1. Email is received by SES
2. SES rule (which is deployed by the CDK in the project) says to write the email to an S3 bucket and then send a message to an SNS topic.  There is currently no option for the email object itself to be sent directly to Lambda, so SNS is used as a notification mechanism at which point it is Lambda's role to pick up the object from the bucket.
3. This Lambda function is configured to listen for events from the SNS topic
4. The SNS messages indicate where the incoming email was stored (in S3) so the function goes there and reads the content of the message into memory.  See /events folder for sample events that are received from SNS.
5. The original TO address on the message is looked up in the AWS account table (DynamoDB).  If the TO address is found in the table, the the TO field is overwritten with the value of the 'OwnerAddress' field from the table.  If not, the TO address is overwritten with the ADDRESS_ADMIN env variable.
6. The FROM address is overwritten with the ADDRESS_FROM env variable.  This is done because SES needs a verified from address or domain.
7. The email is sent and if the recipient's email has not been verified yet, the email is sent to ADDRESS_ADMIN instead.  If your AWS account is not in the SES Sandbox, all outgoing emails should be sent as intended.

## Environment Vars for fwEmail
|Env Var|Source|
|--|--|
|SES_DOMAIN_NAME | cdk.json context.SES_DOMAIN_NAME
|ADDRESS_FROM | cdk.json context.ADDRESS_FROM
|ADDRESS_ADMIN | cdk.json context.ADDRESS_ADMIN
|TABLE_NAME | cdk.json context.ACCOUNT_TABLE_NAME

# /events
The /events folder contains several sample events that are used to debug or build further functionality in the future.

- `event_SNS_message.json`: This is the decode "message" field from `event_SNS.json` and is the bulk of fields we care about.  The fields you see in this file are what is used to find the message object in the bucket. 
- `event_SNS.json`: This file is a copy of the format of the message that is sent from SNS when an email is placed in the S3 bucket.  The fields we really care about are encoded in the `message` field which is provided in a decoded format in `event_SNS_message.json`.
- `sample_vend_request.json`: This is a sample event that is sent to the vendEmail Lambda.  This event intentionally includes a key/value pair that is not needed for the request to test / show that only the keys and values we care about are considered in the verification process.
- `sample_vend_response.json`: This is a sample response from the vendEmail function.