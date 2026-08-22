"""OpenAlex Connector (PRD v2.1 §4.4 B).

대규모 학술 그래프에서 법률AI·공공정책·국제법 등 영문 연구를 탐색합니다.
대량 결과는 cursor 페이지네이션을 사용하며, 전수 순회는 하지 않습니다.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from datetime import date

from ..models import Query, RawItem, Resource
from ..normalizers.normalize import (
    build_work_id,
    clean_whitespace,
    doi_to_url,
    infer_document_type,
    normalize_authors,
    normalize_doi,
    parse_date,
)
from .base import SourceConnector

logger = logging.getLogger(__name__)


class OpenAlexConnector(SourceConnector):
    connector_id = "openalex"

    PER_PAGE = 50
    MAX_PAGES = 4

    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:
        # 2026-02-13 부터 API Key 가 필수입니다. 키가 없으면 여기서 건너뜁니다.
        method = self.require_method("OPEN_API")
        api_key = self.secret_for(method)
        use_cursor = bool(getattr(self.config, "use_cursor", True))
        seen: set[str] = set()
        emitted = 0

        for query in queries:
            if emitted >= self._limit():
                return
            cursor = "*" if use_cursor else None
            for _ in range(self.MAX_PAGES):
                params: dict[str, str | int] = {
                    "search": query.query_string,
                    "filter": (
                        f"from_updated_date:{since.isoformat()},"
                        f"to_publication_date:{until.isoformat()}"
                    ),
                    "per-page": self.PER_PAGE,
                }
                if cursor:
                    params["cursor"] = cursor
                # polite pool(mailto)은 폐지되었고 인증은 API Key 로만 합니다.
                if api_key:
                    params["api_key"] = api_key

                try:
                    data = self.ctx.client.get_json(method.endpoint, params=params)
                except Exception as exc:
                    logger.warning("[openalex] 질의 실패 (%s): %s", query.query_string, exc)
                    break

                results = data.get("results") or []
                if not results:
                    break

                for item in results:
                    key = normalize_doi(item.get("doi")) or clean_whitespace(item.get("id"))
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    yield RawItem(
                        source_id=self.config.source_id, payload=item, discovered_by_query=query
                    )
                    emitted += 1
                    if emitted >= self._limit():
                        return

                cursor = (data.get("meta") or {}).get("next_cursor")
                if not cursor:
                    break

    def normalize(self, raw: RawItem) -> Resource | None:
        item = raw.payload
        title = clean_whitespace(item.get("display_name") or item.get("title"))
        if not title:
            return None

        doi = normalize_doi(item.get("doi"))
        openalex_id = clean_whitespace(item.get("id"))
        published = parse_date(item.get("publication_date"))
        modified = parse_date(item.get("updated_date"))
        created = parse_date(item.get("created_date"))

        oa = item.get("open_access") or {}
        best_location = item.get("best_oa_location") or {}
        primary_location = item.get("primary_location") or {}

        is_oa = bool(oa.get("is_oa"))
        oa_url = clean_whitespace(best_location.get("pdf_url") or oa.get("oa_url"))
        license_name = clean_whitespace(best_location.get("license"))
        landing = clean_whitespace(
            primary_location.get("landing_page_url") or best_location.get("landing_page_url")
        ) or doi_to_url(doi) or openalex_id

        source_info = primary_location.get("source") or {}
        journal = clean_whitespace(source_info.get("display_name"))

        keywords = [
            clean_whitespace(c.get("display_name"))
            for c in (item.get("concepts") or [])[:8]
            if c.get("display_name")
        ]

        query = raw.discovered_by_query
        return Resource(
            source_id=self.config.source_id,
            source_type="OPEN_API",
            work_id=build_work_id(doi=doi, identifier=openalex_id, title=title),
            title_original=title,
            authors=normalize_authors(item.get("authorships")),
            publisher=clean_whitespace(source_info.get("host_organization_name")),
            journal_or_series=journal,
            publication_date=published,
            source_registered_date=created,
            source_modified_date=modified,
            discovered_at=self._now(),
            doi=doi,
            official_identifier=openalex_id,
            landing_url=landing,
            oa_url=oa_url,
            license=license_name,
            license_unknown=not (is_oa and bool(license_name)),
            language=clean_whitespace(item.get("language")) or "en",
            document_type=infer_document_type(item.get("type"), title),
            keywords=keywords,
            abstract_original=_abstract_from_inverted_index(item.get("abstract_inverted_index")),
            query_original=query.canonical_ko if query else "",
            query_language=query.language if query else "",
            query_terms_expanded=query.expanded_terms if query else [],
            query_dictionary_version=query.dictionary_version if query else "",
            discovered_by_query=query.query_string if query else "",
        )


def _abstract_from_inverted_index(index: dict | None) -> str:
    """OpenAlex 의 inverted index 초록을 평문으로 되돌립니다."""
    if not index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, spots in index.items():
        for spot in spots or []:
            positions.append((int(spot), word))
    if not positions:
        return ""
    positions.sort()
    return clean_whitespace(" ".join(word for _, word in positions))
