"""설정 및 Source Registry 로더 (PRD v2.1 §5).

- `config/config.yaml`  : 운영 설정
- `config/sources.yaml` : Source Registry
- `config/topics.yaml`  : 주제 분류 체계
- `config/search_terms.yaml` : 검색어 사전
- `.env`                : 비밀정보 (Git 제외)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from .models import SearchTerm, SourceConfig

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


class ConfigError(RuntimeError):
    """설정 파일이 없거나 형식이 잘못된 경우."""


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"설정 파일을 찾을 수 없습니다: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ConfigError(f"설정 파일 형식이 올바르지 않습니다(맵이 아님): {path}")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """defaults 위에 소스별 값을 덮어씁니다."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


# ---------------------------------------------------------------------------
# 주제 체계
# ---------------------------------------------------------------------------

@dataclass
class Topic:
    topic_id: str
    name: str
    description: str = ""
    keywords_strong: list[str] = field(default_factory=list)
    keywords_weak: list[str] = field(default_factory=list)
    trust_boost: int = 0


@dataclass
class TopicRegistry:
    version: str
    topics: list[Topic]
    document_type_scores: dict[str, int]

    UNCLASSIFIED = "99_미분류_검토필요"
    MULTI_TOPIC = "90_복수주제"

    def ids(self) -> list[str]:
        return [t.topic_id for t in self.topics]

    def get(self, topic_id: str) -> Topic | None:
        for t in self.topics:
            if t.topic_id == topic_id:
                return t
        return None

    def classifiable(self) -> list[Topic]:
        """실제 분류 후보가 되는 주제(복수주제/미분류 제외)."""
        skip = {self.UNCLASSIFIED, self.MULTI_TOPIC}
        return [t for t in self.topics if t.topic_id not in skip]

    def document_type_score(self, document_type: str) -> int:
        return self.document_type_scores.get(document_type, self.document_type_scores.get("기타", 3))


def load_topics(path: Path | None = None) -> TopicRegistry:
    data = _read_yaml(path or CONFIG_DIR / "topics.yaml")
    topics = [
        Topic(
            topic_id=t["topic_id"],
            name=t.get("name", t["topic_id"]),
            description=t.get("description", ""),
            keywords_strong=list(t.get("keywords_strong") or []),
            keywords_weak=list(t.get("keywords_weak") or []),
            trust_boost=int(t.get("trust_boost", 0)),
        )
        for t in data.get("topics", [])
    ]
    if not topics:
        raise ConfigError("topics.yaml 에 주제가 정의되어 있지 않습니다.")
    return TopicRegistry(
        version=str(data.get("version", "")),
        topics=topics,
        document_type_scores=dict(data.get("document_type_scores") or {}),
    )


# ---------------------------------------------------------------------------
# 검색어 사전
# ---------------------------------------------------------------------------

@dataclass
class SearchTermDictionary:
    dictionary_version: str
    terms: list[SearchTerm]
    required_baseline: list[str]

    def by_scope(self, scope: str) -> list[SearchTerm]:
        return [t for t in self.terms if scope in t.source_scope]

    def find(self, canonical_ko: str) -> SearchTerm | None:
        for t in self.terms:
            if t.canonical_ko == canonical_ko:
                return t
        return None

    def missing_required(self) -> list[str]:
        """§3.3 필수 키워드 중 사전에 없는 항목 (§23.1 수용기준 자동검사)."""
        present: set[str] = set()
        for t in self.terms:
            present.add(t.canonical_ko)
            present.update(t.ko_variants)
            present.update(t.related_terms)
        return [k for k in self.required_baseline if k not in present]


def load_search_terms(path: Path | None = None) -> SearchTermDictionary:
    data = _read_yaml(path or CONFIG_DIR / "search_terms.yaml")
    terms = [SearchTerm(**t) for t in data.get("terms", [])]
    if not terms:
        raise ConfigError("search_terms.yaml 에 검색어가 정의되어 있지 않습니다.")
    return SearchTermDictionary(
        dictionary_version=str(data.get("dictionary_version", "unversioned")),
        terms=terms,
        required_baseline=list(data.get("required_baseline") or []),
    )


# ---------------------------------------------------------------------------
# Source Registry
# ---------------------------------------------------------------------------

@dataclass
class SourceRegistry:
    registry_version: str
    sources: list[SourceConfig]

    def enabled(self) -> list[SourceConfig]:
        """활성 소스를 우선순위 순으로 반환합니다."""
        return sorted((s for s in self.sources if s.enabled), key=lambda s: (s.priority, s.source_id))

    def get(self, source_id: str) -> SourceConfig | None:
        for s in self.sources:
            if s.source_id == source_id:
                return s
        return None

    def requiring_credentials(self) -> list[tuple[SourceConfig, Any]]:
        """사전 발급·승인이 필요한 (소스, 접근방식) 목록 — API 가이드 생성용 (§5.1)."""
        out: list[tuple[SourceConfig, Any]] = []
        for s in self.sources:
            for m in s.access_methods:
                if m.credential_required or m.auth_type != "NONE":
                    out.append((s, m))
        return out


def load_sources(path: Path | None = None) -> SourceRegistry:
    data = _read_yaml(path or CONFIG_DIR / "sources.yaml")
    defaults = data.get("defaults") or {}
    sources: list[SourceConfig] = []
    seen: set[str] = set()
    for raw in data.get("sources", []):
        merged = _deep_merge(defaults, raw)
        cfg = SourceConfig(**merged)
        if cfg.source_id in seen:
            raise ConfigError(f"sources.yaml 에 중복된 source_id 가 있습니다: {cfg.source_id}")
        seen.add(cfg.source_id)
        sources.append(cfg)
    if not sources:
        raise ConfigError("sources.yaml 에 등록된 소스가 없습니다.")
    return SourceRegistry(registry_version=str(data.get("registry_version", "")), sources=sources)


# ---------------------------------------------------------------------------
# 운영 설정
# ---------------------------------------------------------------------------

class AppConfig:
    """`config/config.yaml` 접근 래퍼. 점 표기 경로로 값을 읽습니다."""

    def __init__(self, data: dict[str, Any], project_root: Path):
        self._data = data
        self.project_root = project_root

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def path(self, dotted: str, default: str = "") -> Path:
        """설정에 적힌 상대경로를 프로젝트 기준 절대경로로 변환합니다."""
        value = self.get(dotted, default)
        p = Path(str(value))
        return p if p.is_absolute() else (self.project_root / p)

    @property
    def raw(self) -> dict[str, Any]:
        return self._data


def load_app_config(path: Path | None = None) -> AppConfig:
    cfg_path = path or CONFIG_DIR / "config.yaml"
    return AppConfig(_read_yaml(cfg_path), PROJECT_ROOT)


# ---------------------------------------------------------------------------
# 비밀정보
# ---------------------------------------------------------------------------

def load_env(dotenv_path: Path | None = None) -> None:
    """`.env` 를 환경변수로 읽어들입니다. 이미 설정된 환경변수를 덮어쓰지 않습니다."""
    load_dotenv(dotenv_path or PROJECT_ROOT / ".env", override=False)


def get_secret(env_var: str | None) -> str | None:
    """환경변수에서 비밀값을 읽습니다. 값이 비어 있으면 None 을 반환합니다."""
    if not env_var:
        return None
    value = os.environ.get(env_var, "").strip()
    return value or None


def mask_secret(value: str | None) -> str:
    """로그 출력용 마스킹 (§18.3)."""
    if not value:
        return "(미설정)"
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"


# ---------------------------------------------------------------------------
# 한 번에 로드
# ---------------------------------------------------------------------------

@dataclass
class Settings:
    app: AppConfig
    sources: SourceRegistry
    topics: TopicRegistry
    search_terms: SearchTermDictionary


def load_settings(config_dir: Path | None = None) -> Settings:
    """모든 설정을 한 번에 로드합니다."""
    load_env()
    base = config_dir or CONFIG_DIR
    return Settings(
        app=load_app_config(base / "config.yaml"),
        sources=load_sources(base / "sources.yaml"),
        topics=load_topics(base / "topics.yaml"),
        search_terms=load_search_terms(base / "search_terms.yaml"),
    )
