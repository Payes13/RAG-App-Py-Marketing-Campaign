import boto3
from botocore.exceptions import ClientError

def _client():
    return boto3.client("s3")

# .read(): When S3 returns a file, it doesn't give you all the bytes at once — it gives you a stream (think of it like a pipe, not a bucket). .read() pulls everything out of that stream into memory as bytes. Without calling .read(), you'd just have an open pipe sitting there, not actual data. Same concept as fs.readFile in Node vs getting a readable stream.
def download_file(bucket: str, key: str) -> bytes:
    s3 = _client()
    response = s3.get_object(Bucket=bucket, Key=key)
    return response["Body"].read()

# WE PERFORM A SERVER-SIDE UPLOAD NOT A PRESIGNED URL. The Lambda itself holds the PDF bytes in memory, then calls s3.put_object() directly on line 14 using its IAM role credentials. There's no URL generated for a client to use. The s3://marketing-ai-outputs/... string returned on line 15 is just an internal AWS path notation — not a URL anyone can open in a browser. It's used for logging/reference only.
def upload_file(bucket: str, key: str, data: bytes, content_type: str = "application/pdf") -> str:
    s3 = _client()
    s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
    return f"s3://{bucket}/{key}"

# head_object is like sending a HEAD HTTP request — it asks S3 "does this file exist and what are its metadata?" without downloading the actual content. It's cheap and fast.
# ClientError is boto3's catch-all exception for any AWS API error. The tricky part: it fires for both "file not found" AND real errors (permissions denied, network issues, etc.). So the code inspects the error code on line 23:
# Code "404" → file doesn't exist → return False (expected, handle it gracefully)
# Anything else → raise it back up, because that's a real problem
# TS EQUIVALENT
# try {
#   await s3.headObject({ Bucket, Key }).promise();
#   return true;
# } catch (e: any) {
#   if (e.statusCode === 404) return false;
#   throw e; // unexpected error, let it bubble up
# }
def key_exists(bucket: str, key: str) -> bool:
    s3 = _client()
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise
