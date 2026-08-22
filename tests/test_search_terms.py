"""검색어 사전 및 다국어 확장 엔진 테스트 (PRD v2.1 §3.3, §6.4, §23.1)."""

from __future__ import annotations

import pytest

from src.config_loader import load_search_terms
from src.discovery.query_expander import NullTranslator, QueryExpander

# §23.1 MVP 수용기준이 명시한 필수 키워드
ACCEPTANCE_KEYWORDS = [
    "포렌식", "위법수집증거", "판결", "방위사업법", "군사기밀보호법", "군사기지",
    "사법제도", "군검찰", "군사경찰", "증거능력", "법률전", "군검사",
    "형사소송법", "군사법원", "통합방위법",
]


@pytest.fixture(scope="module")
def dictionary():
    return load_search_terms()


def test_required_baseline_has_no_missing_terms(dictionary):
    """§3.3 필수 키워드가 사전에 모두 존재해야 합니다."""
    assert dictionary.missing_required() == []


def test_acceptance_keywords_present(dictionary):
    """§23.1 수용기준이 나열한 키워드가 사전에 있어야 합니다."""
    present = set()
    for term in dictionary.terms:
        present.add(term.canonical_ko)
        present.update(term.ko_variants)
        present.update(term.related_terms)
    missing = [k for k in ACCEPTANCE_KEYWORDS if k not in present]
    assert missing == [], f"수용기준 키워드 누락: {missing}"


def test_dictionary_is_versioned(dictionary):
    assert dictionary.dictionary_version
    assert dictionary.dictionary_version != "unversioned"


def test_international_terms_have_english(dictionary):
    """international scope 용어는 영문 대응어를 가져야 합니다 (§6.4)."""
    missing = [
        t.canonical_ko
        for t in dictionary.terms
        if "international" in t.source_scope and not (t.en_terms or t.en_acronyms)
    ]
    assert missing == [], f"영문 대응어 없음: {missing}"


# ---------------------------------------------------------------------------
# 확장 엔진
# ---------------------------------------------------------------------------

def test_english_query_contains_no_hangul(dictionary):
    """query_language=en 소스에 한국어 seed term 을 보내지 않아야 합니다 (§6.4 원칙 1)."""
    expander = QueryExpander(dictionary)
    queries = expander.build_queries(language="en", scope="international")
    assert queries, "영문 질의가 생성되지 않았습니다."
    for query in queries:
        assert not any("가" <= ch <= "힣" for ch in query.query_string), (
            f"영문 질의에 한글이 포함되었습니다: {query.query_string}"
        )


def test_english_query_uses_verified_terms(dictionary):
    """검수된 영문 학술용어로 변환·확장되어야 합니다."""
    expander = QueryExpander(dictionary)
    queries = {q.canonical_ko: q for q in expander.build_queries(language="en", scope="international")}

    operational = queries["작전법"]
    assert "operational law" in operational.query_string
    assert operational.machine_suggested is False

    ihl = queries["국제인도법"]
    # 동의어와 약어가 함께 확장되어야 합니다.
    assert "international humanitarian law" in ihl.query_string
    assert "IHL" in ihl.query_string


def test_korean_query_expands_variants(dictionary):
    """국내 질의는 띄어쓰기·약칭 변형을 함께 조회합니다 (§3.3 확장 규칙)."""
    expander = QueryExpander(dictionary)
    queries = {q.canonical_ko: q for q in expander.build_queries(language="ko", scope="domestic")}

    criminal = queries["형사소송법"]
    assert "형사소송법" in criminal.query_string
    assert "형소법" in criminal.expanded_terms


def test_query_records_reproducibility_fields(dictionary):
    """실제 사용한 Query 와 사전 버전을 기록해 재현 가능해야 합니다 (§6.4 원칙 7)."""
    expander = QueryExpander(dictionary)
    query = expander.build_queries(language="en", scope="international")[0]

    assert query.dictionary_version == dictionary.dictionary_version
    assert query.original_terms
    assert query.expanded_terms
    assert query.query_string


def test_unmapped_term_is_not_machine_translated_by_default():
    """사전에 없으면 기본적으로 확장하지 않고 검수 대상으로 남깁니다."""
    from src.config_loader import SearchTermDictionary
    from src.models import SearchTerm

    dictionary = SearchTermDictionary(
        dictionary_version="test-1",
        terms=[
            SearchTerm(
                canonical_ko="사전에없는용어",
                source_scope=["international"],
                topic_id="99_미분류_검토필요",
            )
        ],
        required_baseline=[],
    )
    expander = QueryExpander(dictionary, translator=NullTranslator())
    queries = expander.build_queries(language="en", scope="international")

    assert queries == []
    assert "사전에없는용어" in expander.unresolved


def test_machine_suggested_is_flagged():
    """번역 어댑터를 붙이면 machine_suggested 로 표시됩니다 (§6.4 원칙 4)."""
    from src.config_loader import SearchTermDictionary
    from src.models import SearchTerm

    class StubTranslator:
        def translate_ko_to_en(self, text: str) -> list[str]:
            return ["stub translation"]

    dictionary = SearchTermDictionary(
        dictionary_version="test-1",
        terms=[SearchTerm(canonical_ko="신규용어", source_scope=["international"])],
        required_baseline=[],
    )
    expander = QueryExpander(dictionary, translator=StubTranslator())
    query = expander.build_queries(language="en", scope="international")[0]

    assert query.machine_suggested is True
    assert "stub translation" in query.query_string
