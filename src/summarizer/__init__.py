"""요약·분석 엔진 (PRD v2.1 §14)."""

from __future__ import annotations

import logging

from ..config_loader import AppConfig
from .base import Summarizer, Summary, determine_basis
from .extractive import ExtractiveSummarizer

logger = logging.getLogger(__name__)


def build_summarizer(app: AppConfig) -> Summarizer:
    """설정에 따라 요약 공급자를 선택합니다.

    `llm` 공급자를 쓸 수 없으면 추출식 요약으로 자동 대체합니다.
    """
    provider = str(app.get("summarizer.provider", "extractive")).lower()
    max_chars = int(app.get("summarizer.max_fulltext_chars", 40_000))

    if provider == "llm":
        from .llm import ClaudeSummarizer  # noqa: PLC0415

        try:
            summarizer = ClaudeSummarizer.from_config(app)
            summarizer._get_client()  # 자격증명·패키지 확인
            return summarizer
        except Exception as exc:
            logger.warning("LLM 요약을 사용할 수 없어 추출식 요약을 사용합니다: %s", exc)

    return ExtractiveSummarizer(max_fulltext_chars=max_chars)


__all__ = [
    "ExtractiveSummarizer",
    "Summarizer",
    "Summary",
    "build_summarizer",
    "determine_basis",
]
