# Claude Code Prompt - Marketing Campaign AI

## Application Context

Build an AI-powered backend application for an airline that automates the creation of marketing campaigns. The system analyzes customer data from two sources — files stored in an AWS S3 bucket (PDFs and CSVs) and structured data in PostgreSQL tables — to generate personalized marketing campaign content using an LLM via AWS Bedrock.

After generating the campaign, the system must save two PDF files to a dedicated output S3 bucket: one with the campaign content and one with the full metadata for replication purposes.

---

## Tech Stack

- **Language:** Python 3.11+
- **AI Framework:** LangChain
- **LLM:** AWS Bedrock (`anthropic.claude-3-sonnet-20240229-v1:0`)
- **Embeddings:** AWS Bedrock Titan (`amazon.titan-embed-text-v1`)
- **Database:** PostgreSQL with `pgvector` extension
- **File Storage:** AWS S3 (input: PDFs and CSVs / output: generated campaign PDFs)
- **PDF Generation:** `reportlab` library
- **Compute:** AWS Lambda + API Gateway (serverless, no Docker)
- **Infrastructure as Code:** AWS CDK (Python)
- **CI/CD:** AWS CodePipeline + CodeBuild
- **Dependencies:** `requirements.txt`

---

## System Architecture

A LangChain Agent orchestrates three tools automatically depending on the user's request:

### Tool 1 - Text-to-SQL (structured data from PostgreSQL)
1. User asks a question in natural language
2. Agent generates a SQL query for PostgreSQL
3. Query is executed and results are returned
4. Results are injected into the final prompt

### Tool 2 - RAG over PDFs from S3 (unstructured data)
1. PDFs are downloaded from S3, processed into chunks, and stored as embeddings in PostgreSQL via `pgvector`
2. On query, semantic search retrieves relevant chunks
3. Relevant content is injected into the final prompt

### Tool 3 - CSV Analyzer from S3 (semi-structured data)
1. CSVs are downloaded from S3 and loaded into a pandas DataFrame
2. Agent can query the DataFrame to extract audience insights
3. Results are injected into the final prompt

### Final Flow
All tool results are combined into a structured prompt → LLM generates the campaign → two PDFs are generated and saved to the output S3 bucket.

---

## Project File Structure

```
marketing-ai/
├── app.py                                 # CDK app entry point
├── requirements.txt                       # Python dependencies
├── requirements-dev.txt                   # Dev dependencies (pytest, etc.)
├── .env.example                           # Environment variable names (no values)
├── cdk/
│   ├── __init__.py
│   ├── marketing_ai_stack.py              # Main CDK stack (Lambda, API GW, S3, RDS, IAM)
│   └── pipeline_stack.py                 # CDK Pipeline stack (CodePipeline + CodeBuild)
├── src/
│   ├── handlers/
│   │   ├── campaign_handler.py            # Lambda handler: POST /campaign/generate
│   │   └── ingestion_handler.py           # Lambda handler: triggered by S3 input upload events
│   ├── agents/
│   │   └── marketing_agent.py             # LangChain ReAct Agent with tools
│   ├── tools/
│   │   ├── text_to_sql_tool.py            # Tool: Text-to-SQL over PostgreSQL
│   │   ├── pdf_rag_tool.py                # Tool: semantic search over PDF embeddings
│   │   └── csv_analyzer_tool.py           # Tool: load and query CSVs from S3
│   ├── prompts/
│   │   └── campaign_prompt.py             # ChatPromptTemplate with few-shot examples
│   ├── output/
│   │   ├── pdf_generator.py               # Generate campaign PDF and metadata PDF using reportlab
│   │   └── s3_uploader.py                 # Upload generated PDFs to output S3 bucket
│   ├── db/
│   │   ├── postgres_client.py             # PostgreSQL connection (psycopg2)
│   │   └── vector_store.py                # pgvector setup and similarity search
│   ├── ingestion/
│   │   ├── pdf_ingester.py                # Download PDF from S3, chunk, embed, store
│   │   └── csv_ingester.py                # Download CSV from S3, load into DataFrame
│   └── utils/
│       ├── bedrock_client.py              # AWS Bedrock LLM + Embeddings client
│       ├── s3_client.py                   # S3 download/upload helper
│       └── file_naming.py                 # Generate standardized file names
├── scripts/
│   └── manual_ingest.py                   # Run ingestion manually for local testing
└── tests/
    ├── test_agent.py
    ├── test_text_to_sql.py
    ├── test_rag.py
    └── test_pdf_generator.py
```

---

## Database Schema

Create the following tables in PostgreSQL:

```sql
-- Customer data (structured)
CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    email VARCHAR(255),
    age INTEGER,
    city VARCHAR(100),
    country VARCHAR(100),
    language VARCHAR(50)
);

-- Flight history
CREATE TABLE flights (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    route VARCHAR(100),
    origin VARCHAR(100),
    destination VARCHAR(100),
    flight_date DATE,
    travel_class VARCHAR(50)
);

-- Customer preferences
CREATE TABLE preferences (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    seat_type VARCHAR(50),
    meal_type VARCHAR(50),
    travel_frequency VARCHAR(50),
    family_size INTEGER
);

-- PDF embeddings (pgvector)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE document_embeddings (
    id SERIAL PRIMARY KEY,
    content TEXT,
    embedding vector(1536),
    source_file VARCHAR(255),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Generated campaigns log
CREATE TABLE generated_campaigns (
    id SERIAL PRIMARY KEY,
    campaign_file_key VARCHAR(255),
    metadata_file_key VARCHAR(255),
    route VARCHAR(100),
    audience_description TEXT,
    campaign_type VARCHAR(50),
    language VARCHAR(10),
    tokens_used INTEGER,
    generated_at TIMESTAMP DEFAULT NOW()
);
```

### PostgreSQL Users and Permissions

Create two separate users with minimum required permissions. Never use a superuser or the master DB user in the application. Store both passwords in AWS Secrets Manager as separate secrets.

```sql
-- User 1: read-only, used exclusively by the LangChain Agent (Text-to-SQL tool)
CREATE USER marketing_ai_readonly WITH PASSWORD '${DB_READONLY_PASSWORD}';
GRANT CONNECT ON DATABASE marketing_ai TO marketing_ai_readonly;
GRANT USAGE ON SCHEMA public TO marketing_ai_readonly;
GRANT SELECT ON customers TO marketing_ai_readonly;
GRANT SELECT ON flights TO marketing_ai_readonly;
GRANT SELECT ON preferences TO marketing_ai_readonly;
GRANT SELECT ON document_embeddings TO marketing_ai_readonly;
-- Explicitly deny write access (defense in depth)
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM marketing_ai_readonly;

-- User 2: app user, used exclusively by application code (never by the LLM)
CREATE USER marketing_ai_app WITH PASSWORD '${DB_APP_PASSWORD}';
GRANT CONNECT ON DATABASE marketing_ai TO marketing_ai_app;
GRANT USAGE ON SCHEMA public TO marketing_ai_app;
GRANT SELECT, INSERT ON generated_campaigns TO marketing_ai_app;
GRANT SELECT, INSERT ON document_embeddings TO marketing_ai_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO marketing_ai_app;
-- Explicitly deny access to customer data tables
REVOKE ALL ON customers FROM marketing_ai_app;
REVOKE ALL ON flights FROM marketing_ai_app;
REVOKE ALL ON preferences FROM marketing_ai_app;
```

**Usage in code:**
- `postgres_client.py` must accept a `user_role` parameter: `"readonly"` or `"app"`
- The LangChain Agent's `text_to_sql_tool.py` must **always** connect using `marketing_ai_readonly`
- The campaign handler's save logic must **always** connect using `marketing_ai_app`
- Both passwords come from separate entries in AWS Secrets Manager: `marketing-ai/db-readonly-password` and `marketing-ai/db-app-password`

---

## Implementation Details

### File Naming Convention

Create a `file_naming.py` utility that generates consistent file names based on route and date:

```python
# Input:  route="Montreal-San Salvador", date="2026-03-04"
# Output:
#   campaign file:  campaigns/campaign-MTL-SAL-20260304.pdf
#   metadata file:  metadata/metadata-campaign-MTL-SAL-20260304.pdf

# Rules:
# - Origin city → first 3 letters uppercase (Montreal → MTL)
# - Destination city → first 3 letters uppercase (San Salvador → SAL)
# - Date → YYYYMMDD format
# - Spaces and special characters removed
```

---

### LangChain Agent

Implement a ReAct Agent with exactly three tools:

**Tool 1: `query_customer_database`**
- Description: "Use this tool when you need to find customer audiences, flight history, demographics, or any structured customer data."
- Input: natural language question
- Process: generate SQL → validate → execute on PostgreSQL → return results
- **Security:** the PostgreSQL user must have SELECT-only permissions. Validate and sanitize all generated SQL before executing. Never allow DROP, INSERT, UPDATE, DELETE.

**Tool 2: `search_campaign_documents`**
- Description: "Use this tool when you need context about previous marketing campaigns, destination descriptions, or marketing strategies from PDF documents."
- Input: natural language question
- Process: generate embedding → similarity search in pgvector → return top 3 relevant chunks

**Tool 3: `analyze_csv_data`**
- Description: "Use this tool when you need to analyze audience data, customer segments, or metrics stored in CSV files in S3."
- Input: S3 file key + natural language question about the data
- Process: download CSV from S3 → load into pandas → use LLM to query DataFrame → return results

---

### Final Prompt Structure

Use `ChatPromptTemplate` from LangChain. The prompt must have these sections in this exact order:

```
[SYSTEM - Role]
You are an expert marketing specialist for an airline. Your job is to create
compelling, data-driven marketing campaigns based on real customer data.
Always write in a warm, engaging tone. Never mention specific prices.
Always include an unsubscribe option reminder.

[Few-shot Examples]
Include 2 complete examples of well-formed campaigns (email format):
- Example 1: family-focused route campaign in Spanish
- Example 2: business traveler campaign in English

[Audience Context]
{audience_data}  <- injected from Text-to-SQL and/or CSV tool results

[Previous Campaign Context]
{marketing_context}  <- injected from RAG tool results

[Specific Instructions]
Generate a {campaign_type} campaign for the route {route}.
Target audience: {audience_description}
Language: {language}

The campaign must include:
- Subject line (max 50 characters)
- Preview text (max 90 characters)
- Email body (max 200 words)
- One clear CTA button text
- Tone: {tone}

[Restrictions]
- Do not mention specific prices
- Do not use technical jargon
- Always include unsubscribe reminder
- Output must be valid JSON
```

---

### PDF Output Generation (`src/output/pdf_generator.py`)

Use the `reportlab` library to generate two PDF files after each campaign is created.

**File 1: Campaign PDF**
- S3 key: `campaigns/campaign-{ORIGIN}-{DEST}-{YYYYMMDD}.pdf`
- Content:
  - Airline logo placeholder at the top
  - Title: "Marketing Campaign — {route}"
  - Generated date
  - Subject line (styled as email subject)
  - Preview text
  - Email body (full text)
  - CTA button (styled as a colored box with button text)
  - Footer: "Generated by Marketing AI"

**File 2: Metadata PDF**
- S3 key: `metadata/metadata-campaign-{ORIGIN}-{DEST}-{YYYYMMDD}.pdf`
- Content:
  - Title: "Campaign Metadata — {route}"
  - Section 1 — Campaign Parameters:
    - Route
    - Audience description
    - Campaign type
    - Language
    - Tone
    - Generated at (timestamp)
  - Section 2 — LLM Configuration:
    - Model used (`anthropic.claude-3-sonnet-20240229-v1:0`)
    - Max tokens configured
    - Tokens consumed (input + output)
  - Section 3 — Data Sources Used:
    - PostgreSQL tables queried (list)
    - SQL queries executed (full text)
    - CSV files used (S3 keys)
    - PDF documents retrieved from RAG (file names + chunk excerpts)
  - Section 4 — Full Prompt Used:
    - Complete final prompt sent to the LLM (verbatim, monospace font)
  - Section 5 — Audience Summary:
    - Audience size
    - Top cities
    - Average age
    - Other key demographics retrieved

Both PDFs must be generated in memory (using `BytesIO`) and uploaded directly to S3 without saving to disk, since Lambda has no persistent storage.

---

### Lambda Handlers

**POST /campaign/generate (`campaign_handler.py`)**

Input event body:
```json
{
  "route": "Montreal-San Salvador",
  "audience_description": "young families with children",
  "campaign_type": "email",
  "language": "es",
  "tone": "warm and exciting",
  "csv_file_key": "audiences/latam_families_2024.csv"
}
```

Full output flow:
1. Run Agent (Text-to-SQL + RAG + CSV tools)
2. Generate campaign content via LLM
3. Generate campaign PDF → upload to `campaigns/campaign-MTL-SAL-{date}.pdf`
4. Generate metadata PDF → upload to `metadata/metadata-campaign-MTL-SAL-{date}.pdf`
5. Log campaign to `generated_campaigns` table in PostgreSQL
6. Return HTTP 200 with:

```json
{
  "campaign": {
    "subject_line": "...",
    "preview_text": "...",
    "body": "...",
    "cta": "..."
  },
  "output_files": {
    "campaign_pdf": "s3://marketing-ai-outputs/campaigns/campaign-MTL-SAL-20260304.pdf",
    "metadata_pdf": "s3://marketing-ai-outputs/metadata/metadata-campaign-MTL-SAL-20260304.pdf"
  },
  "audience_size": 3200,
  "tokens_used": 1840,
  "generated_at": "2026-03-04T10:23:00Z"
}
```

**S3 Event Trigger (`ingestion_handler.py`)**
- Triggered automatically when a new PDF or CSV is uploaded to the **input** S3 bucket
- For PDFs: chunk (500 tokens, 50 overlap) → embed → store in `document_embeddings`
- For CSVs: validate format → store metadata in a `csv_files` table for reference
- Log the ingestion result (success/failure) with the file key

---

### CDK Stack (`cdk/marketing_ai_stack.py`)

Provision the following resources:

- **S3 Bucket 1 (Input):** `marketing-ai-documents` — stores source PDFs and CSVs, versioning enabled, triggers ingestion Lambda on PUT events
- **S3 Bucket 2 (Output):** `marketing-ai-outputs` — stores generated campaign PDFs and metadata PDFs, versioning enabled, organized by prefixes `campaigns/` and `metadata/`
- **Lambda Functions:**
  - `campaign-generator`: handler `src/handlers/campaign_handler.py`, timeout 60s, memory 512MB
  - `document-ingestion`: handler `src/handlers/ingestion_handler.py`, triggered by S3 PUT events on input bucket, timeout 120s, memory 512MB
- **API Gateway:** REST API with one endpoint `POST /campaign/generate` connected to `campaign-generator` Lambda
- **RDS PostgreSQL:** use existing PostgreSQL URL via environment variable
- **IAM Roles:**
  - Lambda execution role with permissions: `bedrock:InvokeModel`, `s3:GetObject`, `s3:ListBucket` on input bucket, `s3:PutObject` on output bucket
  - Input S3 bucket policy: read-only for Lambda
  - Output S3 bucket policy: write-only for Lambda
- **Environment Variables** (from AWS Secrets Manager, never hardcoded):
  - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`
  - `AWS_BEDROCK_REGION`
  - `S3_INPUT_BUCKET_NAME`
  - `S3_OUTPUT_BUCKET_NAME`

---

### CI/CD Pipeline (`cdk/pipeline_stack.py`)

Set up a CDK Pipeline with the following stages:

```
Source (CodeCommit or GitHub)
      ↓
Build (CodeBuild)
  - pip install -r requirements.txt
  - run pytest tests/
  - cdk synth
      ↓
Deploy Staging
  - cdk deploy --require-approval never (staging account/env)
      ↓
Manual Approval Gate
      ↓
Deploy Production
  - cdk deploy --require-approval never (prod account/env)
```

CodeBuild `buildspec.yml` must:
- Use Python 3.11 runtime
- Install AWS CDK CLI
- Run unit tests before deploy
- Fail the pipeline if any test fails

---

## Important Considerations

- **PDF generation in memory:** Always use `BytesIO` for PDF generation in Lambda. Never write to disk. Upload the in-memory buffer directly to S3 using `boto3`.
- **Credentials:** All secrets must come from AWS Secrets Manager. Never hardcode credentials. Include `.env.example` with variable names only.
- **Error Handling:** Handle cases where the LLM generates invalid SQL, pgvector returns no results, S3 file is missing, PDF generation fails, or Bedrock throttles the request. Return meaningful HTTP error responses (400, 500). If PDF upload to S3 fails, still return the campaign JSON so the user is not blocked.
- **Logging:** Add structured logs (JSON format) at every Agent step: which tool was called, what SQL was generated, how many documents were retrieved, S3 upload result, total latency.
- **SQL Schema in Prompt:** The Text-to-SQL prompt must always include the full table schema so the LLM generates accurate queries.
- **Chunking Strategy:** PDFs must be split into chunks of 500 tokens with 50-token overlap using LangChain's `RecursiveCharacterTextSplitter`.
- **Duplicate file names:** If a campaign for the same route and date already exists in S3, append a counter suffix: `campaign-MTL-SAL-20260304-2.pdf`.

---

## Security Implementation

Create a dedicated `src/security/` module with the following files and rules. Every SQL query generated by the LLM **must pass all six layers** before being executed. If any layer fails, reject the query immediately, log the rejection reason, and return a 400 error.

```
src/
└── security/
    ├── __init__.py
    ├── sql_validator.py        # Layers 1, 2, 3: SQL-specific guards
    ├── prompt_guard.py         # Layer 6: Prompt injection detection
    └── query_logger.py         # Audit logging for all queries
```

---

### Layer 1 — Table Whitelist (`sql_validator.py`)

Only the following tables are allowed in any generated SQL query. Reject immediately if any other table name is detected:

```python
ALLOWED_TABLES = [
    "customers",
    "flights",
    "preferences",
    "document_embeddings",
    "generated_campaigns",
    "csv_files"
]
```

Implementation rules:
- Parse the SQL using the `sqlparse` library to extract all table references
- If any table is not in `ALLOWED_TABLES`, reject with reason: `"Table '{table}' is not allowed"`
- This check must run before any other validation

---

### Layer 2 — Malicious Pattern Detection (`sql_validator.py`)

Before executing any SQL, scan it against the following regex blocklist. Match must be case-insensitive:

```python
BLOCKED_PATTERNS = [
    r"\bDROP\b",
    r"\bDELETE\b",
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bTRUNCATE\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"--",                      # SQL comment injection
    r"/\*",                     # Block comment injection
    r"\bUNION\b",               # UNION-based injection
    r"\bpg_sleep\b",            # Time-based attacks
    r"\binformation_schema\b",  # Schema enumeration
    r"\bpg_catalog\b",          # Internal catalog access
    r"\bpg_tables\b",
    r"\bpg_user\b",
    r"\bcopy\b",                # COPY command (file read/write)
    r";\s*\w",                  # Multiple statements
]
```

If any pattern matches, reject with reason: `"Blocked pattern detected: '{pattern}'"`.

---

### Layer 3 — Query Complexity Limit (`sql_validator.py`)

Reject queries that exceed the following thresholds to prevent accidental or malicious heavy queries:

```python
COMPLEXITY_LIMITS = {
    "max_joins": 3,           # Max number of JOINs allowed
    "max_subqueries": 1,      # Max number of nested subqueries
    "max_where_conditions": 10,  # Max conditions in WHERE clause
}
```

Implementation: use `sqlparse` to count JOIN keywords, subquery depth, and AND/OR conditions. Reject with reason: `"Query too complex: exceeded {limit_name}"`.

---

### Layer 4 — Query Timeout (PostgreSQL level)

Set a hard timeout at the PostgreSQL session level before executing any query. This prevents runaway queries from blocking the database:

```python
# In postgres_client.py, before every query execution:
cursor.execute("SET statement_timeout = '5000';")  # 5 seconds max
cursor.execute(sql_query)
```

If the query exceeds 5 seconds, PostgreSQL raises `QueryCanceledError`. Catch it and return: `"Query timed out after 5 seconds"`.

---

### Layer 5 — Column-level Masking in Logs (`query_logger.py`)

All query results must be masked before writing to logs or including in the metadata PDF. The actual data passed to the LLM is never masked — only what gets logged.

```python
FIELDS_TO_MASK_IN_LOGS = ["email", "name"]

# Masking rules:
# email: carlos.mendoza@email.com  →  car***@***.com
# name:  Carlos Mendoza            →  C*** M***
```

Implementation: after query execution, iterate over result rows and apply masking only when writing to logs or the metadata PDF. The original unmasked data is passed to the LLM prompt as normal.

---

### Layer 6 — Prompt Injection Detection (`prompt_guard.py`)

Before passing any user input to the LangChain Agent, scan it for prompt injection patterns. This protects the Agent itself from being manipulated by malicious user input.

```python
INJECTION_PATTERNS = [
    r"ignore (previous|all|prior) instructions",
    r"forget (your|all|the) rules",
    r"now act as",
    r"you are now",
    r"disregard (your|all|the)",
    r"pretend (you are|to be)",
    r"do not follow",
    r"override (your|the) (instructions|rules|prompt)",
    r"system prompt",
    r"jailbreak",
    r"DAN",                    # "Do Anything Now" jailbreak
    r"\[INST\]",               # Llama instruction injection
    r"<\|im_start\|>",         # ChatML injection
]
```

If any pattern matches in the user's input, reject the request before it reaches the Agent with HTTP 400 and reason: `"Input contains disallowed content"`. Do not reveal which pattern was matched.

---

### Security Audit Logging (`query_logger.py`)

Every query attempt — whether allowed or rejected — must be logged to CloudWatch with the following structure:

```json
{
  "timestamp": "2026-03-04T10:23:00Z",
  "event_type": "sql_query",
  "status": "allowed | rejected",
  "rejection_layer": "table_whitelist | malicious_pattern | complexity | timeout | prompt_injection | null",
  "rejection_reason": "...",
  "generated_sql": "SELECT ... (masked)",
  "tables_accessed": ["customers", "flights"],
  "execution_time_ms": 120,
  "rows_returned": 42,
  "lambda_request_id": "..."
}
```

This log must be written for every query, including rejected ones. Rejected queries must never reach the database.

---

## Out of Scope (do not build)

- Frontend or UI of any kind
- Monday.com integration
- Authentication or authorization
- Multi-tenant support
