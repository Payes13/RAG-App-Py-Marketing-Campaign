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
  "httpMethod": "POST",
  "path": "/campaign/generate",
  "headers": { "Content-Type": "application/json" },
  "body": "{\"route\": \"Montreal-San Salvador\", \"audience_description\": \"Frequent business travellers aged 30-55\", \"campaign_type\": \"promotional\", \"language\": \"en\", \"tone\": \"professional\", \"csv_file_key\": \"uploads/q1-bookings.csv\"}"
}
```

The `body` value above, once parsed with `json.loads()`, becomes:
```json
{
  "route": "Montreal-San Salvador",
  "audience_description": "Frequent business travellers aged 30-55",
  "campaign_type": "promotional",
  "language": "en",
  "tone": "professional",
  "csv_file_key": "uploads/q1-bookings.csv"
}
```

Fields `route`, `audience_description`, `campaign_type`, `language`, and `tone` are **required** — missing any returns HTTP 400. `csv_file_key` is optional (defaults to `""`).

> Note: `event["body"]` is a **JSON string**, not an object — you must call `json.loads(event["body"])` to parse it. API Gateway always serializes the request body as a string.

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

## `agent_result` — AgentExecutor Output

From [marketing_agent.py:152](../src/agents/marketing_agent.py#L152): `agent_result = agent_executor.invoke({...})`

Because `return_intermediate_steps=True` is set, the result has two keys:

```python
agent_result = {
    "output": """
        Here is a summary of the data gathered for the Montreal–San Salvador promotional campaign:

        AUDIENCE (from database):
        - 1,842 customers have flown the Montreal–San Salvador route in the past 12 months
        - Age range: 30–55, average age 43
        - 68% business travellers, 32% leisure
        - Top origin cities: Montreal (61%), Quebec City (22%), Ottawa (17%)
        - Preferred class: Business (54%), Economy Plus (31%), Economy (15%)
        - Languages: French (58%), English (42%)
        - Average booking lead time: 38 days

        MARKETING CONTEXT (from PDFs):
        - Previous winter sun campaign (Jan 2025) achieved 34% open rate, 12% CTR
        - El Salvador positioned as Central America's hidden gem — beaches, volcanoes, colonial cities
        - San Salvador direct flight launched March 2025, strong brand recognition with MTL business community
        - Competitor Air Transat running similar route with 10% lower base fare — differentiate on comfort and frequency

        CSV INSIGHTS:
        - Bookings spike sharply 6 weeks before departure for this route
        - Highest booking day: Tuesday and Wednesday
        - Average party size: 1.8 passengers (mostly solo or couple travel)
        - Q1 load factor: 78%, well above break-even

        Recommendation: Focus campaign on business traveller convenience (direct, frequent, business class),
        with a secondary message around weekend leisure extensions to beaches.
    """,
    "intermediate_steps": [...]   # every tool call that happened along the way
}
```

### `output` — the agent's final summary

```
"Audience summary for Montreal–San Salvador route:
 - 1,842 customers have flown this route in the past 12 months
 - 68% are business travellers aged 30–55, predominantly male
 - Top cities of origin: Montreal, Quebec City, Ottawa
 - Preferred class: Business (54%), Economy Plus (31%)
 - Previous campaign themes: winter sun escapes, direct flight convenience
 - CSV insight: bookings spike 6 weeks before departure for this route"
```

This string becomes `audience_data` and is passed directly into Phase 2 (`_generate_campaign()`).

### `intermediate_steps` — one entry per tool call

Each entry is a tuple of `(action, tool_output)`:

```python
intermediate_steps = [
    (
        AgentAction(
            tool="query_customer_database",
            tool_input="How many customers flew Montreal to San Salvador in the last 12 months and what are their demographics?",
            log="Thought: I need audience size and demographics...\nAction: query_customer_database\nAction Input: ..."
        ),
        '[{"age": 42, "city": "Montreal", "travel_class": "Business"}, ...]'  # raw JSON rows returned by the tool
    ),
    (
        AgentAction(
            tool="search_campaign_documents",
            tool_input="Montreal San Salvador previous campaigns destination guide",
            log="Thought: Now I need PDF context...\nAction: search_campaign_documents\nAction Input: ..."
        ),
        "El Salvador is Central America's smallest country... previous winter campaign achieved 34% open rate..."
    ),
    (
        AgentAction(
            tool="analyze_csv_data",
            tool_input="uploads/q1-bookings.csv:What are the booking patterns for the Montreal-San Salvador route?",
            log="Thought: A CSV was provided, I should analyze it...\nAction: analyze_csv_data\nAction Input: ..."
        ),
        "Bookings peak 6 weeks before departure. Average party size is 1.8 passengers..."
    ),
]
```

The code only uses `agent_result.get("output", "")` — the intermediate steps are ignored after the run (they're captured separately via `_tool_metadata`).

---

## Tool Return Values — What Each Tool Sends Back to the LLM

Every tool returns a **plain string**. That string becomes the `Observation:` the LLM reads before deciding its next step. The LLM never sees Python objects — only text.

---

### Tool 1: `query_customer_database` — [text_to_sql_tool.py](../src/tools/text_to_sql_tool.py)

**Input (written by the LLM):**
```
Action Input: How many customers flew the Montreal to San Salvador route in the last 12 months and what are their demographics?
```

**What happens internally:** natural language → LLM generates SQL → validated → executed against PostgreSQL → rows serialized to JSON string.

**Return value (the string the LLM sees as Observation):**
```
[{"age": 42, "city": "Montreal", "country": "Canada", "language": "fr", "travel_class": "Business"},
 {"age": 38, "city": "Quebec City", "country": "Canada", "language": "fr", "travel_class": "Economy Plus"},
 {"age": 51, "city": "Montreal", "country": "Canada", "language": "en", "travel_class": "Business"},
 {"age": 34, "city": "Ottawa", "country": "Canada", "language": "en", "travel_class": "Economy"},
 ...1842 total rows...]
```

> It's the raw output of `json.dumps(rows, default=str)` — a JSON array of dicts, one per customer row. If no rows found: `"No data found for this query."`. If security rejected the SQL: `"Query rejected by security validation: ..."`.

---

### Tool 2: `search_campaign_documents` — [pdf_rag_tool.py](../src/tools/pdf_rag_tool.py)

**Input (written by the LLM):**
```
Action Input: Montreal San Salvador previous campaigns destination marketing strategy
```

**What happens internally:** question → embedded via Bedrock Titan → vector similarity search in `document_embeddings` table → top 3 matching PDF chunks retrieved and formatted.

**Return value (the string the LLM sees as Observation):**
```
[Document 1 — campaigns/sal-winter-2025.pdf (similarity: 0.934)]
El Salvador Winter Sun Campaign — January 2025
Target audience: Quebec-based families and couples aged 28-50.
Key message: "Escape the cold — direct to San Salvador in 5h30."
Results: 34% open rate, 12% CTR, 8% conversion. Strong performance with French-speaking segment.
Best-performing subject line: "Le soleil vous attend à San Salvador ☀️"

---

[Document 2 — destinations/el-salvador-guide.pdf (similarity: 0.891)]
El Salvador is Central America's smallest and most densely populated country.
Key attractions: Pacific beaches (El Tunco, El Zonte), Santa Ana volcano, colonial city of Suchitoto.
Tourism positioning: "The hidden gem of Central America." Growing surf tourism market.
Air Canada Rouge operates YUL-SAL 4x weekly. Flight time: 5h25.

---

[Document 3 — campaigns/latam-business-2024.pdf (similarity: 0.847)]
Latin America Business Traveller Campaign — Q3 2024
Insight: Business travellers on LATAM routes prioritize punctuality, lounge access, and lie-flat seats.
Recommended CTA for business segment: "Upgrade to Business Class from $X."
```

> Each chunk is a 500-token excerpt from an ingested PDF, prefixed with its source file and similarity score. The `---` separator is added by the tool between chunks.

---

### Tool 3: `analyze_csv_data` — [csv_analyzer_tool.py](../src/tools/csv_analyzer_tool.py)

**Input (written by the LLM):**
```
Action Input: uploads/q1-bookings.csv:What are the booking patterns and audience characteristics for the Montreal-San Salvador route?
```

**What happens internally:** splits on `:` → downloads CSV from S3 → loads into pandas DataFrame → sends column types + first 5 rows + summary stats to the LLM → LLM answers the question → answer string returned.

**Return value (the string the LLM sees as Observation):**
```
Booking patterns for Montreal–San Salvador (Q1 2026, 2,341 rows):

- Peak booking window: 5–7 weeks before departure (42% of all bookings)
- Highest booking days: Tuesday (24%) and Wednesday (21%)
- Average party size: 1.8 passengers
- Solo travellers: 58%, couples: 31%, groups 3+: 11%
- Revenue class breakdown: J (Business) 31%, W (Economy Plus) 28%, Y (Economy) 41%
- Q1 load factor: 78.4% — above the 72% break-even threshold
- Month-over-month growth: +14% vs Q1 2025
```

> Unlike Tool 1 (raw DB rows) and Tool 2 (raw PDF text), Tool 3 returns a **synthesized answer** — the CSV tool calls the LLM internally to interpret the data before returning it. The ReAct agent's LLM then reads this pre-interpreted answer as its Observation.

---
