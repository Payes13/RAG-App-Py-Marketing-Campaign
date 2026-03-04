"""
LangChain ReAct Agent for marketing campaign generation.

Orchestrates three tools (SQL, RAG, CSV), gathers audience and marketing context,
then generates a campaign using the structured prompt template.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any

from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate

from src.prompts.campaign_prompt import get_campaign_prompt
from src.tools.csv_analyzer_tool import analyze_csv_data, get_csv_metadata, reset_csv_metadata
from src.tools.pdf_rag_tool import get_rag_metadata, reset_rag_metadata, search_campaign_documents
from src.tools.text_to_sql_tool import get_tool_metadata, query_customer_database, reset_tool_metadata
from src.utils.bedrock_client import get_llm

logger = logging.getLogger(__name__)

REACT_PROMPT_TEMPLATE = """You are a marketing intelligence agent for an airline.
Your goal is to gather comprehensive data to support the creation of a {campaign_type} campaign.

Route: {route}
Target audience: {audience_description}
Language: {language}
Tone: {tone}
CSV file (if provided): {csv_file_key}

Use the available tools to:
1. Query the customer database for demographic data, flight history, and audience size for this route
2. Search PDF documents for context about previous campaigns and destination information
3. If a CSV file key is provided, analyze the CSV data for additional audience insights

Gather enough information to write a compelling campaign.
After gathering data, provide a concise summary of:
- The audience (size, demographics, preferences)
- Relevant marketing context from documents
- Key insights from CSV analysis (if applicable)

{tools}

{tool_names}

Use this format:
Thought: I need to gather data about the audience and context
Action: [tool name]
Action Input: [tool input]
Observation: [result]
... (repeat as needed)
Thought: I now have enough data to summarize
Final Answer: [your data summary]

{agent_scratchpad}"""


def _build_react_agent():
    llm = get_llm(max_tokens=2048)
    tools = [query_customer_database, search_campaign_documents, analyze_csv_data]

    prompt = PromptTemplate.from_template(REACT_PROMPT_TEMPLATE)
    agent = create_react_agent(llm, tools, prompt)
    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=10,
        return_intermediate_steps=True,
    )


def _generate_campaign(
    audience_data: str,
    marketing_context: str,
    route: str,
    audience_description: str,
    campaign_type: str,
    language: str,
    tone: str,
) -> dict:
    """Call the LLM with the structured campaign prompt and parse the JSON response."""
    llm = get_llm(max_tokens=1024)
    prompt = get_campaign_prompt()
    chain = prompt | llm

    response = chain.invoke({
        "audience_data": audience_data or "No structured audience data available.",
        "marketing_context": marketing_context or "No previous campaign documents found.",
        "route": route,
        "audience_description": audience_description,
        "campaign_type": campaign_type,
        "language": language,
        "tone": tone,
    })

    content = response.content.strip()

    # Strip markdown code block if present
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if len(lines) > 2 else content

    try:
        campaign = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error(json.dumps({"event": "campaign_json_parse_error", "error": str(exc),
                                  "raw_content": content[:500]}))
        raise ValueError(f"LLM did not return valid JSON: {exc}") from exc

    required_keys = {"subject_line", "preview_text", "body", "cta"}
    missing = required_keys - set(campaign.keys())
    if missing:
        raise ValueError(f"Campaign JSON is missing required keys: {missing}")

    return campaign


def run_marketing_agent(
    route: str,
    audience_description: str,
    campaign_type: str,
    language: str,
    tone: str,
    csv_file_key: str = "",
    request_id: str = "unknown",
) -> dict[str, Any]:
    """
    Main entry point for campaign generation.

    1. Runs the ReAct agent to gather audience data and marketing context.
    2. Generates campaign content via the structured LLM prompt.
    3. Returns a dict with the campaign and full metadata for the metadata PDF.
    """
    logger.info(json.dumps({
        "event": "agent_start",
        "route": route,
        "audience_description": audience_description,
        "campaign_type": campaign_type,
        "language": language,
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }))

    # Reset tool metadata collectors
    reset_tool_metadata()
    reset_rag_metadata()
    reset_csv_metadata()

    # Phase 1: Gather data with ReAct agent
    agent_executor = _build_react_agent()
    try:
        agent_result = agent_executor.invoke({
            "route": route,
            "audience_description": audience_description,
            "campaign_type": campaign_type,
            "language": language,
            "tone": tone,
            "csv_file_key": csv_file_key or "None provided",
        })
        audience_data = agent_result.get("output", "")
    except Exception as exc:
        logger.warning(json.dumps({"event": "agent_partial_failure", "error": str(exc)}))
        audience_data = f"Agent encountered an error: {exc}"

    # Collect RAG context separately
    rag_meta = get_rag_metadata()
    marketing_context = "\n\n".join(
        chunk.get("content_excerpt", "") for chunk in rag_meta.get("rag_chunks", [])
    )

    logger.info(json.dumps({
        "event": "agent_data_gathered",
        "audience_data_length": len(audience_data),
        "marketing_context_length": len(marketing_context),
    }))

    # Phase 2: Generate campaign content
    campaign = _generate_campaign(
        audience_data=audience_data,
        marketing_context=marketing_context,
        route=route,
        audience_description=audience_description,
        campaign_type=campaign_type,
        language=language,
        tone=tone,
    )

    # Collect all metadata
    sql_meta = get_tool_metadata()
    csv_meta = get_csv_metadata()

    metadata = {
        "route": route,
        "audience_description": audience_description,
        "campaign_type": campaign_type,
        "language": language,
        "tone": tone,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
        "sql_queries": sql_meta.get("sql_queries", []),
        "tables_accessed": sql_meta.get("tables_accessed", []),
        "csv_files_used": csv_meta.get("csv_files_used", []),
        "rag_chunks": rag_meta.get("rag_chunks", []),
        "audience_data": audience_data,
        "marketing_context": marketing_context,
        "tokens_used": 0,  # Token counting requires response metadata; set to 0 as default
    }

    logger.info(json.dumps({
        "event": "campaign_generation_complete",
        "route": route,
        "request_id": request_id,
    }))

    return {"campaign": campaign, "metadata": metadata}
