# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# V5: LLM-assisted introspection — add intelligence without going full agentic
# Interpretation happens server-side, so client context stays lean — the tradeoff is inference cost (you pay for the introspect model call).
#
# V5 takes back some control: instead of giving the calling LLM raw taxonomy
# values to interpret (V4's get_taxonomy), V5 has its own LLM interpret the
# teacher's question and recommend specific filter values with rationale.
#
# Removes get_taxonomy — introspect_query now provides both the interpretation
# AND the rationale that taxonomy used to surface.
#
# Tools exposed:
#   introspect_query — recommends filter values for a teacher's question
#   search_content — the actual search
#   get_resource_detail — drill-down on a specific resource
#
# Dependency: boto3 (already in sandbox)

import json
import re
import sys
from typing import Annotated, Literal, Optional

import boto3
from mcp.server.fastmcp import FastMCP
from pydantic import Field

import mock_bff_sqlite as mock_bff

mcp = FastMCP(
    "AnyCompany Search",
    instructions="Search AnyCompany K-12 educational content library. Find lessons, assessments, activities, and videos across Math, Science, Literacy/ELA, Social Studies, and Spanish for grades K-12.",
    host="127.0.0.1",
    port=8005,
    stateless_http=True,
)
mock_bff.init(sys.argv[1] if len(sys.argv) > 1 else "anycompany_content.db")

bedrock = boto3.client("bedrock-runtime", region_name="us-west-2")

INTROSPECT_PROMPT = """You are a AnyCompany content search expert. Given a teacher's question,
analyze it and recommend specific search parameters for the search_content tool.

Available search filters and their valid values:
{taxonomy}

Return a JSON object with two top-level keys:
- "filters": a dict of recommended filter values to pass to search_content
- "rationale": a dict explaining why each non-trivial filter value was chosen (skip obvious ones like topic extraction)

Example:
{{
  "filters": {{"topic": "fractions", "subject": "Math", "min_grade": 7, "max_grade": 7, "format": "Assessment"}},
  "rationale": {{
    "subject": "Topic 'fractions' is a Math concept",
    "format": "'quiz' or 'test' maps to format='Assessment'"
  }}
}}

Always include in filters:
- topic: the core search term
- subject: infer from context when the topic strongly implies one subject. "fractions" → Math, "civil war" → Social Studies, "photosynthesis" → Science, "grammar" → Literacy/ELA. If the topic could span multiple subjects (e.g. "climate change"), omit subject for broader results.
- min_grade and max_grade: extract from the question
- format: if the teacher mentions a content type

Translate synonyms and informal language:
- "worksheet" → format: "Activity"
- "quiz" or "test" → format: "Assessment"
- For educational concepts in search terms, always keep the user's word first and add the 2 most common alternative terms, comma-separated. Example: user says "dividing" → topic: "dividing,division,quotient".
- "TEKS" or "Texas standards" → state_standard: "TX-TEKS"
- Match taxonomy case exactly.

Return only the JSON object, no markdown formatting.
"""


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


async def _get_full_taxonomy():
    """Get all taxonomy context for the introspect prompt — uses tool-level field names."""
    all_fields = [
        "subject",
        "format",
        "structure",
        "file_type",
        "resource_class",
        "state_standard",
        "state_version",
        "language",
        "product_line",
        "topic",
        "grade",
    ]
    return await mock_bff.get_taxonomy(fields=all_fields)


def _parse_introspect_response(text: str) -> dict:
    """Parse Amazon Bedrock response, handling markdown-wrapped JSON if present."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {"error": "Failed to parse introspect response", "raw": text}


@mcp.tool()
async def introspect_query(
    question: Annotated[
        str, Field(description="The teacher's original question in natural language.")
    ],
) -> dict:
    """Analyze a teacher's question and recommend search parameters for search_content.
    Uses an LLM trained on AnyCompany content vocabulary to translate natural language into
    precise filter values. Returns recommended filters and a rationale for non-trivial choices.
    Pass the returned filter values to search_content exactly as formatted — commas and casing
    are part of the search syntax, not cosmetic formatting. Use the rationale to explain to
    the user why specific filters were chosen.
    Use this when the user's question requires a search; for general advice or non-search
    questions, answer directly without calling this tool."""
    if not question or not isinstance(question, str):
        return {"error": "question must be a non-empty string"}
    if len(question) > 1000:
        return {"error": "question exceeds maximum length of 1000 characters"}
    taxonomy = await _get_full_taxonomy()
    prompt = INTROSPECT_PROMPT.format(taxonomy=json.dumps(taxonomy, indent=2))

    response = bedrock.converse(
        modelId="us.amazon.nova-2-lite-v1:0",
        messages=[
            {"role": "user", "content": [{"text": f"Teacher's question: {question}"}]}
        ],
        system=[{"text": prompt}],
    )
    raw_text = response["output"]["message"]["content"][0]["text"]
    return _parse_introspect_response(raw_text)


@mcp.tool()
async def search_content(
    topic: Annotated[
        Optional[str],
        Field(
            description="Search topic — supports comma-separated terms for OR matching (e.g. 'dividing,division,fractions'). Pass introspect_query values exactly as formatted."
        ),
    ] = None,
    subject: Annotated[
        Optional[str],
        Field(description="Subject area (Math, Science, Literacy/ELA, etc.)."),
    ] = None,
    min_grade: Annotated[
        Optional[int], Field(description="Lowest grade 0-12 (0=K).")
    ] = None,
    max_grade: Annotated[
        Optional[int], Field(description="Highest grade 0-12.")
    ] = None,
    format: Annotated[
        Optional[str],
        Field(
            description="Content format (Lesson, Video, Assessment, Activity, etc.)."
        ),
    ] = None,
    structure: Annotated[
        Optional[str],
        Field(description="Structure type (Asset, Sequence, Collection, Program)."),
    ] = "Asset",
    state_standard: Annotated[
        Optional[str], Field(description="Standards alignment code (e.g. TX-TEKS).")
    ] = None,
    language: Annotated[
        Optional[str], Field(description="Content language code.")
    ] = "en",
    resource_class: Annotated[
        Optional[str],
        Field(
            description="Resource classification (Student Resource, Teacher Support, Program Guide)."
        ),
    ] = "Student Resource",
    file_type: Annotated[
        Optional[str], Field(description="Technical format (PDF, HTML, etc.).")
    ] = None,
    product_line: Annotated[
        Optional[str], Field(description="Product or program name.")
    ] = None,
    state_version: Annotated[
        Optional[str], Field(description="State-specific edition code.")
    ] = None,
    detail: Annotated[
        Optional[Literal["concise", "detailed"]],
        Field(
            description="Use concise for broad searches and browsing. Use detailed only for a specific resource when full metadata is needed."
        ),
    ] = "concise",
) -> dict:
    """Search AnyCompany K-12 educational content — lessons, assessments, activities, videos, and more.
    Returns matching content with title, subject, grade range, and format.
    Searches metadata only — does not search full content text.
    `topic` is a fuzzy search; all other parameters are strict filters.
    Parameter descriptions here are intentionally short hints — call introspect_query() for LLM-recommended values translated from the teacher's natural-language question.
    Sensible defaults are applied (structure='Asset', resource_class='Student Resource', language='en'). The response includes defaults_applied when defaults were used so you can see what was filtered. Override defaults explicitly if the user wants broader content."""
    defaults_applied = {}
    if structure == "Asset":
        defaults_applied["structure"] = "Asset"
    if resource_class == "Student Resource":
        defaults_applied["resource_class"] = "Student Resource"
    if language == "en":
        defaults_applied["language"] = "en"
    if detail == "concise":
        defaults_applied["detail"] = "concise"

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
        response_format=detail,
    )
    return _wrap_response(defaults_applied, results)


@mcp.tool()
async def get_resource_detail(
    node_id: Annotated[str, Field(description="Resource ID from search results.")],
) -> dict:
    """Get full metadata for a single resource by its node_id.
    Use after searching to get complete details including keywords, standards,
    catalog group, and other fields not returned in search results."""
    return await mock_bff.get_resource_detail(node_id)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
