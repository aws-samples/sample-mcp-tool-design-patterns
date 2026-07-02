# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""Mock BFF layer for AnyCompany content search — SQLite edition.

Drop-in replacement for mock_bff.py. Uses aiosqlite instead of asyncpg
so the demo runs with zero infrastructure (no Postgres needed).

Usage:
    import mock_bff_sqlite as mock_bff
    mock_bff.init("anycompany_content.db")
    results = await mock_bff.search_content(discipline="Math", grade_from=7, grade_to=7, keyword="fractions")
"""

import os

import aiosqlite

_db_path = None


def init(db_path=None):
    global _db_path
    _db_path = db_path or os.environ.get("DATABASE_URL", "anycompany_content.db")


CONCISE_FIELDS = [
    "node_id",
    "title",
    "discipline",
    "grade_from",
    "grade_to",
    "media_type",
    "content_bucket",
]

MAX_STRING_LENGTH = 200
VALID_GRADES = range(0, 13)  # 0 (Kindergarten) through 12


def _validate_string(value, name):
    """Validate string input: type check and length limit."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    if len(value) > MAX_STRING_LENGTH:
        raise ValueError(
            f"{name} exceeds maximum length of {MAX_STRING_LENGTH} characters"
        )
    return value


def _validate_grade(value, name):
    """Validate grade input: must be integer 0-12."""
    if value is None:
        return None
    if not isinstance(value, int) or value not in VALID_GRADES:
        raise ValueError(f"{name} must be an integer between 0 and 12")
    return value


async def _query(sql, params=()):
    async with aiosqlite.connect(_db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cur:
            return [dict(row) for row in await cur.fetchall()]


async def search_content(
    discipline=None,
    grade_from=None,
    grade_to=None,
    media_type=None,
    keyword=None,
    standards_alignment=None,
    version_state=None,
    content_type=None,
    content_bucket=None,
    file_type=None,
    language=None,
    catalog_group=None,
    hide_from_student=None,
    download=None,
    response_format="concise",
):
    provided = sum(
        1
        for v in [
            discipline,
            grade_from,
            grade_to,
            media_type,
            keyword,
            standards_alignment,
            version_state,
            content_type,
            content_bucket,
            file_type,
            language,
            catalog_group,
            hide_from_student,
            download,
        ]
        if v is not None
    )
    # If keyword looks like a node_id (e.g. "n-tk-1006"), do a direct lookup.
    # This allows V1/V2 (which lack a dedicated get_resource_detail tool) to
    # still resolve specific resources when the user provides an ID.
    if provided == 1 and keyword and keyword.startswith("n-"):
        keyword = _validate_string(keyword, "keyword")
        rows = await _query(
            "SELECT * FROM anycompany_content WHERE node_id = ?", (keyword,)
        )
        if rows:
            return rows
    if provided < 2:
        return {"error": "Too few search criteria"}

    # Input validation
    discipline = _validate_string(discipline, "discipline")
    media_type = _validate_string(media_type, "media_type")
    keyword = _validate_string(keyword, "keyword")
    standards_alignment = _validate_string(standards_alignment, "standards_alignment")
    version_state = _validate_string(version_state, "version_state")
    content_type = _validate_string(content_type, "content_type")
    content_bucket = _validate_string(content_bucket, "content_bucket")
    file_type = _validate_string(file_type, "file_type")
    language = _validate_string(language, "language")
    catalog_group = _validate_string(catalog_group, "catalog_group")
    download = _validate_string(download, "download")
    grade_from = _validate_grade(grade_from, "grade_from")
    grade_to = _validate_grade(grade_to, "grade_to")
    if response_format not in ("concise", "detailed"):
        raise ValueError("response_format must be 'concise' or 'detailed'")

    # Safe: fields sourced from hardcoded CONCISE_FIELDS, not user input
    fields = ", ".join(CONCISE_FIELDS) if response_format == "concise" else "*"
    sql = f"SELECT {fields} FROM anycompany_content WHERE 1=1"  # nosec B608
    params = []

    if discipline:
        sql += " AND discipline = ?"
        params.append(discipline)
    if grade_from is not None:
        sql += " AND grade_to >= ?"
        params.append(grade_from)
    if grade_to is not None:
        sql += " AND grade_from <= ?"
        params.append(grade_to)
    if media_type:
        sql += " AND media_type = ?"
        params.append(media_type)
    if keyword:
        # Comma-separated keywords are ORed together (synonym expansion).
        terms = [t.strip() for t in keyword.split(",") if t.strip()]
        kw_clauses = []
        relevance_terms = []
        for term in terms:
            # Include node_id in keyword search so IDs are discoverable
            # even without a dedicated lookup tool (V1/V2 scenario).
            kw_clauses.append(
                "(search_text LIKE ? OR title LIKE ? OR keywords LIKE ? OR node_id LIKE ?)"
            )
            params.extend([f"%{term}%"] * 4)
            relevance_terms.append(term)
        sql += " AND (" + " OR ".join(kw_clauses) + ")"  # nosec B608
    if standards_alignment:
        sql += " AND standards_alignment = ?"
        params.append(standards_alignment)
    if version_state:
        sql += " AND version_state = ?"
        params.append(version_state)
    if content_type:
        sql += " AND content_type = ?"
        params.append(content_type)
    if content_bucket:
        sql += " AND content_bucket = ?"
        params.append(content_bucket)
    if file_type:
        sql += " AND file_type = ?"
        params.append(file_type)
    if language:
        sql += " AND language = ?"
        params.append(language)
    if catalog_group:
        sql += " AND catalog_group = ?"
        params.append(catalog_group)
    if hide_from_student is not None:
        sql += " AND hide_from_student = ?"
        params.append(hide_from_student)
    if download:
        sql += " AND download = ?"
        params.append(download)

    # Relevance ranking: title hits weighted highest, then keywords, then search_text.
    # Each keyword term contributes to score; multi-term matches accumulate.
    if keyword and relevance_terms:
        score_parts = []
        for term in relevance_terms:
            score_parts.append(f"(CASE WHEN title LIKE ? THEN 10 ELSE 0 END)")
            params.append(f"%{term}%")
            score_parts.append(f"(CASE WHEN keywords LIKE ? THEN 5 ELSE 0 END)")
            params.append(f"%{term}%")
            score_parts.append(f"(CASE WHEN search_text LIKE ? THEN 1 ELSE 0 END)")
            params.append(f"%{term}%")
        sql += f" ORDER BY ({' + '.join(score_parts)}) DESC"  # nosec B608

    sql += " LIMIT 25"
    return await _query(sql, params)


async def get_taxonomy(fields=None):
    if not fields:
        return {
            "error": "Provide field names from the search tool (e.g. ['subject', 'resource_class'])"
        }
    if not isinstance(fields, list) or len(fields) > 20:
        return {"error": "fields must be a list of up to 20 field names"}

    ctx = {}
    col_map = {
        "subject": "discipline",
        "format": "media_type",
        "structure": "content_type",
        "resource_class": "content_bucket",
        "state_standard": "standards_alignment",
        "state_version": "version_state",
        "product_line": "catalog_group",
    }
    notes = {
        "subject": "Subject area. 'math' → Math, 'reading' or 'english' → Literacy/ELA, 'history' → Social Studies",
        "format": "Content format. 'worksheet' → Activity, 'quiz' or 'test' → Assessment, 'homework' → Adaptive Homework, 'lecture' → Lesson, 'clip' → Video",
        "structure": "Structural type. Asset = single resource, Sequence = ordered set, Collection = grouped resources, Program = full curriculum.",
        "file_type": "Technical format. 'printable' → PDF, 'online' → HTML, 'something interactive' → Interactive",
        "resource_class": "Resource classification. 'teacher materials' → Teacher Support, 'student stuff' → Student Resource, 'scope and sequence' → Program Guide",
        "state_standard": "State standard codes. 'Texas standards' or 'TEKS' → TX-TEKS, 'California' or 'Common Core' → CA-CCSS.",
        "state_version": "State-specific content versions. 'Texas version' → TX, 'California edition' → CA.",
        "language": "'English' → en, 'Spanish' or 'in Spanish' → es. Default is English.",
        "product_line": "Product line. 'the math program' → AnyCompany Math, 'perspectives' → AnyCompany Reading",
        "download": "Download permission. 'downloadable' → allowed, 'no download' → none",
    }

    for f in fields:
        f = f.lower().strip()
        if f == "hide_from_student":
            ctx[f] = {"values": [True, False], "note": "TRUE = teacher-only content."}
        elif f in ("grade", "min_grade", "max_grade"):
            ctx["grade"] = {
                "range": "0-12 (0 = Kindergarten)",
                "note": "'7th graders' → 7. 'middle school' → 6-8. 'elementary' → 0-5. 'high school' → 9-12.",
            }
        elif f in ("topic", "keyword", "keywords"):
            ctx["topic"] = {
                "note": "Searches title, keywords, and search_text fields.",
                "synonym_guidance": {
                    "dividing / quotient": "search 'fraction' or 'division' in Math",
                    "quiz / test": "Use format='Assessment'",
                    "worksheet": "Use format='Activity'",
                },
            }
        elif f in col_map or f == "file_type" or f == "download":
            col = col_map.get(f, f)
            # Validated: col is always from hardcoded col_map or literal "file_type"/"download"
            allowed_columns = set(col_map.values()) | {"file_type", "download"}
            if col not in allowed_columns:
                ctx[f] = {"error": f"Invalid column: {col}"}
                continue
            rows = await _query(
                f"SELECT DISTINCT {col} FROM anycompany_content WHERE {col} IS NOT NULL ORDER BY {col}"
            )  # nosec B608
            ctx[f] = {"values": [r[col] for r in rows], "note": notes.get(f, "")}
        else:
            ctx[f] = {
                "error": f"Unknown field: {f}. Call get_taxonomy() with no arguments to see available fields."
            }
    return ctx


async def get_resource_detail(node_id):
    if not isinstance(node_id, str) or len(node_id) > 50:
        return {"error": "node_id must be a string of up to 50 characters"}
    rows = await _query(
        "SELECT * FROM anycompany_content WHERE node_id = ?", (node_id,)
    )
    return rows[0] if rows else {"error": f"No resource found with node_id: {node_id}"}
