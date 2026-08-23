"""Crossref Connector (PRD v2.1 §4.4 A).

DOI 메타데이터의 기준축. 제목·저자·학술지·발행일·DOI 를 정규화하여
중복 판별의 기준을 제공합니다. 원문은 링크로 보존하고, 실제 OA 원문은
OA Resolver 가 별도로 찾습니다.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from datetime import date

from ..models import Query, RawItem, Resource
from ..normalizers.normalize import (
    build_work_id,
    clean_whitespace,
    detect_language,
    doi_to_url,
    infer_document_type,
    normalize_authors,
    normalize_doi,
    parse_date,
    year_of,
)
from ..http_client import describe_http_error
from .base import SourceConnector

logger = logging.getLogger(__name__)


class CrossrefConnector(SourceConnector):
    connector_id = "crossref"

    ROWS_PER_QUERY = 25

    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:
        method = self.require_method("OPEN_API")
        seen: set[str] = set()
        emitted = 0

        for query in queries:
            if emitted >= self._limit():
                return
            params: dict[str, str | int] = {
                "query.bibliographic": query.query_string,
                # 등록 지연을 고려해 index-date 기준으로 재조회 (§UC-02 look-back)
                "filter": f"from-index-date:{since.isoformat()},until-index-date:{until.isoformat()}",
                "rows": self.ROWS_PER_QUERY,
                "sort": "indexed",
                "order": "desc",
                "select": (
                    "DOI,title,author,container-title,issued,created,indexed,URL,"
                    "abstract,license,link,type,publisher,subject,language"
                ),
            }
            # polite pool 사용을 위한 연락 이메일 (키가 아님)
            if email := self.ctx.contact_email:
                params["mailto"] = email

            try:
                data = self.ctx.client.get_json(method.endpoint, params=params)
            except Exception as exc:
                logger.warning(
                    "[crossref] 질의 실패: %s (질의: %.40s)",
                    describe_http_error(exc), query.query_string,
                )
                continue

            for item in (data.get("message") or {}).get("items", []):
                doi = normalize_doi(item.get("DOI"))
                if not doi or doi in seen:
                    continue
                seen.add(doi)
                yield RawItem(source_id=self.config.source_id, payload=item, discovered_by_query=query)
                emitted += 1
                if emitted >= self._limit():
                    return

    def normalize(self, raw: RawItem) -> Resource | None:
        item = raw.payload
        doi = normalize_doi(item.get("DOI"))
        if not doi:
            return None

        title = clean_whitespace(_first(item.get("title")))
        if not title:
            return None

        authors = normalize_authors(item.get("author"))
        published = parse_date(item.get("issued", {}).get("date-parts"))
        registered = parse_date(item.get("created", {}).get("date-time"))
        modified = parse_date(item.get("indexed", {}).get("date-time"))
        journal = clean_whitespace(_first(item.get("container-title")))

        license_url, license_known = _license_of(item)
        pdf_url = _pdf_link_of(item)

        query = raw.discovered_by_query
        return Resource(
            source_id=self.config.source_id,
            source_type="OPEN_API",
            work_id=build_work_id(doi=doi),
            title_original=title,
            authors=authors,
            publisher=clean_whitespace(item.get("publisher")),
            journal_or_series=journal,
            publication_date=published,
            source_registered_date=registered,
            source_modified_date=modified,
            discovered_at=self._now(),
            doi=doi,
            official_identifier=doi,
            landing_url=clean_whitespace(item.get("URL")) or doi_to_url(doi),
            download_url=pdf_url,
            license=license_url,
            license_unknown=not license_known,
            language=clean_whitespace(item.get("language")) or detect_language(title),
            document_type=infer_document_type(item.get("type"), title),
            keywords=[clean_whitespace(s) for s in (item.get("subject") or [])],
            abstract_original=_strip_jats(item.get("abstract")),
            query_original=query.canonical_ko if query else "",
            query_language=query.language if query else "",
            query_terms_expanded=query.expanded_terms if query else [],
            query_dictionary_version=query.dictionary_version if query else "",
            discovered_by_query=query.query_string if query else "",
        )


class CrossrefResolver:
    """DOI 로 Crossref 메타데이터를 보강하는 IDENTIFIER_RESOLVER 역할 (§4.4 A)."""

    def __init__(self, connector: CrossrefConnector):
        self.connector = connector

    def enrich(self, resource: Resource) -> Resource:
        """DOI 가 있는 자료의 서지정보를 Crossref 기준으로 보완합니다."""
        if not resource.doi:
            return resource
        method = self.connector.config.method("OPEN_API")
        if not method or not method.endpoint:
            return resource
        url = f"{method.endpoint.rstrip('/')}/{resource.doi}"
        params = {}
        if email := self.connector.ctx.contact_email:
            params["mailto"] = email
        try:
            data = self.connector.ctx.client.get_json(url, params=params)
        except Exception as exc:
            logger.debug("[crossref] DOI 보강 실패 (%s): %s", resource.doi, exc)
            return resource

        item = data.get("message") or {}
        if not resource.journal_or_series:
            resource.journal_or_series = clean_whitespace(_first(item.get("container-title")))
        if not resource.publisher:
            resource.publisher = clean_whitespace(item.get("publisher"))
        if not resource.authors:
            resource.authors = normalize_authors(item.get("author"))
        if not resource.publication_date:
            resource.publication_date = parse_date(item.get("issued", {}).get("date-parts"))
        if not resource.work_id:
            resource.work_id = build_work_id(
                doi=resource.doi, title=resource.title_original, year=year_of(resource.publication_date)
            )
        return resource


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _first(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    return str(value or "")


def _license_of(item: dict) -> tuple[str, bool]:
    """라이선스 URL 과 '확인됨' 여부를 반환합니다."""
    licenses = item.get("license") or []
    for lic in licenses:
        url = clean_whitespace(lic.get("URL"))
        if not url:
            continue
        lowered = url.lower()
        # 명시적 오픈 라이선스만 '확인됨' 으로 취급 (§8.4)
        if "creativecommons.org" in lowered or "opensource.org" in lowered:
            return url, True
        return url, False
    return "", False


def _pdf_link_of(item: dict) -> str:
    for link in item.get("link") or []:
        if str(link.get("content-type", "")).lower() == "application/pdf":
            return clean_whitespace(link.get("URL"))
    return ""


def _strip_jats(abstract: object) -> str:
    """Crossref 초록의 JATS 태그를 제거합니다."""
    import re

    if not abstract:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(abstract))
    return clean_whitespace(text)
