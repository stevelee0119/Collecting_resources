"""주제 분류 (PRD v2.1 §12.1).

하이브리드 분류:
1. 규칙 기반 키워드 매칭
2. (선택) 임베딩/LLM 분류 어댑터
3. 기관/학술지 기반 사전분류
4. 낮은 신뢰도는 `99_미분류_검토필요`

두 개 이상 주제가 근소한 차이로 경합하면 `90_복수주제` 로 보냅니다.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

from ..config_loader import TopicRegistry
from ..models import Resource

logger = logging.getLogger(__name__)

STRONG_WEIGHT = 3.0
WEAK_WEIGHT = 1.0
#: 제목에서 발견된 키워드에 주는 가중
TITLE_MULTIPLIER = 2.0

#: 기관/학술지 기반 사전분류 (§12.1 3단계)
SOURCE_TOPIC_HINTS: dict[str, str] = {
    "law_go_kr": "05_형사_수사_사법",
    "kicj": "05_형사_수사_사법",
    "jpri": "05_형사_수사_사법",
    "ioj": "05_형사_수사_사법",
    "humanrights": "06_헌법_인권",
    "kida": "03_국방정책_행정법",
    "arxiv": "08_AI_법률AI_디지털법",
}
#: 사전분류가 주는 보너스 점수
SOURCE_HINT_BONUS = 1.5


class TopicModel(Protocol):
    """임베딩/LLM 기반 분류 어댑터 (선택)."""

    def classify(self, text: str, topic_ids: list[str]) -> dict[str, float]:
        ...


@dataclass
class ClassificationResult:
    topic_primary: str
    topics: list[str] = field(default_factory=list)
    confidence: float = 0.0
    scores: dict[str, float] = field(default_factory=dict)


class TopicClassifier:
    """규칙 기반 + 선택적 모델 기반 하이브리드 분류기."""

    def __init__(
        self,
        topics: TopicRegistry,
        *,
        min_confidence: float = 0.25,
        multi_topic_margin: float = 0.15,
        model: TopicModel | None = None,
    ):
        self.topics = topics
        self.min_confidence = min_confidence
        self.multi_topic_margin = multi_topic_margin
        self.model = model

    # ------------------------------------------------------------------
    def classify(self, resource: Resource, fulltext: str = "") -> ClassificationResult:
        title = f"{resource.title_ko} {resource.title_original}".strip()
        body = " ".join(
            [resource.abstract_original, " ".join(resource.keywords), fulltext[:20_000]]
        )

        scores = self._rule_scores(title, body)

        # 검색어 사전이 알려준 주제에 가중을 줍니다 (어떤 검색어로 발견됐는지 활용).
        if resource.topic_primary and resource.topic_primary in scores:
            scores[resource.topic_primary] += 1.0

        # 기관/학술지 기반 사전분류
        if hint := SOURCE_TOPIC_HINTS.get(resource.source_id):
            scores[hint] = scores.get(hint, 0.0) + SOURCE_HINT_BONUS

        # 선택적 모델 분류를 합산
        if self.model:
            try:
                model_scores = self.model.classify(
                    f"{title}\n{resource.abstract_original}", self.topics.ids()
                )
                for topic_id, value in model_scores.items():
                    scores[topic_id] = scores.get(topic_id, 0.0) + value * 3.0
            except Exception as exc:
                logger.debug("모델 기반 분류 실패, 규칙 기반 결과만 사용합니다: %s", exc)

        return self._decide(scores)

    # ------------------------------------------------------------------
    def _rule_scores(self, title: str, body: str) -> dict[str, float]:
        title_l = title.lower()
        body_l = body.lower()
        scores: dict[str, float] = {}

        for topic in self.topics.classifiable():
            score = 0.0
            for keyword in topic.keywords_strong:
                k = keyword.lower()
                if k in title_l:
                    score += STRONG_WEIGHT * TITLE_MULTIPLIER
                elif k in body_l:
                    score += STRONG_WEIGHT
            for keyword in topic.keywords_weak:
                k = keyword.lower()
                if k in title_l:
                    score += WEAK_WEIGHT * TITLE_MULTIPLIER
                elif k in body_l:
                    score += WEAK_WEIGHT
            if score > 0:
                scores[topic.topic_id] = score
        return scores

    def _decide(self, scores: dict[str, float]) -> ClassificationResult:
        if not scores:
            return ClassificationResult(
                topic_primary=TopicRegistry.UNCLASSIFIED, topics=[], confidence=0.0, scores={}
            )

        total = sum(scores.values())
        normalized = {k: v / total for k, v in scores.items()}
        ranked = sorted(normalized.items(), key=lambda kv: kv[1], reverse=True)

        top_id, top_conf = ranked[0]
        if top_conf < self.min_confidence:
            return ClassificationResult(
                topic_primary=TopicRegistry.UNCLASSIFIED,
                topics=[t for t, _ in ranked[:3]],
                confidence=top_conf,
                scores=normalized,
            )

        # 근소한 차이로 경합하면 복수주제로 처리
        contenders = [t for t, c in ranked if top_conf - c <= self.multi_topic_margin]
        if len(contenders) > 1:
            return ClassificationResult(
                topic_primary=TopicRegistry.MULTI_TOPIC,
                topics=contenders,
                confidence=top_conf,
                scores=normalized,
            )

        return ClassificationResult(
            topic_primary=top_id,
            topics=[t for t, _ in ranked[:3]],
            confidence=top_conf,
            scores=normalized,
        )

    # ------------------------------------------------------------------
    def apply(self, resource: Resource, fulltext: str = "") -> Resource:
        result = self.classify(resource, fulltext)
        resource.topic_primary = result.topic_primary
        resource.topics = result.topics
        resource.score_breakdown = dict(resource.score_breakdown)
        resource.score_breakdown["topic_confidence"] = round(result.confidence, 4)
        return resource
