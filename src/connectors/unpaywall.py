"""Unpaywall Connector (PRD v2.1 §4.4 E).

DOI 기반으로 합법적인 오픈액세스 원문 위치를 확인합니다.
유료 출판사 페이지 대신 `best_oa_location` 의 공개본을 사용합니다.

Unpaywall 은 API Key 가 아니라 연락 이메일(`email` 파라미터)을 요구합니다.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Sequence
from datetime import date

from ..models import Query, RawItem, Resource
from ..normalizers.normalize import clean_whitespace, normalize_doi
from .base import CredentialMissingError, SourceConnector

logger = logging.getLogger(__name__)


class OpenAccessLocation:
    """Unpaywall 이 찾아낸 합법적 공개본 위치."""

    def __init__(self, pdf_url: str, landing_url: str, license_name: str, version: str):
        self.pdf_url = pdf_url
        self.landing_url = landing_url
        self.license = license_name
        self.version = version

    def __repr__(self) -> str:  # pragma: no cover
        return f"<OpenAccessLocation {self.pdf_url or self.landing_url} license={self.license}>"


class UnpaywallConnector(SourceConnector):
    """OA_RESOLVER 전용 — 스스로 탐색하지 않습니다."""

    connector_id = "unpaywall"
    passive = True

    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:  # noqa: ARG002
        return iter(())

    def normalize(self, raw: RawItem) -> Resource | None:  # noqa: ARG002
        return None

    # ------------------------------------------------------------------
    def resolve(self, doi: str) -> OpenAccessLocation | None:
        """DOI 의 합법적인 OA 위치를 반환합니다."""
        doi = normalize_doi(doi)
        if not doi:
            return None

        method = self.config.method("OPEN_API")
        if not method or not method.endpoint:
            return None
        email = self.secret_for(method) or self.ctx.contact_email
        if not email:
            raise CredentialMissingError(
                self.config.name, method.credential_env_var, self.config.auth_docs_url
            )

        url = f"{method.endpoint.rstrip('/')}/{doi}"
        try:
            data = self.ctx.client.get_json(url, params={"email": email})
        except Exception as exc:
            logger.debug("[unpaywall] 조회 실패 (%s): %s", doi, exc)
            return None

        if not data.get("is_oa"):
            return None

        best = data.get("best_oa_location") or {}
        pdf_url = clean_whitespace(best.get("url_for_pdf"))
        landing_url = clean_whitespace(best.get("url_for_landing_page") or best.get("url"))
        if not pdf_url and not landing_url:
            return None

        return OpenAccessLocation(
            pdf_url=pdf_url,
            landing_url=landing_url,
            license_name=clean_whitespace(best.get("license")) or "오픈액세스(라이선스 미표기)",
            version=clean_whitespace(best.get("version")),
        )
