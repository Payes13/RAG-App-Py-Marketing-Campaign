# Recommended Reading Order

---

## 1. Foundation (Infrastructure & Config)

Start here to understand what AWS resources exist and how the app is wired up.

| #  | File | What it does |
|----|------|-------------|
| 1 | [.env.example](.env.example) | All environment variables the app needs |
| 2 | [scripts/init_db.sql](scripts/init_db.sql) | The database tables — understand the data model first |
| 3 | [requirements.txt](requirements.txt) | All Python dependencies (your `package.json`) |

---

## 2. Utilities (Shared Building Blocks)

These are used by almost everything else. Read them next.

| #  | File | What it does |
|----|------|-------------|
| 4 | [src/utils/bedrock_client.py](src/utils/bedrock_client.py) | Creates the LLM + embeddings clients (AWS Bedrock) |
| 5 | [src/utils/s3_client.py](src/utils/s3_client.py) | Upload/download files from S3 |
| 6 | [src/utils/file_naming.py](src/utils/file_naming.py) | Generates consistent PDF file names |
| 7 | [src/db/postgres_client.py](src/db/postgres_client.py) | Opens PostgreSQL connections with the right user |
| 8 | [src/db/vector_store.py](src/db/vector_store.py) | Stores/searches embeddings via pgvector |

---

## 3. Security (Runs Before Any Data Query)

| #  | File | What it does |
|----|------|-------------|
| 9 | [src/security/prompt_guard.py](src/security/prompt_guard.py) | Detects prompt injection in user input |
| 10 | [src/security/sql_validator.py](src/security/sql_validator.py) | 3-layer SQL validation before execution |
| 11 | [src/security/query_logger.py](src/security/query_logger.py) | Audit log for every query attempt |

---

## 4. Ingestion (How Data Gets Into the System)

| #  | File | What it does |
|----|------|-------------|
| 12 | [src/ingestion/pdf_ingester.py](src/ingestion/pdf_ingester.py) | Downloads PDF → chunks → embeds → stores |
| 13 | [src/ingestion/csv_ingester.py](src/ingestion/csv_ingester.py) | Downloads CSV → validates → stores metadata |

---

## 5. Agent Tools (The AI's Capabilities)

| #  | File | What it does |
|----|------|-------------|
| 14 | [src/tools/text_to_sql_tool.py](src/tools/text_to_sql_tool.py) | NL question → SQL → PostgreSQL results |
| 15 | [src/tools/pdf_rag_tool.py](src/tools/pdf_rag_tool.py) | NL question → vector search → relevant PDF chunks |
| 16 | [src/tools/csv_analyzer_tool.py](src/tools/csv_analyzer_tool.py) | Downloads CSV → pandas → LLM analysis |

---

## 6. Agent + Prompt (The AI Brain)

| #  | File | What it does |
|----|------|-------------|
| 17 | [src/prompts/campaign_prompt.py](src/prompts/campaign_prompt.py) | The prompt template with few-shot examples |
| 18 | [src/agents/marketing_agent.py](src/agents/marketing_agent.py) | The ReAct agent that orchestrates the 3 tools |

---

## 7. Output (What Gets Generated)

| #  | File | What it does |
|----|------|-------------|
| 19 | [src/output/pdf_generator.py](src/output/pdf_generator.py) | Builds the campaign + metadata PDFs in memory |
| 20 | [src/output/s3_uploader.py](src/output/s3_uploader.py) | Uploads the PDFs to S3 |

---

## 8. Entry Points (Where Requests Come In)

| #  | File | What it does |
|----|------|-------------|
| 21 | [src/handlers/campaign_handler.py](src/handlers/campaign_handler.py) | `POST /campaign/generate` — the main Lambda |
| 22 | [src/handlers/ingestion_handler.py](src/handlers/ingestion_handler.py) | S3 event trigger — runs when a file is uploaded |

---

## 9. Infrastructure (Deploy Last to Understand)

| #  | File | What it does |
|----|------|-------------|
| 23 | [cdk/marketing_ai_stack.py](cdk/marketing_ai_stack.py) | AWS resources (Lambda, S3, API Gateway) |
| 24 | [app.py](app.py) | CDK entry point — ties the stacks together |

---