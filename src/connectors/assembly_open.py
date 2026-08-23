"""열린국회정보(open.assembly.go.kr) Open API Connector.

국회사무처가 운영하는 국회정보 개방 포털입니다. API 마다 난수형 ID 가 부여되고
주소는 `https://open.assembly.go.kr/portal/openapi/{API_ID}` 형태입니다.

인증키는 **공공데이터포털 키가 아니라 열린국회정보 전용 키**이며 `KEY`
파라미터로 전달합니다 (`ASSEMBLY_API_KEY`).

## 응답 구조를 관대하게 파싱하는 이유

이 포털의 JSON 응답은 아래 형태가 관례입니다.

```
{ "<API_ID>": [ { "head": [ {"list_total_count": N},
                            {"RESULT": {"CODE": "INFO-000", "MESSAGE": "..."}} ] },
                { "row": [ {...}, {...} ] } ] }
```

다만 이 구조를 **공식 문서로 직접 대조하지는 못했습니다**(개발 환경에서 해당
도메인 접속이 차단되어 있고, API ID 별 상세 페이지는 검색으로도 확인되지
않습니다). 그래서 구조를 단정하지 않고 다음 순서로 레코드를 찾습니다.

1. 응답 어디에 있든 `row` 키에 달린 딕셔너리 목록
2. 그것이 없으면 응답에서 가장 큰 딕셔너리 목록

둘 다 실패하면 **응답의 실제 키 목록을 경고 로그로 남깁니다.** 그 값을 보고
`sources.yaml` 의 `field_map` 을 맞추면 코드 수정 없이 동작합니다.
엔드포인트와 달리 이것은 응답 해석에 대한 보수적 추정이며, 틀려도 잘못된
요청을 보내지 않습니다.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from datetime import date
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..models import Query, RawItem, Resource
from ..normalizers.normalize import (
    build_work_id,
    clean_whitespace,
    infer_document_type,
    normalize_authors,
    parse_date,
)
from ..http_client import describe_http_error
from .base import SourceConnector

logger = logging.getLogger(__name__)

#: 정상 처리 코드. 그 외에는 메시지를 로그로 남깁니다.
RESULT_OK = "INFO-000"
#: 조건에 맞는 데이터가 없음 — 오류가 아닙니다.
RESULT_NO_DATA = "INFO-200"

#: title 을 못 찾았을 때 후보로 볼 키 이름 조각
TITLE_HINTS = ("TITLE", "NM", "제목", "명")


class AssemblyOpenConnector(SourceConnector):
    connector_id = "assembly_open"

    default_document_type = "연구보고서"

    PAGE_SIZE = 100

    #: 한 질의당 최대 페이지 수. 목록이 최신순이므로 보통 1페이지로 충분합니다.
    MAX_PAGES = 5

    #: 응답 필드명이 확인되지 않아 기본 매핑을 두지 않습니다.
    #: sources.yaml 의 field_map 이 비어 있으면 이름 규칙으로 추정합니다.
    default_field_map: dict[str, str] = {}

    # ------------------------------------------------------------------
    @property
    def field_map(self) -> dict[str, str]:
        """`sources.yaml` 의 field_map. 빈 값은 제거해 추정 규칙에 맡깁니다."""
        merged = dict(self.default_field_map)
        merged.update(getattr(self.config, "field_map", None) or {})
        return {k: v for k, v in merged.items() if v}

    # ------------------------------------------------------------------
    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:
        method = self.require_method("OPEN_API")
        key = self.secret_for(method)
        page_size = min(self.PAGE_SIZE, int(getattr(self.config, "max_page_size", self.PAGE_SIZE)))
        query_param = str(getattr(self.config, "assembly_query_param", "") or "")
        static = dict(getattr(self.config, "assembly_static_params", None) or {})

        seen: set[str] = set()
        emitted = 0

        for query in queries:
            if emitted >= self._limit():
                return

            # 목록은 최신순이므로, since 보다 오래된 레코드가 나오면 멈춥니다.
            for page in range(1, self.MAX_PAGES + 1):
                params: dict[str, Any] = {
                    "KEY": key or "",
                    "Type": "json",
                    "pIndex": page,
                    "pSize": page_size,
                    **static,
                }
                # 검색어 파라미터명은 API 마다 다릅니다. 확인되면 sources.yaml 에 넣고,
                # 그 전까지는 전체 목록을 받아 파이프라인이 주제·기간으로 거릅니다.
                if query_param:
                    params[query_param] = query.query_string

                try:
                    data = self.ctx.client.get_json(method.endpoint, params=params)
                except Exception as exc:
                    logger.warning(
                        "[%s] 질의 실패: %s (질의: %.40s)",
                        self.config.source_id, describe_http_error(exc), query.query_string,
                    )
                    break

                code, message = _result_status(data)
                if code and not code.startswith(RESULT_OK):
                    level = logger.info if code.startswith(RESULT_NO_DATA) else logger.warning
                    level("[%s] 응답 코드 %s: %s", self.config.source_id, code, message)
                    break

                rows = _extract_rows(data)
                if not rows:
                    if page == 1:
                        logger.warning(
                            "[%s] 레코드를 찾지 못했습니다. 응답 최상위 키: %s",
                            self.config.source_id,
                            sorted(data)[:20] if isinstance(data, dict) else type(data),
                        )
                    break

                # 목록은 최신순이 관례지만 그것에 기대어 페이지 중간에서 끊지는
                # 않습니다. 순서가 어긋나면 유효한 레코드를 조용히 잃기 때문입니다.
                # 페이지를 끝까지 본 뒤, 그 페이지 전체가 기간 이전이면 멈춥니다.
                older_than_window = 0
                dated_rows = 0
                for row in rows:
                    identifier = self._identifier_of(row)
                    key_value = identifier or _title_of(row, self.field_map)
                    if not key_value or key_value in seen:
                        continue

                    published = parse_date(
                        _first(row, self.field_map.get("publication_date", ""), "")
                    )
                    if published:
                        dated_rows += 1
                        if published < since:
                            older_than_window += 1
                        if not (since <= published <= until):
                            continue

                    seen.add(key_value)
                    yield RawItem(
                        source_id=self.config.source_id, payload=row, discovered_by_query=query
                    )
                    emitted += 1
                    if emitted >= self._limit():
                        return

                page_is_all_old = dated_rows > 0 and older_than_window == dated_rows
                if page_is_all_old or len(rows) < page_size:
                    break

    # ------------------------------------------------------------------
    def _identifier_of(self, row: dict) -> str:
        """식별자. 전용 필드가 없으면 URL 의 쿼리 파라미터에서 꺼냅니다.

        NARS 현안분석처럼 목록에 ID 필드가 없고 파일 URL 에만
        `?doc_id=...` 로 들어 있는 경우가 있습니다.
        """
        value = clean_whitespace(str(_first(row, self.field_map.get("identifier", ""), "") or ""))
        if value:
            return value

        id_param = str(getattr(self.config, "assembly_id_param", "") or "")
        if not id_param:
            return ""
        for field in ("download_url", "landing_url"):
            url = clean_whitespace(str(_first(row, self.field_map.get(field, ""), "") or ""))
            if not url:
                continue
            found = parse_qs(urlparse(url).query).get(id_param)
            if found and found[0]:
                return clean_whitespace(found[0])
        return ""

    # ------------------------------------------------------------------
    def normalize(self, raw: RawItem) -> Resource | None:
        row = raw.payload
        fields = self.field_map

        title = _title_of(row, fields)
        if not title:
            logger.warning(
                "[%s] 제목 필드를 찾지 못했습니다. 응답 필드: %s",
                self.config.source_id, sorted(k for k in row if isinstance(k, str))[:30],
            )
            return None

        identifier = self._identifier_of(row)
        landing = clean_whitespace(str(_first(row, fields.get("landing_url", ""), "")))
        template = str(getattr(self.config, "landing_url_template", "") or "")
        if not landing and template and identifier:
            landing = template.format(id=identifier)

        query = raw.discovered_by_query
        return Resource(
            source_id=self.config.source_id,
            source_type="OPEN_API",
            work_id=build_work_id(
                identifier=f"{self.config.source_id}:{identifier}" if identifier else "",
                title=title,
            ),
            title_original=title,
            title_ko=title,
            authors=normalize_authors(_first(row, fields.get("authors", ""), "")),
            publisher=clean_whitespace(str(_first(row, fields.get("publisher", ""), "")))
            or self.config.name,
            publication_date=parse_date(_first(row, fields.get("publication_date", ""), "")),
            source_registered_date=parse_date(_first(row, fields.get("registered_date", ""), "")),
            discovered_at=self._now(),
            official_identifier=f"{self.config.source_id}:{identifier}" if identifier else "",
            landing_url=landing,
            download_url=clean_whitespace(str(_first(row, fields.get("download_url", ""), ""))),
            license_unknown=True,
            language="ko",
            document_type=infer_document_type(
                _first(row, fields.get("document_type", ""), ""), title
            )
            or self.default_document_type,
            abstract_original=clean_whitespace(str(_first(row, fields.get("abstract", ""), ""))),
            query_original=query.canonical_ko if query else "",
            query_language=query.language if query else "",
            query_terms_expanded=query.expanded_terms if query else [],
            query_dictionary_version=query.dictionary_version if query else "",
            discovered_by_query=query.query_string if query else "",
        )


# ---------------------------------------------------------------------------
# 응답 파싱 도우미 — 구조를 단정하지 않습니다.
# ---------------------------------------------------------------------------

def _first(row: dict, field: str, default: Any) -> Any:
    """`field_map` 이 가리키는 값. 대소문자 차이를 허용합니다."""
    if not field:
        return default
    if field in row:
        return row[field]
    lowered = {str(k).lower(): v for k, v in row.items()}
    return lowered.get(field.lower(), default)


def _title_of(row: dict, fields: dict) -> str:
    """설정된 제목 필드, 없으면 이름 규칙으로 추정합니다."""
    title = clean_whitespace(str(_first(row, fields.get("title", ""), "") or ""))
    if title:
        return title
    candidates = [
        clean_whitespace(str(value))
        for key, value in row.items()
        if isinstance(key, str)
        and isinstance(value, str)
        and any(hint in key.upper() for hint in TITLE_HINTS)
        and "URL" not in key.upper()
    ]
    return max(candidates, key=len) if candidates else ""


def _result_status(data: Any) -> tuple[str, str]:
    """응답 어딘가에 있는 RESULT 코드/메시지를 찾습니다."""
    for node in _walk(data):
        if isinstance(node, dict) and "RESULT" in node:
            result = node["RESULT"]
            if isinstance(result, dict):
                return (
                    clean_whitespace(str(result.get("CODE", ""))),
                    clean_whitespace(str(result.get("MESSAGE", ""))),
                )
    return "", ""


def _extract_rows(data: Any) -> list[dict]:
    """레코드 목록을 찾습니다.

    1순위는 `row` 키에 달린 딕셔너리 목록(포털 관례),
    2순위는 응답에서 가장 큰 딕셔너리 목록입니다.
    """
    for node in _walk(data):
        if isinstance(node, dict):
            rows = node.get("row")
            if isinstance(rows, list) and rows and all(isinstance(r, dict) for r in rows):
                return rows

    best: list[dict] = []
    for node in _walk(data):
        if (
            isinstance(node, list)
            and node
            and all(isinstance(r, dict) for r in node)
            and len(node) > len(best)
            # head 처럼 메타데이터만 담긴 목록은 제외합니다.
            and not any("RESULT" in r or "list_total_count" in r for r in node)
        ):
            best = node
    return best


def _walk(node: Any) -> Iterator[Any]:
    """중첩된 dict/list 를 모두 순회합니다."""
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)
