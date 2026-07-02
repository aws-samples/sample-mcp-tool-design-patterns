# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
# V2: Better descriptions — THE FIX
# The tool definition is noticeably larger — that is the bloat tradeoff. Every call pays it whether the tool is used or not.
#
# Same BFF field names as V1, zero backend refactoring.
# What changed: each parameter has rich descriptions with valid values,
# natural language mappings, and synonym lists. The tool layer also adds
# helpful errors and filter context that V1 lacks.
#
# This works — but look at the token cost. Every single tool call
# sends all this context whether the LLM needs it or not.
#
# Dropped from V1 (with reasons):
#   copyright_year — rarely a search criterion for teachers
#   download — administrative restriction, not a search need
#   hide_from_student — role-based; BFF should handle based on who's logged in

import sys

from mcp.server.fastmcp import FastMCP

import mock_bff_sqlite as mock_bff

mcp = FastMCP(
    "AnyCompany Search",
    instructions="Search AnyCompany K-12 educational content library. Find lessons, assessments, activities, and videos across Math, Science, Literacy/ELA, Social Studies, and Spanish for grades K-12.",
    host="127.0.0.1",
    port=8002,
    stateless_http=True,
)
mock_bff.init(sys.argv[1] if len(sys.argv) > 1 else "anycompany_content.db")


def _wrap_response(results):
    """Wrap a BFF response with helpful messaging when needed.
    V2 has no defaults, so successful responses just return results."""
    if isinstance(results, dict) and "error" in results:
        return {
            "error": "Search too broad. Provide at least 2 of: keyword, discipline, grade range, media_type, content_type, standards_alignment, content_bucket, or other filters."
        }
    if not results:
        return {
            "result_count": 0,
            "results": [],
            "note": "No results found. Did the user want to expand the search from these filters?",
        }
    return {"result_count": len(results), "results": results}


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
    version_state: str = None,
) -> dict:
    """Search AnyCompany K-12 educational content — lessons, assessments, activities, videos, and more.
    Returns matching content with full metadata.
    Searches metadata only — does not search full content text.
    `keyword` is a fuzzy search; all other parameters are strict filters.
    Use discipline and grade filters to narrow results — keyword alone returns too many results.

    Args:
        keyword: Topic or concept to match against resource titles and metadata tags.
            Matches against title, keywords, and content index using substring search.
            Use a single concept: 'fractions', 'civil war', 'climate', 'photosynthesis'.
            Synonym awareness: 'dividing'/'quotient' relate to fractions/division in Math.
            'multiply'/'product' relate to multiplication.
            'quiz'/'test' map to media_type='Assessment' for format filtering.
            'worksheet' maps to media_type='Activity' for format filtering.
        discipline: Subject area filter. Valid values: Math, Science, Literacy/ELA, Social Studies, Spanish, Art, Music, Physical Education, Health, Computer Science.
            Map common terms: 'reading', 'english', 'language arts', 'ELA', 'writing' → Literacy/ELA.
            'history', 'geography', 'civics', 'government', 'economics' → Social Studies.
            'biology', 'chemistry', 'physics', 'earth science', 'life science' → Science.
            'español', 'spanish class' → Spanish.
            Most teachers teach one subject — always try to infer it from context.
            Omitting this filter returns all disciplines which is usually too broad.
        grade_from: Minimum grade level, integer 0-12 where 0=Kindergarten.
            Interpret teacher language: '7th graders' → 7, 'my 3rd grade class' → 3.
            'middle school' → 6, 'elementary' → 0, 'high school' → 9, 'AP' → 11.
            'kindergarten' or 'K' → 0.
            Set equal to grade_to for a single grade level.
            For ranges: 'upper elementary' → grade_from=3, grade_to=5.
            'lower elementary' → grade_from=0, grade_to=2.
        grade_to: Maximum grade level, integer 0-12.
            Set equal to grade_from for a single grade.
            'middle school' → 8, 'elementary' → 5, 'high school' → 12.
            Always set both grade_from and grade_to together for best results.
        media_type: Content format filter. Valid values: Lesson, Assessment, Activity, Video, Adaptive Homework.
            Map teacher language: 'worksheet', 'handout', 'printable', 'practice sheet' → Activity.
            'quiz', 'test', 'exam', 'check for understanding', 'formative assessment' → Assessment.
            'homework', 'adaptive practice', 'practice problems' → Adaptive Homework.
            'lecture', 'instruction', 'direct teach', 'lesson plan' → Lesson.
            'clip', 'watch', 'visual', 'tutorial video' → Video.
            'something interactive' often means Activity or Adaptive Homework.
        content_type: Structural type filter. Valid values: Asset, Sequence, Collection, Program.
            Asset = single standalone resource (one lesson, one video, one worksheet).
            Sequence = ordered set of resources forming a unit or chapter.
            Collection = grouped resources on a theme (not ordered).
            Program = full curriculum package.
            Map: 'full unit' or 'chapter' → Sequence, 'single activity' or 'just one thing' → Asset,
            'whole curriculum' or 'full program' → Program, 'resource bundle' or 'collection' → Collection.
            Most teachers want Asset (single resources). Use Sequence/Program when they ask for units or curriculums.
        standards_alignment: State standard alignment code. Valid values: CA-CCSS, TX-TEKS, FL-NGSSS, AL-CCRS, NY-CCLS, OH-OLS, PA-PACS, IL-ILS, GA-GSE, VA-SOL, MA-MCF, WA-WELS, CO-CAS, NC-NCSCOS, MI-GLCE.
            Map: 'Texas standards' or 'TEKS' or 'TEKS-aligned' → TX-TEKS.
            'California standards' or 'Common Core' or 'CCSS' → CA-CCSS.
            'Florida standards' or 'NGSSS' → FL-NGSSS.
            'Alabama standards' or 'CCRS' → AL-CCRS.
            'New York standards' or 'CCLS' → NY-CCLS.
            IMPORTANT: Only about half of records have standards alignment data.
            Results will be limited when using this filter.
            If the teacher mentions a state without saying 'standards', they may want version_state instead.
        language: Content language filter. Valid values: en, es.
            Map: 'English' → en, 'Spanish', 'in Spanish', 'en español' → es.
            Default is English — only use this filter if the teacher explicitly asks for Spanish content.
            Nearly all content is in English.
        content_bucket: Audience type filter. Valid values: Teacher Support, Student Resource, Program Guide.
            Map: 'teacher materials', 'teacher guide', 'answer key', 'teacher edition' → Teacher Support.
            'student materials', 'student facing', 'for students' → Student Resource.
            'scope and sequence', 'program overview', 'pacing guide' → Program Guide.
            Most content is Student Resource. Use Teacher Support when teacher asks for answer keys.
        file_type: Technical file format filter. Valid values: PDF, HTML, Video, Interactive.
            Map: 'printable', 'print', 'download and print' → PDF.
            'online', 'web-based', 'browser' → HTML.
            'something interactive', 'drag and drop', 'manipulative' → Interactive.
            Note: this overlaps with media_type for videos. Use media_type='Video' for video content,
            use this field only when the teacher specifically asks about file format.
        catalog_group: Product line filter. Valid values: AnyCompany Math, AnyCompany Reading, AnyCompany Adaptive, AnyCompany Spanish, AnyCompany Reader.
            Map: 'the math program' → AnyCompany Math.
            'perspectives', 'ELA program' → AnyCompany Reading.
            'adaptive learning' → AnyCompany Adaptive.
            Use this when the teacher specifically mentions a program name.
        version_state: State-specific content version filter. Valid values: CA, TX, FL, AL, NY, OH, PA, IL, GA, VA, MA, WA, CO, NC, MI.
            Map: 'Texas version' or 'Texas edition' → TX, 'California edition' → CA.
            Only about a fifth of records are state-tagged.
            Different from standards_alignment: this is about state-specific content editions,
            not standards alignment.
    """
    results = await mock_bff.search_content(
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
        version_state=version_state,
        response_format="detailed",
    )

    return _wrap_response(results)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
