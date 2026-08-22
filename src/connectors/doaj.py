"""DOAJ Connector (PRD v2.1 §4.4 F).

검증된 오픈액세스 저널·논문 메타데이터를 수집합니다.
DOAJ 등재 논문은 정의상 오픈액세스이므로 원문 확보 후보로 우선합니다.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from datetime import date
from urllib.parse import quote

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


class DoajConnector(SourceConnector):
    connector_id = "doaj"

    PAGE_SIZE = 50

    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:
        method = self.require_method("OPEN_API")
        # 공식 문서상 pageSize 상한은 100 입니다.
        page_size = min(self.PAGE_SIZE, int(getattr(self.config, "max_page_size", 100)))
        seen: set[str] = set()
        emitted = 0

        for query in queries:
            if emitted >= self._limit():
                return
            # DOAJ 는 경로에 질의를 담는 Elasticsearch 문법을 사용합니다.
            search = (
                f"({query.query_string}) AND "
                f"last_updated:[{since.isoformat()} TO {until.isoformat()}]"
            )
            url = f"{method.endpoint.rstrip('/')}/{quote(search, safe='')}"
            params = {"pageSize": page_size, "sort": "last_updated:desc"}
            if api_key := self.secret_for(method):
                params["api_key"] = api_key

            try:
                data = self.ctx.client.get_json(url, params=params)
            except Exception as exc:
                logger.warning("[doaj] 질의 실패 (%s): %s", query.query_string, exc)
                continue

            for item in data.get("results") or []:
                item_id = clean_whitespace(item.get("id"))
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
        bibjson = item.get("bibjson") or {}
        title = clean_whitespace(bibjson.get("title"))
        if not title:
            return None

        doi = ""
        landing = ""
        fulltext = ""
        for ident in bibjson.get("identifier") or []:
            if str(ident.get("type", "")).lower() == "doi":
                doi = normalize_doi(ident.get("id"))
        for link in bibjson.get("link") or []:
            link_type = str(link.get("type", "")).lower()
            if link_type == "fulltext":
                fulltext = clean_whitespace(link.get("url"))
            elif not landing:
                landing = clean_whitespace(link.get("url"))

        journal = (bibjson.get("journal") or {}).get("title", "")
        published = parse_date(
            f"{bibjson.get('year', '')}-{str(bibjson.get('month', '1')).zfill(2)}-01"
            if bibjson.get("year")
            else None
        )
        license_info = (bibjson.get("journal") or {}).get("license") or []
        license_name = clean_whitespace(license_info[0].get("type")) if license_info else ""

        query = raw.discovered_by_query
        return Resource(
            source_id=self.config.source_id,
            source_type="OPEN_API",
            work_id=build_work_id(doi=doi, identifier=clean_whitespace(item.get("id")), title=title),
            title_original=title,
            authors=normalize_authors(bibjson.get("author")),
            publisher=clean_whitespace((bibjson.get("journal") or {}).get("publisher")),
            journal_or_series=clean_whitespace(journal),
            publication_date=published,
            source_registered_date=parse_date(item.get("created_date")),
            source_modified_date=parse_date(item.get("last_updated")),
            discovered_at=self._now(),
            doi=doi,
            official_identifier=clean_whitespace(item.get("id")),
            landing_url=landing or doi_to_url(doi),
            oa_url=fulltext,
            license=license_name or "DOAJ 등재 오픈액세스",
            # DOAJ 등재 = 검증된 오픈액세스
            license_unknown=False,
            language=clean_whitespace(_first(bibjson.get("journal", {}).get("language"))) or "en",
            document_type=infer_document_type("article", title),
            keywords=[clean_whitespace(k) for k in (bibjson.get("keywords") or [])],
            abstract_original=clean_whitespace(bibjson.get("abstract")),
            query_original=query.canonical_ko if query else "",
            query_language=query.language if query else "",
            query_terms_expanded=query.expanded_terms if query else [],
            query_dictionary_version=query.dictionary_version if query else "",
            discovered_by_query=query.query_string if query else "",
        )


def _first(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    return str(value or "")
