"""Source Adapter 표준 인터페이스 (PRD v2.1 §21).

소스별 구현 차이를 core pipeline 과 분리해, 사이트/API 구조가 바뀌어도
해당 Adapter 만 수정하면 되도록 합니다.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from ..config_loader import AppConfig, get_secret
from ..http_client import PoliteClient
from ..models import (
    AccessMethod,
    CandidateKind,
    DownloadCandidate,
    DownloadPolicy,
    DownloadResult,
    ErrorCode,
    PolicyDecision,
    Query,
    RawItem,
    Resource,
    SearchTerm,
    SourceConfig,
)

if TYPE_CHECKING:  # discovery 패키지와의 순환 import 를 피하기 위해 타입 전용으로만 참조합니다.
    from ..discovery.query_expander import QueryExpander

logger = logging.getLogger(__name__)


class ConnectorError(RuntimeError):
    """Connector 수준의 실패. `error_code` 로 원인을 구분합니다 (§22)."""

    def __init__(self, message: str, error_code: str = ErrorCode.DISCOVERY_FAILED.value):
        super().__init__(message)
        self.error_code = error_code


class CredentialMissingError(ConnectorError):
    """API Key/OAuth/기관승인 등 사전 발급이 필요한데 값이 없는 경우."""

    def __init__(self, source_name: str, env_var: str | None, docs_url: str = ""):
        hint = f"환경변수 {env_var} 를 .env 에 설정하세요." if env_var else "인증정보가 필요합니다."
        guide = " docs/API_발급_연동_가이드.md 의 발급 절차를 참고하세요."
        super().__init__(
            f"[{source_name}] 인증정보가 없어 수집을 건너뜁니다. {hint}{guide}"
            + (f" (공식 문서: {docs_url})" if docs_url else ""),
            ErrorCode.CREDENTIAL_MISSING.value,
        )


class EndpointNotConfiguredError(ConnectorError):
    """공식 엔드포인트가 아직 확정되지 않아 자동수집을 시도하지 않는 경우."""

    def __init__(self, source_name: str, method_type: str = ""):
        super().__init__(
            f"[{source_name}] 공식 엔드포인트가 sources.yaml 에 설정되어 있지 않습니다"
            f"{f' ({method_type})' if method_type else ''}. "
            "공식 문서를 확인해 endpoint 를 채우면 자동으로 활성화됩니다.",
            ErrorCode.ENDPOINT_NOT_CONFIGURED.value,
        )


@dataclass
class ConnectorContext:
    """Connector 가 공유하는 실행 컨텍스트."""

    app: AppConfig
    client: PoliteClient
    expander: "QueryExpander"
    max_items: int = 200

    @property
    def contact_email(self) -> str:
        return get_secret("CONTACT_EMAIL") or ""


class SourceConnector(ABC):
    """모든 수집기의 기반 클래스.

    하위 클래스는 최소 `discover()` 와 `normalize()` 를 구현합니다.
    나머지 메서드는 Source Registry 정책에 따른 기본 동작을 제공합니다.
    """

    #: `sources.yaml` 의 `connector` 값과 매칭되는 식별자
    connector_id: str = ""

    #: 이 소스가 스스로 탐색하지 않고 다른 소스의 결과를 흡수하는 경우 True
    passive: bool = False

    def __init__(self, config: SourceConfig, ctx: ConnectorContext):
        self.config = config
        self.ctx = ctx

    # ------------------------------------------------------------------
    # 1) 질의 준비
    # ------------------------------------------------------------------
    def prepare_queries(
        self, terms: Sequence[SearchTerm] | None = None, source_language: str | None = None
    ) -> list[Query]:
        """소스 언어에 맞는 Query 를 생성합니다 (§6.4).

        `terms` 를 주지 않으면 사전 전체에서 이 소스의 scope 에 맞는 항목을 사용합니다.
        """
        language = source_language or self.config.query_language
        scope = "international" if language == "en" else "domestic"
        return self.ctx.expander.build_queries(
            language=language,
            scope=scope,
            max_queries=self.max_queries(),
        )

    def max_queries(self) -> int:
        """소스별 질의 개수 상한. 우선순위가 높을수록 더 많이 탐색합니다."""
        return {1: 12, 2: 8, 3: 5}.get(self.config.priority, 5)

    # ------------------------------------------------------------------
    # 2) 탐색
    # ------------------------------------------------------------------
    @abstractmethod
    def discover(
        self, since: date, until: date, queries: Sequence[Query]
    ) -> Iterator[RawItem]:
        """기간과 질의로 신규·수정 자료를 찾습니다."""

    # ------------------------------------------------------------------
    # 3) 메타데이터 조회 (필요한 소스만 재정의)
    # ------------------------------------------------------------------
    def fetch_metadata(self, item: RawItem) -> dict[str, Any]:
        """상세 메타데이터가 별도 호출로 제공되는 소스에서 재정의합니다."""
        return item.payload

    # ------------------------------------------------------------------
    # 4) 정규화
    # ------------------------------------------------------------------
    @abstractmethod
    def normalize(self, raw: RawItem) -> Resource | None:
        """원본 레코드를 `Resource` 로 변환합니다."""

    # ------------------------------------------------------------------
    # 5) 다운로드 후보 결정
    # ------------------------------------------------------------------
    def resolve_download(self, metadata: Resource) -> DownloadCandidate | None:
        """소스가 직접 아는 원문 위치를 반환합니다.

        여기서 None 을 반환해도 파이프라인이 OA Resolver 로 다시 시도합니다.
        """
        if self.config.download_policy == DownloadPolicy.LINK_ONLY:
            return None
        url = metadata.download_url or metadata.oa_url
        if not url:
            return None
        return DownloadCandidate(
            url=url,
            kind=CandidateKind.DIRECT_FILE,
            source_id=self.config.source_id,
            license=metadata.license,
            is_open_access=not metadata.license_unknown,
            origin=f"connector:{self.config.source_id}",
        )

    # ------------------------------------------------------------------
    # 6) 접근정책 검사 (§7)
    # ------------------------------------------------------------------
    def check_access_policy(self, candidate: DownloadCandidate) -> PolicyDecision:
        """Source Registry 의 `download_policy` 에 따라 자동 다운로드 허용 여부를 판정합니다."""
        policy = self.config.download_policy

        if policy == DownloadPolicy.LINK_ONLY:
            return PolicyDecision(
                allowed=False,
                reason="정책상 링크만 보존하는 소스입니다.",
                error_code=ErrorCode.POLICY_BLOCKED.value,
            )
        if policy == DownloadPolicy.MANUAL_REVIEW:
            return PolicyDecision(
                allowed=False,
                reason="자동수집 허용 여부가 확인되지 않아 사람 검토가 필요합니다.",
                error_code=ErrorCode.POLICY_BLOCKED.value,
            )
        if policy == DownloadPolicy.OA_ONLY and not candidate.is_open_access:
            return PolicyDecision(
                allowed=False,
                reason="오픈액세스 여부가 확인되지 않았습니다.",
                error_code=ErrorCode.POLICY_BLOCKED.value,
            )
        if candidate.kind == CandidateKind.LANDING_PAGE:
            return PolicyDecision(
                allowed=False,
                reason="게시글 페이지는 원문 파일이 아니므로 링크로 보존합니다.",
                error_code=ErrorCode.POLICY_BLOCKED.value,
            )
        return PolicyDecision(allowed=True, reason="자동 다운로드 허용")

    # ------------------------------------------------------------------
    # 7) 다운로드
    # ------------------------------------------------------------------
    def download(self, candidate: DownloadCandidate) -> DownloadResult:
        """실제 다운로드는 공용 Downloader 가 수행합니다.

        파이프라인이 주입한 downloader 를 사용하며, 소스별 특수 처리가 필요하면
        하위 클래스에서 재정의합니다.
        """
        downloader = getattr(self, "_downloader", None)
        if downloader is None:
            return DownloadResult(
                success=False,
                error_code=ErrorCode.DOWNLOAD_FAILED.value,
                error_message="Downloader 가 주입되지 않았습니다.",
            )
        return downloader.download(candidate, client=self.ctx.client)

    def attach_downloader(self, downloader: Any) -> None:
        self._downloader = downloader

    # ------------------------------------------------------------------
    # 공통 도우미
    # ------------------------------------------------------------------
    def require_method(self, *types: str) -> AccessMethod:
        """지정한 접근방식 중 사용 가능한 것을 반환하고, 인증정보를 검증합니다."""
        for method_type in types:
            method = self.config.method(method_type)
            if method is None:
                continue
            if not method.endpoint:
                continue
            if method.credential_required and not get_secret(method.credential_env_var):
                raise CredentialMissingError(
                    self.config.name, method.credential_env_var, self.config.auth_docs_url
                )
            return method
        raise EndpointNotConfiguredError(self.config.name, ", ".join(types))

    def secret_for(self, method: AccessMethod) -> str | None:
        return get_secret(method.credential_env_var)

    def _now(self) -> datetime:
        return datetime.now()

    def _limit(self) -> int:
        return self.ctx.max_items

    def __repr__(self) -> str:  # pragma: no cover - 디버깅용
        return f"<{type(self).__name__} source_id={self.config.source_id}>"


class PassiveConnector(SourceConnector):
    """스스로 탐색하지 않는 소스 (예: SSRN).

    다른 소스가 발견한 항목을 파이프라인이 이 소스로 넘겨줍니다 (§4.4 H).
    """

    passive = True

    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:  # noqa: ARG002
        return iter(())
