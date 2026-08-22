"""메타데이터 정규화 (PRD v2.1 §6.1 4단계)."""

from .normalize import (
    build_work_id,
    clean_whitespace,
    detect_language,
    doi_to_url,
    infer_document_type,
    normalize_authors,
    normalize_doi,
    normalize_text,
    normalize_title,
    parse_date,
    text_sha256,
    title_similarity,
)

__all__ = [
    "build_work_id",
    "clean_whitespace",
    "detect_language",
    "doi_to_url",
    "infer_document_type",
    "normalize_authors",
    "normalize_doi",
    "normalize_text",
    "normalize_title",
    "parse_date",
    "text_sha256",
    "title_similarity",
]
