import sqlite3
import os
import hashlib

class CollectionDatabase:
    """
    수집된 자료의 URL 및 메타데이터를 저장하여 중복 수집을 방지하고
    최초 실행 여부(2026.1.1~2026.7.31 수집)를 관리하는 SQLite DB 관리 클래스
    """
    def __init__(self, db_path="database.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """데이터베이스, 수집 이력 및 시스템 상태 테이블 생성"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. 수집 이력 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS collections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url_hash TEXT UNIQUE,
                    title TEXT,
                    publisher TEXT,
                    url TEXT,
                    access_type TEXT,
                    file_path TEXT,
                    collected_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 2. 시스템 상태 및 메타정보 테이블 (최초 실행 여부 저장)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sys_status (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()

    def is_first_run(self) -> bool:
        """
        시스템의 최초 실행 여부를 확인합니다. (first_run_completed 기록이 없으면 True)
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM sys_status WHERE key = 'first_run_completed'")
            row = cursor.fetchone()
            return row is None or row[0] != 'true'

    def mark_first_run_completed(self):
        """
        최초 실행(2026.1.1~2026.7.31 검색)이 완료되었음을 기록합니다.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO sys_status (key, value)
                VALUES ('first_run_completed', 'true')
            """)
            conn.commit()
            print("[Database] 최초 수집(2026.1.1~2026.7.31) 상태가 완료로 기록되었습니다.")

    def is_already_collected(self, url: str) -> bool:
        """
        URL의 SHA256 해시를 이용해 이미 다운로드/수집된 자료인지 확인합니다 (중복 방지).
        """
        url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM collections WHERE url_hash = ?", (url_hash,))
            return cursor.fetchone() is not None

    def add_collection(self, title: str, publisher: str, url: str, access_type: str, file_path: str = ""):
        """
        새로 수집된 자료 정보를 DB에 등록합니다.
        """
        url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO collections (url_hash, title, publisher, url, access_type, file_path)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (url_hash, title, publisher, url, access_type, file_path))
            conn.commit()
