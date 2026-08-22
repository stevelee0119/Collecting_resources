"""ScienceON / AccessON (KISTI) Connector (PRD v2.1 §4.2 C).

국내외 학술논문·연구보고서의 메타데이터와 오픈액세스 원문 후보를 탐색합니다.
`QUERY + OA_RESOLVER` 모드로 동작합니다.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config_loader import get_secret
from ..normalizers.normalize import clean_whitespace, normalize_doi
from .generic_api import GenericApiConnector, dig

logger = logging.getLogger(__name__)


class ScienceOnConnector(GenericApiConnector):
    connector_id = "scienceon"

    default_document_type = "학술논문"

    default_request = {
        "method": "GET",
        "format": "xml",
        "key_param": "token",
        "query_param": "searchQuery",
        "from_param": "dateFrom",
        "until_param": "dateUntil",
        "date_format": "%Y%m%d",
        "page_size_param": "displayCount",
        "page_size": 50,
        "static_params": {"target": "ARTI", "version": "1.0"},
        "records_node": "record",
    }

    default_field_map = {
        "title": "Title",
        "authors": "Author",
        "publisher": "Publisher",
        "series": "JournalName",
        "publication_date": "PubYear",
        "identifier": "CN",
        "landing_url": "ContentURL",
        "download_url": "FullTextURL",
        "abstract": "Abstract",
        "keywords": "Keyword",
        "doi": "DOI",
    }

    # ------------------------------------------------------------------
    @property
    def request_config(self) -> dict[str, Any]:
        """API Gateway 는 token 과 별도로 client_id 를 함께 요구합니다."""
        config = super().request_config
        client_id = get_secret(str(getattr(self.config, "client_id_env_var", "SCIENCEON_CLIENT_ID")))
        if client_id:
            static = dict(config.get("static_params") or {})
            static["client_id"] = client_id
            config["static_params"] = static
        else:
            logger.warning(
                "[scienceon] client_id 가 설정되지 않았습니다. "
                "SCIENCEON_CLIENT_ID 를 .env 에 추가하세요."
            )
        return config

    # ------------------------------------------------------------------
    def find_oa_pdf(self, doi: str) -> tuple[str, str] | None:
        """AccessON 계열의 공개 원문 위치를 DOI 로 조회합니다 (OA_RESOLVER 역할)."""
        doi = normalize_doi(doi)
        if not doi:
            return None
        method = self.config.method("OPEN_API")
        if not method or not method.endpoint:
            return None
        secret = self.secret_for(method)
        if not secret:
            return None

        req = self.request_config
        params = dict(req.get("static_params") or {})
        params[str(req.get("key_param", "token"))] = secret
        params[str(req.get("query_param", "searchQuery"))] = doi
        try:
            records = self._call(method.endpoint, req, params, {})
        except Exception as exc:
            logger.debug("[scienceon] OA 조회 실패 (%s): %s", doi, exc)
            return None

        for record in records:
            url = clean_whitespace(dig(record, self.field_map.get("download_url", "")) or record.get("FullTextURL"))
            if url:
                return url, "ScienceON/AccessON 공개 원문"
        return None
