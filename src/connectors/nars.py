"""국회입법조사처(NARS) Connector (PRD v2.1 §4.3).

공식 RSS 주소가 확인되지 않아, 공공데이터포털에 등재된 Open API 를 사용합니다
(§4.1 우선순위 1 — 공식 Open API 우선).

- 국회사무처_국회입법조사처 연구보고서(NARS 현안분석): data.go.kr 15125970
- 국회사무처_국회입법조사처 제공 자료 통합 API: data.go.kr 15126137

오퍼레이션 경로와 응답 필드명은 데이터셋 상세페이지에서 확인해
`sources.yaml` 의 `endpoint` / `request` / `field_map` 에 입력하십시오.
"""

from __future__ import annotations

import logging

from ..models import RawItem, Resource
from .generic_api import GenericApiConnector

logger = logging.getLogger(__name__)


class NarsConnector(GenericApiConnector):
    connector_id = "nars"

    default_document_type = "연구보고서"

    #: 공공데이터포털 표준 응답 구조를 기본값으로 둡니다.
    default_request = {
        "method": "GET",
        "format": "xml",
        "key_param": "serviceKey",
        "query_param": "searchWord",
        "page_size_param": "numOfRows",
        "page_size": 50,
        "static_params": {"pageNo": 1},
        "records_node": "item",
    }

    default_field_map = {
        "title": "title",
        "authors": "author",
        "publisher": "deptName",
        "publication_date": "publishDate",
        "registered_date": "regDate",
        "identifier": "brdSeq",
        "landing_url": "linkUrl",
        "download_url": "fileUrl",
        "abstract": "summary",
        "document_type": "reportType",
    }

    # ------------------------------------------------------------------
    def normalize(self, raw: RawItem) -> Resource | None:
        resource = super().normalize(raw)
        if resource is None:
            return None

        # 응답에 상세 링크가 없으면 공식 게시글 URL 을 조합합니다.
        template = str(getattr(self.config, "landing_url_template", "") or "")
        if not resource.landing_url and template and resource.official_identifier:
            identifier = resource.official_identifier.split(":")[-1]
            resource.landing_url = template.format(id=identifier)

        resource.publisher = resource.publisher or self.config.name
        return resource
