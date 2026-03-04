# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Run all tests
pytest tests/

# Run a single test file
pytest tests/test_text_to_sql.py -v

# Run a single test
pytest tests/test_text_to_sql.py::TestLayer2BlockedPatterns::test_clean_select_passes -v

# CDK synth (requires AWS credentials)
python app.py
cdk synth
```

## Architecture

### Request Flow

```
POST /campaign/generate (API Gateway)
  → campaign_handler.py
      → prompt_guard.py         (Layer 6: reject injection before agent)
      → run_marketing_agent()   (marketing_agent.py)
          → ReAct agent with 3 tools:
              → query_customer_database   (text_to_sql_tool.py)
              → search_campaign_documents (pdf_rag_tool.py)
              → analyze_csv_data          (csv_analyzer_tool.py)
          → _generate_campaign()  (campaign prompt → LLM → JSON)
      → generate_campaign_pdf()  (BytesIO, never to disk)
      → generate_metadata_pdf()  (BytesIO, never to disk)
      → upload_campaign_pdfs()   (S3 output bucket)
      → _log_campaign_to_db()    (generated_campaigns table, app user)
```

### Two-Phase Agent Design

The agent runs in two phases, not one:
1. **ReAct phase** — `_build_react_agent()` gathers data using the 3 tools (audience data, RAG context, CSV insights)
2. **Generation phase** — `_generate_campaign()` calls the structured `ChatPromptTemplate` with gathered data to produce campaign JSON

The LLM is called **twice** per request: once for data gathering (ReAct), once for content generation.

### Tool Metadata Pattern

Each tool module maintains a module-level `_tool_metadata` dict populated during execution. After the ReAct agent runs, `get_tool_metadata()` / `get_rag_metadata()` / `get_csv_metadata()` collect this data for the metadata PDF. **Always call `reset_*_metadata()` before each agent run** to avoid cross-request leakage (these dicts are module globals, they persist across Lambda warm invocations).

### Database Connections

`get_connection(user_role)` in `postgres_client.py` accepts `"readonly"` or `"app"`:
- `"readonly"` → `marketing_ai_readonly` — used **only** in `text_to_sql_tool.py`
- `"app"` → `marketing_ai_app` — used **only** in `campaign_handler.py` for writes

Passwords come from AWS Secrets Manager (cached at module level to avoid repeated API calls on warm Lambda). Required env vars: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_READONLY_SECRET_NAME`, `DB_APP_SECRET_NAME`.

### SQL Security (6 Layers)

Every LLM-generated SQL must pass all layers or is rejected immediately:
- **Layer 1** (`sql_validator.py`): table whitelist — only 6 tables allowed
- **Layer 2** (`sql_validator.py`): regex blocklist — DDL, UNION, comment injection, etc.
- **Layer 3** (`sql_validator.py`): complexity limits — max 3 JOINs, 1 subquery, 10 WHERE conditions
- **Layer 4** (`postgres_client.py`): `SET statement_timeout = '5000'` before every query
- **Layer 5** (`query_logger.py`): mask `email` and `name` fields in logs only (not in LLM input)
- **Layer 6** (`prompt_guard.py`): prompt injection detection on **user input** before it reaches the agent

### File Naming

`file_naming.py` derives 3-letter city codes from route strings:
- Multi-word cities use the **last word** (`San Salvador` → `SAL`, not `SAN`)
- Route splits on the **first hyphen** only (`Montreal-San Salvador` → origin=`Montreal`, dest=`San Salvador`)
- Duplicate keys get a numeric suffix: `campaign-MTL-SAL-20260304-2.pdf`

### PDF Generation

Both PDFs are generated entirely in memory via `BytesIO` + `reportlab` and uploaded directly to S3. Never write to disk — Lambda has no persistent storage.

### CSV Tool Input Format

The `analyze_csv_data` tool expects input as a colon-separated string: `"s3_key:question about the data"`.

## Key Files

| File | Purpose |
|------|---------|
| `src/handlers/campaign_handler.py` | Lambda entry point for `POST /campaign/generate` |
| `src/agents/marketing_agent.py` | Two-phase agent orchestration |
| `src/security/sql_validator.py` | SQL layers 1–3 (whitelist, patterns, complexity) |
| `src/db/postgres_client.py` | DB connections + layer 4 timeout enforcement |
| `src/utils/file_naming.py` | S3 key generation for campaign/metadata PDFs |
| `src/prompts/campaign_prompt.py` | Campaign `ChatPromptTemplate` with few-shot examples |
| `scripts/init_db.sql` | Full DB schema including `csv_files` table |
| `.env.example` | All required environment variable names |

## Environment Variables

See `.env.example`. Set these before running locally. AWS credentials must be configured separately (SDK picks them up from environment or IAM role).

## Ingestion Flow

`ingestion_handler.py` is triggered by S3 PUT events on the input bucket:
- `.pdf` → `pdf_ingester.py`: download → chunk (500 tokens, 50 overlap via `RecursiveCharacterTextSplitter`) → embed (Titan) → store in `document_embeddings`
- `.csv` → `csv_ingester.py`: download → validate → store metadata in `csv_files` table

## LangChain Version

Pinned to `langchain==0.1.20`. Do not upgrade without testing — the ReAct agent API changed significantly in 0.2.x.
