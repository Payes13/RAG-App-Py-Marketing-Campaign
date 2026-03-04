import os
from langchain_aws import ChatBedrockConverse, BedrockEmbeddings

LLM_MODEL_ID = "anthropic.claude-3-sonnet-20240229-v1:0"
EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v1"


def get_llm(max_tokens: int = 2048) -> ChatBedrockConverse:
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
