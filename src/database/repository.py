"""SQLite 저장소 (PRD v2.1 §17).

파이프라인의 모든 상태를 기록하며, 감사가능성(§18.4)을 위해
"언제 / 어디서 / 어떤 정책으로 / 어떤 근거로" 를 모두 남깁니다.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..models import (
    PriorityLevel,
    Resource,
    ResourceStatus,
    RunReport,
    SourceConfig,
)
from ..normalizers.normalize import first_author, normalize_title
from .schema import DDL_STATEMENTS, FTS_STATEMENTS, SCHEMA_VERSION

logger = logging.getLogger(__name__)


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_load(value: Any, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class Repository:
    """자료·실행·오류 이력을 담당하는 SQLite 저장소."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.fts_enabled = False
        self._init_schema()

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Repository:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _init_schema(self) -> None:
        with self._conn:
            for ddl in DDL_STATEMENTS:
                self._conn.execute(ddl)
            for ddl in FTS_STATEMENTS:
                try:
                    self._conn.execute(ddl)
                    self.fts_enabled = True
                except sqlite3.OperationalError as exc:
                    # FTS5 미탑재 빌드에서도 나머지 기능은 동작해야 합니다.
                    logger.warning("FTS5 전문검색을 사용할 수 없습니다: %s", exc)
                    self.fts_enabled = False
            self._conn.execute(
                "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    # ------------------------------------------------------------------
    # 소스
    # ------------------------------------------------------------------
    def sync_sources(self, sources: Sequence[SourceConfig]) -> None:
        """레지스트리 내용을 DB 에 반영합니다(런타임 상태는 보존)."""
        with self._conn:
            for s in sources:
                self._conn.execute(
                    """
                    INSERT INTO sources (source_id, name, base_domain, mode, query_language,
                                         download_policy, enabled, last_policy_review_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id) DO UPDATE SET
                        name = excluded.name,
                        base_domain = excluded.base_domain,
                        mode = excluded.mode,
                        query_language = excluded.query_language,
                        download_policy = excluded.download_policy,
                        enabled = excluded.enabled,
                        last_policy_review_at = excluded.last_policy_review_at
                    """,
                    (
                        s.source_id,
                        s.name,
                        s.base_domain,
                        ",".join(m.value for m in s.mode),
                        s.query_language,
                        s.download_policy.value,
                        int(s.enabled),
                        _iso(s.last_policy_review_at),
                    ),
                )

    def record_source_attempt(self, source_id: str, *, success: bool, reason: str = "") -> int:
        """소스 실행 결과를 기록하고 연속 실패 횟수를 반환합니다 (§16.3)."""
        now = _iso(datetime.now())
        with self._conn:
            if success:
                self._conn.execute(
                    """UPDATE sources SET last_success_at = ?, last_attempt_at = ?,
                       consecutive_failures = 0, disabled_reason = NULL WHERE source_id = ?""",
                    (now, now, source_id),
                )
                return 0
            self._conn.execute(
                """UPDATE sources SET last_attempt_at = ?,
                   consecutive_failures = consecutive_failures + 1, disabled_reason = ?
                   WHERE source_id = ?""",
                (now, reason, source_id),
            )
        row = self._conn.execute(
            "SELECT consecutive_failures FROM sources WHERE source_id = ?", (source_id,)
        ).fetchone()
        return int(row["consecutive_failures"]) if row else 0

    def source_state(self, source_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM sources WHERE source_id = ?", (source_id,)
        ).fetchone()
        return dict(row) if row else None

    def last_successful_run(self, run_type: str | None = None) -> datetime | None:
        """마지막으로 완료된 실행 시각 — 증분 수집 기준점."""
        sql = "SELECT started_at FROM runs WHERE finished_at IS NOT NULL"
        params: list[Any] = []
        if run_type:
            sql += " AND run_type = ?"
            params.append(run_type)
        sql += " ORDER BY started_at DESC LIMIT 1"
        row = self._conn.execute(sql, params).fetchone()
        return _parse_datetime(row["started_at"]) if row else None

    def has_any_run(self) -> bool:
        row = self._conn.execute("SELECT 1 FROM runs LIMIT 1").fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # 중복 판별 (§11.1)
    # ------------------------------------------------------------------
    def find_by_doi(self, doi: str) -> Resource | None:
        if not doi:
            return None
        row = self._conn.execute(
            "SELECT * FROM resources WHERE doi = ? ORDER BY last_seen_at DESC LIMIT 1", (doi,)
        ).fetchone()
        return self._row_to_resource(row) if row else None

    def find_by_identifier(self, source_id: str, identifier: str) -> Resource | None:
        if not identifier:
            return None
        row = self._conn.execute(
            """SELECT * FROM resources WHERE source_id = ? AND official_identifier = ?
               ORDER BY last_seen_at DESC LIMIT 1""",
            (source_id, identifier),
        ).fetchone()
        return self._row_to_resource(row) if row else None

    def find_by_file_hash(self, file_sha256: str) -> Resource | None:
        if not file_sha256:
            return None
        row = self._conn.execute(
            "SELECT * FROM resources WHERE file_sha256 = ? ORDER BY last_seen_at DESC LIMIT 1",
            (file_sha256,),
        ).fetchone()
        return self._row_to_resource(row) if row else None

    def find_by_text_hash(self, text_sha256: str) -> Resource | None:
        if not text_sha256:
            return None
        row = self._conn.execute(
            "SELECT * FROM resources WHERE text_sha256 = ? ORDER BY last_seen_at DESC LIMIT 1",
            (text_sha256,),
        ).fetchone()
        return self._row_to_resource(row) if row else None

    def find_candidates_by_title(self, title_norm: str, year: int | None) -> list[Resource]:
        """제목+연도 fuzzy match 후보 (§11.1 5순위)."""
        if not title_norm:
            return []
        prefix = title_norm[:12]
        sql = "SELECT * FROM resources WHERE title_original LIKE ? OR title_ko LIKE ?"
        params: list[Any] = [f"%{prefix}%", f"%{prefix}%"]
        if year:
            sql += " AND (publication_date IS NULL OR substr(publication_date, 1, 4) = ?)"
            params.append(str(year))
        sql += " LIMIT 25"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_resource(r) for r in rows]

    def file_hash_exists(self, file_sha256: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM files WHERE file_sha256 = ?", (file_sha256,)
        ).fetchone()
        return row is not None

    # ------------------------------------------------------------------
    # Work 그룹
    # ------------------------------------------------------------------
    def upsert_work(
        self, work_id: str, *, doi: str, title_norm: str, first_author: str, pub_year: int | None
    ) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO works (work_id, doi, title_norm, first_author, pub_year, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(work_id) DO UPDATE SET
                    doi = COALESCE(NULLIF(excluded.doi, ''), works.doi),
                    title_norm = COALESCE(NULLIF(excluded.title_norm, ''), works.title_norm)
                """,
                (work_id, doi, title_norm, first_author, pub_year, _iso(datetime.now())),
            )

    # ------------------------------------------------------------------
    # 자료 저장
    # ------------------------------------------------------------------
    def save_resource(self, resource: Resource) -> None:
        now = _iso(datetime.now())
        resource.last_seen_at = resource.last_seen_at or datetime.now()
        resource.first_seen_at = resource.first_seen_at or datetime.now()

        # work_id 는 resources 의 외래키이므로 자료를 저장하기 전에 work 를 만들어 둡니다.
        if resource.work_id:
            self.upsert_work(
                resource.work_id,
                doi=resource.doi,
                title_norm=normalize_title(resource.title_original or resource.title_ko),
                first_author=first_author(resource.authors),
                pub_year=resource.publication_date.year if resource.publication_date else None,
            )

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO resources (
                    resource_id, work_id, source_id, source_type, title_original, title_ko,
                    authors, publisher, journal_or_series, publication_date,
                    source_registered_date, source_modified_date, discovered_at, downloaded_at,
                    doi, official_identifier, landing_url, download_url, oa_url, license,
                    license_unknown, access_mode, language, document_type, topic_primary, keywords,
                    query_original, query_language, query_terms_expanded, query_dictionary_version,
                    discovered_by_query, abstract_original, file_path, file_sha256, text_sha256,
                    file_size, text_extract_failed, summary_ko, summary_basis, summary_generated_at,
                    relevance_score, priority_level, score_breakdown, status, version_of,
                    error_code, error_message, first_seen_at, last_seen_at, alerted_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(resource_id) DO UPDATE SET
                    work_id = COALESCE(excluded.work_id, resources.work_id),
                    title_original = excluded.title_original,
                    title_ko = excluded.title_ko,
                    source_modified_date = excluded.source_modified_date,
                    downloaded_at = COALESCE(excluded.downloaded_at, resources.downloaded_at),
                    landing_url = excluded.landing_url,
                    download_url = excluded.download_url,
                    oa_url = excluded.oa_url,
                    license = excluded.license,
                    license_unknown = excluded.license_unknown,
                    access_mode = excluded.access_mode,
                    topic_primary = excluded.topic_primary,
                    file_path = excluded.file_path,
                    file_sha256 = excluded.file_sha256,
                    text_sha256 = excluded.text_sha256,
                    file_size = excluded.file_size,
                    text_extract_failed = excluded.text_extract_failed,
                    summary_ko = excluded.summary_ko,
                    summary_basis = excluded.summary_basis,
                    summary_generated_at = excluded.summary_generated_at,
                    relevance_score = excluded.relevance_score,
                    priority_level = excluded.priority_level,
                    score_breakdown = excluded.score_breakdown,
                    status = excluded.status,
                    version_of = excluded.version_of,
                    error_code = excluded.error_code,
                    error_message = excluded.error_message,
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    resource.resource_id,
                    # 빈 문자열은 works 외래키를 만족하지 못하므로 NULL 로 저장합니다.
                    resource.work_id or None,
                    resource.source_id,
                    resource.source_type,
                    resource.title_original,
                    resource.title_ko,
                    _json_dump(resource.authors),
                    resource.publisher,
                    resource.journal_or_series,
                    _iso(resource.publication_date),
                    _iso(resource.source_registered_date),
                    _iso(resource.source_modified_date),
                    _iso(resource.discovered_at),
                    _iso(resource.downloaded_at),
                    resource.doi,
                    resource.official_identifier,
                    resource.landing_url,
                    resource.download_url,
                    resource.oa_url,
                    resource.license,
                    int(resource.license_unknown),
                    resource.access_mode.value,
                    resource.language,
                    resource.document_type,
                    resource.topic_primary,
                    _json_dump(resource.keywords),
                    resource.query_original,
                    resource.query_language,
                    _json_dump(resource.query_terms_expanded),
                    resource.query_dictionary_version,
                    resource.discovered_by_query,
                    resource.abstract_original,
                    resource.file_path,
                    resource.file_sha256,
                    resource.text_sha256,
                    resource.file_size,
                    int(resource.text_extract_failed),
                    resource.summary_ko,
                    resource.summary_basis.value,
                    _iso(resource.summary_generated_at),
                    resource.relevance_score,
                    resource.priority_level.value,
                    _json_dump(resource.score_breakdown),
                    resource.status.value,
                    resource.version_of,
                    resource.error_code,
                    resource.error_message,
                    _iso(resource.first_seen_at),
                    _iso(resource.last_seen_at),
                    _iso(resource.alerted_at),
                ),
            )
            # 주제 매핑
            self._conn.execute(
                "DELETE FROM resource_topics WHERE resource_id = ?", (resource.resource_id,)
            )
            for topic_id in dict.fromkeys([resource.topic_primary, *resource.topics]):
                if not topic_id:
                    continue
                self._conn.execute(
                    """INSERT OR REPLACE INTO resource_topics (resource_id, topic_id, confidence, is_primary)
                       VALUES (?, ?, ?, ?)""",
                    (
                        resource.resource_id,
                        topic_id,
                        float(resource.score_breakdown.get("topic_confidence", 0.0)),
                        int(topic_id == resource.topic_primary),
                    ),
                )
            # 출처 URL 보존
            for url, role in (
                (resource.landing_url, "landing"),
                (resource.download_url, "download"),
                (resource.oa_url, "oa"),
            ):
                if url:
                    self._conn.execute(
                        """INSERT OR IGNORE INTO resource_source_map
                           (resource_id, source_id, url, url_role, seen_at)
                           VALUES (?, ?, ?, ?, ?)""",
                        (resource.resource_id, resource.source_id, url, role, now),
                    )
        self._index_fts(resource)

    def add_source_url(self, resource_id: str, source_id: str, url: str, role: str) -> None:
        """같은 자료를 다른 출처에서도 발견했을 때 URL 을 추가 보존합니다 (§11.2)."""
        if not url:
            return
        with self._conn:
            self._conn.execute(
                """INSERT OR IGNORE INTO resource_source_map
                   (resource_id, source_id, url, url_role, seen_at) VALUES (?, ?, ?, ?, ?)""",
                (resource_id, source_id, url, role, _iso(datetime.now())),
            )

    def touch_resource(self, resource_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE resources SET last_seen_at = ? WHERE resource_id = ?",
                (_iso(datetime.now()), resource_id),
            )

    def mark_alerted(self, resource_ids: Iterable[str]) -> None:
        now = _iso(datetime.now())
        with self._conn:
            self._conn.executemany(
                "UPDATE resources SET alerted_at = ? WHERE resource_id = ?",
                [(now, rid) for rid in resource_ids],
            )

    def register_file(
        self,
        *,
        file_sha256: str,
        resource_id: str,
        file_path: str,
        file_size: int,
        content_type: str,
        extension: str,
    ) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT OR REPLACE INTO files
                   (file_sha256, resource_id, file_path, file_size, content_type, extension, downloaded_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    file_sha256,
                    resource_id,
                    file_path,
                    file_size,
                    content_type,
                    extension,
                    _iso(datetime.now()),
                ),
            )

    def sync_topics(self, topics: Iterable[Any]) -> None:
        with self._conn:
            for t in topics:
                self._conn.execute(
                    "INSERT OR REPLACE INTO topics (topic_id, name, description) VALUES (?, ?, ?)",
                    (t.topic_id, t.name, t.description),
                )

    # ------------------------------------------------------------------
    # 전문검색
    # ------------------------------------------------------------------
    def _index_fts(self, resource: Resource, fulltext: str = "") -> None:
        if not self.fts_enabled:
            return
        with self._conn:
            self._conn.execute(
                "DELETE FROM resources_fts WHERE resource_id = ?", (resource.resource_id,)
            )
            self._conn.execute(
                """INSERT INTO resources_fts (resource_id, title, abstract, summary, fulltext, keywords)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    resource.resource_id,
                    f"{resource.title_ko} {resource.title_original}".strip(),
                    resource.abstract_original,
                    resource.summary_ko,
                    fulltext[:200_000],
                    " ".join(resource.keywords),
                ),
            )

    def index_fulltext(self, resource: Resource, fulltext: str) -> None:
        self._index_fts(resource, fulltext)

    def search(self, query: str, limit: int = 50) -> list[Resource]:
        """제목·초록·요약·본문 전문검색 (§17.2)."""
        if not self.fts_enabled:
            like = f"%{query}%"
            rows = self._conn.execute(
                """SELECT * FROM resources
                   WHERE title_original LIKE ? OR title_ko LIKE ? OR abstract_original LIKE ?
                   ORDER BY relevance_score DESC LIMIT ?""",
                (like, like, like, limit),
            ).fetchall()
            return [self._row_to_resource(r) for r in rows]
        rows = self._conn.execute(
            """SELECT r.* FROM resources_fts f
               JOIN resources r ON r.resource_id = f.resource_id
               WHERE resources_fts MATCH ?
               ORDER BY rank LIMIT ?""",
            (query, limit),
        ).fetchall()
        return [self._row_to_resource(r) for r in rows]

    # ------------------------------------------------------------------
    # 실행 이력
    # ------------------------------------------------------------------
    def start_run(self, report: RunReport) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO runs (run_id, run_type, started_at, since_date, until_date,
                                     dictionary_version, status)
                   VALUES (?, ?, ?, ?, ?, ?, 'RUNNING')""",
                (
                    report.run_id,
                    report.run_type.value,
                    _iso(report.started_at),
                    _iso(report.since),
                    _iso(report.until),
                    report.dictionary_version,
                ),
            )

    def finish_run(self, report: RunReport, status: str = "SUCCEEDED") -> None:
        with self._conn:
            self._conn.execute(
                """UPDATE runs SET finished_at = ?, new_count = ?, updated_count = ?,
                       failed_sources = ?, status = ? WHERE run_id = ?""",
                (
                    _iso(report.finished_at or datetime.now()),
                    report.new_count,
                    report.updated_count,
                    len(report.failed_sources),
                    status,
                    report.run_id,
                ),
            )

    def add_run_item(
        self, run_id: str, source_id: str, outcome: str, *, resource_id: str = "", detail: str = ""
    ) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO run_items (run_id, source_id, resource_id, outcome, detail, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (run_id, source_id, resource_id or None, outcome, detail, _iso(datetime.now())),
            )

    def log_error(
        self,
        *,
        run_id: str = "",
        source_id: str = "",
        resource_id: str = "",
        error_code: str,
        message: str = "",
        url: str = "",
    ) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO errors (run_id, source_id, resource_id, error_code, message, url, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id or None,
                    source_id or None,
                    resource_id or None,
                    error_code,
                    message,
                    url,
                    _iso(datetime.now()),
                ),
            )

    def log_alert(
        self,
        *,
        run_id: str,
        channel: str,
        recipient: str,
        subject: str,
        item_count: int,
        status: str,
        detail: str = "",
    ) -> None:
        with self._conn:
            self._conn.execute(
                """INSERT INTO alerts (run_id, channel, recipient, subject, item_count, status, detail, sent_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, channel, recipient, subject, item_count, status, detail, _iso(datetime.now())),
            )

    def failed_sources_since(self, since: datetime) -> list[str]:
        """일일 수집에 실패했던 소스 — 월간 정합성 점검에서 재시도 (§16.2)."""
        rows = self._conn.execute(
            """SELECT DISTINCT source_id FROM errors
               WHERE created_at >= ? AND source_id IS NOT NULL""",
            (_iso(since),),
        ).fetchall()
        return [r["source_id"] for r in rows]

    # ------------------------------------------------------------------
    # 조회
    # ------------------------------------------------------------------
    def all_resources(self) -> list[Resource]:
        rows = self._conn.execute(
            "SELECT * FROM resources ORDER BY first_seen_at DESC"
        ).fetchall()
        return [self._row_to_resource(r) for r in rows]

    def resources_for_run(self, run_id: str) -> list[Resource]:
        rows = self._conn.execute(
            """SELECT r.* FROM resources r
               JOIN run_items i ON i.resource_id = r.resource_id
               WHERE i.run_id = ? AND i.outcome IN ('NEW', 'UPDATED')
               GROUP BY r.resource_id
               ORDER BY r.relevance_score DESC""",
            (run_id,),
        ).fetchall()
        return [self._row_to_resource(r) for r in rows]

    def counts(self) -> dict[str, int]:
        def scalar(sql: str, params: Sequence[Any] = ()) -> int:
            row = self._conn.execute(sql, params).fetchone()
            return int(row[0]) if row else 0

        return {
            "resources": scalar("SELECT COUNT(*) FROM resources"),
            "files": scalar("SELECT COUNT(*) FROM files"),
            "downloaded": scalar("SELECT COUNT(*) FROM resources WHERE access_mode = 'DOWNLOADED'"),
            "link_only": scalar("SELECT COUNT(*) FROM resources WHERE access_mode = 'LINK_ONLY'"),
            "with_doi": scalar("SELECT COUNT(*) FROM resources WHERE doi <> ''"),
            "errors": scalar("SELECT COUNT(*) FROM errors"),
            "runs": scalar("SELECT COUNT(*) FROM runs"),
        }

    # ------------------------------------------------------------------
    def _row_to_resource(self, row: sqlite3.Row) -> Resource:
        data = dict(row)
        return Resource(
            resource_id=data["resource_id"],
            work_id=data.get("work_id") or "",
            source_id=data["source_id"],
            source_type=data.get("source_type") or "",
            title_original=data.get("title_original") or "",
            title_ko=data.get("title_ko") or "",
            authors=_json_load(data.get("authors"), []),
            publisher=data.get("publisher") or "",
            journal_or_series=data.get("journal_or_series") or "",
            publication_date=_parse_date(data.get("publication_date")),
            source_registered_date=_parse_date(data.get("source_registered_date")),
            source_modified_date=_parse_date(data.get("source_modified_date")),
            discovered_at=_parse_datetime(data.get("discovered_at")),
            downloaded_at=_parse_datetime(data.get("downloaded_at")),
            doi=data.get("doi") or "",
            official_identifier=data.get("official_identifier") or "",
            landing_url=data.get("landing_url") or "",
            download_url=data.get("download_url") or "",
            oa_url=data.get("oa_url") or "",
            license=data.get("license") or "",
            license_unknown=bool(data.get("license_unknown", 1)),
            access_mode=data.get("access_mode") or "PENDING",
            language=data.get("language") or "",
            document_type=data.get("document_type") or "기타",
            topic_primary=data.get("topic_primary") or "99_미분류_검토필요",
            keywords=_json_load(data.get("keywords"), []),
            query_original=data.get("query_original") or "",
            query_language=data.get("query_language") or "",
            query_terms_expanded=_json_load(data.get("query_terms_expanded"), []),
            query_dictionary_version=data.get("query_dictionary_version") or "",
            discovered_by_query=data.get("discovered_by_query") or "",
            abstract_original=data.get("abstract_original") or "",
            file_path=data.get("file_path") or "",
            file_sha256=data.get("file_sha256") or "",
            text_sha256=data.get("text_sha256") or "",
            file_size=int(data.get("file_size") or 0),
            text_extract_failed=bool(data.get("text_extract_failed", 0)),
            summary_ko=data.get("summary_ko") or "",
            summary_basis=data.get("summary_basis") or "METADATA_ONLY",
            summary_generated_at=_parse_datetime(data.get("summary_generated_at")),
            relevance_score=int(data.get("relevance_score") or 0),
            priority_level=data.get("priority_level") or PriorityLevel.P4.value,
            score_breakdown=_json_load(data.get("score_breakdown"), {}),
            status=data.get("status") or ResourceStatus.NEW.value,
            version_of=data.get("version_of") or "",
            error_code=data.get("error_code") or "",
            error_message=data.get("error_message") or "",
            first_seen_at=_parse_datetime(data.get("first_seen_at")),
            last_seen_at=_parse_datetime(data.get("last_seen_at")),
            alerted_at=_parse_datetime(data.get("alerted_at")),
        )
