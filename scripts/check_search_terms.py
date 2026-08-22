"""검색어 사전 품질 점검 (PRD v2.1 §3.3, §6.6, §23.1).

- 필수 키워드 누락 검사
- 영문 대응어가 없는 international scope 용어 검사
- 미검수(human_verified=false) 용어 목록
CI 나 운영 점검에서 사용합니다. 문제가 있으면 종료코드 1 을 반환합니다.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config_loader import load_search_terms  # noqa: E402


def main() -> int:
    dictionary = load_search_terms()
    problems = 0

    print(f"검색어 사전 버전: {dictionary.dictionary_version}")
    print(f"등록 용어 수: {len(dictionary.terms)}")
    print(f"필수 키워드 수: {len(dictionary.required_baseline)}\n")

    missing = dictionary.missing_required()
    if missing:
        problems += 1
        print(f"[실패] 필수 키워드 {len(missing)}개 누락:")
        for keyword in missing:
            print(f"  - {keyword}")
    else:
        print("[통과] PRD §3.3 필수 키워드가 모두 포함되어 있습니다.")

    no_english = [
        t.canonical_ko
        for t in dictionary.terms
        if "international" in t.source_scope and not t.en_terms and not t.en_acronyms
    ]
    if no_english:
        problems += 1
        print(f"\n[실패] 영문 대응어가 없는 international 용어 {len(no_english)}개:")
        for term in no_english:
            print(f"  - {term}")
    else:
        print("[통과] international scope 용어에 모두 영문 대응어가 있습니다.")

    unverified = [t.canonical_ko for t in dictionary.terms if not t.human_verified]
    if unverified:
        print(f"\n[주의] 사람 검수가 필요한 용어 {len(unverified)}개: {', '.join(unverified)}")

    machine = [t.canonical_ko for t in dictionary.terms if t.machine_suggested]
    if machine:
        print(f"[주의] 기계 제안 용어 {len(machine)}개: {', '.join(machine)}")

    print()
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
