"""데이터 모델 (PRD v2.1 §10, §3.2, §5).

Source Registry 설정과 파이프라인이 주고받는 자료 구조를 pydantic 으로 정의합니다.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# 열거형
# ---------------------------------------------------------------------------

class SourceMode(str, Enum):
    """소스 수집 모드 (§3.2)."""

    FULL = "FULL"
    QUERY = "QUERY"
    FEED = "FEED"
    LINK_ONLY = "LINK_ONLY"
    OA_RESOLVER = "OA_RESOLVER"
    IDENTIFIER_RESOLVER = "IDENTIFIER_RESOLVER"


class AuthType(str, Enum):
    """접근방식별 인증모델 (§5)."""

    NONE = "NONE"
    API_KEY = "API_KEY"
    OAUTH2 = "OAUTH2"
    SERVICE_ACCOUNT = "SERVICE_ACCOUNT"
    INSTITUTION_APPROVAL = "INSTITUTION_APPROVAL"
    OTHER = "OTHER"


class DownloadPolicy(str, Enum):
    """원문 다운로드 정책 (§5, §7)."""

    ALLOWED = "allowed"
    OA_ONLY = "oa_only"
    LINK_ONLY = "link_only"
    MANUAL_REVIEW = "manual_review"


class AccessMode(str, Enum):
    """자료가 최종적으로 어떤 형태로 확보되었는지."""

    DOWNLOADED = "DOWNLOADED"
    LINK_ONLY = "LINK_ONLY"
    PENDING = "PENDING"
    FAILED = "FAILED"


class SummaryBasis(str, Enum):
    """요약 근거 수준 (§14.2)."""

    FULLTEXT = "FULLTEXT"
    ABSTRACT = "ABSTRACT"
    METADATA_ONLY = "METADATA_ONLY"


class PriorityLevel(str, Enum):
    """중요도 우선순위 (§12.3)."""

    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class ResourceStatus(str, Enum):
    NEW = "NEW"
    UPDATED = "UPDATED"
    DUPLICATE = "DUPLICATE"
    LINK_ONLY = "LINK_ONLY"
    FAILED = "FAILED"
    QUARANTINED = "QUARANTINED"


class RunType(str, Enum):
    BACKFILL = "BACKFILL"
    DAILY_INCREMENTAL = "DAILY_INCREMENTAL"
    MONTHLY_RECONCILIATION = "MONTHLY_RECONCILIATION"


class ErrorCode(str, Enum):
    """오류 코드 (§22)."""

    DISCOVERY_FAILED = "DISCOVERY_FAILED"
    API_RATE_LIMIT = "API_RATE_LIMIT"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    PAYWALL = "PAYWALL"
    LINK_EXPIRED = "LINK_EXPIRED"
    FILE_NOT_DOCUMENT = "FILE_NOT_DOCUMENT"
    FILE_CORRUPTED = "FILE_CORRUPTED"
    DUPLICATE_FILE = "DUPLICATE_FILE"
    TEXT_EXTRACTION_FAILED = "TEXT_EXTRACTION_FAILED"
    SUMMARY_FAILED = "SUMMARY_FAILED"
    CREDENTIAL_MISSING = "CREDENTIAL_MISSING"
    ENDPOINT_NOT_CONFIGURED = "ENDPOINT_NOT_CONFIGURED"
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"


# ---------------------------------------------------------------------------
# Source Registry
# ---------------------------------------------------------------------------

class AccessMethod(BaseModel):
    """소스의 개별 접근방식과 그 인증모델 (§5)."""

    model_config = ConfigDict(extra="allow")

    type: str
    auth_type: AuthType = AuthType.NONE
    credential_required: bool = False
    credential_env_var: str | None = None
    endpoint: str = ""
    detail_endpoint: str = ""
    verification_status: str = "PENDING_VERIFICATION"


class RetryPolicy(BaseModel):
    max_attempts: int = 3
    backoff: str = "exponential"


class SourceConfig(BaseModel):
    """`config/sources.yaml` 의 소스 1건 (§5 필수 정책 필드)."""

    model_config = ConfigDict(extra="allow")

    source_id: str
    name: str
    base_domain: str = ""
    connector: str
    mode: list[SourceMode] = Field(default_factory=list)
    query_language: str = "ko"
    priority: int = 3
    enabled: bool = True

    access_methods: list[AccessMethod] = Field(default_factory=list)
    credential_guide_required: bool = False
    auth_docs_url: str = ""
    contact_or_policy_url: str = ""

    robots_policy: str = "respect"
    terms_checked_at: date | None = None
    last_policy_review_at: date | None = None
    last_success_at: datetime | None = None

    download_policy: DownloadPolicy = DownloadPolicy.LINK_ONLY
    rate_limit_rps: float = 0.5
    max_concurrency: int = 2
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    lookback_days: int = 3

    notes: str = ""

    def method(self, method_type: str) -> AccessMethod | None:
        """지정한 타입의 접근방식을 반환합니다."""
        for m in self.access_methods:
            if m.type.upper() == method_type.upper():
                return m
        return None

    def preferred_method(self) -> AccessMethod | None:
        """§4.1 우선순위에 따라 사용할 접근방식을 고릅니다."""
        order = ["OPEN_API", "REST_API", "OAI_PMH", "RSS", "ATOM", "SITEMAP", "HTML"]
        available = {m.type.upper(): m for m in self.access_methods}
        for key in order:
            if key in available:
                return available[key]
        return self.access_methods[0] if self.access_methods else None

    def has_mode(self, mode: SourceMode) -> bool:
        return mode in self.mode


# ---------------------------------------------------------------------------
# 검색어
# ---------------------------------------------------------------------------

class SearchTerm(BaseModel):
    """검색어 사전의 항목 (§6.5)."""

    model_config = ConfigDict(extra="allow")

    canonical_ko: str
    ko_variants: list[str] = Field(default_factory=list)
    en_terms: list[str] = Field(default_factory=list)
    en_acronyms: list[str] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)
    exclude_terms: list[str] = Field(default_factory=list)
    source_scope: list[str] = Field(default_factory=lambda: ["domestic"])
    topic_id: str = "99_미분류_검토필요"
    priority: int = 3
    human_verified: bool = False
    machine_suggested: bool = False
    reviewed_at: date | None = None


class Query(BaseModel):
    """소스로 실제 전송되는 검색 질의. 재현성을 위해 원문/확장어를 모두 보존합니다."""

    query_string: str
    language: str
    canonical_ko: str = ""
    original_terms: list[str] = Field(default_factory=list)
    expanded_terms: list[str] = Field(default_factory=list)
    exclude_terms: list[str] = Field(default_factory=list)
    dictionary_version: str = ""
    topic_id: str = ""
    machine_suggested: bool = False


# ---------------------------------------------------------------------------
# 수집 자료
# ---------------------------------------------------------------------------

class RawItem(BaseModel):
    """Connector 가 discover 로 뽑아낸 원본 레코드."""

    model_config = ConfigDict(extra="allow")

    source_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    discovered_by_query: Query | None = None


class Resource(BaseModel):
    """정규화된 자료 1건 (§10.1 필수 필드)."""

    model_config = ConfigDict(extra="allow")

    resource_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    work_id: str = ""
    source_id: str
    source_type: str = ""

    title_original: str = ""
    title_ko: str = ""
    authors: list[str] = Field(default_factory=list)
    publisher: str = ""
    journal_or_series: str = ""

    publication_date: date | None = None
    source_registered_date: date | None = None
    source_modified_date: date | None = None
    discovered_at: datetime | None = None
    downloaded_at: datetime | None = None

    doi: str = ""
    official_identifier: str = ""
    landing_url: str = ""
    download_url: str = ""
    oa_url: str = ""
    license: str = ""
    license_unknown: bool = True

    access_mode: AccessMode = AccessMode.PENDING
    language: str = ""
    document_type: str = "기타"

    topic_primary: str = "99_미분류_검토필요"
    topics: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    query_original: str = ""
    query_language: str = ""
    query_terms_expanded: list[str] = Field(default_factory=list)
    query_dictionary_version: str = ""
    discovered_by_query: str = ""

    abstract_original: str = ""

    file_path: str = ""
    file_sha256: str = ""
    text_sha256: str = ""
    file_size: int = 0
    text_extract_failed: bool = False

    summary_ko: str = ""
    summary_basis: SummaryBasis = SummaryBasis.METADATA_ONLY
    summary_generated_at: datetime | None = None

    relevance_score: int = 0
    priority_level: PriorityLevel = PriorityLevel.P4
    score_breakdown: dict[str, float] = Field(default_factory=dict)

    status: ResourceStatus = ResourceStatus.NEW
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    alerted_at: datetime | None = None

    version_of: str = ""
    error_code: str = ""
    error_message: str = ""

    def best_title(self) -> str:
        return self.title_ko or self.title_original or "(제목 없음)"

    def canonical_url(self) -> str:
        """사용자에게 제공할 대표 링크. 공식 Landing Page 를 우선합니다."""
        return self.landing_url or self.oa_url or self.download_url


# ---------------------------------------------------------------------------
# 다운로드
# ---------------------------------------------------------------------------

class CandidateKind(str, Enum):
    DIRECT_FILE = "DIRECT_FILE"
    LANDING_PAGE = "LANDING_PAGE"


class DownloadCandidate(BaseModel):
    """다운로드 후보 URL 과 그 근거."""

    url: str
    kind: CandidateKind = CandidateKind.DIRECT_FILE
    source_id: str = ""
    license: str = ""
    is_open_access: bool = False
    origin: str = ""  # 어떤 resolver 가 찾았는지 (unpaywall / core / connector ...)


class PolicyDecision(BaseModel):
    """§7 다운로드 허용 판정 결과."""

    allowed: bool
    reason: str = ""
    error_code: str = ""


class DownloadResult(BaseModel):
    """실제 다운로드 수행 결과."""

    success: bool
    staged_path: str = ""
    file_sha256: str = ""
    file_size: int = 0
    content_type: str = ""
    final_url: str = ""
    error_code: str = ""
    error_message: str = ""


class ValidationResult(BaseModel):
    """검증기 공통 결과 (§8)."""

    valid: bool
    stage: str = ""
    reason: str = ""
    error_code: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 실행 이력
# ---------------------------------------------------------------------------

class SourceRunReport(BaseModel):
    """한 소스의 1회 실행 결과 요약."""

    source_id: str
    source_name: str = ""
    discovered: int = 0
    new_resources: int = 0
    updated_resources: int = 0
    duplicates: int = 0
    downloaded: int = 0
    link_only: int = 0
    failed: int = 0
    skipped_reason: str = ""
    error_code: str = ""
    error_message: str = ""

    @property
    def ok(self) -> bool:
        return not self.error_code


class RunReport(BaseModel):
    """실행 전체 결과."""

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_type: RunType
    started_at: datetime
    finished_at: datetime | None = None
    since: date | None = None
    until: date | None = None
    dictionary_version: str = ""
    sources: list[SourceRunReport] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)

    @property
    def new_count(self) -> int:
        return sum(s.new_resources for s in self.sources)

    @property
    def updated_count(self) -> int:
        return sum(s.updated_resources for s in self.sources)

    @property
    def failed_sources(self) -> list[SourceRunReport]:
        return [s for s in self.sources if s.error_code]
