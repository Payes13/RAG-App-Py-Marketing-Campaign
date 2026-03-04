"""
Tool 3: CSV Analyzer — downloads a CSV from S3 and answers questions about it.

Input format: "s3_key:question"
Example:      "audiences/latam_families_2024.csv:What is the average age?"
"""
import io
import json
import logging
import os

import pandas as pd
from langchain.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage

from src.utils.bedrock_client import get_llm
from src.utils.s3_client import download_file

logger = logging.getLogger(__name__)

# Shared metadata collector
_csv_metadata: dict = {
    "csv_files_used": [],
}


def reset_csv_metadata():
    _csv_metadata["csv_files_used"] = []


def get_csv_metadata() -> dict:
    return _csv_metadata


@tool
def analyze_csv_data(input_str: str) -> str:
    """Use this tool when you need to analyze audience data, customer segments,
    or metrics stored in CSV files in S3.
    Input format: 's3_key:question about the data'
    Example: 'audiences/latam_families_2024.csv:What is the average age of customers?'"""
    bucket = os.environ.get("S3_INPUT_BUCKET_NAME", "marketing-ai-documents")

    # Parse input
    if ":" not in input_str:
        return "Invalid input. Use format: 's3_key:question'"

    s3_key, question = input_str.split(":", 1)
    s3_key = s3_key.strip()
    question = question.strip()

    try:
        # Download and parse CSV
        csv_bytes = download_file(bucket, s3_key)
        df = pd.read_csv(io.BytesIO(csv_bytes))

        logger.info(json.dumps({
            "event": "csv_loaded",
            "key": s3_key,
            "rows": len(df),
            "columns": df.columns.tolist(),
        }))

        # Track metadata
        if s3_key not in _csv_metadata["csv_files_used"]:
            _csv_metadata["csv_files_used"].append(s3_key)

        # Prepare context for LLM
        sample_data = df.head(5).to_csv(index=False)
        column_info = {col: str(df[col].dtype) for col in df.columns}
        summary_stats = df.describe(include="all").to_string()

        system_prompt = f"""You are a data analyst. Answer the user's question about the CSV data.
Be concise and factual. Return only the answer, no preamble.

CSV COLUMNS AND TYPES:
{json.dumps(column_info, indent=2)}

SAMPLE DATA (first 5 rows):
{sample_data}

SUMMARY STATISTICS:
{summary_stats}"""

        llm = get_llm(max_tokens=512)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=question),
        ]
        response = llm.invoke(messages)
        answer = response.content.strip()

        logger.info(json.dumps({
            "event": "csv_analysis_complete",
            "key": s3_key,
            "question": question,
        }))

        return answer

    except Exception as exc:
        logger.error(json.dumps({"event": "csv_tool_error", "key": s3_key, "error": str(exc)}))
        return f"Error analyzing CSV '{s3_key}': {exc}"
