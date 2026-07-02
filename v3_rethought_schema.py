# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# V3: Rethought schema — same knowledge as V2, tighter structure
# The definition is smaller than V2 because LLM-friendly names and enums do the work that verbose descriptions did before.
#
# Same rich context as V2 but:
# - LLM-friendly parameter names (subject not discipline, format not media_type)
# - Shorter descriptions — the name itself communicates intent
# - Literal enums constrain valid values through schema
# - Sensible defaults (resource_class, structure, language, detail)
# - Thin translation layer maps to BFF field names
# - Added get_resource_detail tool for drill-down
# - Added detail enum (concise vs detailed response)
# - Helpful errors and filter context at tool layer
#
# Note: The enums add token bloat to V3's definition — this intentionally
# sets up V4's motivation (lazy-loaded taxonomy instead of inline enums).

import sys
from typing import Annotated, Literal, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

import mock_bff_sqlite as mock_bff

mcp = FastMCP(
    "AnyCompany Search",
    instructions="Search AnyCompany K-12 educational content library. Find lessons, assessments, activities, and videos across Math, Science, Literacy/ELA, Social Studies, and Spanish for grades K-12.",
    host="127.0.0.1",
    port=8003,
    stateless_http=True,
)
mock_bff.init(sys.argv[1] if len(sys.argv) > 1 else "anycompany_content.db")


def _build_filters_applied(**params):
    """Build a filter context dict showing what filters were applied to the search."""
    return {k: v for k, v in params.items() if v is not None}


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
async def search_content(
    topic: Annotated[
        Optional[str],
        Field(
            description=(
                "Core search topic — extract the specific concept from the user's question. "
                "Matches against title, keywords, and content index using substring search. "
                "Good: 'fractions', 'civil war', 'climate'. Use a single concept, not a full sentence. "
                "Synonyms: 'dividing'/'quotient' relate to fractions/division. 'multiply'/'product' relate to multiplication."
            )
        ),
    ] = None,
    subject: Annotated[
        Optional[
            Literal[
                "Math",
                "Science",
                "Literacy/ELA",
                "Social Studies",
                "Spanish",
                "Art",
                "Music",
                "Physical Education",
                "Health",
                "Computer Science",
            ]
        ],
        Field(
            description=(
                "'reading'/'english'/'language arts' → Literacy/ELA. 'history'/'geography'/'civics' → Social Studies. "
                "'biology'/'chemistry'/'physics' → Science. Omitting returns all — usually too broad."
            )
        ),
    ] = None,
    min_grade: Annotated[
        Optional[Literal[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]],
        Field(
            description=(
                "Lowest grade 0-12 (0=K). '7th graders' → 7. 'middle school' → 6. 'elementary' → 0. "
                "'high school' → 9. 'upper elementary' → 3. Always set with max_grade."
            )
        ),
    ] = None,
    max_grade: Annotated[
        Optional[Literal[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]],
        Field(
            description=(
                "Highest grade 0-12. Same as min_grade for single grade. "
                "'middle school' → 8. 'elementary' → 5. 'high school' → 12."
            )
        ),
    ] = None,
    format: Annotated[
        Optional[
            Literal["Lesson", "Assessment", "Activity", "Video", "Adaptive Homework"]
        ],
        Field(
            description=(
                "'worksheet'/'handout'/'printable' → Activity. 'quiz'/'test'/'exam' → Assessment. "
                "'homework'/'adaptive practice' → Adaptive Homework. 'lecture'/'instruction' → Lesson. "
                "'clip'/'watch' → Video. 'interactive' → Activity or Adaptive Homework."
            )
        ),
    ] = None,
    structure: Annotated[
        Optional[Literal["Asset", "Sequence", "Collection", "Program"]],
        Field(
            description=(
                "Asset = single resource. Sequence = ordered set (unit/chapter). Collection = grouped. Program = full curriculum. "
                "'full unit' → Sequence. 'just one thing' → Asset. 'whole curriculum' → Program."
            )
        ),
    ] = "Asset",
    state_standard: Annotated[
        Optional[
            Literal[
                "CA-CCSS",
                "TX-TEKS",
                "FL-NGSSS",
                "AL-CCRS",
                "NY-CCLS",
                "OH-OLS",
                "PA-PACS",
                "IL-ILS",
                "GA-GSE",
                "VA-SOL",
                "MA-MCF",
                "WA-WELS",
                "CO-CAS",
                "NC-NCSCOS",
                "MI-GLCE",
            ]
        ],
        Field(
            description=(
                "'TEKS'/'Texas standards' → TX-TEKS. 'Common Core'/'CCSS' → CA-CCSS. "
                "About half of records have this. Different from state_version."
            )
        ),
    ] = None,
    language: Annotated[
        Optional[Literal["en", "es"]],
        Field(
            description=(
                "'in Spanish' → es. Only change if teacher explicitly asks for Spanish content."
            )
        ),
    ] = "en",
    resource_class: Annotated[
        Optional[Literal["Teacher Support", "Student Resource", "Program Guide"]],
        Field(
            description=(
                "'answer key'/'teacher guide' → Teacher Support. 'scope and sequence' → Program Guide."
            )
        ),
    ] = "Student Resource",
    file_type: Annotated[
        Optional[Literal["PDF", "HTML", "Video", "Interactive"]],
        Field(
            description=(
                "'printable' → PDF. 'online' → HTML. Use when teacher asks about file format specifically."
            )
        ),
    ] = None,
    product_line: Annotated[
        Optional[
            Literal[
                "AnyCompany Math",
                "AnyCompany Reading",
                "AnyCompany Adaptive",
                "AnyCompany Spanish",
                "AnyCompany Reader",
            ]
        ],
        Field(description=("Use if teacher mentions a specific program name.")),
    ] = None,
    state_version: Annotated[
        Optional[
            Literal[
                "CA",
                "TX",
                "FL",
                "AL",
                "NY",
                "OH",
                "PA",
                "IL",
                "GA",
                "MA",
                "WA",
                "CO",
                "NC",
                "MI",
            ]
        ],
        Field(
            description=(
                "State-specific content editions. About a fifth of records. "
                "Different from state_standard — this is edition, not alignment."
            )
        ),
    ] = None,
    detail: Annotated[
        Optional[Literal["concise", "detailed"]],
        Field(
            description="Use concise for broad searches. Use detailed only when full metadata is needed."
        ),
    ] = "concise",
) -> dict:
    """Search AnyCompany K-12 educational content — lessons, assessments, activities, videos, and more.
    Returns matching content with title, subject, grade range, and format.
    Metadata search only — does not search full content text.
    `topic` is a fuzzy search; all other parameters are strict filters.
    Use subject and grade filters to narrow results — topic alone returns too many.
    Sensible defaults are applied (structure='Asset', resource_class='Student Resource', language='en'). The response includes defaults_applied when defaults were used so you can see what was filtered. Override defaults explicitly if the user wants broader content."""
    # Track which defaults were applied (vs explicit user overrides)
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
    node_id: Annotated[
        str, Field(description="Resource ID from search results (node_id field).")
    ],
) -> dict:
    """Get full metadata for a single resource by its node_id.
    Use after searching to get complete details including keywords, standards,
    catalog group, and other fields not returned in concise search results."""
    return await mock_bff.get_resource_detail(node_id)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
