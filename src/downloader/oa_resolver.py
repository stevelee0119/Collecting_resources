"""OA Resolver (PRD v2.1 §6.1 7단계, §25-5).

Unpaywall · CORE · OpenAlex · ScienceON 등을 교차 조회하여
합법적인 오픈액세스 공개본을 최대한 찾습니다.

유료 출판사 페이지 대신 `best_oa_location` 같은 공개본을 사용하며,
찾지 못하면 자료를 잃지 않도록 LINK_ONLY 로 보존합니다.
"""

from __future__ import annotations

import logging

from ..connectors.core import CoreConnector
from ..connectors.scienceon import ScienceOnConnector
from ..connectors.unpaywall import UnpaywallConnector
from ..models import CandidateKind, DownloadCandidate, Resource

logger = logging.getLogger(__name__)


class OpenAccessResolver:
    """DOI 를 받아 합법적인 OA 원문 위치를 순차 탐색합니다."""

    def __init__(
        self,
        *,
        unpaywall: UnpaywallConnector | None = None,
        core: CoreConnector | None = None,
        scienceon: ScienceOnConnector | None = None,
    ):
        self.unpaywall = unpaywall
        self.core = core
        self.scienceon = scienceon

    # ------------------------------------------------------------------
    def resolve(self, resource: Resource) -> DownloadCandidate | None:
        """자료의 OA 원문 후보를 찾습니다. 못 찾으면 None."""
        # 0) 소스가 이미 OA URL 을 알고 있으면 그대로 사용
        if resource.oa_url and not resource.license_unknown:
            return DownloadCandidate(
                url=resource.oa_url,
                kind=CandidateKind.DIRECT_FILE,
                source_id=resource.source_id,
                license=resource.license,
                is_open_access=True,
                origin="metadata",
            )

        if not resource.doi:
            return None

        for finder in (self._via_unpaywall, self._via_core, self._via_scienceon):
            try:
                candidate = finder(resource)
            except Exception as exc:
                logger.debug("[oa_resolver] %s 실패: %s", finder.__name__, exc)
                continue
            if candidate:
                logger.info(
                    "[oa_resolver] 공개본 확보 (%s): %s", candidate.origin, resource.doi
                )
                return candidate
        return None

    # ------------------------------------------------------------------
    def _via_unpaywall(self, resource: Resource) -> DownloadCandidate | None:
        if not self.unpaywall:
            return None
        location = self.unpaywall.resolve(resource.doi)
        if not location:
            return None
        url = location.pdf_url or location.landing_url
        if not url:
            return None
        # 원문 PDF 가 아니라 landing page 만 있으면 링크로만 보존합니다.
        kind = CandidateKind.DIRECT_FILE if location.pdf_url else CandidateKind.LANDING_PAGE
        resource.oa_url = url
        resource.license = location.license
        resource.license_unknown = False
        return DownloadCandidate(
            url=url,
            kind=kind,
            source_id=resource.source_id,
            license=location.license,
            is_open_access=True,
            origin="unpaywall",
        )

    def _via_core(self, resource: Resource) -> DownloadCandidate | None:
        if not self.core:
            return None
        found = self.core.find_oa_pdf(resource.doi)
        if not found:
            return None
        url, license_name = found
        resource.oa_url = url
        resource.license = license_name
        resource.license_unknown = False
        return DownloadCandidate(
            url=url,
            kind=CandidateKind.DIRECT_FILE,
            source_id=resource.source_id,
            license=license_name,
            is_open_access=True,
            origin="core",
        )

    def _via_scienceon(self, resource: Resource) -> DownloadCandidate | None:
        if not self.scienceon:
            return None
        found = self.scienceon.find_oa_pdf(resource.doi)
        if not found:
            return None
        url, license_name = found
        resource.oa_url = url
        resource.license = license_name
        resource.license_unknown = False
        return DownloadCandidate(
            url=url,
            kind=CandidateKind.DIRECT_FILE,
            source_id=resource.source_id,
            license=license_name,
            is_open_access=True,
            origin="scienceon",
        )
