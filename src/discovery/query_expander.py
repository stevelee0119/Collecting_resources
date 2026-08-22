"""다국어 검색어 변환·확장 엔진 (PRD v2.1 §6.4, §6.5, §6.6).

핵심 원칙:
1. `query_language: en` 소스에는 한국어 seed term 을 그대로 보내지 않는다.
2. 검수된 한·영 대응사전을 먼저 조회하고, 없을 때만 번역 어댑터를 보조 사용한다.
3. 자동 생성된 용어는 `machine_suggested=true` 로 표시해 검수 대상에 남긴다.
4. 실제로 사용한 Query 전문을 기록해 재현 가능하게 한다.
"""

from __future__ import annotations

import logging
from typing import Protocol

from ..config_loader import SearchTermDictionary
from ..models import Query, SearchTerm

logger = logging.getLogger(__name__)


class Translator(Protocol):
    """사전에 없는 용어를 보조 번역하는 어댑터."""

    def translate_ko_to_en(self, text: str) -> list[str]:
        ...


class NullTranslator:
    """기본값 — 사전에 없으면 번역하지 않습니다.

    검수되지 않은 기계 번역을 핵심 검색어로 쓰지 않는다는 §6.4 원칙에 따라,
    번역 어댑터를 명시적으로 붙이지 않는 한 확장하지 않습니다.
    """

    def translate_ko_to_en(self, text: str) -> list[str]:  # noqa: ARG002
        return []


class QueryExpander:
    """검색어 사전을 소스 언어에 맞는 Query 로 변환합니다."""

    def __init__(
        self,
        dictionary: SearchTermDictionary,
        translator: Translator | None = None,
        *,
        max_terms_per_query: int = 6,
    ):
        self.dictionary = dictionary
        self.translator = translator or NullTranslator()
        self.max_terms_per_query = max_terms_per_query
        self.unresolved: list[str] = []

    # ------------------------------------------------------------------
    def build_queries(
        self,
        *,
        language: str,
        scope: str,
        topic_ids: list[str] | None = None,
        max_queries: int | None = None,
    ) -> list[Query]:
        """소스 하나에 사용할 Query 목록을 만듭니다.

        Args:
            language: 소스의 `query_language` (ko / en / multilingual)
            scope: `domestic` 또는 `international`
            topic_ids: 특정 주제로 제한할 경우 topic_id 목록
            max_queries: 생성할 최대 Query 수
        """
        terms = self.dictionary.by_scope(scope)
        if topic_ids:
            terms = [t for t in terms if t.topic_id in topic_ids]
        terms = sorted(terms, key=lambda t: (t.priority, t.canonical_ko))

        queries: list[Query] = []
        for term in terms:
            query = self._build_one(term, language)
            if query:
                queries.append(query)
            if max_queries and len(queries) >= max_queries:
                break
        return queries

    # ------------------------------------------------------------------
    def _build_one(self, term: SearchTerm, language: str) -> Query | None:
        lang = (language or "ko").lower()
        if lang == "en":
            return self._build_english(term)
        if lang == "multilingual":
            english = self._build_english(term)
            korean = self._build_korean(term)
            if english and korean:
                merged = f"({korean.query_string}) OR ({english.query_string})"
                return Query(
                    query_string=merged,
                    language="multilingual",
                    canonical_ko=term.canonical_ko,
                    original_terms=korean.original_terms,
                    expanded_terms=korean.expanded_terms + english.expanded_terms,
                    exclude_terms=term.exclude_terms,
                    dictionary_version=self.dictionary.dictionary_version,
                    topic_id=term.topic_id,
                    machine_suggested=english.machine_suggested,
                )
            return english or korean
        return self._build_korean(term)

    def _build_korean(self, term: SearchTerm) -> Query:
        """국내 소스용 — 띄어쓰기·약칭 변형을 함께 조회합니다 (§3.3 확장 규칙)."""
        variants = self._dedupe([term.canonical_ko, *term.ko_variants])[: self.max_terms_per_query]
        return Query(
            query_string=self._or_join(variants),
            language="ko",
            canonical_ko=term.canonical_ko,
            original_terms=[term.canonical_ko],
            expanded_terms=variants,
            exclude_terms=term.exclude_terms,
            dictionary_version=self.dictionary.dictionary_version,
            topic_id=term.topic_id,
            machine_suggested=False,
        )

    def _build_english(self, term: SearchTerm) -> Query | None:
        """영문 소스용 — 검수된 영문 용어로만 질의를 만듭니다."""
        machine_suggested = False
        en_terms = self._dedupe([*term.en_terms, *term.en_acronyms])

        if not en_terms:
            # 사전에 없는 용어만 번역 어댑터를 보조적으로 사용 (§6.4 원칙 4)
            suggested = self._dedupe(self.translator.translate_ko_to_en(term.canonical_ko))
            if not suggested:
                self.unresolved.append(term.canonical_ko)
                logger.debug(
                    "영문 대응어가 없어 영문 소스 검색에서 제외합니다: %s", term.canonical_ko
                )
                return None
            en_terms = suggested
            machine_suggested = True
            logger.info(
                "사전에 없는 용어를 기계 제안으로 확장했습니다(검수 필요): %s → %s",
                term.canonical_ko,
                ", ".join(en_terms),
            )

        en_terms = en_terms[: self.max_terms_per_query]
        return Query(
            query_string=self._or_join(en_terms, phrase=True),
            language="en",
            canonical_ko=term.canonical_ko,
            original_terms=[term.canonical_ko],
            expanded_terms=en_terms,
            exclude_terms=term.exclude_terms,
            dictionary_version=self.dictionary.dictionary_version,
            topic_id=term.topic_id,
            machine_suggested=machine_suggested,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _dedupe(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            cleaned = (item or "").strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                out.append(cleaned)
        return out

    @staticmethod
    def _or_join(terms: list[str], *, phrase: bool = False) -> str:
        """Boolean/phrase 검색을 지원하는 소스를 위해 정확구문 + OR 그룹을 만듭니다."""
        if not terms:
            return ""
        if len(terms) == 1:
            return f'"{terms[0]}"' if phrase and " " in terms[0] else terms[0]
        parts = [f'"{t}"' if (phrase and " " in t) else t for t in terms]
        return " OR ".join(parts)


class DeepTranslatorAdapter:
    """선택 기능 — `deep-translator` 가 설치된 경우에만 동작합니다 (§19.3).

    자동 번역 결과는 항상 `machine_suggested` 로 표시되어 검수 대상이 됩니다.
    """

    def __init__(self) -> None:
        try:
            from deep_translator import GoogleTranslator  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover - 선택 의존성
            raise RuntimeError(
                "deep-translator 가 설치되어 있지 않습니다. "
                "pip install deep-translator 후 사용하세요."
            ) from exc
        self._translator = GoogleTranslator(source="ko", target="en")

    def translate_ko_to_en(self, text: str) -> list[str]:
        try:
            result = self._translator.translate(text)
        except Exception as exc:  # pragma: no cover - 외부 서비스
            logger.warning("보조 번역 실패 (%s): %s", text, exc)
            return []
        return [result] if result else []
