# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# V4: Lazy loading — same result, leanest baseline
# The search tool definition is the leanest so far — valid values load on demand only when the taxonomy tool is called.
#
# Strip all inline context from descriptions. Move valid values,
# natural language mappings, and synonym guidance into the taxonomy tool.
# The LLM pays for context only when it needs it.
#
# Helpful errors and filter context still apply at the tool layer —
# those are response improvements, not description improvements.

import sys
from typing import Annotated, Literal, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

import mock_bff_sqlite as mock_bff

mcp = FastMCP(
    "AnyCompany Search",
    instructions="Search AnyCompany K-12 educational content library. Find lessons, assessments, activities, and videos across Math, Science, Literacy/ELA, Social Studies, and Spanish for grades K-12.",
    host="127.0.0.1",
    port=8004,
    stateless_http=True,
)
mock_bff.init(sys.argv[1] if len(sys.argv) > 1 else "anycompany_content.db")


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


@mcp.tool()
async def get_taxonomy(
    fields: Annotated[
        list[str],
        Field(
            description="Field names from the search_content tool to get info about (e.g. ['subject', 'resource_class'])."
        ),
    ],
) -> dict:
    """Get complete descriptions, valid values, and natural language mappings for fields in the search_content tool.
    The search_content tool exposes only short hints in its parameter descriptions — full guidance lives here.
    Pass parameter names from search_content (e.g. ['subject', 'resource_class', 'state_standard']) to get
    valid values and how to interpret common teacher language for those filters.
    Use this before searching to translate the user's natural-language request into precise filter values."""
    if not fields or not isinstance(fields, list):
        return {"error": "fields must be a non-empty list of field names"}
    fields = [str(f)[:100] for f in fields[:20]]
    return await mock_bff.get_taxonomy(fields=fields)


@mcp.tool()
async def search_content(
    topic: Annotated[
        Optional[str],
        Field(
            description="Search topic — concept from the user's question (e.g. 'fractions')."
        ),
    ] = None,
    subject: Annotated[
        Optional[str],
        Field(
            description='Subject area, e.g. "Math", "Science", "Literacy/ELA" (enum).'
        ),
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
            description='Content format, e.g. "Lesson", "Video", "Assessment" (enum).'
        ),
    ] = None,
    structure: Annotated[
        Optional[str],
        Field(description='Structure type, e.g. "Asset", "Sequence" (enum).'),
    ] = "Asset",
    state_standard: Annotated[
        Optional[str],
        Field(
            description='Standards alignment code, e.g. "TX-TEKS", "CA-CCSS" (enum).'
        ),
    ] = None,
    language: Annotated[
        Optional[str], Field(description="Content language code (enum).")
    ] = "en",
    resource_class: Annotated[
        Optional[str],
        Field(
            description='Document classification, e.g. "Teacher Support", "Student Resource" (enum).'
        ),
    ] = "Student Resource",
    file_type: Annotated[
        Optional[str],
        Field(description='Technical file format, e.g. "PDF", "HTML" (enum).'),
    ] = None,
    product_line: Annotated[
        Optional[str], Field(description="Product or program name (enum).")
    ] = None,
    state_version: Annotated[
        Optional[str], Field(description="State-specific edition code (enum).")
    ] = None,
    detail: Annotated[
        Optional[Literal["concise", "detailed"]],
        Field(
            description="Use concise for broad searches and browsing. Use detailed only for a specific resource when full metadata is needed."
        ),
    ] = "concise",
) -> dict:
    """Search AnyCompany K-12 content. All parameters except topic accept only enumerated values.
    Call get_taxonomy() with parameter names to get valid values before searching.
    `topic` is a fuzzy keyword match; all other parameters are strict filters.
    Examples in field descriptions are accurate but not comprehensive — always confirm via get_taxonomy.
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
    if not node_id or len(node_id) > 50:
        return {"error": "node_id must be a non-empty string of up to 50 characters"}
    return await mock_bff.get_resource_detail(node_id)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
