"""메타데이터 정규화 유틸 (PRD v2.1 §6.1 4단계, §11).

DOI·제목·날짜·문서유형을 일관된 형태로 맞춰 중복 판별과 분류의 기준을 만듭니다.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime

# ---------------------------------------------------------------------------
# DOI
# ---------------------------------------------------------------------------

_DOI_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)

_DOI_PATTERN = re.compile(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", re.IGNORECASE)


def normalize_doi(raw: str | None) -> str:
    """DOI 를 소문자 `10.xxxx/yyy` 형태로 정규화합니다."""
    if not raw:
        return ""
    value = str(raw).strip()
    lowered = value.lower()
    for prefix in _DOI_PREFIXES:
        if lowered.startswith(prefix):
            value = value[len(prefix):]
            break
    match = _DOI_PATTERN.search(value)
    if not match:
        return ""
    return match.group(0).lower().rstrip(".,;")


def doi_to_url(doi: str) -> str:
    return f"https://doi.org/{doi}" if doi else ""


# ---------------------------------------------------------------------------
# 제목 / 텍스트
# ---------------------------------------------------------------------------

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s가-힣]", re.UNICODE)


def normalize_title(raw: str | None) -> str:
    """비교용 제목 — 유니코드 정규화 + 소문자 + 구두점/공백 제거."""
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", str(raw)).lower()
    text = _PUNCT.sub(" ", text)
    return _WS.sub(" ", text).strip()


def normalize_text(raw: str | None) -> str:
    """본문 해시용 정규화 — 공백/줄바꿈 차이를 제거합니다 (§11.1 4순위)."""
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", str(raw)).lower()
    text = _WS.sub(" ", text)
    return text.strip()


def text_sha256(raw: str | None) -> str:
    """정규화 텍스트 SHA256."""
    normalized = normalize_text(raw)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def title_similarity(a: str, b: str) -> float:
    """토큰 자카드 유사도 — 제목 fuzzy match 용."""
    tokens_a = set(normalize_title(a).split())
    tokens_b = set(normalize_title(b).split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union else 0.0


def clean_whitespace(raw: str | None) -> str:
    if not raw:
        return ""
    return _WS.sub(" ", str(raw)).strip()


# ---------------------------------------------------------------------------
# 날짜
# ---------------------------------------------------------------------------

_DATE_PATTERNS = (
    re.compile(r"(?P<y>\d{4})[-./](?P<m>\d{1,2})[-./](?P<d>\d{1,2})"),
    re.compile(r"(?P<y>\d{4})[-./](?P<m>\d{1,2})(?!\d)"),
    re.compile(r"(?P<y>\d{4})(?P<m>\d{2})(?P<d>\d{2})"),
    re.compile(r"(?P<y>\d{4})년\s*(?P<m>\d{1,2})월\s*(?:(?P<d>\d{1,2})일)?"),
    re.compile(r"^(?P<y>\d{4})$"),
)


def parse_date(raw: object) -> date | None:
    """다양한 표기의 날짜 문자열을 `date` 로 변환합니다.

    연도만 있으면 1월 1일로, 연-월만 있으면 해당 월 1일로 채웁니다.
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, (list, tuple)):
        # Crossref date-parts: [[2026, 8, 22]]
        parts = list(raw)
        while parts and isinstance(parts[0], (list, tuple)):
            parts = list(parts[0])
        if not parts:
            return None
        try:
            year = int(parts[0])
            month = int(parts[1]) if len(parts) > 1 else 1
            day = int(parts[2]) if len(parts) > 2 else 1
            return date(year, month, day)
        except (ValueError, TypeError):
            return None

    text = str(raw).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        groups = match.groupdict()
        try:
            year = int(groups["y"])
            month = int(groups.get("m") or 1)
            day = int(groups.get("d") or 1)
            month = min(max(month, 1), 12)
            day = min(max(day, 1), 31)
            while day > 1:
                try:
                    return date(year, month, day)
                except ValueError:
                    day -= 1
            return date(year, month, 1)
        except (ValueError, TypeError):
            continue
    return None


def year_of(value: date | None) -> int | None:
    return value.year if value else None


# ---------------------------------------------------------------------------
# 저자
# ---------------------------------------------------------------------------

def normalize_authors(raw: object) -> list[str]:
    """다양한 형태의 저자 필드를 문자열 리스트로 통일합니다."""
    if not raw:
        return []
    if isinstance(raw, str):
        parts = re.split(r"[;,·]|\band\b", raw)
        return [clean_whitespace(p) for p in parts if clean_whitespace(p)]
    if isinstance(raw, dict):
        raw = [raw]
    authors: list[str] = []
    for item in raw:  # type: ignore[union-attr]
        if isinstance(item, str):
            name = clean_whitespace(item)
        elif isinstance(item, dict):
            name = clean_whitespace(
                item.get("name")
                or item.get("display_name")
                or " ".join(
                    filter(None, [item.get("given", ""), item.get("family", "")])
                )
                or (item.get("author") or {}).get("display_name", "")
            )
        else:
            name = clean_whitespace(str(item))
        if name:
            authors.append(name)
    return authors


def first_author(authors: list[str]) -> str:
    return authors[0] if authors else ""


# ---------------------------------------------------------------------------
# 문서유형
# ---------------------------------------------------------------------------

_DOC_TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("법령", ("법률", "시행령", "시행규칙", "법령", "act", "statute", "decree")),
    ("판례", ("판례", "판결", "선고", "case law", "judgment", "precedent")),
    ("실무제요", ("실무제요", "실무편람", "handbook")),
    ("매뉴얼", ("매뉴얼", "manual", "가이드북", "guidebook", "guide")),
    ("지침", ("지침", "훈령", "예규", "guideline", "directive")),
    ("연구보고서", ("연구보고서", "정책연구", "research report", "report", "working paper")),
    ("학술논문", ("논문", "journal", "article", "학회지", "연구논문")),
    ("정책자료", ("정책", "policy", "brief", "이슈페이퍼")),
    ("프리프린트", ("preprint", "프리프린트", "arxiv", "ssrn")),
    ("간행물", ("간행물", "뉴스레터", "newsletter", "bulletin", "계간", "월간")),
]


def infer_document_type(*texts: str | None) -> str:
    """제목·유형 필드 등에서 문서유형을 추정합니다."""
    haystack = " ".join(t.lower() for t in texts if t)
    if not haystack:
        return "기타"
    for doc_type, needles in _DOC_TYPE_RULES:
        if any(n in haystack for n in needles):
            return doc_type
    return "기타"


def detect_language(text: str | None) -> str:
    """한글 포함 여부로 간단히 언어를 판정합니다."""
    if not text:
        return ""
    hangul = sum(1 for ch in text if "가" <= ch <= "힣")
    latin = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if hangul == 0 and latin == 0:
        return ""
    return "ko" if hangul >= max(1, latin // 4) else "en"


# ---------------------------------------------------------------------------
# work_id
# ---------------------------------------------------------------------------

def build_work_id(*, doi: str = "", identifier: str = "", title: str = "", year: int | None = None) -> str:
    """동일 연구성과를 묶는 논리 ID 를 만듭니다 (§10.1 work_id)."""
    if doi:
        return f"doi:{doi}"
    if identifier:
        return f"id:{identifier}"
    basis = f"{normalize_title(title)}|{year or ''}"
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]
    return f"title:{digest}"
