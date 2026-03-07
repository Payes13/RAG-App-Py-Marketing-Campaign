"""
__init__.py — why it exists and why it's empty

Python needs it to treat a folder as a package (importable module). Without it, from src.agents.marketing_agent import run_marketing_agent would fail with ModuleNotFoundError.

It's empty because there's nothing to export at the package level — it's just a marker file saying "this folder is a Python package". Every src/*/ folder in this project has one for the same reason.

// No TS equivalent — in TS/Node, any folder with an index.ts acts as a package.
// Python needs the __init__.py file explicitly.
"""

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

# It assembles and returns a fully configured, ready-to-run AI agent. Three things get built and wired together: 
# 1. the brain (Claude) -> llm = get_llm(max_tokens=2048)
# 2. the hands (3 functions it can call) -> tools = [...]  
# 3. the instructions (ReAct loop format) -> prompt = PromptTemplate(...)
# agent = create_react_agent(llm, tools, prompt)   # wire them into an agent
# return AgentExecutor(agent=agent, tools=tools, ...)  # wrap with a runner
def _build_react_agent():
    llm = get_llm(max_tokens=2048)
    # search_campaign_documents -> PDF RAG tool
    # The agent decides which tools to call and how many times — that's what "ReAct" means (Reason + Act). CSV is conditional (if a CSV file key is provided), but SQL and PDF RAG always run.
    # WE ARE PASSING REFERENCES (LIKE A POINTER) OF THE TOOLS NOT CALLING THEM
    tools = [query_customer_database, search_campaign_documents, analyze_csv_data]

    # LangChain's create_react_agent and AgentExecutor expect a list because the agent needs to know all available tools upfront — it reads their names and descriptions to decide which one to call at each step. A list is just the container format LangChain requires. LangChain holds onto those references and calls them itself later, at the right moment during the ReAct loop.
    prompt = PromptTemplate.from_template(REACT_PROMPT_TEMPLATE)
    agent = create_react_agent(llm, tools, prompt)
    """
    Why return AgentExecutor and not agent?

    create_react_agent produces the decision-making logic — the thing that reads the prompt and decides "call this tool with this input." But it can't run itself.

    AgentExecutor is the runner that actually executes the loop:

    while not done:
        1. Ask the agent: "what should I do next?"
        2. Agent says: "call query_customer_database with question X"
        3. AgentExecutor calls the tool, gets the result
        4. Feeds the result back to the agent
        5. Repeat until agent says "Final Answer"

    // TypeScript mental model
    const agent = buildDecisionLogic(llm, tools, prompt)  // just logic, can't run itself

    const agentExecutor = new AgentExecutor({
        agent,
        tools,
        maxIterations: 10,       // stop after 10 tool calls max (prevents infinite loop)
        handleParsingErrors: true // if LLM output is malformed, retry instead of crash
    })

    // Only the executor can actually be run:
    agentExecutor.invoke({ route: "Montreal-San Salvador", ... })

    agent = the brain. AgentExecutor = the body that runs the brain in a loop. You need both.
    """
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
    """
    Why it's reset in marketing_agent.py and not inside the tool itself

    Because _tool_metadata is a module-level global — it persists between Lambda warm invocations. If request 1 ran 3 SQL queries, those 3 are still sitting in the list when request 2 arrives.

    The reset happens at the start of each request in marketing_agent.py:


    # marketing_agent.py:145-147
    reset_tool_metadata()   # wipe SQL queries from previous request

    It's done in marketing_agent.py and not inside the tool because the agent can call each tool multiple times per request. If the reset happened inside query_customer_database, it would wipe the previous call's data on every new call — you'd only ever see the last query, not all of them.
    """
    reset_tool_metadata()
    reset_rag_metadata()
    reset_csv_metadata()

    # Phase 1: Gather data with ReAct agent
    """
    THEY BASICALLY BUILT A REACT AGENT THAT CAN CALL TOOLS TO GATHER DATA.
    ReAct = Reason + Act. The LLM loops:

    Reason — "I need customer demographics for this route"
    Act — call query_customer_database
    Observe — read the result
    Reason again — "now I need PDF context"
    Act — call search_campaign_documents
    ... repeat until it decides it has enough, then outputs "Final Answer"
    The LLM decides which tool, what input, and how many times — all based on the prompt instructions and what the tools return. The code just builds the setup and fires .invoke(). The agent figures out the rest itself.

    Now adding agent_result to CODE_SAMPLES.md:
    """

    """
    REASON QUESTIONS EXPLAIN:
    The programmer didn't hardcode the questions — the LLM generates them on its own, based on two things:

    1. The goal given in the prompt

    Looking at marketing_agent.py:23-38, the REACT_PROMPT_TEMPLATE tells the LLM:

    Your goal is to gather comprehensive data to support the creation of a {campaign_type} campaign.
    Route: {route}
    Target audience: {audience_description}

    Use the available tools to:
    1. Query the customer database for demographic data, flight history, and audience size
    2. Search PDF documents for context about previous campaigns
    3. If a CSV file key is provided, analyze the CSV data
    That's the LLM's mission statement. It knows what it needs to accomplish.

    2. The tool descriptions (the docstrings)

    The LLM also sees the tool menu:

    query_customer_database: Use this tool when you need to find customer audiences, flight history, demographics...
    search_campaign_documents: Use this tool when you need previous campaign examples, destination guides...
    analyze_csv_data: Use this tool when you need to analyze booking data from a CSV file...

    From those two inputs, the LLM figures out the "Thought" reasoning entirely by itself:

    Thought: My goal is a promotional campaign for Montreal-San Salvador.
         The prompt says to start with customer demographics.
         The tool "query_customer_database" is for demographics.
         → I'll call that first with a relevant question.
    The programmer never wrote that reasoning — the LLM produced it. The programmer only wrote:

    What the goal is (the prompt template)
    What each tool does (the docstrings)
    What format to follow (the Thought/Action/Observation loop)
    The LLM fills in everything in between. That's the whole point of an agent vs. a hardcoded pipeline.
    """
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
    # The ReAct LLM got the full chunk text and already synthesized it into audience_data (the output string). marketing_context is just a secondary reference passed to the generation prompt — the real marketing intelligence is already baked into audience_data from Phase 1. The 200-char excerpts in marketing_context are more like source citations than the actual content.
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
