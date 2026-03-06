# Code Samples & Reference Data

---

## Lambda Event & Context — Sample Payloads

When AWS calls a Lambda handler, it passes two objects: `event` and `context`.

### `event` — what triggered the Lambda

For `ingestion_handler.py` (triggered by S3 file upload):
```json
{
  "Records": [
    {
      "s3": {
        "bucket": { "name": "marketing-ai-documents" },
        "object": { "key": "reports/q1-2026.pdf" }
      }
    },
    {
      "s3": {
        "bucket": { "name": "marketing-ai-documents" },
        "object": { "key": "reports/q2-2026.pdf" }
      }
    }
  ]
}
```

For `campaign_handler.py` (triggered by API Gateway POST request):
```json
{
  "body": "{\"route\": \"Montreal-San Salvador\", \"date\": \"2026-03-04\"}",
  "httpMethod": "POST",
  "path": "/campaign/generate",
  "headers": { "Content-Type": "application/json" }
}
```

> Note: `event["body"]` is a **JSON string**, not an object — you must call `json.loads(event["body"])` to parse it.

### `context` — metadata about the Lambda invocation itself

```python
context.aws_request_id       # "abc-123-def-456"  ← unique ID for this run
context.function_name        # "campaign-generator"
context.function_version     # "$LATEST"
context.memory_limit_in_mb   # "512"
context.get_remaining_time_in_millis()  # milliseconds before Lambda times out
```

> `request_id = getattr(context, "aws_request_id", "local")` — reads the request ID safely. Falls back to `"local"` when running tests without a real Lambda context.

---

## Secrets Manager — `get_secret_value()` Response

From [postgres_client.py:18](../src/db/postgres_client.py#L18): `response = client.get_secret_value(SecretId=secret_name)`

The full response object looks like this:
```json
{
  "ARN": "arn:aws:secretsmanager:us-east-1:123456789:secret:marketing-ai/db-app-password-AbCdEf",
  "Name": "marketing-ai/db-app-password",
  "VersionId": "abc123-def456",
  "SecretString": "{\"password\": \"my-super-secret-db-password\"}",
  "VersionStages": ["AWSCURRENT"],
  "CreatedDate": "2026-01-15T10:30:00Z"
}
```

The code only cares about `response["SecretString"]` — everything else is metadata.

`SecretString` can come in two formats depending on how you created the secret in AWS:

**Format 1 — JSON object** (most common, what this app uses):
```json
"SecretString": "{\"password\": \"my-super-secret-db-password\"}"
```
→ `json.loads()` parses it → `.get("password", secret)` extracts just the password value.

**Format 2 — plain string**:
```json
"SecretString": "my-super-secret-db-password"
```
→ `json.loads()` throws `JSONDecodeError` → the `except` block catches it → uses the raw string directly.

That's why the `try/except` exists in `_get_secret()` — to handle both formats gracefully.

---
