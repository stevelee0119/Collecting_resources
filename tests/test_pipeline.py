"""파이프라인 통합 테스트 (PRD v2.1 §6.1 전체 흐름).

로컬 HTTP 서버와 스텁 Connector 로 탐색 → 검증 → 다운로드 → 분류 →
주제별 저장 → Manifest → 요약까지의 경로를 실제로 실행합니다.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator, Sequence
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from src.connectors import CONNECTOR_REGISTRY
from src.connectors.base import SourceConnector
from src.database import Repository
from src.discovery import Pipeline
from src.models import (
    AccessMode,
    CandidateKind,
    DownloadCandidate,
    Query,
    RawItem,
    Resource,
    RunType,
    SourceConfig,
)

from .conftest import minimal_pdf

PDF_BYTES = minimal_pdf("military court evidence admissibility digital forensics study", pad=4000)
HTML_BYTES = b"<!DOCTYPE html><html><head><title>404 Not Found</title></head><body>" + b"x" * 3000 + b"</body></html>"
PAYWALL_HTML = (
    b"<!DOCTYPE html><html><head><title>Evidence Admissibility</title></head>"
    b"<body>Please log in to continue</body></html>"
)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: A002 - 테스트 로그 억제
        pass

    def do_GET(self):  # noqa: N802
        if self.path == "/robots.txt":
            self._respond(200, b"User-agent: *\nAllow: /\n", "text/plain")
        elif self.path == "/paper.pdf":
            self._respond(200, PDF_BYTES, "application/pdf")
        elif self.path == "/notfound.pdf":
            self._respond(200, HTML_BYTES, "text/html")
        elif self.path == "/paywall":
            self._respond(200, PAYWALL_HTML, "text/html")
        elif self.path == "/forbidden.pdf":
            self._respond(403, b"denied", "text/plain")
        else:
            self._respond(404, b"missing", "text/plain")

    def _respond(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def server() -> Iterator[str]:
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


# ---------------------------------------------------------------------------
# 스텁 Connector
# ---------------------------------------------------------------------------

class StubConnector(SourceConnector):
    """테스트용 소스 — 미리 정해둔 자료 목록을 반환합니다."""

    connector_id = "stub"
    items: list[dict] = []

    def prepare_queries(self, terms=None, source_language=None) -> list[Query]:
        return [
            Query(
                query_string='"military court" OR court-martial',
                language="en",
                canonical_ko="군사법원",
                original_terms=["군사법원"],
                expanded_terms=["military court", "court-martial"],
                dictionary_version="test-1",
                topic_id="01_군사법_군사사법",
            )
        ]

    def discover(self, since: date, until: date, queries: Sequence[Query]) -> Iterator[RawItem]:
        for item in self.items:
            yield RawItem(
                source_id=self.config.source_id, payload=item, discovered_by_query=queries[0]
            )

    def normalize(self, raw: RawItem) -> Resource | None:
        item = raw.payload
        query = raw.discovered_by_query
        return Resource(
            source_id=self.config.source_id,
            source_type="OPEN_API",
            work_id=f"id:{item['id']}",
            title_original=item["title"],
            title_ko=item.get("title_ko", ""),
            authors=["Hong Gildong"],
            publisher="테스트 기관",
            publication_date=date(2026, 8, 1),
            source_modified_date=date(2026, 8, 1),
            doi=item.get("doi", ""),
            official_identifier=item["id"],
            landing_url=item.get("landing", ""),
            download_url=item.get("download", ""),
            oa_url=item.get("download", ""),
            license=item.get("license", "https://creativecommons.org/licenses/by/4.0/"),
            license_unknown=False,
            abstract_original=item.get("abstract", ""),
            keywords=item.get("keywords", []),
            document_type="학술논문",
            discovered_at=self._now(),
            query_original=query.canonical_ko if query else "",
            query_language=query.language if query else "",
            query_terms_expanded=query.expanded_terms if query else [],
            query_dictionary_version=query.dictionary_version if query else "",
            discovered_by_query=query.query_string if query else "",
        )

    def resolve_download(self, metadata: Resource) -> DownloadCandidate | None:
        url = metadata.download_url
        if not url:
            return None
        return DownloadCandidate(
            url=url,
            kind=CandidateKind.DIRECT_FILE,
            source_id=self.config.source_id,
            license=metadata.license,
            is_open_access=True,
            origin="connector:stub",
        )


def stub_source(**overrides) -> SourceConfig:
    data = {
        "source_id": "stub",
        "name": "테스트 소스",
        "base_domain": "127.0.0.1",
        "connector": "stub",
        "mode": ["QUERY"],
        "query_language": "en",
        "priority": 1,
        "enabled": True,
        "access_methods": [
            {"type": "OPEN_API", "auth_type": "NONE", "credential_required": False,
             "endpoint": "http://127.0.0.1/stub", "verification_status": "VERIFIED"}
        ],
        "download_policy": "allowed",
        "rate_limit_rps": 0,
        "robots_policy": "respect",
        "lookback_days": 3,
    }
    data.update(overrides)
    return SourceConfig(**data)


@pytest.fixture
def stub_registry(settings, monkeypatch):
    """레지스트리를 스텁 소스 하나로 교체합니다."""
    monkeypatch.setitem(CONNECTOR_REGISTRY, "stub", StubConnector)
    settings.sources.sources = [stub_source()]
    return settings


def run_pipeline(settings, repo: Repository, items: list[dict], **kwargs):
    StubConnector.items = items
    with Pipeline(settings, repo) as pipeline:
        return pipeline.run(RunType.BACKFILL, since=date(2026, 1, 1), until=date(2026, 12, 31), **kwargs)


# ---------------------------------------------------------------------------
# 전체 흐름
# ---------------------------------------------------------------------------

def test_end_to_end_download_and_store(stub_registry, repo, server, project: Path):
    report = run_pipeline(
        stub_registry,
        repo,
        [
            {
                "id": "stub:1",
                "doi": "10.1234/military.2026.1",
                "title": "Evidence Admissibility in Military Courts",
                "title_ko": "군사법원의 증거능력 판단 기준",
                "landing": f"{server}/paper.pdf",
                "download": f"{server}/paper.pdf",
                "abstract": (
                    "군사법원과 군검찰의 군사재판 절차를 검토한다. "
                    "보통군사법원과 고등군사법원의 군형사 절차 운영 실태를 분석하고 "
                    "군사경찰의 군사법 집행 실무를 정리한다."
                ),
                "keywords": ["군사법원", "군검찰", "군사재판"],
            }
        ],
    )

    assert report.new_count == 1
    resource = report.resources[0]

    # 다운로드 및 주제별 저장 (§9)
    assert resource.access_mode == AccessMode.DOWNLOADED
    stored = Path(resource.file_path)
    assert stored.exists()
    assert stored.parent.name == "01_군사법_군사사법", f"주제 분류: {resource.topic_primary}"

    # 파일명 규칙 (§9.3)
    downloaded_prefix = resource.downloaded_at.strftime("%y%m%d")
    assert stored.name.startswith(f"{downloaded_prefix}_STUB_")

    # 해시 계산 (§6.1 10단계)
    assert len(resource.file_sha256) == 64
    assert len(resource.text_sha256) == 64

    # 분류·중요도 (§12)
    assert resource.relevance_score > 0
    assert resource.priority_level.value in ("P1", "P2", "P3", "P4")

    # 요약 및 근거수준 (§14)
    assert resource.summary_ko
    assert resource.summary_basis.value == "FULLTEXT"
    assert "요약 근거수준" in resource.summary_ko

    # Manifest (§9.1)
    manifest_dir = project / "data" / "manifests"
    manifests = list(manifest_dir.rglob("*.csv"))
    assert manifests, "Manifest 가 생성되지 않았습니다."
    assert "군사법원" in manifests[0].read_text(encoding="utf-8-sig")

    # 누적 CSV/Excel (§17.3)
    assert (project / "data" / "metadata" / "list_download_resources.csv").exists()
    assert (project / "data" / "metadata" / "list_download_resources.xlsx").exists()

    # 감사 추적 (§18.4)
    assert resource.discovered_by_query
    assert resource.query_dictionary_version == "test-1"
    assert "military court" in resource.query_terms_expanded


def test_html_error_page_is_not_stored_as_pdf(stub_registry, repo, server):
    """HTML 오류페이지가 PDF 로 저장되지 않아야 합니다 (§8.3)."""
    report = run_pipeline(
        stub_registry,
        repo,
        [{
            "id": "stub:2",
            "title": "Broken military court paper",
            "landing": f"{server}/notfound.pdf",
            "download": f"{server}/notfound.pdf",
            "abstract": "군사법원 증거능력 관련 연구",
        }],
    )
    resource = report.resources[0]
    assert resource.access_mode == AccessMode.LINK_ONLY
    assert not resource.file_path


def test_paywalled_landing_is_link_only(stub_registry, repo, server):
    """로그인 요구 페이지는 다운로드하지 않고 링크만 보존합니다 (§7.2)."""
    report = run_pipeline(
        stub_registry,
        repo,
        [{
            "id": "stub:3",
            "title": "Paywalled military court study",
            "landing": f"{server}/paywall",
            "download": f"{server}/paywall",
            "abstract": "군사법원 관련 유료 자료",
        }],
    )
    resource = report.resources[0]
    assert resource.access_mode == AccessMode.LINK_ONLY
    assert resource.error_code == "PAYWALL"


def test_403_is_recorded_as_login_required(stub_registry, repo, server):
    """403 은 우회하지 않고 사유를 기록합니다 (§8.1, §7.3)."""
    report = run_pipeline(
        stub_registry,
        repo,
        [{
            "id": "stub:4",
            "title": "Restricted military court study",
            "landing": f"{server}/forbidden.pdf",
            "download": f"{server}/forbidden.pdf",
            "abstract": "군사법원 접근제한 자료",
        }],
    )
    resource = report.resources[0]
    assert resource.access_mode == AccessMode.LINK_ONLY
    assert resource.error_code == "LOGIN_REQUIRED"


def test_link_only_policy_skips_download(stub_registry, repo, server):
    """download_policy: link_only 소스는 다운로드하지 않습니다 (§7.2)."""
    stub_registry.sources.sources = [stub_source(download_policy="link_only")]
    report = run_pipeline(
        stub_registry,
        repo,
        [{
            "id": "stub:5",
            "title": "Military court law journal",
            "landing": f"{server}/paper.pdf",
            "download": f"{server}/paper.pdf",
            "abstract": "군사법원 증거능력",
        }],
    )
    resource = report.resources[0]
    assert resource.access_mode == AccessMode.LINK_ONLY
    assert not resource.file_path
    # 링크는 보존되어야 합니다 (§25-4)
    assert resource.canonical_url()


def test_second_run_detects_duplicate(stub_registry, repo, server):
    """같은 자료를 다시 만나면 중복으로 처리하고 파일을 재저장하지 않습니다 (§11)."""
    item = {
        "id": "stub:6",
        "doi": "10.1234/dup.2026",
        "title": "Duplicate military court study",
        "landing": f"{server}/paper.pdf",
        "download": f"{server}/paper.pdf",
        "abstract": "군사법원 증거능력 중복 테스트",
    }
    first = run_pipeline(stub_registry, repo, [item])
    assert first.new_count == 1

    second = run_pipeline(stub_registry, repo, [item])
    assert second.new_count == 0
    assert second.sources[0].duplicates == 1

    # 파일은 한 번만 저장됩니다.
    library = Path(first.resources[0].file_path).parent
    assert len(list(library.glob("*.pdf"))) == 1


def test_dry_run_does_not_write_files(stub_registry, repo, server, project: Path):
    report = run_pipeline(
        stub_registry,
        repo,
        [{
            "id": "stub:7",
            "title": "Dry run military court study",
            "landing": f"{server}/paper.pdf",
            "download": f"{server}/paper.pdf",
            "abstract": "군사법원",
        }],
        dry_run=True,
    )
    assert report.new_count == 1
    assert not list((project / "data" / "library").rglob("*.pdf"))
    assert repo.counts()["resources"] == 0


def test_low_relevance_resource_is_link_only(stub_registry, repo, server):
    """중요도가 낮으면 원문을 받지 않고 링크만 보존합니다 (§6.3 3차 필터)."""
    stub_registry.app.raw["run"]["download_relevance_threshold"] = 99
    report = run_pipeline(
        stub_registry,
        repo,
        [{
            "id": "stub:8",
            "title": "Unrelated cooking recipes",
            "landing": f"{server}/paper.pdf",
            "download": f"{server}/paper.pdf",
            "abstract": "요리법에 관한 글",
        }],
    )
    resource = report.resources[0]
    assert resource.access_mode == AccessMode.LINK_ONLY


def test_multi_topic_resource_goes_to_shared_folder(stub_registry, repo, server):
    """두 주제에 걸친 자료는 90_복수주제 로 분류합니다 (§3.1, §12.1)."""
    report = run_pipeline(
        stub_registry,
        repo,
        [{
            "id": "stub:11",
            "title": "Evidence admissibility in military courts",
            "landing": f"{server}/paper.pdf",
            "download": f"{server}/paper.pdf",
            "abstract": (
                "군사법원에서의 증거능력 판단과 위법수집증거 배제법칙 적용 기준을 검토한다. "
                "군검찰과 군사경찰의 수사절차에서 디지털포렌식 증거의 실무 적용 방안을 제시한다."
            ),
            "keywords": ["군사법원", "증거능력", "디지털포렌식"],
        }],
    )
    resource = report.resources[0]
    assert resource.topic_primary == "90_복수주제"
    # 경합한 주제들이 함께 기록되어야 합니다.
    assert "01_군사법_군사사법" in resource.topics
    assert "05_형사_수사_사법" in resource.topics


def test_unclassifiable_goes_to_review_folder(stub_registry, repo, server):
    """분류 신뢰도가 낮으면 99_미분류_검토필요 로 보냅니다 (§12.1)."""
    report = run_pipeline(
        stub_registry,
        repo,
        [{
            "id": "stub:9",
            "title": "Completely unrelated topic about gardening",
            "landing": f"{server}/paper.pdf",
            "download": f"{server}/paper.pdf",
            "abstract": "정원 가꾸기에 대한 글입니다.",
        }],
    )
    assert report.resources[0].topic_primary == "99_미분류_검토필요"


def test_run_history_is_recorded(stub_registry, repo, server):
    """실행·항목 이력이 DB 에 남아야 합니다 (§17.1, §18.4)."""
    report = run_pipeline(
        stub_registry,
        repo,
        [{
            "id": "stub:10",
            "title": "Military court audit trail study",
            "landing": f"{server}/paper.pdf",
            "download": f"{server}/paper.pdf",
            "abstract": "군사법원 증거능력",
        }],
    )
    runs = repo._conn.execute("SELECT * FROM runs WHERE run_id = ?", (report.run_id,)).fetchone()
    assert runs["status"] == "SUCCEEDED"
    assert runs["dictionary_version"]

    items = repo._conn.execute(
        "SELECT * FROM run_items WHERE run_id = ?", (report.run_id,)
    ).fetchall()
    assert any(i["outcome"] == "NEW" for i in items)


def test_source_credential_failure_does_not_stop_run(settings, repo, monkeypatch):
    """인증정보가 없는 소스는 건너뛰고 나머지는 계속 진행합니다 (§16.3)."""
    monkeypatch.setitem(CONNECTOR_REGISTRY, "stub", StubConnector)
    # 실제 Connector(nkis)를 쓰되 인증정보가 없는 상태를 만듭니다.
    # require_method 가 요청 전에 예외를 던지므로 네트워크에 나가지 않습니다.
    blocked = stub_source(
        source_id="blocked",
        name="인증필요 소스",
        connector="nkis",
        query_language="ko",
        auth_docs_url="https://example.invalid/docs",
        access_methods=[{
            "type": "OPEN_API", "auth_type": "API_KEY", "credential_required": True,
            "credential_env_var": "MISSING_KEY_FOR_TEST",
            "endpoint": "http://127.0.0.1:1/x", "verification_status": "PENDING_VERIFICATION",
        }],
    )
    settings.sources.sources = [blocked, stub_source()]
    StubConnector.items = []

    with Pipeline(settings, repo) as pipeline:
        report = pipeline.run(RunType.BACKFILL, since=date(2026, 1, 1), until=date(2026, 12, 31))

    failed = {s.source_id: s for s in report.sources if s.error_code}
    assert "blocked" in failed
    assert failed["blocked"].error_code == "CREDENTIAL_MISSING"
    assert "API_발급_연동_가이드" in failed["blocked"].error_message
    # 나머지 소스는 정상 처리됩니다.
    assert any(s.source_id == "stub" and not s.error_code for s in report.sources)

    # 오류가 DB 에 기록되어 추적 가능해야 합니다 (§22).
    errors = repo._conn.execute(
        "SELECT * FROM errors WHERE run_id = ? AND source_id = 'blocked'", (report.run_id,)
    ).fetchall()
    assert errors and errors[0]["error_code"] == "CREDENTIAL_MISSING"


def test_endpoint_not_configured_is_skipped_not_crawled(settings, repo, monkeypatch):
    """공식 엔드포인트가 없으면 자동수집을 시도하지 않습니다 (§4.3)."""
    monkeypatch.setitem(CONNECTOR_REGISTRY, "stub", StubConnector)
    unset = stub_source(
        source_id="unset_feed",
        name="RSS 미확정 기관",
        connector="institution_feed",
        query_language="ko",
        access_methods=[{
            "type": "RSS", "auth_type": "NONE", "credential_required": False,
            "endpoint": "", "verification_status": "PENDING_VERIFICATION",
        }],
    )
    settings.sources.sources = [unset]

    with Pipeline(settings, repo) as pipeline:
        report = pipeline.run(RunType.BACKFILL, since=date(2026, 1, 1), until=date(2026, 12, 31))

    assert report.sources[0].error_code == "ENDPOINT_NOT_CONFIGURED"
