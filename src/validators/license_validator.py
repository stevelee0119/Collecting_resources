"""권리·라이선스 확인 4단계 (PRD v2.1 §8.4, §18.5).

OA 라이선스 또는 공공누리 등 권리정보를 저장하고, 불명확하면
`license_unknown=True` 로 두어 외부 재배포 없이 내부 색인·링크 중심으로 처리합니다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..models import Resource

logger = logging.getLogger(__name__)

#: 명시적으로 재사용이 허용된 라이선스 표지
OPEN_LICENSE_MARKERS = (
    "cc-by",
    "cc by",
    "cc0",
    "creativecommons",
    "public domain",
    "publicdomain",
    "open government licence",
    "mit",
    "apache-2.0",
)

#: 공공누리 유형 (제1유형만 상업적 이용까지 자유)
KOGL_MARKERS = ("공공누리", "kogl", "제1유형", "제2유형", "제3유형", "제4유형")


@dataclass
class LicenseAssessment:
    """라이선스 판정 결과."""

    license_name: str
    is_open: bool
    redistributable: bool
    note: str = ""


class LicenseValidator:
    """라이선스 문자열을 해석해 내부 보관/외부 재배포 가능 여부를 나눕니다."""

    def assess(self, license_text: str | None, *, source_download_policy: str = "") -> LicenseAssessment:
        text = (license_text or "").strip()
        lowered = text.lower()

        if not text:
            return LicenseAssessment(
                license_name="",
                is_open=False,
                redistributable=False,
                note="라이선스 정보가 없어 불명확(license_unknown)으로 처리합니다.",
            )

        if any(marker in lowered for marker in OPEN_LICENSE_MARKERS):
            return LicenseAssessment(
                license_name=text,
                is_open=True,
                # CC-BY-NC/ND 계열은 내부 보관은 되지만 재배포 조건이 붙습니다.
                redistributable="-nd" not in lowered and "noderiv" not in lowered,
                note="오픈 라이선스 확인",
            )

        if any(marker in lowered for marker in KOGL_MARKERS):
            first_type = "제1유형" in text or "type1" in lowered
            return LicenseAssessment(
                license_name=text,
                is_open=True,
                redistributable=first_type,
                note="공공누리 확인 — 유형별 이용조건을 준수하세요.",
            )

        if source_download_policy == "allowed":
            return LicenseAssessment(
                license_name=text,
                is_open=True,
                redistributable=False,
                note="소스 정책상 공개 다운로드가 허용된 자료입니다.",
            )

        return LicenseAssessment(
            license_name=text,
            is_open=False,
            redistributable=False,
            note="라이선스 해석이 불명확합니다. 내부 색인·링크 중심으로 처리합니다.",
        )

    # ------------------------------------------------------------------
    def apply(self, resource: Resource, *, source_download_policy: str = "") -> Resource:
        """판정 결과를 자료에 반영합니다."""
        assessment = self.assess(resource.license, source_download_policy=source_download_policy)
        resource.license = assessment.license_name
        resource.license_unknown = not assessment.is_open
        if assessment.note:
            logger.debug("[license] %s → %s", resource.best_title()[:40], assessment.note)
        return resource
