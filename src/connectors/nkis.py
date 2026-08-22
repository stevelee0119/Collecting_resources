"""NKIS 국가정책연구포털 Connector (PRD v2.1 §4.2 D).

정부출연연구기관의 연구보고서·정기간행물·정책자료·세미나자료를 수집합니다.
인증키 기반 공식 Open API 를 사용하며, 엔드포인트와 응답 필드명은
`sources.yaml` 의 `request` / `field_map` 으로 주입합니다.
"""

from __future__ import annotations

from .generic_api import GenericApiConnector


class NkisConnector(GenericApiConnector):
    connector_id = "nkis"

    default_document_type = "연구보고서"

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
        "records_path": "response.body.items.item",
    }

    default_field_map = {
        "title": "title",
        "authors": "author",
        "publisher": "instNm",
        "series": "seriesNm",
        "publication_date": "pblictDe",
        "registered_date": "regDt",
        "modified_date": "updtDt",
        "identifier": "reportId",
        "landing_url": "detailUrl",
        "download_url": "fileUrl",
        "abstract": "abstract",
        "keywords": "keyword",
        "document_type": "reportType",
        "license": "copyright",
    }
