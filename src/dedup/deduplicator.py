"""중복·개정판·동일 논문 처리 (PRD v2.1 §11).

판정 우선순위:
1. DOI 완전일치
2. 공식 ID(arXiv ID / KCI ID / RISS Control No. / 보고서 ID) 완전일치
3. 파일 SHA256 일치
4. 정규화 텍스트 SHA256 일치
5. 제목+저자+연도 fuzzy match

URL 해시만으로는 중복을 판단하지 않습니다 (§11.4).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from ..database import Repository
from ..models import Resource
from ..normalizers.normalize import (
    first_author,
    normalize_title,
    title_similarity,
    year_of,
)

logger = logging.getLogger(__name__)

#: 제목 fuzzy match 로 동일 자료로 볼 최소 유사도
TITLE_MATCH_THRESHOLD = 0.85


class DedupVerdict(str, Enum):
    NEW = "NEW"
    DUPLICATE = "DUPLICATE"
    NEW_VERSION = "NEW_VERSION"


@dataclass
class DedupResult:
    verdict: DedupVerdict
    existing: Resource | None = None
    matched_by: str = ""

    @property
    def is_new(self) -> bool:
        return self.verdict == DedupVerdict.NEW


class Deduplicator:
    """다단계 중복 판별기."""

    def __init__(self, repo: Repository):
        self.repo = repo

    # ------------------------------------------------------------------
    def check_metadata(self, resource: Resource) -> DedupResult:
        """다운로드 이전 — 식별자·제목 기준 1차 판별 (§6.1 6단계)."""
        if resource.doi:
            existing = self.repo.find_by_doi(resource.doi)
            if existing:
                return self._compare(resource, existing, "doi")

        if resource.official_identifier:
            existing = self.repo.find_by_identifier(
                resource.source_id, resource.official_identifier
            )
            if existing:
                return self._compare(resource, existing, "official_identifier")

        fuzzy = self._fuzzy_match(resource)
        if fuzzy:
            return self._compare(resource, fuzzy, "title+year")

        return DedupResult(verdict=DedupVerdict.NEW)

    # ------------------------------------------------------------------
    def check_content(self, resource: Resource) -> DedupResult:
        """다운로드 이후 — 파일/텍스트 해시 기준 2차 판별 (§6.1 10단계)."""
        if resource.file_sha256:
            existing = self.repo.find_by_file_hash(resource.file_sha256)
            if existing and existing.resource_id != resource.resource_id:
                return DedupResult(
                    verdict=DedupVerdict.DUPLICATE, existing=existing, matched_by="file_sha256"
                )

        if resource.text_sha256:
            existing = self.repo.find_by_text_hash(resource.text_sha256)
            if existing and existing.resource_id != resource.resource_id:
                return DedupResult(
                    verdict=DedupVerdict.DUPLICATE, existing=existing, matched_by="text_sha256"
                )

        return DedupResult(verdict=DedupVerdict.NEW)

    # ------------------------------------------------------------------
    def _compare(self, incoming: Resource, existing: Resource, matched_by: str) -> DedupResult:
        """동일 식별자일 때 개정판인지 단순 중복인지 판정합니다 (§11.3)."""
        modified_changed = (
            incoming.source_modified_date
            and existing.source_modified_date
            and incoming.source_modified_date > existing.source_modified_date
        )
        file_changed = (
            incoming.file_sha256
            and existing.file_sha256
            and incoming.file_sha256 != existing.file_sha256
        )

        if modified_changed or file_changed:
            logger.info(
                "개정판을 감지했습니다 (%s): %s", matched_by, incoming.best_title()[:50]
            )
            return DedupResult(
                verdict=DedupVerdict.NEW_VERSION, existing=existing, matched_by=matched_by
            )

        return DedupResult(
            verdict=DedupVerdict.DUPLICATE, existing=existing, matched_by=matched_by
        )

    def _fuzzy_match(self, resource: Resource) -> Resource | None:
        """제목+저자+연도로 동일 자료 후보를 찾습니다."""
        title = resource.title_original or resource.title_ko
        if not title:
            return None
        year = year_of(resource.publication_date)
        candidates = self.repo.find_candidates_by_title(normalize_title(title), year)

        incoming_author = first_author(resource.authors).lower()
        for candidate in candidates:
            similarity = title_similarity(
                title, candidate.title_original or candidate.title_ko
            )
            if similarity < TITLE_MATCH_THRESHOLD:
                continue
            candidate_author = first_author(candidate.authors).lower()
            # 저자 정보가 양쪽에 있으면 함께 확인합니다.
            if incoming_author and candidate_author and incoming_author != candidate_author:
                continue
            return candidate
        return None

    # ------------------------------------------------------------------
    def merge_sources(self, incoming: Resource, existing: Resource) -> None:
        """같은 자료를 다른 출처에서 발견한 경우 URL 을 모두 보존합니다 (§11.2)."""
        for url, role in (
            (incoming.landing_url, "landing"),
            (incoming.download_url, "download"),
            (incoming.oa_url, "oa"),
        ):
            if url:
                self.repo.add_source_url(existing.resource_id, incoming.source_id, url, role)
        self.repo.touch_resource(existing.resource_id)

    def link_version(self, new_resource: Resource, previous: Resource) -> None:
        """개정판을 이전 버전과 연결합니다. 이전 파일은 삭제하지 않습니다 (§11.3)."""
        new_resource.version_of = previous.resource_id
        new_resource.work_id = previous.work_id or new_resource.work_id
