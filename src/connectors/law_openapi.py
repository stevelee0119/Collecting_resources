"""국가법령정보 공동활용 Connector (PRD v2.1 §4.2 F).

법령·행정규칙·판례를 수집합니다. 공포일·시행일·개정일을 각각 별도 필드로
저장하여 "신규 법령"과 "개정 법령"을 구분합니다.

인증정보는 API Key 가 아니라 신청 시 부여되는 사용자 식별자(OC)입니다.
원문은 공식 Landing Page 로 보존합니다(`download_policy: link_only`).
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections.abc import Iterator, Sequence
from datetime import date

from ..models import Query, RawItem, Resource
from ..normalizers.normalize import (
    build_work_id,
    clean_whitespace,
    parse_date,
)
from .base import SourceConnector

logger = logging.getLogger(__name__)

#: target 코드 → (문서유형, 주 검색 필드)
TARGET_META: dict[str, tuple[str, str]] = {
    "law": ("법령", "법령명한글"),
    "admrul": ("지침", "행정규칙명"),
    "prec": ("판례", "사건명"),
    "expc": ("정책자료", "안건명"),
    # 위원회 결정문 계열. 응답 필드명은 아직 대조하지 못해 제목 추출은
    # _fallback_title() 의 일반 규칙에 맡깁니다.
    "nhrck": ("결정문", "제목"),
}


class LawOpenApiConnector(SourceConnector):
    connector_id = "law_openapi"

    DISPLAY = 100

    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:
        method = self.require_method("OPEN_API")
        oc = self.secret_for(method)
        targets = list(getattr(self.config, "law_targets", None) or ["law"])
        emitted = 0

        for target in targets:
            doc_type, _ = TARGET_META.get(target, ("기타", "법령명한글"))
            for query in queries:
                if emitted >= self._limit():
                    return
                params = {
                    "OC": oc or "",
                    "target": target,
                    "type": "XML",
                    "query": query.query_string,
                    "display": int(getattr(self.config, "law_display", self.DISPLAY)),
                    "page": 1,
                    "sort": "ddes",  # 최근 공포일 순
                }
                # target 별 날짜범위 파라미터(예: 판례 prncYd)를 지원하면 함께 보냅니다.
                date_params = getattr(self.config, "law_date_param", None) or {}
                if date_param := date_params.get(target):
                    params[date_param] = f"{since.strftime('%Y%m%d')}~{until.strftime('%Y%m%d')}"
                try:
                    response = self.ctx.client.get(method.endpoint, params=params)
                    response.raise_for_status()
                    records = _parse_law_xml(response.content)
                except Exception as exc:
                    logger.warning(
                        "[law_go_kr] 질의 실패 (target=%s, %s): %s", target, query.query_string, exc
                    )
                    continue

                for record in records:
                    record["_target"] = target
                    record["_document_type"] = doc_type
                    # 기간 필터 — 공포일/선고일 기준
                    key_date = _primary_date(record)
                    if key_date and not (since <= key_date <= until):
                        continue
                    yield RawItem(
                        source_id=self.config.source_id, payload=record, discovered_by_query=query
                    )
                    emitted += 1
                    if emitted >= self._limit():
                        return

    # ------------------------------------------------------------------
    def normalize(self, raw: RawItem) -> Resource | None:
        item = raw.payload
        target = str(item.get("_target", "law"))
        doc_type = str(item.get("_document_type", "법령"))

        title = clean_whitespace(
            item.get("법령명한글")
            or item.get("행정규칙명")
            or item.get("사건명")
            or item.get("안건명")
            or item.get("제목")
        ) or _fallback_title(item)
        if not title:
            # 어떤 필드가 실제로 오는지 알아야 TARGET_META 를 보완할 수 있습니다.
            logger.warning(
                "[%s] 제목 필드를 찾지 못했습니다 (target=%s). 응답 필드: %s",
                self.config.source_id,
                target,
                sorted(k for k in item if not k.startswith("_")),
            )
            return None

        identifier = clean_whitespace(
            item.get("법령ID")
            or item.get("행정규칙ID")
            or item.get("판례일련번호")
            or item.get("ID")
        )
        landing = clean_whitespace(item.get("법령상세링크") or item.get("행정규칙상세링크") or item.get("판례상세링크"))
        if landing and landing.startswith("/"):
            landing = f"https://www.law.go.kr{landing}"

        promulgated = parse_date(item.get("공포일자"))
        enforced = parse_date(item.get("시행일자"))
        decided = parse_date(item.get("선고일자"))

        # 발행일 = 공포일(법령) 또는 선고일(판례)
        publication_date = promulgated or decided
        # 개정 여부 판단을 위해 시행일을 수정일로 둡니다.
        modified_date = enforced or promulgated or decided

        revision_type = clean_whitespace(item.get("제개정구분명"))

        query = raw.discovered_by_query
        resource = Resource(
            source_id=self.config.source_id,
            source_type="OPEN_API",
            work_id=build_work_id(identifier=f"law:{target}:{identifier}", title=title),
            title_original=title,
            title_ko=title,
            publisher=clean_whitespace(item.get("소관부처명") or item.get("법원명")) or "국가법령정보센터",
            journal_or_series=doc_type,
            publication_date=publication_date,
            source_registered_date=promulgated,
            source_modified_date=modified_date,
            discovered_at=self._now(),
            official_identifier=f"law:{target}:{identifier}",
            landing_url=landing,
            license="공공누리(국가법령정보센터 이용조건 확인 필요)",
            license_unknown=True,
            language="ko",
            document_type=doc_type,
            keywords=[k for k in [revision_type, clean_whitespace(item.get("법령구분명"))] if k],
            abstract_original=clean_whitespace(item.get("판시사항") or item.get("판결요지")),
            query_original=query.canonical_ko if query else "",
            query_language=query.language if query else "",
            query_terms_expanded=query.expanded_terms if query else [],
            query_dictionary_version=query.dictionary_version if query else "",
            discovered_by_query=query.query_string if query else "",
        )
        # 공포·시행·개정일을 개별 필드로도 보존합니다 (§4.2 F 특이사항).
        resource.score_breakdown = {}
        setattr(resource, "promulgation_date", promulgated.isoformat() if promulgated else "")
        setattr(resource, "enforcement_date", enforced.isoformat() if enforced else "")
        setattr(resource, "revision_type", revision_type)
        return resource


# ---------------------------------------------------------------------------

def _parse_law_xml(content: bytes) -> list[dict]:
    root = ET.fromstring(content)
    records: list[dict] = []
    for node in root.findall(".//law") + root.findall(".//prec") + root.findall(".//admrul"):
        record = {}
        for child in node:
            tag = child.tag.split("}")[-1]
            text = clean_whitespace(child.text)
            if text:
                record[tag] = text
        if record:
            records.append(record)
    if records:
        return records
    # 스키마가 다른 경우 최상위 반복 노드를 추정합니다.
    for child in root:
        if len(list(child)) > 1:
            record = {c.tag.split("}")[-1]: clean_whitespace(c.text) for c in child if c.text}
            if record:
                records.append(record)
    return records


def _fallback_title(item: dict) -> str:
    """알려지지 않은 target 의 제목 필드를 일반 규칙으로 추정합니다.

    법제처 DRF 응답은 target 마다 필드명이 다릅니다(법령명한글·사건명·안건명 …).
    확인되지 않은 target 이라도 수집이 멈추지 않도록, 이름이 `명`/`제목`으로
    끝나는 필드 중 가장 긴 값을 제목으로 씁니다. 엔드포인트와 달리 이것은
    응답 해석에 대한 보수적 추정이며, 틀려도 잘못된 요청을 보내지 않습니다.
    """
    candidates = [
        clean_whitespace(value)
        for key, value in item.items()
        if not key.startswith("_")
        and isinstance(value, str)
        and (key.endswith("명") or key.endswith("제목"))
        and "링크" not in key
    ]
    return max(candidates, key=len) if candidates else ""


def _primary_date(record: dict) -> date | None:
    return parse_date(record.get("공포일자") or record.get("선고일자") or record.get("시행일자"))
