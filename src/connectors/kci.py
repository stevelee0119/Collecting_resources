"""KCI Connector (PRD v2.1 §4.2 A) — 국내 학술 최우선 소스.

접근방식 우선순위:
1. OAI-PMH (키 없이 사용 가능한 공개 메타데이터 경로 — 우선 검토)
2. Open API (API Key 필요)

원문은 KCI 가 제공하는 공개 원문 또는 OA 위치가 확인된 경우만 다운로드합니다.
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
)
from .base import EndpointNotConfiguredError, SourceConnector
from .oai_pmh import OaiPmhClient, OaiPmhError

logger = logging.getLogger(__name__)


class KciConnector(SourceConnector):
    connector_id = "kci"

    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:
        """OAI-PMH 를 우선 시도하고, 실패하면 Open API 로 넘어갑니다."""
        oai = self.config.method("OAI_PMH")
        if oai and oai.endpoint:
            try:
                yield from self._discover_via_oai(oai.endpoint, since, until, queries)
                return
            except OaiPmhError as exc:
                logger.warning("[kci] OAI-PMH 수집 실패, Open API 로 전환합니다: %s", exc)
            except Exception as exc:
                logger.warning("[kci] OAI-PMH 접속 실패, Open API 로 전환합니다: %s", exc)

        # OAI-PMH 를 쓸 수 없으면 Open API (인증정보가 없으면 예외로 건너뜀)
        method = self.require_method("OPEN_API")
        yield from self._discover_via_api(method.endpoint, self.secret_for(method), since, until, queries)

    # ------------------------------------------------------------------
    def _discover_via_oai(
        self, endpoint: str, since: date, until: date, queries: Sequence[Query]
    ) -> Iterator[RawItem]:
        client = OaiPmhClient(
            self.ctx.client, endpoint, str(getattr(self.config, "oai_metadata_prefix", "oai_dc"))
        )
        # OAI-PMH 는 키워드 검색을 지원하지 않으므로 기간 전체를 받아
        # 검색어 사전으로 로컬 필터링합니다.
        needles = _needles_from(queries)
        emitted = 0
        for record in client.list_records(since=since, until=until, max_records=self._limit() * 5):
            haystack = " ".join(
                _flatten(record.get(f)) for f in ("title", "subject", "description")
            ).lower()
            matched = _match_query(haystack, queries, needles)
            if needles and matched is None:
                continue
            record["_access_method"] = "OAI_PMH"
            yield RawItem(
                source_id=self.config.source_id, payload=record, discovered_by_query=matched
            )
            emitted += 1
            if emitted >= self._limit():
                return

    def _discover_via_api(
        self,
        endpoint: str,
        api_key: str | None,
        since: date,
        until: date,
        queries: Sequence[Query],
    ) -> Iterator[RawItem]:
        if not endpoint:
            raise EndpointNotConfiguredError(self.config.name, "OPEN_API")

        # 공식 활용방법 문서의 요청 파라미터: apiCode, key, title, author, pubiYr
        # 일자 범위 필터가 없고 발행연도(pubiYr) 단위만 제공되므로
        # 조회 기간에 걸친 연도를 순회한 뒤 등록일 기준으로 다시 걸러냅니다.
        api_code = str(getattr(self.config, "kci_api_code", "articleSearch"))
        years = range(since.year, until.year + 1)

        emitted = 0
        for query in queries:
            for year in years:
                if emitted >= self._limit():
                    return
                params = {
                    "apiCode": api_code,
                    "key": api_key or "",
                    "title": query.query_string,
                    "pubiYr": year,
                }
                try:
                    response = self.ctx.client.get(endpoint, params=params)
                    response.raise_for_status()
                    records = _parse_kci_xml(response.content)
                except Exception as exc:
                    logger.warning(
                        "[kci] Open API 질의 실패 (%s, %d년): %s", query.query_string, year, exc
                    )
                    continue

                for record in records:
                    record["_access_method"] = "OPEN_API"
                    yield RawItem(
                        source_id=self.config.source_id, payload=record, discovered_by_query=query
                    )
                    emitted += 1
                    if emitted >= self._limit():
                        return

    # ------------------------------------------------------------------
    def normalize(self, raw: RawItem) -> Resource | None:
        payload = raw.payload
        title = clean_whitespace(_first(payload.get("title")))
        if not title:
            return None

        identifiers = _flatten_list(payload.get("identifier"))
        doi = ""
        landing = ""
        for ident in identifiers:
            candidate = normalize_doi(ident)
            if candidate and not doi:
                doi = candidate
            elif ident.startswith("http") and not landing:
                landing = ident

        oai_id = clean_whitespace(payload.get("oai_identifier"))
        official_id = clean_whitespace(payload.get("article_id")) or oai_id
        published = parse_date(_first(payload.get("date")) or payload.get("pub_date"))
        datestamp = parse_date(payload.get("datestamp"))
        rights = clean_whitespace(_first(payload.get("rights")))

        query = raw.discovered_by_query
        return Resource(
            source_id=self.config.source_id,
            source_type=clean_whitespace(payload.get("_access_method")) or "OAI_PMH",
            work_id=build_work_id(doi=doi, identifier=official_id, title=title),
            title_original=title,
            title_ko=title if detect_language(title) == "ko" else "",
            authors=normalize_authors(payload.get("creator") or payload.get("author")),
            publisher=clean_whitespace(_first(payload.get("publisher"))),
            journal_or_series=clean_whitespace(
                _first(payload.get("source")) or payload.get("journal")
            ),
            publication_date=published,
            source_registered_date=datestamp,
            source_modified_date=datestamp,
            discovered_at=self._now(),
            doi=doi,
            official_identifier=official_id,
            landing_url=landing or doi_to_url(doi),
            license=rights,
            # 권리표기가 없으면 라이선스 불명확으로 두고 자동 다운로드하지 않습니다.
            license_unknown=not bool(rights),
            language=clean_whitespace(_first(payload.get("language"))) or detect_language(title),
            document_type=infer_document_type(_first(payload.get("type")), title),
            keywords=_flatten_list(payload.get("subject"))[:12],
            abstract_original=clean_whitespace(_first(payload.get("description"))),
            query_original=query.canonical_ko if query else "",
            query_language=query.language if query else "",
            query_terms_expanded=query.expanded_terms if query else [],
            query_dictionary_version=query.dictionary_version if query else "",
            discovered_by_query=query.query_string if query else "",
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _first(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    return str(value or "")


def _flatten(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return " ".join(str(v) for v in value)
    return str(value or "")


def _flatten_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [clean_whitespace(str(v)) for v in value if clean_whitespace(str(v))]
    return [clean_whitespace(str(value))] if clean_whitespace(str(value)) else []


def _needles_from(queries: Sequence[Query]) -> list[tuple[str, Query]]:
    """질의를 로컬 필터링용 (키워드, Query) 쌍으로 펼칩니다."""
    pairs: list[tuple[str, Query]] = []
    for query in queries:
        for term in query.expanded_terms or [query.query_string]:
            cleaned = term.strip().strip('"').lower()
            if cleaned:
                pairs.append((cleaned, query))
    return pairs


def _match_query(
    haystack: str, queries: Sequence[Query], needles: list[tuple[str, Query]]
) -> Query | None:
    """어떤 검색어로 이 자료가 발견되었는지 되짚습니다 (§10.1 discovered_by_query)."""
    if not needles:
        return queries[0] if queries else None
    for needle, query in needles:
        if needle in haystack:
            if any(ex.lower() in haystack for ex in query.exclude_terms):
                continue
            return query
    return None


def _parse_kci_xml(content: bytes) -> list[dict]:
    """KCI Open API 의 XML 응답을 dict 목록으로 변환합니다.

    KCI 응답 스키마는 신청 유형에 따라 달라질 수 있으므로, 레코드 노드를
    유연하게 찾고 자식 태그를 그대로 담습니다.
    """
    import xml.etree.ElementTree as ET

    root = ET.fromstring(content)
    records: list[dict] = []

    candidates = (
        root.findall(".//record")
        or root.findall(".//item")
        or root.findall(".//outputData/record")
        or root.findall(".//article")
    )
    for node in candidates:
        record: dict[str, list[str]] = {}
        for child in node.iter():
            if child is node:
                continue
            tag = child.tag.split("}")[-1]
            text = clean_whitespace(child.text)
            if text:
                record.setdefault(tag, []).append(text)
        if record:
            records.append(record)  # type: ignore[arg-type]
    return records
