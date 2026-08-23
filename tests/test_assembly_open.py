"""열린국회정보 Connector 테스트.

응답 구조를 공식 문서로 대조하지 못했으므로, Connector 는 구조를 단정하지 않고
관대하게 파싱합니다. 그 관대함이 실제로 동작하는지 — 그리고 **엉뚱한 것을
레코드로 오인하지 않는지** 확인합니다.
"""

from __future__ import annotations

import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from src.connectors import ConnectorContext, build_connector
from src.discovery.query_expander import QueryExpander
from src.http_client import PoliteClient

API_ID = "nvkfeqbsacvlzjmea"


def _envelope(rows: list[dict], code: str = "INFO-000", message: str = "정상 처리되었습니다.") -> dict:
    """포털 관례 형태의 응답 봉투."""
    return {
        API_ID: [
            {
                "head": [
                    {"list_total_count": len(rows)},
                    {"RESULT": {"CODE": code, "MESSAGE": message}},
                ]
            },
            {"row": rows},
        ]
    }


@pytest.fixture
def assembly_server():
    state: dict = {"payload": _envelope([]), "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            state["requests"].append(self.path)
            body = json.dumps(state["payload"], ensure_ascii=False).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_address[1]}/portal/openapi/{API_ID}"
    finally:
        server.shutdown()
        server.server_close()


def _connector(settings, endpoint: str, monkeypatch, **overrides):
    monkeypatch.setenv("ASSEMBLY_API_KEY", "PROBE-ASSEMBLY")
    source = settings.sources.get("nars")
    source.access_methods[0].endpoint = endpoint
    for name, value in overrides.items():
        setattr(source, name, value)
    client = PoliteClient(user_agent="DL-RCIS/test", rate_limit_rps=100.0, respect_robots=False)
    expander = QueryExpander(settings.search_terms)
    ctx = ConnectorContext(app=settings.app, client=client, expander=expander, max_items=10)
    return build_connector(source, ctx), client


def test_key_is_sent_and_rows_are_read(settings, assembly_server, monkeypatch):
    """인증키가 KEY 파라미터로 나가고 row 목록을 읽어야 합니다."""
    state, endpoint = assembly_server
    state["payload"] = _envelope([
        {"REPORT_ID": "1001", "TITLE": "군사법원 관할 개편 검토", "PUBLISH_DATE": "2026-08-20"},
        {"REPORT_ID": "1002", "TITLE": "국제인도법 이행 현황", "PUBLISH_DATE": "2026-08-21"},
    ])
    connector, client = _connector(
        settings, endpoint, monkeypatch,
        field_map={"title": "TITLE", "identifier": "REPORT_ID", "publication_date": "PUBLISH_DATE"},
    )
    try:
        queries = connector.prepare_queries()[:1]
        items = list(connector.discover(date(2026, 8, 1), date(2026, 8, 31), queries))
    finally:
        client.close()

    assert len(items) == 2
    assert "KEY=PROBE-ASSEMBLY" in state["requests"][0]
    assert "Type=json" in state["requests"][0]

    resource = connector.normalize(items[0])
    assert resource is not None
    assert resource.title_original == "군사법원 관할 개편 검토"
    assert resource.official_identifier == "nars:1001"
    # landing_url_template 이 식별자로 채워집니다.
    assert resource.landing_url.endswith("brdSeq=1001")


def test_title_is_recovered_when_field_map_is_empty(settings, assembly_server, monkeypatch):
    """field_map 을 채우기 전에도 제목을 찾아내야 합니다."""
    state, endpoint = assembly_server
    state["payload"] = _envelope([
        {"REPORT_ID": "2001", "REPORT_NM": "군사법 제도 비교 연구", "LINK_URL": "https://x/y"},
    ])
    connector, client = _connector(settings, endpoint, monkeypatch, field_map={})
    try:
        items = list(connector.discover(date(2026, 8, 1), date(2026, 8, 31),
                                        connector.prepare_queries()[:1]))
    finally:
        client.close()

    assert len(items) == 1
    resource = connector.normalize(items[0])
    assert resource is not None
    # URL 이 아니라 이름 필드를 골라야 합니다.
    assert resource.title_original == "군사법 제도 비교 연구"


def test_no_data_code_is_not_an_error(settings, assembly_server, monkeypatch, caplog):
    """INFO-200(데이터 없음)은 실패가 아닙니다."""
    state, endpoint = assembly_server
    state["payload"] = _envelope([], code="INFO-200", message="해당하는 데이터가 없습니다.")
    connector, client = _connector(settings, endpoint, monkeypatch, field_map={})
    try:
        with caplog.at_level("WARNING"):
            items = list(connector.discover(date(2026, 8, 1), date(2026, 8, 31),
                                            connector.prepare_queries()[:1]))
    finally:
        client.close()

    assert items == []
    assert not [r for r in caplog.records if "응답 코드 INFO-200" in r.getMessage()]


def test_error_code_is_reported(settings, assembly_server, monkeypatch, caplog):
    """인증 오류 등은 메시지를 그대로 남겨야 원인을 압니다."""
    state, endpoint = assembly_server
    state["payload"] = _envelope([], code="INFO-300", message="인증키가 유효하지 않습니다.")
    connector, client = _connector(settings, endpoint, monkeypatch, field_map={})
    try:
        with caplog.at_level("WARNING"):
            list(connector.discover(date(2026, 8, 1), date(2026, 8, 31),
                                    connector.prepare_queries()[:1]))
    finally:
        client.close()

    assert any("인증키가 유효하지 않습니다" in r.getMessage() for r in caplog.records)


def test_head_metadata_is_not_mistaken_for_records(settings, assembly_server, monkeypatch):
    """`row` 가 없을 때도 head 의 메타데이터를 레코드로 오인하면 안 됩니다."""
    state, endpoint = assembly_server
    state["payload"] = {
        API_ID: [
            {"head": [{"list_total_count": 0}, {"RESULT": {"CODE": "INFO-000", "MESSAGE": "ok"}}]},
        ]
    }
    connector, client = _connector(settings, endpoint, monkeypatch, field_map={})
    try:
        items = list(connector.discover(date(2026, 8, 1), date(2026, 8, 31),
                                        connector.prepare_queries()[:1]))
    finally:
        client.close()

    assert items == []


def test_unknown_envelope_falls_back_to_the_largest_record_list(settings, assembly_server, monkeypatch):
    """봉투 형태가 달라도 레코드 목록을 찾아내야 합니다."""
    state, endpoint = assembly_server
    state["payload"] = {
        "result": {
            "items": [
                {"REPORT_ID": "3001", "TITLE": "국방개혁 입법과제", "PUBLISH_DATE": "2026-08-10"},
                {"REPORT_ID": "3002", "TITLE": "군인 인권 보호", "PUBLISH_DATE": "2026-08-11"},
            ]
        }
    }
    connector, client = _connector(
        settings, endpoint, monkeypatch,
        field_map={"title": "TITLE", "identifier": "REPORT_ID", "publication_date": "PUBLISH_DATE"},
    )
    try:
        items = list(connector.discover(date(2026, 8, 1), date(2026, 8, 31),
                                        connector.prepare_queries()[:1]))
    finally:
        client.close()

    assert len(items) == 2


def test_out_of_range_dates_are_filtered(settings, assembly_server, monkeypatch):
    """서버 기간 필터를 확인하기 전까지는 클라이언트에서 거릅니다."""
    state, endpoint = assembly_server
    state["payload"] = _envelope([
        {"REPORT_ID": "4001", "TITLE": "기간 밖 보고서", "PUBLISH_DATE": "2020-01-01"},
        {"REPORT_ID": "4002", "TITLE": "기간 안 보고서", "PUBLISH_DATE": "2026-08-15"},
    ])
    connector, client = _connector(
        settings, endpoint, monkeypatch,
        field_map={"title": "TITLE", "identifier": "REPORT_ID", "publication_date": "PUBLISH_DATE"},
    )
    try:
        items = list(connector.discover(date(2026, 8, 1), date(2026, 8, 31),
                                        connector.prepare_queries()[:1]))
    finally:
        client.close()

    assert len(items) == 1
    assert items[0].payload["REPORT_ID"] == "4002"
