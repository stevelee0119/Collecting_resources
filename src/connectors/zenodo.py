"""Zenodo Connector (PRD v2.1 §4.4 I).

연구보고서·프리프린트·기관 연구성과를 보강하는 범용 오픈 리포지터리입니다.
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
from ..http_client import describe_http_error
from .base import SourceConnector

logger = logging.getLogger(__name__)

OPEN_LICENSE_HINTS = ("cc-by", "cc0", "cc-by-sa", "mit", "apache", "public-domain")


class ZenodoConnector(SourceConnector):
    connector_id = "zenodo"

    PAGE_SIZE = 30

    #: 비인증 요청의 페이지 크기 상한. 넘기면 400 입니다.
    #: 2026-08-23 확인: "Page size cannot be greater than 25. Please use authenticate..."
    ANONYMOUS_PAGE_SIZE = 25

    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:
        method = self.require_method("OPEN_API")
        token = self.secret_for(method)
        page_size = self.PAGE_SIZE if token else min(self.PAGE_SIZE, self.ANONYMOUS_PAGE_SIZE)
        seen: set[str] = set()
        emitted = 0

        for query in queries:
            if emitted >= self._limit():
                return
            params: dict[str, str | int] = {
                "q": f"({query.query_string}) AND updated:[{since.isoformat()} TO {until.isoformat()}]",
                "size": page_size,
                "sort": "mostrecent",
                # 공개(open) 접근권한 자료만 조회합니다.
                "access_right": "open",
            }
            if token:
                params["access_token"] = token

            try:
                data = self.ctx.client.get_json(method.endpoint, params=params)
            except Exception as exc:
                logger.warning(
                    "[zenodo] 질의 실패: %s (질의: %.40s)",
                    describe_http_error(exc), query.query_string,
                )
                continue

            for item in (data.get("hits") or {}).get("hits", []):
                item_id = clean_whitespace(str(item.get("id", "")))
                if not item_id or item_id in seen:
                    continue
                seen.add(item_id)
                yield RawItem(
                    source_id=self.config.source_id, payload=item, discovered_by_query=query
                )
                emitted += 1
                if emitted >= self._limit():
                    return

    def normalize(self, raw: RawItem) -> Resource | None:
        item = raw.payload
        meta = item.get("metadata") or {}
        title = clean_whitespace(meta.get("title"))
        if not title:
            return None

        doi = normalize_doi(meta.get("doi") or item.get("doi"))
        record_id = clean_whitespace(str(item.get("id", "")))
        license_id = clean_whitespace(
            (meta.get("license") or {}).get("id") if isinstance(meta.get("license"), dict) else meta.get("license")
        )
        is_open = str(meta.get("access_right", "")).lower() == "open"
        license_open = is_open and any(h in license_id.lower() for h in OPEN_LICENSE_HINTS)

        pdf_url = ""
        for f in item.get("files") or []:
            if str(f.get("key", "")).lower().endswith((".pdf", ".hwp", ".hwpx", ".docx")):
                pdf_url = clean_whitespace((f.get("links") or {}).get("self"))
                break

        query = raw.discovered_by_query
        return Resource(
            source_id=self.config.source_id,
            source_type="OPEN_API",
            work_id=build_work_id(doi=doi, identifier=f"zenodo:{record_id}", title=title),
            title_original=title,
            authors=normalize_authors(meta.get("creators")),
            publisher="Zenodo",
            journal_or_series=clean_whitespace((meta.get("journal") or {}).get("title", "")),
            publication_date=parse_date(meta.get("publication_date")),
            source_registered_date=parse_date(item.get("created")),
            source_modified_date=parse_date(item.get("updated")),
            discovered_at=self._now(),
            doi=doi,
            official_identifier=f"zenodo:{record_id}",
            landing_url=clean_whitespace((item.get("links") or {}).get("self_html"))
            or doi_to_url(doi),
            oa_url=pdf_url,
            license=license_id,
            license_unknown=not license_open,
            language=clean_whitespace(meta.get("language")) or "en",
            document_type=infer_document_type(meta.get("resource_type", {}).get("type"), title),
            keywords=[clean_whitespace(k) for k in (meta.get("keywords") or [])],
            abstract_original=_strip_html(meta.get("description")),
            query_original=query.canonical_ko if query else "",
            query_language=query.language if query else "",
            query_terms_expanded=query.expanded_terms if query else [],
            query_dictionary_version=query.dictionary_version if query else "",
            discovered_by_query=query.query_string if query else "",
        )


def _strip_html(value: object) -> str:
    import re

    if not value:
        return ""
    return clean_whitespace(re.sub(r"<[^>]+>", " ", str(value)))
