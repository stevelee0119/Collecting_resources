"""추출식 요약기 (기본 공급자).

외부 API 없이 동작합니다. 원문/초록에서 중요 문장을 골라내며,
없는 판례·조문·페이지를 만들어내지 않습니다 (§14.4).
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from ..extractors import ExtractedText
from ..models import Resource, SummaryBasis
from .base import Summary, Summarizer, determine_basis

logger = logging.getLogger(__name__)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。])\s+|(?<=다\.)\s+|\n+")

#: 실무·교육 관련 문장을 고르기 위한 표지
PRACTICAL_MARKERS = (
    "실무",
    "적용",
    "시사점",
    "제언",
    "개선",
    "쟁점",
    "판단",
    "기준",
    "절차",
    "필요",
    "해석",
    "문제",
    "practice",
    "implication",
    "recommend",
    "should",
    "framework",
)
EDUCATION_MARKERS = (
    "교육",
    "훈련",
    "사례",
    "교재",
    "커리큘럼",
    "학습",
    "교수",
    "training",
    "education",
    "curriculum",
    "case study",
)
CAVEAT_MARKERS = (
    "한계",
    "제한",
    "다만",
    "그러나",
    "유의",
    "주의",
    "limitation",
    "however",
    "caveat",
)

#: 불용어 — 키워드 추출 시 제외
STOPWORDS = {
    "그리고", "그러나", "또한", "이는", "이를", "위한", "대한", "통해", "있는", "있다",
    "한다", "하는", "된다", "되는", "the", "and", "for", "this", "that", "with", "from",
    "are", "was", "were", "have", "has", "その", "이러한", "따라", "관한", "경우",
}


class ExtractiveSummarizer(Summarizer):
    """빈도 기반 문장 선별 요약기."""

    name = "extractive"

    def __init__(self, *, max_key_points: int = 5, max_fulltext_chars: int = 40_000):
        self.max_key_points = max_key_points
        self.max_fulltext_chars = max_fulltext_chars

    # ------------------------------------------------------------------
    def summarize(self, resource: Resource, extracted: ExtractedText | None = None) -> Summary:
        basis = determine_basis(resource, extracted)
        body = self._body_for(resource, extracted, basis)
        sentences = self._sentences(body)

        if not sentences:
            return self._metadata_only(resource, basis)

        ranked = self._rank(sentences)
        key_points = [s for s, _ in ranked[: self.max_key_points]]

        return Summary(
            headline=self._headline(resource, ranked),
            key_points=key_points,
            practical_meaning=self._pick(sentences, PRACTICAL_MARKERS)
            or "원문에서 실무 적용에 관한 명시적 서술을 찾지 못했습니다.",
            education_points=self._pick_all(sentences, EDUCATION_MARKERS, limit=2)
            or self._education_fallback(resource),
            caveats=self._pick(sentences, CAVEAT_MARKERS)
            or "원문에 명시된 제한사항은 확인되지 않았습니다.",
            evidence_scope=self._evidence_scope(resource, extracted, basis, key_points),
            basis=basis,
            generated_by=self.name,
        )

    # ------------------------------------------------------------------
    def _body_for(
        self, resource: Resource, extracted: ExtractedText | None, basis: SummaryBasis
    ) -> str:
        if basis == SummaryBasis.FULLTEXT and extracted:
            return extracted.text[: self.max_fulltext_chars]
        if basis == SummaryBasis.ABSTRACT:
            return resource.abstract_original
        return ""

    @staticmethod
    def _sentences(text: str) -> list[str]:
        if not text:
            return []
        raw = SENTENCE_SPLIT_RE.split(text)
        out: list[str] = []
        for sentence in raw:
            cleaned = re.sub(r"\s+", " ", sentence).strip()
            # 너무 짧거나 목차·페이지 번호로 보이는 줄은 제외
            if len(cleaned) < 25 or len(cleaned) > 400:
                continue
            if re.fullmatch(r"[\d\s.\-–—]+", cleaned):
                continue
            out.append(cleaned)
        return out

    def _rank(self, sentences: list[str]) -> list[tuple[str, float]]:
        """단어 빈도 기반으로 문장 점수를 매깁니다."""
        counter: Counter[str] = Counter()
        for sentence in sentences:
            for token in self._tokens(sentence):
                counter[token] += 1
        if not counter:
            return [(s, 0.0) for s in sentences]

        peak = max(counter.values())
        scored: list[tuple[str, float]] = []
        for index, sentence in enumerate(sentences):
            tokens = self._tokens(sentence)
            if not tokens:
                continue
            score = sum(counter[t] / peak for t in tokens) / len(tokens)
            # 앞부분 문장에 약간의 가중치 (초록·서론에 핵심이 몰림)
            position_bonus = 0.15 if index < len(sentences) * 0.2 else 0.0
            scored.append((sentence, score + position_bonus))

        scored.sort(key=lambda kv: kv[1], reverse=True)
        return scored

    @staticmethod
    def _tokens(sentence: str) -> list[str]:
        tokens = re.findall(r"[가-힣]{2,}|[A-Za-z]{3,}", sentence.lower())
        return [t for t in tokens if t not in STOPWORDS]

    # ------------------------------------------------------------------
    def _headline(self, resource: Resource, ranked: list[tuple[str, float]]) -> str:
        if ranked:
            top = ranked[0][0]
            if len(top) <= 160:
                return top
            return top[:157] + "…"
        return resource.best_title()

    @staticmethod
    def _pick(sentences: list[str], markers: tuple[str, ...]) -> str:
        for sentence in sentences:
            lowered = sentence.lower()
            if any(m in lowered for m in markers):
                return sentence
        return ""

    @staticmethod
    def _pick_all(sentences: list[str], markers: tuple[str, ...], limit: int) -> list[str]:
        out: list[str] = []
        for sentence in sentences:
            lowered = sentence.lower()
            if any(m in lowered for m in markers):
                out.append(sentence)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _education_fallback(resource: Resource) -> list[str]:
        """원문에 교육 관련 서술이 없을 때, 주제 기준의 활용 방향만 제시합니다."""
        return [
            f"'{resource.best_title()[:60]}' 는 {resource.topic_primary} 분야 "
            "교육자료의 배경지식·참고문헌으로 활용할 수 있습니다."
        ]

    @staticmethod
    def _evidence_scope(
        resource: Resource,
        extracted: ExtractedText | None,
        basis: SummaryBasis,
        key_points: list[str],
    ) -> str:
        if basis == SummaryBasis.FULLTEXT and extracted:
            pages = [p for p in (extracted.page_of(kp) for kp in key_points) if p]
            if pages:
                return f"원문 {extracted.page_count}쪽 중 {min(pages)}~{max(pages)}쪽 기준"
            return f"원문 전체 {extracted.page_count}쪽 기준"
        if basis == SummaryBasis.ABSTRACT:
            return "초록 기준 (원문 전체 미분석)"
        return "제목·키워드·서지정보 기준"

    def _metadata_only(self, resource: Resource, basis: SummaryBasis) -> Summary:
        title = resource.best_title()
        publisher = resource.publisher or resource.source_id
        return Summary(
            headline=f"{publisher} 발간 '{title}'",
            key_points=[
                f"발행기관: {publisher}",
                f"발행일: {resource.publication_date or '미상'}",
                f"문서유형: {resource.document_type}",
            ],
            practical_meaning="원문·초록을 확보하지 못해 내용 분석을 수행하지 않았습니다.",
            education_points=self._education_fallback(resource),
            caveats="서지정보만으로 판단한 결과이므로 원문 확인이 필요합니다.",
            evidence_scope="제목·키워드·서지정보 기준",
            basis=basis,
            generated_by=self.name,
        )
