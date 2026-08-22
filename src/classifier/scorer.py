"""중요도 평가 (PRD v2.1 §12.2, §12.3).

배점 (합계 100):
- 주제 적합도 40 / 출처 신뢰도 20 / 최신성 15
- 실무·교육 활용성 10 / 문서유형 중요도 10 / OA 및 원문 이용가능성 5

신간 논문은 피인용 횟수가 낮으므로 단순 피인용 수를 핵심 점수로 쓰지 않습니다.
"""

from __future__ import annotations

import logging
from datetime import date

from ..config_loader import AppConfig, TopicRegistry
from ..models import AccessMode, PriorityLevel, Resource

logger = logging.getLogger(__name__)

#: 출처 신뢰도 (0.0 ~ 1.0) — 공식 기관·법령 소스가 가장 높습니다.
SOURCE_TRUST: dict[str, float] = {
    "law_go_kr": 1.0,
    "kci": 0.95,
    "nkis": 0.95,
    "prism": 0.9,
    "jpri": 0.95,
    "ioj": 0.9,
    "kicj": 0.95,
    "humanrights": 0.9,
    "nars": 0.95,
    "kida": 0.9,
    "scienceon": 0.85,
    "crossref": 0.8,
    "openalex": 0.75,
    "doaj": 0.8,
    "core": 0.75,
    "semantic_scholar": 0.7,
    "arxiv": 0.65,
    "ssrn": 0.7,
    "zenodo": 0.6,
    "riss": 0.85,
}
DEFAULT_TRUST = 0.6

#: 실무·교육 활용성을 높이는 표지
PRACTICAL_MARKERS = (
    "실무",
    "매뉴얼",
    "가이드",
    "지침",
    "사례",
    "교육",
    "해설",
    "제요",
    "handbook",
    "guide",
    "manual",
    "casebook",
    "training",
)


class RelevanceScorer:
    """0~100 중요도 점수와 P1~P4 우선순위를 산정합니다."""

    def __init__(self, app: AppConfig, topics: TopicRegistry):
        weights = app.get("scoring.weights", {}) or {}
        self.w_topic = float(weights.get("topic_fit", 40))
        self.w_trust = float(weights.get("source_trust", 20))
        self.w_recency = float(weights.get("recency", 15))
        self.w_practical = float(weights.get("practical_use", 10))
        self.w_doctype = float(weights.get("document_type", 10))
        self.w_oa = float(weights.get("open_access", 5))

        thresholds = app.get("scoring.priority_thresholds", {}) or {}
        self.p1 = int(thresholds.get("P1", 75))
        self.p2 = int(thresholds.get("P2", 55))
        self.p3 = int(thresholds.get("P3", 35))

        self.topics = topics

    # ------------------------------------------------------------------
    def score(self, resource: Resource, *, today: date | None = None) -> Resource:
        today = today or date.today()

        topic_fit = self._topic_fit(resource) * self.w_topic
        trust = SOURCE_TRUST.get(resource.source_id, DEFAULT_TRUST) * self.w_trust
        recency = self._recency(resource, today) * self.w_recency
        practical = self._practical(resource) * self.w_practical
        doctype = self._doctype(resource) * self.w_doctype
        oa = self._open_access(resource) * self.w_oa

        total = topic_fit + trust + recency + practical + doctype + oa
        score = max(0, min(100, round(total)))

        breakdown = dict(resource.score_breakdown)
        breakdown.update(
            {
                "topic_fit": round(topic_fit, 2),
                "source_trust": round(trust, 2),
                "recency": round(recency, 2),
                "practical_use": round(practical, 2),
                "document_type": round(doctype, 2),
                "open_access": round(oa, 2),
                "total": score,
            }
        )

        resource.score_breakdown = breakdown
        resource.relevance_score = score
        resource.priority_level = self._priority(score)
        return resource

    # ------------------------------------------------------------------
    def _topic_fit(self, resource: Resource) -> float:
        """분류 신뢰도를 기반으로 하되, 미분류는 크게 감점합니다."""
        if resource.topic_primary == TopicRegistry.UNCLASSIFIED:
            return 0.15
        confidence = float(resource.score_breakdown.get("topic_confidence", 0.0))
        if resource.topic_primary == TopicRegistry.MULTI_TOPIC:
            # 복수주제는 관련성이 높다고 보되 단일주제보다는 낮게 봅니다.
            return min(1.0, 0.55 + confidence)
        # 규칙 기반 신뢰도는 보통 0.3~0.8 범위이므로 스케일을 조정합니다.
        return min(1.0, 0.35 + confidence * 1.2)

    @staticmethod
    def _recency(resource: Resource, today: date) -> float:
        published = resource.publication_date or resource.source_registered_date
        if not published:
            return 0.4
        days = (today - published).days
        if days < 0:
            return 1.0
        if days <= 30:
            return 1.0
        if days <= 90:
            return 0.85
        if days <= 180:
            return 0.7
        if days <= 365:
            return 0.55
        if days <= 365 * 3:
            return 0.35
        return 0.15

    @staticmethod
    def _practical(resource: Resource) -> float:
        haystack = " ".join(
            [
                resource.title_ko,
                resource.title_original,
                resource.abstract_original[:1000],
                " ".join(resource.keywords),
            ]
        ).lower()
        hits = sum(1 for marker in PRACTICAL_MARKERS if marker in haystack)
        return min(1.0, hits * 0.34)

    def _doctype(self, resource: Resource) -> float:
        raw = self.topics.document_type_score(resource.document_type)
        max_score = max(self.topics.document_type_scores.values() or [10])
        return raw / max_score if max_score else 0.3

    @staticmethod
    def _open_access(resource: Resource) -> float:
        if resource.access_mode == AccessMode.DOWNLOADED:
            return 1.0
        if resource.oa_url or resource.download_url:
            return 0.7
        if not resource.license_unknown:
            return 0.5
        return 0.2

    def _priority(self, score: int) -> PriorityLevel:
        if score >= self.p1:
            return PriorityLevel.P1
        if score >= self.p2:
            return PriorityLevel.P2
        if score >= self.p3:
            return PriorityLevel.P3
        return PriorityLevel.P4
