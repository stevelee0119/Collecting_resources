"""PRISM 정책연구관리시스템 Connector (PRD v2.1 §4.2 E).

중앙·지방정부 정책연구용역 보고서를 수집합니다.
공공데이터포털이 제공하는 인터페이스를 우선 사용합니다.
"""

from __future__ import annotations

from .generic_api import GenericApiConnector


class PrismConnector(GenericApiConnector):
    connector_id = "prism"

    default_document_type = "연구보고서"

    default_request = {
        "method": "GET",
        "format": "json",
        "key_param": "serviceKey",
        "query_param": "researchNm",
        "from_param": "beginDe",
        "until_param": "endDe",
        "date_format": "%Y%m%d",
        "page_size_param": "numOfRows",
        "page_size": 50,
        "static_params": {"type": "json"},
        "records_path": "response.body.items.item",
    }

    default_field_map = {
        "title": "researchNm",
        "authors": "researcherNm",
        "publisher": "orderInstNm",
        "publication_date": "endDe",
        "registered_date": "registDe",
        "modified_date": "updtDe",
        "identifier": "researchId",
        "landing_url": "detailUrl",
        "download_url": "fileDownUrl",
        "abstract": "researchAbstract",
        "keywords": "keyword",
        "document_type": "researchSe",
    }
