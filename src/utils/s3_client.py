import boto3
from botocore.exceptions import ClientError


def _client():
    return boto3.client("s3")


def download_file(bucket: str, key: str) -> bytes:
    s3 = _client()
    response = s3.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()


def upload_file(bucket: str, key: str, data: bytes, content_type: str = "application/pdf") -> str:
    s3 = _client()
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
    return f"s3://{bucket}/{key}"


def key_exists(bucket: str, key: str) -> bool:
    s3 = _client()
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise
