"""요약·분석 엔진 인터페이스 (PRD v2.1 §14).

신규 문서마다 다음을 생성합니다.
1. 한줄 핵심
2. 핵심 내용 3~5개
3. 국방·법률 실무상 의미
4. 군법무 교육에 활용 가능한 포인트
5. 주요 제한·주의사항
6. 원문 근거범위

요약 근거 수준(FULLTEXT / ABSTRACT / METADATA_ONLY)을 함께 기록하여
초록 기반 요약을 전체 논문 분석처럼 오인하지 않도록 합니다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..extractors import ExtractedText
from ..models import Resource, SummaryBasis


@dataclass
class Summary:
    """구조화된 요약 결과."""

    headline: str = ""
    key_points: list[str] = field(default_factory=list)
    practical_meaning: str = ""
    education_points: list[str] = field(default_factory=list)
    caveats: str = ""
    evidence_scope: str = ""
    basis: SummaryBasis = SummaryBasis.METADATA_ONLY
    generated_by: str = ""

    def to_markdown(self) -> str:
        """저장·표시용 텍스트로 직렬화합니다."""
        lines: list[str] = []
        if self.headline:
            lines.append(f"**한줄 핵심**: {self.headline}")
        if self.key_points:
            lines.append("\n**핵심 내용**")
            lines.extend(f"- {p}" for p in self.key_points)
        if self.practical_meaning:
            lines.append(f"\n**실무상 의미**: {self.practical_meaning}")
        if self.education_points:
            lines.append("\n**법무교육 활용 포인트**")
            lines.extend(f"- {p}" for p in self.education_points)
        if self.caveats:
            lines.append(f"\n**제한·주의사항**: {self.caveats}")
        if self.evidence_scope:
            lines.append(f"\n**원문 근거범위**: {self.evidence_scope}")
        lines.append(f"\n**요약 근거수준**: {self.basis.value}")
        return "\n".join(lines).strip()

    def short(self, max_points: int = 3) -> list[str]:
        """알림 카드용 3줄 요약."""
        out = [self.headline] if self.headline else []
        out.extend(self.key_points[: max_points - len(out)])
        return [line for line in out if line][:max_points]


def determine_basis(resource: Resource, extracted: ExtractedText | None) -> SummaryBasis:
    """어떤 근거로 요약할 수 있는지 판정합니다 (§14.2)."""
    if extracted and not extracted.failed and extracted.text.strip():
        return SummaryBasis.FULLTEXT
    if resource.abstract_original.strip():
        return SummaryBasis.ABSTRACT
    return SummaryBasis.METADATA_ONLY


class Summarizer(ABC):
    """요약 공급자 어댑터. 공급자를 교체할 수 있는 구조입니다 (§19.2)."""

    name: str = "base"

    @abstractmethod
    def summarize(self, resource: Resource, extracted: ExtractedText | None = None) -> Summary:
        """자료 1건의 구조화 요약을 생성합니다."""

    def apply(self, resource: Resource, extracted: ExtractedText | None = None) -> Resource:
        """요약 결과를 자료에 반영합니다."""
        from datetime import datetime  # noqa: PLC0415

        summary = self.summarize(resource, extracted)
        resource.summary_ko = summary.to_markdown()
        resource.summary_basis = summary.basis
        resource.summary_generated_at = datetime.now()
        return resource
