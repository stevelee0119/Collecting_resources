"""CORE Connector (PRD v2.1 §4.4 D).

오픈액세스 원문 확보의 핵심 소스. QUERY 로 신규 자료를 찾고,
OA_RESOLVER 로 DOI 에 대응하는 합법적인 공개본을 탐색합니다.
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


class CoreConnector(SourceConnector):
    connector_id = "core"

    PAGE_SIZE = 30

    def _headers(self) -> dict[str, str]:
        method = self.require_method("OPEN_API")
        token = self.secret_for(method)
        return {"Authorization": f"Bearer {token}"} if token else {}

    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:
        method = self.require_method("OPEN_API")
        headers = self._headers()
        seen: set[str] = set()
        emitted = 0

        for query in queries:
            if emitted >= self._limit():
                return
            body = {
                "q": f"({query.query_string}) AND createdDate>={since.isoformat()}",
                "limit": self.PAGE_SIZE,
                "sort": "createdDate:desc",
            }
            try:
                response = self.ctx.client.post(method.endpoint, json=body, headers=headers)
                response.raise_for_status()
                data = response.json()
            except Exception as exc:
                logger.warning("[core] 질의 실패 (%s): %s", query.query_string, exc)
                continue

            for item in data.get("results") or []:
                item_id = clean_whitespace(str(item.get("id", "")))
                if not item_id or item_id in seen:
                    continue
                published = parse_date(item.get("publishedDate") or item.get("createdDate"))
                if published and published > until:
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
        title = clean_whitespace(item.get("title"))
        if not title:
            return None

        doi = normalize_doi(item.get("doi"))
        core_id = clean_whitespace(str(item.get("id", "")))
        pdf_url = clean_whitespace(item.get("downloadUrl"))
        landing = clean_whitespace(
            item.get("sourceFulltextUrls", [""])[0] if item.get("sourceFulltextUrls") else ""
        ) or doi_to_url(doi)

        query = raw.discovered_by_query
        return Resource(
            source_id=self.config.source_id,
            source_type="OPEN_API",
            work_id=build_work_id(doi=doi, identifier=f"core:{core_id}", title=title),
            title_original=title,
            authors=normalize_authors(item.get("authors")),
            publisher=clean_whitespace((item.get("publisher") or "")),
            journal_or_series=clean_whitespace(
                (item.get("journals") or [{}])[0].get("title", "") if item.get("journals") else ""
            ),
            publication_date=parse_date(item.get("publishedDate")),
            source_registered_date=parse_date(item.get("createdDate")),
            source_modified_date=parse_date(item.get("updatedDate")),
            discovered_at=self._now(),
            doi=doi,
            official_identifier=f"core:{core_id}",
            landing_url=landing,
            oa_url=pdf_url,
            license=clean_whitespace(item.get("license")) or "CORE 오픈액세스",
            # CORE 는 OA 저장소 원문만 색인합니다.
            license_unknown=not bool(pdf_url),
            language=clean_whitespace((item.get("language") or {}).get("code", "")) or "en",
            document_type=infer_document_type(item.get("documentType"), title),
            keywords=[],
            abstract_original=clean_whitespace(item.get("abstract")),
            query_original=query.canonical_ko if query else "",
            query_language=query.language if query else "",
            query_terms_expanded=query.expanded_terms if query else [],
            query_dictionary_version=query.dictionary_version if query else "",
            discovered_by_query=query.query_string if query else "",
        )

    # ------------------------------------------------------------------
    # OA_RESOLVER 역할
    # ------------------------------------------------------------------
    def find_oa_pdf(self, doi: str) -> tuple[str, str] | None:
        """DOI 로 CORE 에서 공개 원문 URL 과 라이선스를 찾습니다."""
        if not doi:
            return None
        method = self.config.method("OPEN_API")
        if not method or not method.endpoint:
            return None
        try:
            response = self.ctx.client.post(
                method.endpoint,
                json={"q": f'doi:"{doi}"', "limit": 3},
                headers=self._headers(),
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.debug("[core] OA 조회 실패 (%s): %s", doi, exc)
            return None

        for item in data.get("results") or []:
            url = clean_whitespace(item.get("downloadUrl"))
            if url:
                return url, clean_whitespace(item.get("license")) or "CORE 오픈액세스"
        return None
