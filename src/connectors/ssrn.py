"""SSRN Connector (PRD v2.1 §4.4 H).

법학·사회과학 preprint·working paper 확보에 필수인 소스이지만,
검색화면을 대량 스크래핑하지 않습니다.

전략:
1. OpenAlex/Crossref/Semantic Scholar 가 발견한 SSRN 논문을 흡수한다.
2. 공식 SSRN Abstract Page 를 canonical source 로 연결한다.
3. 라이선스와 이용조건이 명확히 확인되지 않으면 LINK_ONLY 로 보존한다.
4. 로그인·CAPTCHA·지문·세션 우회는 하지 않는다 (§7.3).
"""

from __future__ import annotations

import logging
import re

from ..models import (
    AccessMode,
    DownloadCandidate,
    DownloadPolicy,
    ErrorCode,
    PolicyDecision,
    RawItem,
    Resource,
)
from ..normalizers.normalize import normalize_doi
from .base import PassiveConnector

logger = logging.getLogger(__name__)

# SSRN DOI 프리픽스 및 초록 페이지 URL 패턴
SSRN_DOI_PREFIX = "10.2139/ssrn."
SSRN_ABSTRACT_RE = re.compile(r"abstract(?:_id)?=(\d+)", re.IGNORECASE)
SSRN_DOI_ID_RE = re.compile(r"10\.2139/ssrn\.(\d+)", re.IGNORECASE)


def is_ssrn_resource(resource: Resource) -> bool:
    """다른 소스가 발견한 자료가 SSRN 논문인지 판정합니다."""
    if resource.doi.startswith(SSRN_DOI_PREFIX):
        return True
    haystack = " ".join(
        [resource.landing_url, resource.download_url, resource.oa_url, resource.publisher]
    ).lower()
    return "ssrn.com" in haystack or "ssrn" == resource.publisher.strip().lower()


def ssrn_abstract_id(resource: Resource) -> str:
    """SSRN abstract id 를 추출합니다."""
    if match := SSRN_DOI_ID_RE.search(resource.doi):
        return match.group(1)
    for url in (resource.landing_url, resource.download_url, resource.oa_url):
        if url and (match := SSRN_ABSTRACT_RE.search(url)):
            return match.group(1)
    return ""


def ssrn_landing_url(abstract_id: str) -> str:
    """공식 SSRN Abstract Page URL (canonical source)."""
    return f"https://papers.ssrn.com/sol3/papers.cfm?abstract_id={abstract_id}" if abstract_id else ""


class SsrnConnector(PassiveConnector):
    """SSRN 자료를 canonical landing page 로 정리하는 흡수형 Connector."""

    connector_id = "ssrn"

    def normalize(self, raw: RawItem) -> Resource | None:  # noqa: ARG002
        # 자체 탐색을 하지 않으므로 정규화 대상이 없습니다.
        return None

    # ------------------------------------------------------------------
    def adopt(self, resource: Resource) -> Resource:
        """다른 소스가 찾은 SSRN 논문을 SSRN 소스 정책으로 재정리합니다."""
        abstract_id = ssrn_abstract_id(resource)
        landing = ssrn_landing_url(abstract_id) or resource.landing_url

        resource.landing_url = landing
        resource.publisher = resource.publisher or "SSRN"
        resource.official_identifier = (
            f"ssrn:{abstract_id}" if abstract_id else resource.official_identifier
        )
        if not resource.doi and abstract_id:
            resource.doi = normalize_doi(f"{SSRN_DOI_PREFIX}{abstract_id}")

        # 라이선스가 확인되지 않으면 원문 자동 다운로드를 하지 않습니다.
        if resource.license_unknown:
            resource.download_url = ""
            resource.oa_url = ""
            resource.access_mode = AccessMode.LINK_ONLY

        resource.document_type = resource.document_type or "프리프린트"
        logger.debug("[ssrn] canonical landing page 로 정리: %s", landing)
        return resource

    # ------------------------------------------------------------------
    def check_access_policy(self, candidate: DownloadCandidate) -> PolicyDecision:
        """SSRN 은 라이선스가 명확히 확인된 경우에만 다운로드를 허용합니다."""
        if self.config.download_policy == DownloadPolicy.LINK_ONLY:
            return PolicyDecision(
                allowed=False,
                reason=(
                    "SSRN 은 이용조건·논문별 라이선스가 확인되기 전까지 링크만 보존합니다. "
                    "공식 Abstract Page 를 통해 열람하세요."
                ),
                error_code=ErrorCode.POLICY_BLOCKED.value,
            )
        if not candidate.is_open_access or not candidate.license:
            return PolicyDecision(
                allowed=False,
                reason="논문별 오픈 라이선스가 확인되지 않았습니다.",
                error_code=ErrorCode.POLICY_BLOCKED.value,
            )
        # SSRN 도메인 자체에서의 자동 다운로드는 수행하지 않습니다.
        if "ssrn.com" in candidate.url.lower():
            return PolicyDecision(
                allowed=False,
                reason="SSRN 사이트에서의 자동 다운로드는 수행하지 않습니다.",
                error_code=ErrorCode.POLICY_BLOCKED.value,
            )
        return PolicyDecision(allowed=True, reason="제3자 OA 저장소의 공개본")

    def resolve_download(self, metadata: Resource) -> DownloadCandidate | None:  # noqa: ARG002
        # SSRN 은 스스로 다운로드 후보를 만들지 않습니다.
        return None
