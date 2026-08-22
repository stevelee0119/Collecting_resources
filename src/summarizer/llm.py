"""LLM 요약 어댑터 (선택 공급자, PRD v2.1 §14, §19.2).

공급자를 교체할 수 있는 adapter 구조이며, 기본 구현은 Anthropic Claude 입니다.
`config.yaml` 의 `summarizer.provider: llm` 로 활성화합니다.

핵심 원칙 (§14.4):
- 원문/초록에 없는 판례·조문·페이지를 만들어내지 않도록 프롬프트에서 금지하고,
  근거로 제공한 텍스트 범위를 `evidence_scope` 에 명시합니다.
- API Key 는 소스코드에 두지 않고 환경변수(`ANTHROPIC_API_KEY`)로만 읽습니다.
"""

from __future__ import annotations

import json
import logging
import re

from ..config_loader import AppConfig, get_secret
from ..extractors import ExtractedText
from ..models import Resource, SummaryBasis
from .base import Summary, Summarizer, determine_basis
from .extractive import ExtractiveSummarizer

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """당신은 군법무·국방법·공공정책 분야 리서치 분석관입니다.
제공된 자료의 텍스트만 근거로 한국어 요약을 작성합니다.

반드시 지킬 것:
- 제공된 텍스트에 없는 판례번호, 법조문, 페이지 번호, 통계를 만들어내지 마십시오.
- 근거가 부족한 항목은 추측하지 말고 "원문에서 확인되지 않음" 이라고 쓰십시오.
- 법령·판례는 사건번호/법령명/공포·시행일이 원문에 있을 때만 인용하십시오.
- 답변은 아래 JSON 스키마 하나만 출력하고 그 외 텍스트는 쓰지 마십시오.

{
  "headline": "한줄 핵심 (80자 이내)",
  "key_points": ["핵심 내용 3~5개"],
  "practical_meaning": "국방·법률 실무상 의미",
  "education_points": ["군법무 교육에 활용 가능한 포인트 1~3개"],
  "caveats": "주요 제한·주의사항",
  "evidence_scope": "요약의 근거가 된 원문 범위"
}"""

JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


class ClaudeSummarizer(Summarizer):
    """Anthropic Claude 기반 요약기."""

    name = "claude"

    def __init__(
        self,
        *,
        model: str = "claude-opus-5",
        max_tokens: int = 4000,
        effort: str = "medium",
        max_input_chars: int = 60_000,
        fallback: Summarizer | None = None,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.max_input_chars = max_input_chars
        self.fallback = fallback or ExtractiveSummarizer()
        self._client = None

    # ------------------------------------------------------------------
    @classmethod
    def from_config(cls, app: AppConfig) -> ClaudeSummarizer:
        return cls(
            model=str(app.get("summarizer.llm.model", "claude-opus-5")),
            max_tokens=int(app.get("summarizer.llm.max_tokens", 4000)),
            effort=str(app.get("summarizer.llm.effort", "medium")),
            max_input_chars=int(app.get("summarizer.llm.max_input_chars", 60_000)),
            fallback=ExtractiveSummarizer(
                max_fulltext_chars=int(app.get("summarizer.max_fulltext_chars", 40_000))
            ),
        )

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "anthropic 패키지가 설치되어 있지 않습니다. "
                "pip install anthropic 후 사용하거나 summarizer.provider 를 extractive 로 두세요."
            ) from exc
        # API Key 는 환경변수에서만 읽습니다 (§18.3).
        if not get_secret("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY 가 설정되지 않았습니다. "
                "docs/API_발급_연동_가이드.md 를 참고해 .env 에 등록하세요."
            )
        self._client = anthropic.Anthropic()
        return self._client

    # ------------------------------------------------------------------
    def summarize(self, resource: Resource, extracted: ExtractedText | None = None) -> Summary:
        basis = determine_basis(resource, extracted)
        if basis == SummaryBasis.METADATA_ONLY:
            # 서지정보만 있는 자료는 LLM 을 쓰지 않습니다(환각 위험 대비 이득이 없음).
            return self.fallback.summarize(resource, extracted)

        try:
            payload = self._call(resource, extracted, basis)
        except Exception as exc:
            logger.warning(
                "LLM 요약 실패, 추출식 요약으로 대체합니다 (%s): %s",
                resource.best_title()[:40],
                exc,
            )
            return self.fallback.summarize(resource, extracted)

        return Summary(
            headline=str(payload.get("headline", "")).strip(),
            key_points=[str(p).strip() for p in (payload.get("key_points") or []) if str(p).strip()],
            practical_meaning=str(payload.get("practical_meaning", "")).strip(),
            education_points=[
                str(p).strip() for p in (payload.get("education_points") or []) if str(p).strip()
            ],
            caveats=str(payload.get("caveats", "")).strip(),
            evidence_scope=str(payload.get("evidence_scope", "")).strip()
            or self._default_scope(extracted, basis),
            basis=basis,
            generated_by=f"{self.name}:{self.model}",
        )

    # ------------------------------------------------------------------
    def _call(
        self, resource: Resource, extracted: ExtractedText | None, basis: SummaryBasis
    ) -> dict:
        client = self._get_client()
        import anthropic  # noqa: PLC0415

        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
                messages=[{"role": "user", "content": self._user_prompt(resource, extracted, basis)}],
            )
        except anthropic.NotFoundError as exc:
            raise RuntimeError(f"모델 또는 엔드포인트를 찾을 수 없습니다: {exc}") from exc
        except anthropic.RateLimitError as exc:
            retry_after = exc.response.headers.get("retry-after", "60")
            raise RuntimeError(f"호출량 초과 — {retry_after}초 후 재시도하세요.") from exc
        except anthropic.APIStatusError as exc:
            raise RuntimeError(f"API 오류 ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise RuntimeError(f"네트워크 오류: {exc}") from exc

        if response.stop_reason == "refusal":
            raise RuntimeError("모델이 요약 생성을 거부했습니다.")

        text = "".join(block.text for block in response.content if block.type == "text")
        return self._parse_json(text)

    def _user_prompt(
        self, resource: Resource, extracted: ExtractedText | None, basis: SummaryBasis
    ) -> str:
        header = [
            f"제목: {resource.best_title()}",
            f"발행기관: {resource.publisher or '미상'}",
            f"발행일: {resource.publication_date or '미상'}",
            f"문서유형: {resource.document_type}",
            f"주제분류: {resource.topic_primary}",
            f"근거수준: {basis.value}",
        ]
        if basis == SummaryBasis.FULLTEXT and extracted:
            body = extracted.text[: self.max_input_chars]
            scope = f"(원문 전체 {extracted.page_count}쪽 중 앞부분 {len(body)}자)"
        else:
            body = resource.abstract_original[: self.max_input_chars]
            scope = "(초록만 제공됨 — 원문 전체는 분석 대상이 아님)"

        return (
            "\n".join(header)
            + f"\n\n[분석 대상 텍스트 {scope}]\n"
            + body
            + "\n\n위 텍스트만 근거로 JSON 요약을 작성하십시오."
        )

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 모델이 설명을 덧붙인 경우 JSON 블록만 추출합니다.
        if match := JSON_BLOCK_RE.search(text):
            return json.loads(match.group(0))
        raise ValueError("모델 응답에서 JSON 을 찾지 못했습니다.")

    @staticmethod
    def _default_scope(extracted: ExtractedText | None, basis: SummaryBasis) -> str:
        if basis == SummaryBasis.FULLTEXT and extracted:
            return f"원문 전체 {extracted.page_count}쪽 기준"
        if basis == SummaryBasis.ABSTRACT:
            return "초록 기준 (원문 전체 미분석)"
        return "제목·키워드·서지정보 기준"
