"""링크 검증 1~2단계 (PRD v2.1 §8.1, §8.2).

1단계 — HTTP/접속 확인: redirect 제한, 최종 URL 저장, Status 200 확인,
        403/429 는 즉시 우회하지 않고 backoff 후 정책 점검.
2단계 — 자료 일치 확인: API 제목과 Landing Page 제목 비교, DOI/공식 ID 비교.
"""

from __future__ import annotations

import logging
import re

from ..http_client import CircuitOpenError, PoliteClient, RateLimitedError, RobotsDisallowedError
from ..models import ErrorCode, Resource, ValidationResult
from ..normalizers.normalize import normalize_doi, title_similarity

logger = logging.getLogger(__name__)

#: 로그인·결제 요구를 나타내는 문구 (§7.2)
PAYWALL_MARKERS = (
    "로그인이 필요합니다",
    "로그인 후 이용",
    "회원가입",
    "유료 결제",
    "구독 신청",
    "기관인증",
    "login required",
    "please log in",
    "sign in to continue",
    "purchase this article",
    "subscribe to access",
    "access denied",
)

#: 일회성·세션기반 URL 표지 (§7.2)
EPHEMERAL_URL_MARKERS = ("jsessionid", "sessionid", "phpsessid", "tempfile", "token=", "expires=")

TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")

#: 제목 일치로 인정할 최소 유사도
TITLE_MATCH_THRESHOLD = 0.35


def is_ephemeral_url(url: str) -> bool:
    """세션 ID 등 일회성 파라미터가 포함된 링크인지 확인합니다."""
    lowered = (url or "").lower()
    return any(marker in lowered for marker in EPHEMERAL_URL_MARKERS)


class LinkValidator:
    """URL 이 실제로 접근 가능하고 자료와 일치하는지 검증합니다."""

    def __init__(self, client: PoliteClient):
        self.client = client

    # ------------------------------------------------------------------
    def validate_access(self, url: str) -> ValidationResult:
        """1단계 — 접속 확인."""
        if not url or not url.startswith(("http://", "https://")):
            return ValidationResult(
                valid=False,
                stage="access",
                reason="유효하지 않은 URL 형식",
                error_code=ErrorCode.LINK_EXPIRED.value,
            )
        if is_ephemeral_url(url):
            return ValidationResult(
                valid=False,
                stage="access",
                reason="세션 ID 등 일회성 파라미터가 포함된 링크입니다.",
                error_code=ErrorCode.LINK_EXPIRED.value,
            )

        try:
            response = self.client.get(url)
        except RobotsDisallowedError as exc:
            return ValidationResult(
                valid=False, stage="access", reason=str(exc), error_code=ErrorCode.POLICY_BLOCKED.value
            )
        except RateLimitedError as exc:
            return ValidationResult(
                valid=False, stage="access", reason=str(exc), error_code=ErrorCode.API_RATE_LIMIT.value
            )
        except CircuitOpenError as exc:
            return ValidationResult(
                valid=False, stage="access", reason=str(exc), error_code=ErrorCode.DISCOVERY_FAILED.value
            )
        except Exception as exc:
            return ValidationResult(
                valid=False,
                stage="access",
                reason=f"접속 실패: {exc}",
                error_code=ErrorCode.LINK_EXPIRED.value,
            )

        if response.status_code in (401, 403):
            return ValidationResult(
                valid=False,
                stage="access",
                reason=f"접근이 제한된 자료입니다 (HTTP {response.status_code}).",
                error_code=ErrorCode.LOGIN_REQUIRED.value,
            )
        if response.status_code != 200:
            return ValidationResult(
                valid=False,
                stage="access",
                reason=f"정상 응답이 아닙니다 (HTTP {response.status_code}).",
                error_code=ErrorCode.LINK_EXPIRED.value,
            )

        content_type = response.headers.get("Content-Type", "")
        body = ""
        if "text/html" in content_type.lower():
            body = response.text[:200_000]
            if marker := self._paywall_marker(body):
                return ValidationResult(
                    valid=False,
                    stage="access",
                    reason=f"로그인 또는 결제가 필요한 자료입니다 ('{marker}').",
                    error_code=ErrorCode.PAYWALL.value,
                    details={"final_url": str(response.url)},
                )

        return ValidationResult(
            valid=True,
            stage="access",
            details={
                "final_url": str(response.url),
                "content_type": content_type,
                "body": body,
                "status_code": response.status_code,
            },
        )

    # ------------------------------------------------------------------
    def validate_match(self, resource: Resource, page_html: str, final_url: str = "") -> ValidationResult:
        """2단계 — 자료 일치 확인."""
        if not page_html:
            # HTML 이 아니면(예: 직접 PDF) 제목 비교를 건너뜁니다.
            return ValidationResult(valid=True, stage="match", reason="HTML 페이지가 아니므로 제목 비교 생략")

        page_title = self._extract_title(page_html)
        expected = resource.title_original or resource.title_ko

        # DOI 가 페이지에 있으면 강한 일치 근거로 인정합니다.
        if resource.doi and normalize_doi(resource.doi) in page_html.lower():
            return ValidationResult(
                valid=True, stage="match", reason="DOI 일치", details={"page_title": page_title}
            )
        if resource.official_identifier and resource.official_identifier.split(":")[-1] in page_html:
            return ValidationResult(
                valid=True, stage="match", reason="공식 ID 일치", details={"page_title": page_title}
            )

        if not page_title or not expected:
            return ValidationResult(
                valid=True, stage="match", reason="비교할 제목이 없어 통과 처리"
            )

        similarity = title_similarity(expected, page_title)
        if similarity >= TITLE_MATCH_THRESHOLD:
            return ValidationResult(
                valid=True,
                stage="match",
                reason=f"제목 일치 (유사도 {similarity:.2f})",
                details={"page_title": page_title, "similarity": similarity},
            )

        return ValidationResult(
            valid=False,
            stage="match",
            reason=f"페이지 제목이 자료와 일치하지 않습니다 (유사도 {similarity:.2f}).",
            error_code=ErrorCode.LINK_EXPIRED.value,
            details={"page_title": page_title, "similarity": similarity, "final_url": final_url},
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _paywall_marker(html: str) -> str:
        lowered = html.lower()
        for marker in PAYWALL_MARKERS:
            if marker.lower() in lowered:
                return marker
        return ""

    @staticmethod
    def _extract_title(html: str) -> str:
        match = TITLE_TAG_RE.search(html)
        if not match:
            return ""
        return TAG_RE.sub(" ", match.group(1)).strip()
