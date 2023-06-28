## aws-account-factory-email

This solution is designed as a way to allows AWS account owners to effectively register
more than one AWS account to a single email address by means of a go-between email forwarder.

## Background
This solution allows the decoupling of real email addresses to that of the email address
associated with an AWS account.  AWS accounts require a unique email address be provided
at the time of account creation.  This normally prevents a large company from using 
centralized email boxes with the same email address for creating AWS accounts.  This 
solution works around this problem by setting up a mail domain to receive all emails and
then forward them on to real email addresses.  Customers can then use **any** email address
in that domain to register AWS accounts and any emails sent to those addresses will be
forwarded (via this solution) to the right owner of that account.

## Solution Diagram
![Solution Diagram](images/diagram.png)
In this solution there are two flows:  
1. Vend an email address  
> In the above diagram, this flow begins typically with an automated account vending solution or automation or invoked manually.  In this request, Lambda is invoked with a payload (examples in [src/events](src/events)) containing metadata, the solution uses this information to generate a unique account name and email address, stores it in a database and returns the values to the caller.  These values can then be used to create a new AWS account (typically using AWS Organizations)
2. Forward email
> When an AWS account is created using the account email generated from the flow mentioned above, AWS will send various emails to that email address, like account registration confirmation and periodic notifications.  As part of the solution, you configure your AWS account with SES to receive emails for the entire domain.  This solution configures forward rules that allow AWS Lambda to process all incoming emails, check to see if the TO address is in the table and forwards the message on to the account owner's email address instead.  This allows account owners to have multiple accounts associated with one email address.
3. Read / Update / Delete Email Configuration (not pictured)
> Because this is an example of one way this functionality could be created, this solution does not yet implement a read, update, or delete flow that could be used to read the configuration, make modifications or remove mappings.  However, an administrator could create more Lambda functions to do this or use the AWS console directly to interact with the Account Table.  A recommended pattern is to implement [Amazon API Gateway](https://aws.amazon.com/api-gateway/) to provide an API for other applications to consume this functionality.

## Prerequisites
- Administrative access to an AWS account  
- Access to a development environment.  It is recommended to use AWS Cloud9 to avoid having to set up the tools needed to deploy the solution.  See [Getting started with AWS Cloud9](https://aws.amazon.com/cloud9/getting-started/).
- Set up and verify a domain name for use in receiving email with Amazon SES
    - You can use sub-domains like mysubdomain.example.com but try to keep the name as short as possible because there is an overall limit to the length of email addresses (64 characters)
    - The domain must be externally resolvable in order for it to receive emails
    - Follow the instructions in [Verifying a domain with Amazon SES](https://docs.aws.amazon.com/ses/latest/DeveloperGuide/verify-domain-procedure.html).  Once your domain is verified, it is ready to receive emails

## Tools needed for deployment
- Development environment with the AWS CLI and IAM access to your AWS account.  It is recommended to use AWS Cloud9 to simply setting this up.  
- Using Cloud9, all of the following have already been configured for you.  If you choose not to use Cloud9, you will need to install the following.
    - AWS CLI. See [Installing, updating and uninstalling the AWS CLI version 2](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html)
    - Set up the AWS CLI with IAM access credentials. See [Configuring the AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html)
    - Python version 3.9 or later
    - Python packages "pip" and "virtualenv"
    - Node.js version 10.13.0 or later
    - AWS CDK version 2.23.0 or later. For installation instructions see [Getting Started with the AWS CDK](https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html#getting_started_install)
    - Docker version 20.10.x or later

## Pre-Deployment Configuration
- At minimum, edit `SES_DOMAIN_NAME`, `ACCOUNT_FROM`, and `ACCOUNT_ADMIN` in `cdk.json`. See the cdk.json section below for more information on each setting
- Update `aws-cdk-lib==xxxx` in [requirements.txt](./requirements.txt) to match the version which you have installed on your computer. Use `cdk --version` to get the version number.

### cdk.json Settings

The [cdk.json](./cdk.json) file that is located in the root of the this repository tells the CDK 
Toolkit how to execute your app.  There various settings inside this file that 
control the application's behavior. Most of these settings act like environment 
variables.

- SES_DOMAIN_NAME: Set this to the domain in which you want to receive incoming email.  You must own and verify this domain to receive email for this domain.  This solution does _not_ set up or verify the domain for you, see above.
- ACCOUNT_TABLE_NAME: This will be the name of the DynamoDB table that is deployed as part of this solution.
- ADDRESS_FROM: This is the email address that will be used as the FROM address for every email that is forwarded.  The domain part (after the '@' sign) must match the SES_DOMAIN_NAME.
- ADDRESS_ADMIN: This is the email address you wish to use if the solution is unable to find or forward an email to a valid account owner.  Emails will be SENT to this email address.  Typically customers set this to a shared mailbox that the IT team monitors.
- MAIL_HEADER_VALUE: This is the value of the X-Processed-By header that is added to every email forwarded through this system
- COUNTER_LENGTH: This is the length of the number appended to account names (including leading zeros). e.g. this-is-my-account-name-001
- DISABLE_CATCH_ALL: This setting is not present in cdk.json by default. By adding this setting with any value, it will disable the catch-all behavior and the solution will no longer forward messages where the account owner email is not found.  To help prevent a denial of service attack, the catch-all functionality should be disabled.  To enable catch-all, ensure this setting is NOT present in cdk.json.

## Deployment

This project was written to use the AWS CDK to define and provision the needed 
infrastructure for the solution.  Follow the steps below to deploy the solution.

1. Clone this repository to your development environment (your computer or Cloud9 instance)
```
$ git clone <clone url for this repository>
```

2. To manually create a virtualenv (assumes you are in the root of this repository):

```
$ python -m venv .venv
```

3. After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
$ source .venv/bin/activate
```

> Or, if you are a Windows platform, you would activate the virtualenv like this:

```
% .venv\Scripts\activate.bat
```

4. Once the virtualenv is activated, you can install the required dependencies.

```
$ pip install -r requirements.txt
```

5. At this point you can now synthesize the CloudFormation template for this code. This allows you to view the CloudFormation template prior to deployment. If this command succeeds you will see many lines of YAML printed to your scree.

```
$ cdk synth
```

6. To deploy the solution to your account / region, run the following replacing "ACCOUNT-NUMBER" and "REGION":
```
$ cdk bootstrap aws://ACCOUNT-NUMBER/REGION
$ cdk deploy
```

## Testing Python Code
There are also some basic Python unit tests included that test the solution's core python functions (not the CDK code). 

To run the tests, you'll need boto3 and schema python libraries which you can install using pip.
```
pip install -r tests/requirements.txt
```

You should now be able to run the tests:

```
$ pytest
```
or
```
$ python -m unittest
```

## Cleanup Steps
Run the following CDK command to remove the deployed infrastructure:
```
cdk destroy
```
Alternatively, you can delete the CloudFormation stack "AwsMailFwdStack" through the AWS Console.
## CDK Notes

### Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

## Improvement Ideas
- Implement Read/Update/Delete flows for email address configurations
- Implement a Dead Letter Queue (DLQ) where undeliverable messages can go for archive or reprocessing

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

