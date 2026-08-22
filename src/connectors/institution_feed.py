"""기관형 소스 RSS/Atom Connector (PRD v2.1 §4.3).

국내 기관의 공식 공개자료실·연구보고서·간행물 피드를 수집합니다.

`endpoint` 가 비어 있으면 자동수집을 시도하지 않습니다. 기관별로
API/RSS/OAI-PMH 가 없으면 robots.txt·이용약관·저작권정책을 사전 점검한 뒤
개별 Adapter 를 구성해야 하며, 그 전까지는 LINK_ONLY 로 유지합니다.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from datetime import date

from ..models import CandidateKind, DownloadCandidate, Query, RawItem, Resource
from ..normalizers.normalize import (
    build_work_id,
    clean_whitespace,
    infer_document_type,
    parse_date,
)
from .base import EndpointNotConfiguredError, SourceConnector

logger = logging.getLogger(__name__)

DOCUMENT_EXTENSIONS = (".pdf", ".hwp", ".hwpx", ".docx")


class InstitutionFeedConnector(SourceConnector):
    connector_id = "institution_feed"

    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:
        method = self.config.method("RSS") or self.config.method("ATOM")
        if method is None or not method.endpoint:
            raise EndpointNotConfiguredError(self.config.name, "RSS")

        try:
            import feedparser  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - 의존성 누락
            raise EndpointNotConfiguredError(self.config.name, "RSS") from exc

        try:
            # 조건부 요청으로 변경 없는 피드는 건너뜁니다 (§18.2).
            response = self.ctx.client.get(method.endpoint, conditional=True)
            if response.status_code == 304:
                logger.info("[%s] 피드에 변경이 없습니다.", self.config.source_id)
                return
            response.raise_for_status()
            feed = feedparser.parse(response.content)
        except Exception as exc:
            logger.warning("[%s] 피드 수집 실패: %s", self.config.source_id, exc)
            return

        needles = _needles(queries)
        emitted = 0
        for entry in feed.entries:
            published = parse_date(
                entry.get("published") or entry.get("updated") or entry.get("dc_date")
            )
            if published and not (since <= published <= until):
                continue

            haystack = " ".join(
                [
                    clean_whitespace(entry.get("title")),
                    clean_whitespace(entry.get("summary")),
                ]
            ).lower()
            matched = _match(haystack, queries, needles)
            # 기관형 소스는 FULL 성격이므로 검색어가 없어도 수집합니다.
            payload = {
                "title": clean_whitespace(entry.get("title")),
                "link": clean_whitespace(entry.get("link")),
                "summary": clean_whitespace(entry.get("summary")),
                "published": entry.get("published") or entry.get("updated"),
                "author": clean_whitespace(entry.get("author")),
                "id": clean_whitespace(entry.get("id") or entry.get("link")),
                "enclosures": [
                    clean_whitespace(link.get("href"))
                    for link in (entry.get("links") or [])
                    if str(link.get("href", "")).lower().endswith(DOCUMENT_EXTENSIONS)
                ],
                "tags": [clean_whitespace(t.get("term")) for t in (entry.get("tags") or [])],
            }
            yield RawItem(
                source_id=self.config.source_id, payload=payload, discovered_by_query=matched
            )
            emitted += 1
            if emitted >= self._limit():
                return

    # ------------------------------------------------------------------
    def normalize(self, raw: RawItem) -> Resource | None:
        payload = raw.payload
        title = clean_whitespace(payload.get("title"))
        if not title:
            return None

        link = clean_whitespace(payload.get("link"))
        enclosures = [e for e in (payload.get("enclosures") or []) if e]
        published = parse_date(payload.get("published"))
        identifier = clean_whitespace(payload.get("id")) or link

        query = raw.discovered_by_query
        return Resource(
            source_id=self.config.source_id,
            source_type="RSS",
            work_id=build_work_id(identifier=f"{self.config.source_id}:{identifier}", title=title),
            title_original=title,
            title_ko=title,
            authors=[payload["author"]] if payload.get("author") else [],
            publisher=self.config.name,
            publication_date=published,
            source_registered_date=published,
            source_modified_date=published,
            discovered_at=self._now(),
            official_identifier=f"{self.config.source_id}:{identifier}",
            landing_url=link,
            download_url=enclosures[0] if enclosures else "",
            license="",
            # 기관 자료의 이용조건은 개별 확인이 필요합니다.
            license_unknown=True,
            language="ko",
            document_type=infer_document_type(title, payload.get("summary")),
            keywords=[t for t in (payload.get("tags") or []) if t],
            abstract_original=clean_whitespace(payload.get("summary")),
            query_original=query.canonical_ko if query else "",
            query_language=query.language if query else "",
            query_terms_expanded=query.expanded_terms if query else [],
            query_dictionary_version=query.dictionary_version if query else "",
            discovered_by_query=query.query_string if query else "",
        )

    # ------------------------------------------------------------------
    def resolve_download(self, metadata: Resource) -> DownloadCandidate | None:
        """피드에 첨부된 문서 파일이 있을 때만 후보로 제시합니다."""
        url = metadata.download_url
        if not url or not url.lower().endswith(DOCUMENT_EXTENSIONS):
            return None
        return DownloadCandidate(
            url=url,
            kind=CandidateKind.DIRECT_FILE,
            source_id=self.config.source_id,
            license=metadata.license,
            is_open_access=not metadata.license_unknown,
            origin=f"connector:{self.config.source_id}",
        )


def _needles(queries: Sequence[Query]) -> list[tuple[str, Query]]:
    pairs: list[tuple[str, Query]] = []
    for query in queries:
        for term in query.expanded_terms or [query.query_string]:
            cleaned = term.strip().strip('"').lower()
            if cleaned:
                pairs.append((cleaned, query))
    return pairs


def _match(
    haystack: str, queries: Sequence[Query], needles: list[tuple[str, Query]]
) -> Query | None:
    for needle, query in needles:
        if needle in haystack:
            return query
    return queries[0] if queries else None
