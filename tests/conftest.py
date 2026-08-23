"""테스트 공용 픽스처."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config_loader import (  # noqa: E402
    AppConfig,
    Settings,
    load_search_terms,
    load_sources,
    load_topics,
)
from src.database import Repository  # noqa: E402

CONFIG_DIR = PROJECT_ROOT / "config"


def minimal_pdf(text: str = "군사법원 판결의 증거능력 판단 기준에 관한 연구", pad: int = 2000) -> bytes:
    """검증기를 통과하는 최소 PDF 를 만듭니다."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n".encode()
        + b"%%EOF\n"
    )
    # 파일 크기 하한(기본 1024바이트)을 넘기기 위한 주석 패딩
    out += b"%" + b"P" * pad + b"\n"
    return bytes(out)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """임시 프로젝트 루트 (data/, logs/ 포함)."""
    for name in ("library", "staging", "manifests", "metadata", "summaries", "quarantine"):
        (tmp_path / "data" / name).mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs").mkdir(exist_ok=True)
    return tmp_path


@pytest.fixture
def app_config(project: Path) -> AppConfig:
    """실제 config.yaml 내용을 쓰되 경로만 임시 디렉터리로 돌립니다."""
    data = yaml.safe_load((CONFIG_DIR / "config.yaml").read_text(encoding="utf-8"))
    data["notification"]["enabled"] = False
    return AppConfig(data, project)


@pytest.fixture
def settings(app_config: AppConfig) -> Settings:
    return Settings(
        app=app_config,
        sources=load_sources(CONFIG_DIR / "sources.yaml"),
        topics=load_topics(CONFIG_DIR / "topics.yaml"),
        search_terms=load_search_terms(CONFIG_DIR / "search_terms.yaml"),
    )


@pytest.fixture
def repo(app_config: AppConfig):
    repository = Repository(app_config.path("storage.database_path"))
    yield repository
    repository.close()


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "sample.pdf"
    path.write_bytes(minimal_pdf())
    return path


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """테스트가 실제 인증정보를 사용하지 않도록 환경변수를 비웁니다."""
    for var in (
        "KCI_API_KEY", "RISS_API_KEY", "NKIS_API_KEY", "SCIENCEON_API_KEY",
        "SCIENCEON_CLIENT_ID", "KKNOWLEDGE_API_KEY",
        "DATA_GO_KR_API_KEY", "LAW_GO_KR_OC", "CORE_API_KEY",
        "SEMANTIC_SCHOLAR_API_KEY", "OPENALEX_API_KEY", "DOAJ_API_KEY",
        "ZENODO_API_KEY", "ANTHROPIC_API_KEY", "CONTACT_EMAIL",
        "DLRCIS_SMTP_PASSWORD", "DLRCIS_SENDER_EMAIL", "DLRCIS_RECEIVER_EMAIL",
    ):
        monkeypatch.delenv(var, raising=False)


def cleanup(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def credential_probe(settings):
    """인증정보가 실제 HTTP 요청까지 전달되는지 확인하는 프로브.

    소스의 엔드포인트를 로컬 모의 서버로 바꿔 요청 내용을 가로챕니다.
    (외부 API 로 나가지 않습니다.)
    """
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from urllib.parse import parse_qs, urlparse

    from src.connectors import ConnectorContext, build_connector
    from src.discovery.query_expander import QueryExpander
    from src.http_client import PoliteClient

    captured: list[dict] = []

    class _Probe(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _record(self, body: bytes = b"") -> None:
            parsed = urlparse(self.path)
            captured.append({
                "path": parsed.path,
                "query": {k: v[0] for k, v in parse_qs(parsed.query).items()},
                "headers": {k.lower(): v for k, v in self.headers.items()},
                "body": body.decode("utf-8", "ignore")[:400],
            })
            payload = b'{"results":[],"message":{"items":[]},"data":[],"hits":{"hits":[]}}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):  # noqa: N802
            self._record()

        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", 0) or 0)
            self._record(self.rfile.read(length) if length else b"")

    httpd = HTTPServer(("127.0.0.1", 0), _Probe)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    clients: list[PoliteClient] = []

    def probe(source_id: str, method_type: str, since, until) -> list[dict]:  # noqa: ARG001
        config = settings.sources.get(source_id)
        # 이 소스의 모든 엔드포인트를 모의 서버로 돌려 외부 호출을 막습니다.
        for m in config.access_methods:
            if m.endpoint:
                m.endpoint = f"http://127.0.0.1:{httpd.server_port}/{source_id}"

        captured.clear()
        client = PoliteClient(user_agent="probe/1.0", rate_limit_rps=0, respect_robots=False)
        clients.append(client)
        connector = build_connector(
            config,
            ConnectorContext(
                app=settings.app,
                client=client,
                expander=QueryExpander(settings.search_terms),
                max_items=1,
            ),
        )
        list(connector.discover(since, until, connector.prepare_queries()[:1]))
        return list(captured)

    yield probe

    for client in clients:
        client.close()
    httpd.shutdown()
    httpd.server_close()
