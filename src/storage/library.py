"""주제별 최종 저장소 (PRD v2.1 §9).

기본 원칙:
- 수집일자별 목록은 Manifest 로 관리한다.
- 실제 문서는 주제별 폴더에 한 번만 저장한다.
- 동일 문서를 날짜 폴더와 주제 폴더에 중복 저장하지 않는다.

파일명 규칙 (§9.3 — 필수):
    YYMMDD_[SOURCE]_[짧은제목].[ext]
`YYMMDD` 는 **다운로드일** 기준이며 발행일과 별도로 관리합니다.
"""

from __future__ import annotations

import logging
import re
import shutil
import unicodedata
from datetime import date
from pathlib import Path

from ..config_loader import TopicRegistry
from ..models import Resource

logger = logging.getLogger(__name__)

#: Windows 예약문자 (§9.3)
RESERVED_CHARS_RE = re.compile(r'[\\/:*?"<>|]')
#: 제어문자
CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
WHITESPACE_RE = re.compile(r"\s+")

#: Windows 예약 파일명
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

DEFAULT_MAX_FILENAME = 160
#: 짧은제목에 할당하는 최대 길이
TITLE_BUDGET = 80


def sanitize_filename_part(text: str) -> str:
    """파일명 조각을 안전하게 만듭니다."""
    if not text:
        return ""
    cleaned = unicodedata.normalize("NFC", text)
    cleaned = CONTROL_CHARS_RE.sub("", cleaned)
    cleaned = RESERVED_CHARS_RE.sub("", cleaned)
    # 연속 공백을 밑줄로 변경
    cleaned = WHITESPACE_RE.sub("_", cleaned)
    cleaned = re.sub(r"_{2,}", "_", cleaned)
    return cleaned.strip("._-")


def build_filename(
    *,
    downloaded_on: date,
    source_id: str,
    title: str,
    extension: str,
    suffix_hash: str = "",
    max_length: int = DEFAULT_MAX_FILENAME,
) -> str:
    """`YYMMDD_[SOURCE]_[짧은제목].[ext]` 형식의 파일명을 만듭니다.

    Args:
        downloaded_on: 다운로드일 (발행일 아님)
        source_id: 출처 식별자
        title: 자료 제목
        extension: `.pdf` 등 확장자
        suffix_hash: 파일명 충돌 시 붙일 DOI/해시 8자
    """
    prefix = downloaded_on.strftime("%y%m%d")
    source_part = sanitize_filename_part(source_id).upper() or "UNKNOWN"
    title_part = sanitize_filename_part(title)[:TITLE_BUDGET] or "무제"

    if title_part.upper() in RESERVED_NAMES:
        title_part = f"_{title_part}"

    ext = extension if extension.startswith(".") else f".{extension}"
    tail = f"__{suffix_hash}" if suffix_hash else ""

    name = f"{prefix}_{source_part}_{title_part}{tail}{ext}"
    if len(name) <= max_length:
        return name

    # 길이를 초과하면 제목만 줄입니다.
    overflow = len(name) - max_length
    trimmed = title_part[: max(8, len(title_part) - overflow)]
    return f"{prefix}_{source_part}_{trimmed}{tail}{ext}"


class Library:
    """주제별 최종 저장소 관리자."""

    def __init__(self, library_dir: str | Path, topics: TopicRegistry, *, max_filename: int = DEFAULT_MAX_FILENAME):
        self.library_dir = Path(library_dir)
        self.topics = topics
        self.max_filename = max_filename
        self.ensure_folders()

    # ------------------------------------------------------------------
    def ensure_folders(self) -> None:
        """주제 폴더를 생성합니다 (§9.2)."""
        for topic in self.topics.topics:
            (self.library_dir / topic.topic_id).mkdir(parents=True, exist_ok=True)

    def topic_dir(self, topic_id: str) -> Path:
        target = self.library_dir / (topic_id or TopicRegistry.UNCLASSIFIED)
        if not target.exists():
            target = self.library_dir / TopicRegistry.UNCLASSIFIED
            target.mkdir(parents=True, exist_ok=True)
        return target

    # ------------------------------------------------------------------
    def store(self, staged_path: str | Path, resource: Resource, *, downloaded_on: date | None = None) -> Path:
        """staging 파일을 주제별 폴더로 원자적으로 이동합니다.

        Returns:
            최종 저장 경로
        """
        source = Path(staged_path)
        downloaded_on = downloaded_on or date.today()
        target_dir = self.topic_dir(resource.topic_primary)

        filename = build_filename(
            downloaded_on=downloaded_on,
            source_id=resource.source_id,
            title=resource.best_title(),
            extension=source.suffix or ".pdf",
            max_length=self.max_filename,
        )
        target = target_dir / filename

        if target.exists():
            # 동일 파일명 충돌 시 DOI/공식 ID 또는 해시 8자를 덧붙입니다 (§9.3).
            suffix = self._collision_suffix(resource)
            target = target_dir / build_filename(
                downloaded_on=downloaded_on,
                source_id=resource.source_id,
                title=resource.best_title(),
                extension=source.suffix or ".pdf",
                suffix_hash=suffix,
                max_length=self.max_filename,
            )

        # staging → validation → atomic move (§18.1)
        shutil.move(str(source), str(target))
        logger.info("주제별 저장소에 보관했습니다: %s", target)
        return target

    # ------------------------------------------------------------------
    @staticmethod
    def _collision_suffix(resource: Resource) -> str:
        if resource.file_sha256:
            return resource.file_sha256[:8]
        if resource.doi:
            import hashlib  # noqa: PLC0415

            return hashlib.sha256(resource.doi.encode()).hexdigest()[:8]
        return resource.resource_id.replace("-", "")[:8]

    # ------------------------------------------------------------------
    def stats(self) -> dict[str, int]:
        """주제별 보관 파일 수."""
        out: dict[str, int] = {}
        for topic in self.topics.topics:
            folder = self.library_dir / topic.topic_id
            out[topic.topic_id] = (
                sum(1 for p in folder.iterdir() if p.is_file()) if folder.exists() else 0
            )
        return out
