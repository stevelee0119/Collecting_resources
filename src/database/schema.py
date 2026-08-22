"""SQLite 스키마 (PRD v2.1 §17.1, §17.2).

SQLite 가 원본(Source of Truth)이며 CSV/Excel 은 편의용 산출물입니다.
"""

from __future__ import annotations

SCHEMA_VERSION = 2

# --- 기본 테이블 ------------------------------------------------------------

DDL_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS schema_meta (
        key   TEXT PRIMARY KEY,
        value TEXT
    )
    """,
    # 소스 레지스트리의 런타임 상태
    """
    CREATE TABLE IF NOT EXISTS sources (
        source_id             TEXT PRIMARY KEY,
        name                  TEXT NOT NULL,
        base_domain           TEXT,
        mode                  TEXT,
        query_language        TEXT,
        download_policy       TEXT,
        enabled               INTEGER NOT NULL DEFAULT 1,
        last_success_at       TEXT,
        last_attempt_at       TEXT,
        last_policy_review_at TEXT,
        consecutive_failures  INTEGER NOT NULL DEFAULT 0,
        disabled_reason       TEXT
    )
    """,
    # 동일 연구성과를 묶는 논리 단위
    """
    CREATE TABLE IF NOT EXISTS works (
        work_id        TEXT PRIMARY KEY,
        doi            TEXT,
        title_norm     TEXT,
        first_author   TEXT,
        pub_year       INTEGER,
        created_at     TEXT NOT NULL
    )
    """,
    """CREATE INDEX IF NOT EXISTS idx_works_doi ON works(doi)""",
    """CREATE INDEX IF NOT EXISTS idx_works_title ON works(title_norm, pub_year)""",
    # 자료 본체
    """
    CREATE TABLE IF NOT EXISTS resources (
        resource_id             TEXT PRIMARY KEY,
        work_id                 TEXT,
        source_id               TEXT NOT NULL,
        source_type             TEXT,
        title_original          TEXT,
        title_ko                TEXT,
        authors                 TEXT,
        publisher               TEXT,
        journal_or_series       TEXT,
        publication_date        TEXT,
        source_registered_date  TEXT,
        source_modified_date    TEXT,
        discovered_at           TEXT,
        downloaded_at           TEXT,
        doi                     TEXT,
        official_identifier     TEXT,
        landing_url             TEXT,
        download_url            TEXT,
        oa_url                  TEXT,
        license                 TEXT,
        license_unknown         INTEGER NOT NULL DEFAULT 1,
        access_mode             TEXT,
        language                TEXT,
        document_type           TEXT,
        topic_primary           TEXT,
        keywords                TEXT,
        query_original          TEXT,
        query_language          TEXT,
        query_terms_expanded    TEXT,
        query_dictionary_version TEXT,
        discovered_by_query     TEXT,
        abstract_original       TEXT,
        file_path               TEXT,
        file_sha256             TEXT,
        text_sha256             TEXT,
        file_size               INTEGER NOT NULL DEFAULT 0,
        text_extract_failed     INTEGER NOT NULL DEFAULT 0,
        summary_ko              TEXT,
        summary_basis           TEXT,
        summary_generated_at    TEXT,
        relevance_score         INTEGER NOT NULL DEFAULT 0,
        priority_level          TEXT,
        score_breakdown         TEXT,
        status                  TEXT,
        version_of              TEXT,
        error_code              TEXT,
        error_message           TEXT,
        first_seen_at           TEXT,
        last_seen_at            TEXT,
        alerted_at              TEXT,
        FOREIGN KEY (work_id) REFERENCES works(work_id)
    )
    """,
    """CREATE INDEX IF NOT EXISTS idx_resources_doi ON resources(doi)""",
    """CREATE INDEX IF NOT EXISTS idx_resources_ident ON resources(source_id, official_identifier)""",
    """CREATE INDEX IF NOT EXISTS idx_resources_filehash ON resources(file_sha256)""",
    """CREATE INDEX IF NOT EXISTS idx_resources_texthash ON resources(text_sha256)""",
    """CREATE INDEX IF NOT EXISTS idx_resources_work ON resources(work_id)""",
    """CREATE INDEX IF NOT EXISTS idx_resources_priority ON resources(priority_level, relevance_score)""",
    # 동일 자료의 여러 출처 URL 보존 (§11.2)
    """
    CREATE TABLE IF NOT EXISTS resource_source_map (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        resource_id  TEXT NOT NULL,
        source_id    TEXT NOT NULL,
        url          TEXT NOT NULL,
        url_role     TEXT,
        seen_at      TEXT NOT NULL,
        UNIQUE (resource_id, source_id, url),
        FOREIGN KEY (resource_id) REFERENCES resources(resource_id)
    )
    """,
    # 저장된 실제 파일 (버전 보존 — 이전 파일 삭제 금지, §11.3)
    """
    CREATE TABLE IF NOT EXISTS files (
        file_sha256   TEXT PRIMARY KEY,
        resource_id   TEXT NOT NULL,
        file_path     TEXT NOT NULL,
        file_size     INTEGER NOT NULL,
        content_type  TEXT,
        extension     TEXT,
        downloaded_at TEXT NOT NULL,
        FOREIGN KEY (resource_id) REFERENCES resources(resource_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS topics (
        topic_id    TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        description TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resource_topics (
        resource_id TEXT NOT NULL,
        topic_id    TEXT NOT NULL,
        confidence  REAL NOT NULL DEFAULT 0,
        is_primary  INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (resource_id, topic_id),
        FOREIGN KEY (resource_id) REFERENCES resources(resource_id)
    )
    """,
    # 실행 이력
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id             TEXT PRIMARY KEY,
        run_type           TEXT NOT NULL,
        started_at         TEXT NOT NULL,
        finished_at        TEXT,
        since_date         TEXT,
        until_date         TEXT,
        dictionary_version TEXT,
        new_count          INTEGER NOT NULL DEFAULT 0,
        updated_count      INTEGER NOT NULL DEFAULT 0,
        failed_sources     INTEGER NOT NULL DEFAULT 0,
        status             TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_items (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      TEXT NOT NULL,
        source_id   TEXT NOT NULL,
        resource_id TEXT,
        outcome     TEXT NOT NULL,
        detail      TEXT,
        created_at  TEXT NOT NULL,
        FOREIGN KEY (run_id) REFERENCES runs(run_id)
    )
    """,
    """CREATE INDEX IF NOT EXISTS idx_run_items_run ON run_items(run_id, source_id)""",
    # 알림 발송 이력
    """
    CREATE TABLE IF NOT EXISTS alerts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      TEXT,
        channel     TEXT NOT NULL,
        recipient   TEXT,
        subject     TEXT,
        item_count  INTEGER NOT NULL DEFAULT 0,
        status      TEXT NOT NULL,
        detail      TEXT,
        sent_at     TEXT NOT NULL
    )
    """,
    # 오류 (실패 자료는 삭제하지 않고 원인을 남깁니다, §22)
    """
    CREATE TABLE IF NOT EXISTS errors (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id      TEXT,
        source_id   TEXT,
        resource_id TEXT,
        error_code  TEXT NOT NULL,
        message     TEXT,
        url         TEXT,
        created_at  TEXT NOT NULL
    )
    """,
    """CREATE INDEX IF NOT EXISTS idx_errors_run ON errors(run_id, source_id)""",
]

# --- 전문검색 (FTS5, §17.2) --------------------------------------------------

FTS_STATEMENTS: list[str] = [
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS resources_fts USING fts5(
        resource_id UNINDEXED,
        title,
        abstract,
        summary,
        fulltext,
        keywords,
        tokenize = 'unicode61'
    )
    """,
]
