"""RISS Connector (PRD v2.1 §4.2 B).

RISS 는 국내 최대 학술 게이트웨이이므로 유지하되, 접근정책을 분리합니다.

- Open API 승인 + 인증키가 있으면 메타데이터를 수집합니다.
- 승인되지 않았으면 **직접 대량 크롤링하지 않고** 공식 Landing Page 만 보존합니다.
- 화면상 "원문있음" 을 자동 다운로드 권한과 동일시하지 않습니다.
- 원문은 KCI·ScienceON·기관 리포지터리 등 OA 제공처에서 우선 확보합니다.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Sequence
from datetime import date

from ..config_loader import get_secret
from ..models import (
    AccessMode,
    DownloadCandidate,
    DownloadPolicy,
    ErrorCode,
    PolicyDecision,
    Query,
    RawItem,
    Resource,
)
from .base import SourceConnector
from .generic_api import GenericApiConnector

logger = logging.getLogger(__name__)

RISS_CONTROL_NO_RE = re.compile(r"control_no=([A-Za-z0-9]+)", re.IGNORECASE)


def is_riss_resource(resource: Resource) -> bool:
    haystack = " ".join([resource.landing_url, resource.download_url, resource.oa_url]).lower()
    return "riss.kr" in haystack


def riss_control_no(resource: Resource) -> str:
    for url in (resource.landing_url, resource.download_url, resource.oa_url):
        if url and (match := RISS_CONTROL_NO_RE.search(url)):
            return match.group(1)
    return ""


class RissConnector(GenericApiConnector):
    connector_id = "riss"

    default_document_type = "학술논문"

    default_request = {
        "method": "GET",
        "format": "xml",
        "key_param": "apiKey",
        "query_param": "query",
        "from_param": "startDate",
        "until_param": "endDate",
        "date_format": "%Y%m%d",
        "page_size_param": "displayCount",
        "page_size": 50,
        "records_node": "record",
    }

    default_field_map = {
        "title": "title",
        "authors": "author",
        "publisher": "publisher",
        "series": "journal",
        "publication_date": "pubYear",
        "identifier": "controlNo",
        "landing_url": "linkUrl",
        "abstract": "abstract",
        "keywords": "keyword",
    }

    # ------------------------------------------------------------------
    def approved(self) -> bool:
        """Open API 승인·인증키 보유 여부."""
        method = self.config.method("OPEN_API")
        if not method or not method.endpoint:
            return False
        return bool(get_secret(method.credential_env_var))

    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:
        if not self.approved():
            # 승인 전에는 자체 탐색을 하지 않습니다. 다른 소스가 발견한
            # RISS 링크는 파이프라인이 adopt() 로 넘겨줍니다.
            logger.info(
                "[riss] Open API 미승인 상태이므로 직접 탐색을 수행하지 않습니다. "
                "발견된 RISS 링크는 Landing Page 로만 보존됩니다."
            )
            return iter(())
        return super().discover(since, until, queries)

    # ------------------------------------------------------------------
    def adopt(self, resource: Resource) -> Resource:
        """다른 소스가 발견한 RISS 링크를 참조 정보로 보존합니다."""
        control_no = riss_control_no(resource)
        if control_no and not resource.official_identifier:
            resource.official_identifier = f"riss:{control_no}"
        # RISS 도메인은 자동 다운로드 대상이 아닙니다.
        if "riss.kr" in (resource.download_url or "").lower():
            resource.download_url = ""
        if "riss.kr" in (resource.oa_url or "").lower():
            resource.oa_url = ""
        if not resource.download_url and not resource.oa_url:
            resource.access_mode = AccessMode.LINK_ONLY
        return resource

    # ------------------------------------------------------------------
    def check_access_policy(self, candidate: DownloadCandidate) -> PolicyDecision:
        if "riss.kr" in candidate.url.lower():
            return PolicyDecision(
                allowed=False,
                reason=(
                    "RISS 는 자동 다운로드 권한이 확인되지 않아 공식 Landing Page 만 보존합니다. "
                    "원문은 KCI·ScienceON·기관 리포지터리의 공개본으로 확보합니다."
                ),
                error_code=ErrorCode.POLICY_BLOCKED.value,
            )
        if self.config.download_policy == DownloadPolicy.LINK_ONLY:
            return PolicyDecision(
                allowed=False,
                reason="정책상 링크만 보존하는 소스입니다.",
                error_code=ErrorCode.POLICY_BLOCKED.value,
            )
        return SourceConnector.check_access_policy(self, candidate)

    def resolve_download(self, metadata: Resource) -> DownloadCandidate | None:  # noqa: ARG002
        return None
