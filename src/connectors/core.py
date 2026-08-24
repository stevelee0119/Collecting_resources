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
from ..http_client import describe_http_error
from .base import SourceConnector

logger = logging.getLogger(__name__)


#: CORE v3 문서상 **검색 가능한** 날짜 관련 속성 (2026-08-24 운영자 확인).
#: 응답 본문에 있는 이름과 검색 가능한 이름이 다르므로 주의합니다
#: (예: publishedDate 는 응답에 있으나 검색 속성이 아닙니다).
CORE_DATE_FIELDS = ("depositedDate", "createdDate", "yearPublished")

#: 색인에 없는 속성으로 질의했을 때 CORE 가 돌려주는 문구.
UNKNOWN_PROPERTY_HINT = "Could not find a property"


class CoreConnector(SourceConnector):
    connector_id = "core"

    PAGE_SIZE = 30

    def _headers(self) -> dict[str, str]:
        method = self.require_method("OPEN_API")
        token = self.secret_for(method)
        return {"Authorization": f"Bearer {token}"} if token else {}

    # ------------------------------------------------------------------
    def _date_candidates(self) -> list[str]:
        """시도할 날짜 속성 순서. 마지막 빈 문자열은 '날짜 조건 없음'입니다."""
        configured = str(getattr(self.config, "core_date_field", "") or "")
        ordered = [configured] if configured else []
        ordered += [f for f in CORE_DATE_FIELDS if f != configured]
        return [*ordered, ""]

    @staticmethod
    def _date_predicate(field: str, since: date) -> str:
        """속성마다 값의 형식이 다릅니다. yearPublished 는 연도 정수입니다."""
        if field == "yearPublished":
            return f"{field}>={since.year}"
        return f"{field}>={since.isoformat()}"

    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:
        method = self.require_method("OPEN_API")
        headers = self._headers()
        seen: set[str] = set()
        emitted = 0
        # 한 번 통한 속성은 이 실행 안에서 계속 씁니다.
        working_field: str | None = None

        for query in queries:
            if emitted >= self._limit():
                return

            candidates = [working_field] if working_field is not None else self._date_candidates()
            data = None
            for attempt_field in candidates:
                body: dict[str, object] = {
                    "q": query.query_string,
                    "limit": self.PAGE_SIZE,
                }
                if attempt_field:
                    body["q"] = (
                        f"({query.query_string}) AND {self._date_predicate(attempt_field, since)}"
                    )
                    body["sort"] = f"{attempt_field}:desc"
                # 후보를 떠보는 호출은 실패가 곧 정보이므로 재시도하지 않습니다.
                probing = working_field is None and attempt_field != ""
                try:
                    response = self.ctx.client.post(
                        method.endpoint,
                        json=body,
                        headers=headers,
                        max_retries=0 if probing else None,
                    )
                    response.raise_for_status()
                    data = response.json()
                except Exception as exc:
                    described = describe_http_error(exc)
                    # 색인에 없는 속성이면 다음 후보로 넘어갑니다.
                    if attempt_field and UNKNOWN_PROPERTY_HINT in described:
                        logger.info(
                            "[core] '%s' 는 검색 가능한 속성이 아닙니다. 다음 후보를 시도합니다.",
                            attempt_field,
                        )
                        continue
                    logger.warning(
                        "[core] 질의 실패: %s (질의: %.40s)", described, query.query_string
                    )
                    break

                if working_field is None:
                    working_field = attempt_field
                    if attempt_field:
                        logger.info("[core] 날짜 속성 '%s' 로 조회합니다.", attempt_field)
                    else:
                        logger.warning(
                            "[core] 쓸 수 있는 날짜 속성을 찾지 못해 날짜 조건 없이 조회합니다. "
                            "후보: %s. 공식 문서에서 확인해 sources.yaml 의 core_date_field 에 "
                            "넣으면 서버에서 걸러집니다.",
                            ", ".join(CORE_DATE_FIELDS),
                        )
                break

            if data is None:
                continue

            for item in data.get("results") or []:
                item_id = clean_whitespace(str(item.get("id", "")))
                if not item_id or item_id in seen:
                    continue
                published = parse_date(item.get("publishedDate") or item.get("createdDate"))
                # 서버에서 날짜를 못 거른 경우를 대비해 양쪽 경계를 모두 봅니다.
                if published and not (since <= published <= until):
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
