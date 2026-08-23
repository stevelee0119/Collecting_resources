"""디지털집현전 Connector (국가지식정보 통합플랫폼).

국가기관·지방자치단체·공공기관이 생산·관리하는 지식정보의 메타데이터
(제목·날짜·저자·요약·주제어)를 표준화해 제공하는 전 국민 지식 플랫폼입니다.

플랫폼이 제공하는 Open API 는 두 종류입니다.
1. 국가지식정보를 메타데이터로 제공하는 API
2. 디지털집현전이 보유한 국가지식정보 검색용 API

이 Connector 는 2번(검색용 API)을 사용하도록 구성되어 있습니다.
서비스 신청 후 발급되는 상세주소·요청인자·응답 필드를 `sources.yaml` 의
`endpoint` / `request` / `field_map` 에 입력하면 동작합니다.

주의: 디지털집현전은 여러 기관의 자료를 모아 제공하는 **집계 플랫폼**이므로,
개별 기관 소스(KCI·NKIS·법령정보 등)와 동일 자료가 중복 수집될 수 있습니다.
중복은 DOI·공식 ID·파일 해시 기준으로 파이프라인이 걸러냅니다 (§11).
"""

from __future__ import annotations

import logging

from ..models import RawItem, Resource
from ..normalizers.normalize import clean_whitespace
from .generic_api import GenericApiConnector

logger = logging.getLogger(__name__)


class KKnowledgeConnector(GenericApiConnector):
    connector_id = "kknowledge"

    default_document_type = "정책자료"

    #: 공공데이터포털 계열 표준 형식을 기본값으로 둡니다.
    #: 실제 명세를 확인한 뒤 sources.yaml 의 request 로 덮어쓰십시오.
    default_request = {
        "method": "GET",
        "format": "json",
        "key_param": "serviceKey",
        "query_param": "query",
        "from_param": "startDate",
        "until_param": "endDate",
        "date_format": "%Y%m%d",
        "page_size_param": "numOfRows",
        "page_size": 50,
        "static_params": {"pageNo": 1},
        "records_path": "response.body.items.item",
    }

    #: 플랫폼이 표준화해 제공하는 메타데이터 항목 기준
    default_field_map = {
        "title": "title",
        "authors": "author",
        "publisher": "orgName",
        "publication_date": "issuedDate",
        "registered_date": "regDate",
        "modified_date": "updtDate",
        "identifier": "id",
        "landing_url": "url",
        "abstract": "description",
        "keywords": "subject",
        "document_type": "type",
    }

    # ------------------------------------------------------------------
    def normalize(self, raw: RawItem) -> Resource | None:
        resource = super().normalize(raw)
        if resource is None:
            return None

        # 집계 플랫폼이므로 실제 생산기관을 발행기관으로 남기고,
        # 디지털집현전은 발견 경로로만 기록합니다.
        origin = clean_whitespace(raw.payload.get("orgName") or raw.payload.get("provider"))
        resource.publisher = origin or resource.publisher or self.config.name
        resource.source_type = "OPEN_API"

        # 원문 링크가 원 기관 사이트를 가리키므로 라이선스는 개별 확인이 필요합니다.
        resource.license_unknown = True
        return resource
