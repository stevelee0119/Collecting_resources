"""Semantic Scholar Connector (PRD v2.1 §4.4 C).

논문·저자·인용관계·OA PDF URL 을 제공하는 보조 학술 그래프입니다.
2차 확장(인용/피인용, 동일 저자 최근 연구)에도 사용합니다 (§6.3).
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

FIELDS = (
    "paperId,externalIds,title,abstract,venue,year,publicationDate,authors,"
    "openAccessPdf,isOpenAccess,publicationTypes,fieldsOfStudy,url"
)


class SemanticScholarConnector(SourceConnector):
    connector_id = "semantic_scholar"

    PAGE_SIZE = 50

    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:
        method = self.require_method("OPEN_API")
        headers = {}
        if api_key := self.secret_for(method):
            headers["x-api-key"] = api_key

        seen: set[str] = set()
        emitted = 0
        for query in queries:
            if emitted >= self._limit():
                return
            params = {
                "query": query.query_string,
                "limit": self.PAGE_SIZE,
                "fields": FIELDS,
                "publicationDateOrYear": f"{since.isoformat()}:{until.isoformat()}",
            }
            try:
                data = self.ctx.client.get_json(method.endpoint, params=params, headers=headers)
            except Exception as exc:
                logger.warning(
                    "[semantic_scholar] 질의 실패: %s (질의: %.40s)",
                    describe_http_error(exc), query.query_string,
                )
                continue

            for item in data.get("data") or []:
                paper_id = clean_whitespace(item.get("paperId"))
                if not paper_id or paper_id in seen:
                    continue
                seen.add(paper_id)
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

        external = item.get("externalIds") or {}
        doi = normalize_doi(external.get("DOI"))
        paper_id = clean_whitespace(item.get("paperId"))
        oa_pdf = (item.get("openAccessPdf") or {}).get("url", "")
        is_oa = bool(item.get("isOpenAccess")) and bool(oa_pdf)

        query = raw.discovered_by_query
        return Resource(
            source_id=self.config.source_id,
            source_type="OPEN_API",
            work_id=build_work_id(doi=doi, identifier=f"s2:{paper_id}", title=title),
            title_original=title,
            authors=normalize_authors(item.get("authors")),
            journal_or_series=clean_whitespace(item.get("venue")),
            publication_date=parse_date(item.get("publicationDate") or item.get("year")),
            discovered_at=self._now(),
            doi=doi,
            official_identifier=f"s2:{paper_id}",
            landing_url=clean_whitespace(item.get("url")) or doi_to_url(doi),
            oa_url=clean_whitespace(oa_pdf),
            license_unknown=not is_oa,
            license="오픈액세스 PDF 확인" if is_oa else "",
            language="en",
            document_type=infer_document_type(
                " ".join(item.get("publicationTypes") or []), title
            ),
            keywords=[clean_whitespace(f) for f in (item.get("fieldsOfStudy") or [])],
            abstract_original=clean_whitespace(item.get("abstract")),
            query_original=query.canonical_ko if query else "",
            query_language=query.language if query else "",
            query_terms_expanded=query.expanded_terms if query else [],
            query_dictionary_version=query.dictionary_version if query else "",
            discovered_by_query=query.query_string if query else "",
        )
