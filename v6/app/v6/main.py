# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# V6: Strands agent behind MCP — you own the LLM, behavior is testable
#
# Single MCP tool exposed to the client. Behind it, a Strands agent with
# its own model, system prompt, and internal tools handles decomposition,
# synonym translation, taxonomy lookup, and multi-step reasoning.
#
# Hosted via AgentCore CLI (MCP protocol).
# The agent is created at module level so conversation history persists
# across calls within the same process.

import os

from mcp.server.fastmcp import FastMCP
from model.load import load_model
from strands import Agent, tool
from strands.handlers.callback_handler import PrintingCallbackHandler

import mock_bff_sqlite as mock_bff

mock_bff.init("anycompany_content.db")

mcp = FastMCP(
    "AnyCompany Search Agent",
    instructions="Search AnyCompany K-12 educational content library. Find lessons, assessments, activities, and videos across Math, Science, Literacy/ELA, Social Studies, and Spanish for grades K-12.",
    host="127.0.0.1",
    stateless_http=True,
)

SYSTEM_PROMPT = """You are an expert at searching the AnyCompany K-12 educational content library. Teachers ask you for lessons, assessments, activities, and videos across Math, Science, Literacy/ELA, Social Studies, and Spanish for grades K-12. Your answers come from the search tools — not from your own knowledge.

## Instructions
For every search question:

1. Identify which filter fields might be relevant to this question (subject, format, grade, state_standard, resource_class, etc.). Translate teacher language: 'worksheet' → Activity, 'quiz' → Assessment, '7th graders' → grade 7. Translate synonyms: 'dividing' → search for 'fraction' or 'division' in Math. If a state is mentioned (e.g. 'Texas'), use the state_standard filter (TX-TEKS).

2. Before passing a value for any enum field, make sure you have called get_taxonomy to get the possible values for that field. This applies to every search call, including retries. Enum fields are strict filters — values that don't exactly match return zero results.

3. If search returns 0 results, broaden by removing one filter at a time. DO NOT change values to ones not in the taxonomy.

## Response Format
Return the top 5 results by default, listed in the order the search returned them. Include all fields from the search results for each item. If the user asks for more or fewer, follow their lead. For detail requests on a single resource, return complete information. Follow explicit instructions in the question. Never return raw JSON.

## Guardrails
- DO NOT pass enum values you haven't confirmed through get_taxonomy. They are case-sensitive and specific.
- DO NOT invent subject names or filter values.
- DO NOT put format names (Lesson, Activity) in the topic field. Use the format parameter.
- Never invent, guess, or hallucinate content titles, taxonomy values, or metadata.
- If a tool returns no results, say so. Do not make up alternatives.
- If a tool returns an error, report the error and any guidance it provides to the user."""


def _wrap_response(defaults_applied, results):
    """Wrap a BFF response with helpful messaging.
    Only include defaults_applied when defaults were actually used (the agent didn't override them)."""
    base = {}
    if defaults_applied:
        base["defaults_applied"] = defaults_applied
    if isinstance(results, dict) and "error" in results:
        return {
            "error": "Search too broad. Provide at least 2 of: topic, subject, grade range, format, structure, state_standard, resource_class, or other filters."
        }
    if not results:
        base["result_count"] = 0
        base["results"] = []
        base["note"] = (
            "No results found. Did the user want to expand the search from these filters?"
        )
        return base
    base["result_count"] = len(results)
    base["results"] = results
    return base


@tool
async def search_content(
    topic: str = None,
    subject: str = None,
    min_grade: int = None,
    max_grade: int = None,
    format: str = None,
    structure: str = "Asset",
    state_standard: str = None,
    language: str = "en",
    resource_class: str = "Student Resource",
    file_type: str = None,
    product_line: str = None,
    state_version: str = None,
) -> dict:
    """Search AnyCompany K-12 content. All parameters except topic accept only enumerated values.
    Call get_taxonomy() with parameter names to get valid values before searching.
    `topic` is a fuzzy keyword match; all other parameters are strict filters.
    Examples in field descriptions are accurate but not comprehensive — always confirm via get_taxonomy.
    Sensible defaults applied (structure='Asset', resource_class='Student Resource', language='en'). Response includes defaults_applied when defaults were used so you can see what was filtered. Override defaults explicitly for broader content.

    Args:
        topic: Search concept from the user's question.
        subject: Subject area, e.g. "Math", "Science", "Spanish" (enum).
        min_grade: Lowest grade 0-12 (0=K).
        max_grade: Highest grade 0-12.
        format: Content format, e.g. "Lesson", "Video", "Assessment" (enum).
        structure: Structure type, e.g. "Asset", "Sequence" (enum).
        state_standard: Standards alignment code, e.g. "TX-TEKS", "CA-CCSS" (enum).
        language: Content language code (enum).
        resource_class: Document classification, e.g. "Teacher Support", "Student Resource" (enum).
        file_type: Technical file format, e.g. "PDF", "HTML" (enum).
        product_line: Product or program name (enum).
        state_version: State-specific edition code (enum).
    """
    defaults_applied = {}
    if structure == "Asset":
        defaults_applied["structure"] = "Asset"
    if resource_class == "Student Resource":
        defaults_applied["resource_class"] = "Student Resource"
    if language == "en":
        defaults_applied["language"] = "en"

    results = await mock_bff.search_content(
        keyword=topic,
        discipline=subject,
        grade_from=min_grade,
        grade_to=max_grade,
        media_type=format,
        content_type=structure,
        standards_alignment=state_standard,
        language=language,
        content_bucket=resource_class,
        file_type=file_type,
        catalog_group=product_line,
        version_state=state_version,
        response_format="concise",
    )
    return _wrap_response(defaults_applied, results)


@tool
async def get_taxonomy(fields: list[str]) -> dict:
    """Get complete descriptions, valid values, and natural-language mappings for fields in search_content.
    Pass parameter names from search_content (e.g. ['subject', 'resource_class', 'state_standard']) to get
    valid values and how to interpret common teacher language for those filters.
    Use this before searching to translate the user's natural-language request into precise filter values."""
    if not fields or not isinstance(fields, list):
        return {"error": "fields must be a non-empty list of field names"}
    fields = [str(f)[:100] for f in fields[:20]]
    return await mock_bff.get_taxonomy(fields=fields)


@tool
async def get_resource_detail(node_id: str) -> dict:
    """Get full details for a single resource by ID. Use after searching to get complete metadata."""
    if not node_id or len(node_id) > 50:
        return {"error": "node_id must be a non-empty string of up to 50 characters"}
    return await mock_bff.get_resource_detail(node_id)


# Module-level agent — persists conversation history across calls
import json as _json

from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent
from strands.plugins import Plugin, hook


class LoggingPlugin(Plugin):
    """Logs tool calls with inputs and completion to stdout for debugging."""

    name = "logging-plugin"

    @hook
    def log_before_tool(self, event: BeforeToolCallEvent) -> None:
        print(f"\n🔧 Calling: {event.tool_use['name']}", flush=True)
        print(f"   Input: {_json.dumps(event.tool_use['input'], indent=2)}", flush=True)

    @hook
    def log_after_tool(self, event: AfterToolCallEvent) -> None:
        result_str = _json.dumps(event.result, indent=2, default=str)[:500]
        print(f"   Result: {result_str}", flush=True)
        print(f"   ✓ {event.tool_use['name']} complete", flush=True)


agent = Agent(
    model=load_model(),
    tools=[search_content, get_taxonomy, get_resource_detail],
    system_prompt=SYSTEM_PROMPT,
    plugins=[LoggingPlugin()],
    callback_handler=PrintingCallbackHandler(),
)


@mcp.tool()
async def agentic_search_content(question: str) -> str:
    """Search AnyCompany K-12 educational content — lessons, assessments, activities, videos, and adaptive homework
    across Math, Science, Literacy/ELA, Social Studies, and Spanish for grades K-12.
    Ask in natural language. Handles topic extraction, synonym translation, grade level
    interpretation, and standards filtering (TEKS, CCSS, NGSSS, etc.) automatically.
    You can also ask what content is available, what subjects or standards are supported,
    or how to narrow a search."""
    if not question or not isinstance(question, str):
        return "Error: question must be a non-empty string"
    if len(question) > 2000:
        return "Error: question exceeds maximum length of 2000 characters"
    # In local dev, reset conversation history per call to simulate session isolation
    # (AgentCore Runtime handles this via per-session microVMs in production)
    if os.environ.get("LOCAL_DEV"):
        agent.messages.clear()
    result = await agent.invoke_async(question)
    return " ".join([c["text"] for c in result.message["content"] if "text" in c])


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
