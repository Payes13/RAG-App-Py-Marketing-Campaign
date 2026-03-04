"""
Main CDK Stack: Lambda functions, API Gateway, S3 buckets, and IAM roles.
"""
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_apigateway as apigw
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_notifications as s3n
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct


class MarketingAIStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── S3 Buckets ─────────────────────────────────────────────────────────

        input_bucket = s3.Bucket(
            self,
            "InputBucket",
            bucket_name="marketing-ai-documents",
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        output_bucket = s3.Bucket(
            self,
            "OutputBucket",
            bucket_name="marketing-ai-outputs",
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # ── Secrets (referenced, not created here) ─────────────────────────────

        db_readonly_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "DbReadonlySecret", "marketing-ai/db-readonly-password"
        )
        db_app_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "DbAppSecret", "marketing-ai/db-app-password"
        )

        # ── IAM Role for Lambda ────────────────────────────────────────────────

        lambda_role = iam.Role(
            self,
            "LambdaExecutionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )

        # Bedrock: invoke model
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=["*"],
            )
        )

        # S3 input: read-only
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:ListBucket"],
                resources=[
                    input_bucket.bucket_arn,
                    f"{input_bucket.bucket_arn}/*",
                ],
            )
        )

        # S3 output: write-only
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject"],
                resources=[f"{output_bucket.bucket_arn}/*"],
            )
        )

        # Secrets Manager: read secrets
        lambda_role.add_to_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[
                    db_readonly_secret.secret_arn,
                    db_app_secret.secret_arn,
                ],
            )
        )

        # ── Shared environment variables ───────────────────────────────────────

        common_env = {
            "S3_INPUT_BUCKET_NAME": input_bucket.bucket_name,
            "S3_OUTPUT_BUCKET_NAME": output_bucket.bucket_name,
            "DB_READONLY_SECRET_NAME": "marketing-ai/db-readonly-password",
            "DB_APP_SECRET_NAME": "marketing-ai/db-app-password",
            # DB_HOST, DB_PORT, DB_NAME, AWS_BEDROCK_REGION set via SSM or at deploy time
        }

        # ── Lambda: campaign-generator ─────────────────────────────────────────

        campaign_fn = lambda_.Function(
            self,
            "CampaignGeneratorFn",
            function_name="campaign-generator",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="src.handlers.campaign_handler.handler",
            code=lambda_.Code.from_asset("."),
            timeout=Duration.seconds(60),
            memory_size=512,
            role=lambda_role,
            environment=common_env,
        )

        # ── Lambda: document-ingestion ─────────────────────────────────────────

        ingestion_fn = lambda_.Function(
            self,
            "DocumentIngestionFn",
            function_name="document-ingestion",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="src.handlers.ingestion_handler.handler",
            code=lambda_.Code.from_asset("."),
            timeout=Duration.seconds(120),
            memory_size=512,
            role=lambda_role,
            environment=common_env,
        )

        # S3 PUT trigger → ingestion Lambda
        input_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED_PUT,
            s3n.LambdaDestination(ingestion_fn),
        )

        # ── API Gateway ────────────────────────────────────────────────────────

        api = apigw.RestApi(
            self,
            "MarketingAIApi",
            rest_api_name="marketing-ai-api",
            description="Marketing Campaign AI — REST API",
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                logging_level=apigw.MethodLoggingLevel.INFO,
                data_trace_enabled=False,
            ),
        )

        campaign_resource = api.root.add_resource("campaign").add_resource("generate")
        campaign_resource.add_method(
            "POST",
            apigw.LambdaIntegration(campaign_fn),
        )
