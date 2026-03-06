import os
from langchain_aws import ChatBedrockConverse, BedrockEmbeddings

# WHERE ARE THESE VALUES COMING FROM, WHERE DID I GET THEM FROM? R// YOU CAN GRAB THEM FROM THE AWS BEDROCK CONSOLE
LLM_MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v1"

# max_tokens=2048 is a safety cap on the LLM's response length. It tells Bedrock: "stop generating after 2048 tokens, even if you're not done.". Without a limit, the model could generate a very long (and expensive) response
# AWS_BEDROCK_REGION: It is not set in the code — it's an environment variable that must be configured externally. The template for it lives in .env.example:4 (intentionally blank — you fill it in).
# Where you actually set it depends on context:
# Locally: you create a .env file copied from .env.example and fill in your AWS region (e.g., AWS_BEDROCK_REGION=us-east-1)
# In AWS Lambda: you set it in the Lambda function's Environment Variables section in the AWS Console (or via CDK in the infrastructure code)
# At runtime, line 10 reads it with os.environ["AWS_BEDROCK_REGION"] — this is Python's equivalent of Node's process.env.AWS_BEDROCK_REGION. If it's not set, the app crashes immediately with a KeyError, which is intentional — it forces you to configure it properly before running.
# IMPORTANT: IN THE INITIAL PROMPT.MD FILE, IT SAYS: - **Environment Variables** (from AWS Secrets Manager, never hardcoded):
# WITH REPECT TO THE LATEST IMPORTANT NOTE THE AI SAYS:
# The statement "from AWS Secrets Manager, never hardcoded" applies only to passwords/secrets — not to all environment variables. Here's the distinction:
# Plain env vars (non-sensitive config — just tells the app where things are):
# AWS_BEDROCK_REGION → just a region name like us-east-1, not sensitive
# DB_HOST, DB_PORT, DB_NAME → connection info, not credentials
# S3_INPUT_BUCKET_NAME → just a bucket name
# These live as regular Lambda environment variables. No risk if seen.
# AWS Secrets Manager (sensitive credentials — the actual passwords):
# DB_READONLY_SECRET_NAME and DB_APP_SECRET_NAME in .env.example are not the passwords themselves — they're just the name/path used to look up the secret in Secrets Manager
# The actual passwords are fetched at runtime in postgres_client.py:16-17 via boto3.client("secretsmanager").get_secret_value(...)
# So the flow is:
# Lambda env var: DB_APP_SECRET_NAME = "marketing-ai/db-app-password"  ← just a name, not sensitive
#         ↓
# Secrets Manager lookup at runtime
#         ↓
# Actual password retrieved securely ← never stored anywhere in code or env vars
# The spec's statement means: passwords are never hardcoded or put in env vars directly — they're always fetched from Secrets Manager at runtime. AWS_BEDROCK_REGION is just config, not a secret, so it's fine as a plain env var.
def get_llm(max_tokens: int = 2048) -> ChatBedrockConverse:
    # AWS_BEDROCK_REGION set via SSM or at deploy timeset via SSM or at deploy time
    region = os.environ["AWS_BEDROCK_REGION"]
    return ChatBedrockConverse(
        model=LLM_MODEL_ID,
        region_name=region,
        max_tokens=max_tokens,
    )

def get_embeddings() -> BedrockEmbeddings:
    region = os.environ["AWS_BEDROCK_REGION"]
    return BedrockEmbeddings(
        model_id=EMBEDDING_MODEL_ID,
        region_name=region,
    )
