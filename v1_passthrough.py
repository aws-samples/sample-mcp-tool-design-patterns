# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# V1: BFF API fields exposed directly — many fields, minimal descriptions
# The tool definition is small, but low baseline cost is misleading — confusion drives up the actual cost through retries.
#
# True 1:1 passthrough of the internal BFF. The MCP tool exposes the
# same parameter names and types as the underlying search_content function.
# No adapter logic, no type conversion, no renaming.
#
# The LLM sees the field names but doesn't know valid values or how
# to map teacher language to them.
#
# Demo: "I need something on fractions for my 7th graders"
#   → LLM may guess discipline="mathematics" (wrong — it's "Math")
#   → May not know to use grade_from and grade_to together

import sys

from mcp.server.fastmcp import FastMCP

import mock_bff_sqlite as mock_bff

mcp = FastMCP(
    "AnyCompany Search",
    instructions="Search AnyCompany K-12 educational content library. Find lessons, assessments, activities, and videos across Math, Science, Literacy/ELA, Social Studies, and Spanish for grades K-12.",
    host="127.0.0.1",
    port=8001,
    stateless_http=True,
)
mock_bff.init(sys.argv[1] if len(sys.argv) > 1 else "anycompany_content.db")


@mcp.tool()
async def search_content(
    keyword: str = None,
    discipline: str = None,
    grade_from: int = None,
    grade_to: int = None,
    media_type: str = None,
    content_type: str = None,
    standards_alignment: str = None,
    language: str = None,
    content_bucket: str = None,
    file_type: str = None,
    catalog_group: str = None,
    hide_from_student: bool = None,
    download: str = None,
    version_state: str = None,
) -> list[dict]:
    """Performs a global search for educational resources.

    Args:
        keyword: Search keyword
        discipline: Discipline filter
        grade_from: Minimum grade
        grade_to: Maximum grade
        media_type: Media type filter
        content_type: Content type
        standards_alignment: Standards alignment
        language: Language
        content_bucket: Content bucket
        file_type: File type
        catalog_group: Catalog group
        hide_from_student: Hide from student flag
        download: Download permission
        version_state: Version state
    """
    return await mock_bff.search_content(
        keyword=keyword,
        discipline=discipline,
        grade_from=grade_from,
        grade_to=grade_to,
        media_type=media_type,
        content_type=content_type,
        standards_alignment=standards_alignment,
        language=language,
        content_bucket=content_bucket,
        file_type=file_type,
        catalog_group=catalog_group,
        hide_from_student=hide_from_student,
        download=download,
        version_state=version_state,
        response_format="detailed",
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
