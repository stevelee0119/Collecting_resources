"""설정 주도형 Open API Connector 기반 클래스.

국내 공공 Open API 는 신청 유형에 따라 엔드포인트·파라미터·응답 필드명이
달라집니다. 그래서 필드 매핑을 코드에 고정하지 않고 `sources.yaml` 의
`request` / `field_map` 블록으로 주입받습니다.

```yaml
request:
  method: GET                 # GET | POST
  format: json                # json | xml
  key_param: serviceKey       # 인증정보를 실을 파라미터명 (헤더면 key_header 사용)
  query_param: query
  from_param: startDate
  until_param: endDate
  date_format: "%Y%m%d"
  page_size_param: numOfRows
  page_size: 50
  static_params:
    type: json
  records_path: response.body.items.item
field_map:
  title: title
  authors: author
  ...
```
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Sequence
from datetime import date
from typing import Any

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
from ..http_client import describe_http_error
from .base import EndpointNotConfiguredError, SourceConnector

logger = logging.getLogger(__name__)


def dig(data: Any, path: str, default: Any = None) -> Any:
    """`a.b.c` 경로로 중첩 dict/list 를 탐색합니다."""
    if not path:
        return default
    node = data
    for part in path.split("."):
        if isinstance(node, list):
            node = node[0] if node else None
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


class GenericApiConnector(SourceConnector):
    """`request` / `field_map` 설정으로 동작하는 Open API Connector."""

    #: 하위 클래스가 제공하는 기본 요청 설정
    default_request: dict[str, Any] = {}
    #: 하위 클래스가 제공하는 기본 필드 매핑
    default_field_map: dict[str, str] = {}
    #: 이 소스가 제공하는 자료의 기본 문서유형
    default_document_type: str = "기타"

    # ------------------------------------------------------------------
    @property
    def request_config(self) -> dict[str, Any]:
        merged = dict(self.default_request)
        merged.update(getattr(self.config, "request", None) or {})
        return merged

    @property
    def field_map(self) -> dict[str, str]:
        merged = dict(self.default_field_map)
        merged.update(getattr(self.config, "field_map", None) or {})
        return merged

    # ------------------------------------------------------------------
    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:
        method = self.require_method("OPEN_API", "REST_API")
        if not method.endpoint:
            raise EndpointNotConfiguredError(self.config.name, "OPEN_API")

        req = self.request_config
        secret = self.secret_for(method)
        date_format = str(req.get("date_format", "%Y-%m-%d"))
        emitted = 0

        for query in queries:
            if emitted >= self._limit():
                return

            params: dict[str, Any] = dict(req.get("static_params") or {})
            if key_param := req.get("key_param"):
                params[str(key_param)] = secret or ""
            if query_param := req.get("query_param"):
                params[str(query_param)] = query.query_string
            if from_param := req.get("from_param"):
                params[str(from_param)] = since.strftime(date_format)
            if until_param := req.get("until_param"):
                params[str(until_param)] = until.strftime(date_format)
            if size_param := req.get("page_size_param"):
                params[str(size_param)] = int(req.get("page_size", 50))

            headers: dict[str, str] = dict(req.get("static_headers") or {})
            if key_header := req.get("key_header"):
                headers[str(key_header)] = str(req.get("key_header_prefix", "")) + (secret or "")

            try:
                records = self._call(method.endpoint, req, params, headers)
            except Exception as exc:
                logger.warning(
                    "[%s] 질의 실패: %s (질의: %.40s)",
                    self.config.source_id, describe_http_error(exc), query.query_string,
                )
                continue

            for record in records:
                yield RawItem(
                    source_id=self.config.source_id, payload=record, discovered_by_query=query
                )
                emitted += 1
                if emitted >= self._limit():
                    return

    # ------------------------------------------------------------------
    def _call(
        self,
        endpoint: str,
        req: dict[str, Any],
        params: dict[str, Any],
        headers: dict[str, str],
    ) -> list[dict[str, Any]]:
        http_method = str(req.get("method", "GET")).upper()
        response = self.ctx.client.request(
            http_method,
            endpoint,
            params=params if http_method == "GET" else None,
            data=params if http_method == "POST" else None,
            headers=headers or None,
        )
        response.raise_for_status()

        if str(req.get("format", "json")).lower() == "xml":
            return self._parse_xml(response.content, str(req.get("records_node", "")))
        payload = response.json()
        records = dig(payload, str(req.get("records_path", "")), payload)
        if isinstance(records, dict):
            records = [records]
        return [r for r in (records or []) if isinstance(r, dict)]

    @staticmethod
    def _parse_xml(content: bytes, records_node: str) -> list[dict[str, Any]]:
        root = ET.fromstring(content)
        nodes = root.findall(f".//{records_node}") if records_node else []
        if not nodes:
            for candidate in ("item", "record", "row", "article", "law"):
                nodes = root.findall(f".//{candidate}")
                if nodes:
                    break
        records: list[dict[str, Any]] = []
        for node in nodes:
            record: dict[str, Any] = {}
            for child in node:
                tag = child.tag.split("}")[-1]
                text = clean_whitespace(child.text)
                if text:
                    record[tag] = text
            if record:
                records.append(record)
        return records

    # ------------------------------------------------------------------
    def normalize(self, raw: RawItem) -> Resource | None:
        fm = self.field_map
        item = raw.payload

        def field(name: str, default: str = "") -> str:
            path = fm.get(name, "")
            value = dig(item, path) if path else None
            if value is None and path and path in item:
                value = item[path]
            if isinstance(value, list):
                value = value[0] if value else ""
            return clean_whitespace(value) or default

        title = field("title")
        if not title:
            return None

        doi = normalize_doi(field("doi"))
        identifier = field("identifier")
        landing = field("landing_url")
        download = field("download_url")
        license_text = field("license")
        published = parse_date(field("publication_date"))
        registered = parse_date(field("registered_date")) or published
        modified = parse_date(field("modified_date")) or registered

        query = raw.discovered_by_query
        return Resource(
            source_id=self.config.source_id,
            source_type="OPEN_API",
            work_id=build_work_id(
                doi=doi,
                identifier=f"{self.config.source_id}:{identifier}" if identifier else "",
                title=title,
            ),
            title_original=title,
            title_ko=title if detect_language(title) == "ko" else "",
            authors=normalize_authors(dig(item, fm.get("authors", "")) or field("authors")),
            publisher=field("publisher") or self.config.name,
            journal_or_series=field("series"),
            publication_date=published,
            source_registered_date=registered,
            source_modified_date=modified,
            discovered_at=self._now(),
            doi=doi,
            official_identifier=f"{self.config.source_id}:{identifier}" if identifier else "",
            landing_url=landing or doi_to_url(doi),
            download_url=download,
            license=license_text,
            license_unknown=not bool(license_text),
            language=field("language") or detect_language(title),
            document_type=infer_document_type(field("document_type"), title)
            if field("document_type") or title
            else self.default_document_type,
            keywords=_as_list(dig(item, fm.get("keywords", ""))),
            abstract_original=field("abstract"),
            query_original=query.canonical_ko if query else "",
            query_language=query.language if query else "",
            query_terms_expanded=query.expanded_terms if query else [],
            query_dictionary_version=query.dictionary_version if query else "",
            discovered_by_query=query.query_string if query else "",
        )


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        parts = [p.strip() for p in value.replace(";", ",").split(",")]
        return [p for p in parts if p]
    if isinstance(value, (list, tuple)):
        return [clean_whitespace(str(v)) for v in value if clean_whitespace(str(v))]
    return [clean_whitespace(str(value))]
