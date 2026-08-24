"""소스 간 공유 HTTP 자원 테스트 (SharedHostState).

여러 소스가 하나의 API 를 나눠 쓰는 경우(국가법령정보 DRF 를 target 만 달리해
쓰는 law_go_kr / humanrights 등)에 같은 호스트로 요청이 중복되거나
rate limit 이 소스 수만큼 곱해지지 않는지 확인합니다.
"""

from __future__ import annotations

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from src.http_client import PoliteClient, SharedHostState


class _CountingHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server 규약
        self.server.paths.append(self.path)  # type: ignore[attr-defined]
        body = b"<root><law><name>x</name></law></root>"
        self.send_response(200)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: A002 - 테스트 로그 억제
        pass


@pytest.fixture
def counting_server():
    server = HTTPServer(("127.0.0.1", 0), _CountingHandler)
    server.paths = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield server, f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()


def _client(shared: SharedHostState, rps: float = 100.0) -> PoliteClient:
    return PoliteClient(
        user_agent="DL-RCIS/test",
        rate_limit_rps=rps,
        respect_robots=False,
        shared=shared,
    )


def test_identical_request_is_sent_once(counting_server):
    """같은 실행 안에서 완전히 같은 GET 은 한 번만 나갑니다."""
    server, base = counting_server
    shared = SharedHostState("DL-RCIS/test")

    # 서로 다른 소스가 쓰는 별개의 클라이언트라도 공유 상태를 통해 묶입니다.
    first, second = _client(shared), _client(shared)
    params = {"OC": "abc", "target": "prec", "query": "군사법원"}

    r1 = first.get(f"{base}/DRF/lawSearch.do", params=params)
    r2 = second.get(f"{base}/DRF/lawSearch.do", params=params)

    assert r1.status_code == r2.status_code == 200
    assert r1.content == r2.content
    assert len(server.paths) == 1, f"요청이 {len(server.paths)}번 나갔습니다: {server.paths}"
    assert shared.stats.deduplicated_requests == 1

    first.close()
    second.close()


def test_different_target_is_still_requested(counting_server):
    """target 이 다르면 별개 요청입니다 — 필요한 조회까지 막으면 안 됩니다."""
    server, base = counting_server
    shared = SharedHostState("DL-RCIS/test")
    client = _client(shared)

    client.get(f"{base}/DRF/lawSearch.do", params={"OC": "abc", "target": "prec"})
    client.get(f"{base}/DRF/lawSearch.do", params={"OC": "abc", "target": "nhrck"})

    assert len(server.paths) == 2
    assert shared.stats.deduplicated_requests == 0
    client.close()


def test_memo_is_cleared_between_runs(counting_server):
    """메모는 실행 단위입니다. 다음 실행이 낡은 응답을 보면 안 됩니다."""
    server, base = counting_server
    shared = SharedHostState("DL-RCIS/test")
    client = _client(shared)
    params = {"OC": "abc", "target": "prec"}

    client.get(f"{base}/DRF/lawSearch.do", params=params)
    shared.clear_memo()
    client.get(f"{base}/DRF/lawSearch.do", params=params)

    assert len(server.paths) == 2
    client.close()


def test_different_credentials_do_not_share_a_memo_entry(counting_server):
    """인증값이 다르면 다른 요청으로 취급해야 응답이 섞이지 않습니다."""
    server, base = counting_server
    shared = SharedHostState("DL-RCIS/test")
    client = _client(shared)

    client.get(f"{base}/DRF/lawSearch.do", params={"OC": "aaa", "target": "prec"})
    client.get(f"{base}/DRF/lawSearch.do", params={"OC": "bbb", "target": "prec"})

    assert len(server.paths) == 2
    client.close()


def test_host_rate_limit_is_shared_across_sources(counting_server):
    """소스가 둘이어도 호스트가 받는 요청 간격은 유지됩니다."""
    _, base = counting_server
    shared = SharedHostState("DL-RCIS/test", memoize=False)

    # 초당 5회 → 요청 간 최소 0.2초. 서로 다른 클라이언트라도 합산되지 않아야 합니다.
    first, second = _client(shared, rps=5.0), _client(shared, rps=5.0)

    started = time.monotonic()
    first.get(f"{base}/a")
    second.get(f"{base}/b")
    first.get(f"{base}/c")
    elapsed = time.monotonic() - started

    # 3회 요청이면 최소 2번의 간격(0.4초)이 필요합니다.
    assert elapsed >= 0.35, f"호스트 공용 rate limit 이 적용되지 않았습니다 ({elapsed:.2f}s)"

    first.close()
    second.close()


def test_host_limiter_takes_the_most_conservative_rate():
    """같은 호스트에 느린 소스가 하나라도 있으면 그 간격을 따릅니다."""
    shared = SharedHostState("DL-RCIS/test")
    fast = shared.limiter_for("https://www.law.go.kr/DRF/lawSearch.do", 10.0)
    slow = shared.limiter_for("https://www.law.go.kr/DRF/lawService.do", 0.5)

    assert fast is slow, "같은 호스트면 같은 limiter 를 써야 합니다."
    assert slow is not None
    assert slow.min_interval == pytest.approx(2.0)


def test_robots_cache_is_shared():
    """robots.txt 는 호스트당 1회만 읽도록 캐시를 공유합니다."""
    shared = SharedHostState("DL-RCIS/test")
    first, second = _client(shared), _client(shared)
    assert first.robots is second.robots is shared.robots
    first.close()
    second.close()


def test_large_response_is_not_memoized(counting_server):
    """큰 본문까지 메모리에 들고 있지는 않습니다."""
    _, base = counting_server
    shared = SharedHostState("DL-RCIS/test")
    shared.MAX_MEMO_BYTES = 1  # 어떤 응답도 담기지 않는 크기
    client = _client(shared)

    client.get(f"{base}/x")
    client.get(f"{base}/x")

    assert shared.stats.deduplicated_requests == 0
    client.close()


# ---------------------------------------------------------------------------
# robots.txt 예외 — 등록된 공식 API 엔드포인트에만 적용
# ---------------------------------------------------------------------------

class _RobotsDenyAll:
    """모든 경로를 거부하는 robots 캐시 대역."""

    def allowed(self, url: str) -> bool:
        return False


def test_registered_api_endpoint_is_exempt_from_robots(counting_server):
    """공식 API 로 등록된 엔드포인트는 robots.txt 로 막지 않습니다.

    arXiv·Zenodo 처럼 사이트 robots.txt 가 광범위하게 Disallow 를 걸어 두면
    기관이 스스로 제공하는 API 까지 막힙니다.
    """
    server, base = counting_server
    api = f"{base}/api/query"
    client = PoliteClient(
        user_agent="DL-RCIS/test",
        rate_limit_rps=100.0,
        respect_robots=True,
        robots=_RobotsDenyAll(),
        api_endpoints=[api],
    )

    response = client.get(api, params={"search_query": "all:test"})
    assert response.status_code == 200
    assert len(server.paths) == 1
    client.close()


def test_unregistered_path_still_respects_robots(counting_server):
    """등록되지 않은 경로는 그대로 robots.txt 를 따릅니다."""
    from src.http_client import RobotsDisallowedError

    _, base = counting_server
    client = PoliteClient(
        user_agent="DL-RCIS/test",
        rate_limit_rps=100.0,
        respect_robots=True,
        robots=_RobotsDenyAll(),
        api_endpoints=[f"{base}/api/query"],
    )

    with pytest.raises(RobotsDisallowedError):
        client.get(f"{base}/browse/cs")
    client.close()


def test_official_api_endpoints_are_collected_from_the_registry():
    """등록된 OPEN_API / OAI_PMH 엔드포인트만 예외 목록에 들어갑니다."""
    from src.config_loader import load_sources
    from src.http_client import official_api_endpoints

    from .conftest import CONFIG_DIR

    registry = load_sources(CONFIG_DIR / "sources.yaml")

    arxiv = official_api_endpoints(registry.get("arxiv"))
    assert arxiv == ["https://export.arxiv.org/api/query"]

    # RSS 만 있는 소스는 예외 대상이 아닙니다.
    assert official_api_endpoints(registry.get("jpri")) == []

    # 국가법령정보는 목록·본문 엔드포인트를 모두 씁니다.
    law = official_api_endpoints(registry.get("law_go_kr"))
    assert "https://www.law.go.kr/DRF/lawSearch.do" in law
    assert "https://www.law.go.kr/DRF/lawService.do" in law


# ---------------------------------------------------------------------------
# User-Agent 연락처 치환 (PRD §18.2 Polite Harvesting)
# ---------------------------------------------------------------------------

def test_user_agent_placeholder_is_replaced_with_the_contact_email(monkeypatch):
    """자리표시자가 그대로 나가면 연락처 역할을 못 합니다."""
    from src.config_loader import load_settings
    from src.http_client import USER_AGENT_EMAIL_PLACEHOLDER, resolve_user_agent

    settings = load_settings()
    monkeypatch.setenv("CONTACT_EMAIL", "ops@example.org")

    agent = resolve_user_agent(settings.app)
    assert USER_AGENT_EMAIL_PLACEHOLDER not in agent
    assert "mailto:ops@example.org" in agent


def test_user_agent_drops_the_contact_clause_when_no_email(monkeypatch):
    """연락처가 없으면 가짜 주소를 보내지 말고 절을 통째로 뺍니다."""
    from src.config_loader import load_settings
    from src.http_client import USER_AGENT_EMAIL_PLACEHOLDER, resolve_user_agent

    settings = load_settings()
    monkeypatch.delenv("CONTACT_EMAIL", raising=False)

    agent = resolve_user_agent(settings.app)
    assert USER_AGENT_EMAIL_PLACEHOLDER not in agent
    assert "mailto:" not in agent
    assert agent.startswith("DL-RCIS/")


def test_built_client_uses_the_resolved_user_agent(monkeypatch):
    """실제 클라이언트에도 치환된 값이 들어가야 합니다."""
    from src.config_loader import load_settings
    from src.http_client import USER_AGENT_EMAIL_PLACEHOLDER, build_client

    settings = load_settings()
    monkeypatch.setenv("CONTACT_EMAIL", "ops@example.org")
    source = settings.sources.get("crossref")

    client = build_client(settings.app, source)
    try:
        assert USER_AGENT_EMAIL_PLACEHOLDER not in client.user_agent
        assert "ops@example.org" in client.user_agent
    finally:
        client.close()


def test_http_error_description_keeps_the_response_body():
    """진단은 응답 본문에 있습니다. 상태코드만 남기면 원인을 못 찾습니다."""
    import httpx

    from src.http_client import describe_http_error

    request = httpx.Request("GET", "https://api.crossref.org/works?rows=1")
    response = httpx.Response(
        400, request=request, text='{"message":"Invalid filter: from-index-date"}'
    )
    exc = httpx.HTTPStatusError("bad", request=request, response=response)

    described = describe_http_error(exc)
    assert "400" in described
    assert "api.crossref.org" in described
    assert "Invalid filter" in described


def test_http_error_description_surfaces_rate_limit_headers():
    """429 는 본문보다 헤더가 더 많은 것을 말해 줍니다.

    키가 인식되면 남은 허용량이 헤더에 실리므로, 키 문제인지 한도 문제인지
    구분할 수 있습니다.
    """
    import httpx

    from src.http_client import describe_http_error

    request = httpx.Request("GET", "https://api.openalex.org/works")
    response = httpx.Response(
        429,
        request=request,
        headers={"x-ratelimit-remaining": "0", "retry-after": "60"},
        text="Too Many Requests",
    )
    exc = httpx.HTTPStatusError("rate", request=request, response=response)

    described = describe_http_error(exc)
    assert "429" in described
    assert "x-ratelimit-remaining=0" in described
    assert "retry-after=60" in described


def test_openalex_sends_the_key_as_a_url_parameter(monkeypatch, credential_probe):
    """OpenAlex 공식 방식은 api_key URL 파라미터입니다.

    사용량이 0 인데 429 가 나오는 상황을 진단하려면, 먼저 우리 쪽이
    키를 제대로 싣고 있는지가 확정되어야 합니다.
    """
    from datetime import date

    monkeypatch.setenv("OPENALEX_API_KEY", "PROBE-OPENALEX")
    requests = credential_probe("openalex", "OPEN_API", date(2026, 8, 1), date(2026, 8, 23))

    assert requests, "요청이 발생하지 않았습니다."
    assert any(r["query"].get("api_key") == "PROBE-OPENALEX" for r in requests), (
        "api_key 가 URL 파라미터로 실리지 않았습니다."
    )


def test_edge_headers_are_surfaced_for_blocked_responses():
    """엣지(CDN·WAF)에서 잘린 것인지 구분할 수 있어야 합니다.

    cf-ray 가 보이면 API 가 아니라 앞단에서 막힌 것이므로,
    키를 고쳐도 소용이 없습니다.
    """
    import httpx

    from src.http_client import describe_http_error

    request = httpx.Request("GET", "https://api.openalex.org/works")
    response = httpx.Response(
        429,
        request=request,
        headers={"cf-ray": "9abc123-ICN", "server": "cloudflare"},
        text="error code: 1015",
    )
    exc = httpx.HTTPStatusError("rate", request=request, response=response)

    described = describe_http_error(exc)
    assert "cf-ray=9abc123-ICN" in described
    assert "server=cloudflare" in described


def test_429_without_retry_after_is_not_hammered(counting_server):
    """Retry-After 가 없는 429 는 짧은 간격으로 다시 두드리지 않습니다."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from src.http_client import RateLimitedError

    hits: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            hits.append(self.path)
            body = b"too many"
            self.send_response(429)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = PoliteClient(
        user_agent="DL-RCIS/test",
        rate_limit_rps=100.0,
        respect_robots=False,
        max_retries=3,
        backoff_base=0.01,
    )
    try:
        with pytest.raises(RateLimitedError):
            client.get(f"http://127.0.0.1:{server.server_address[1]}/works")
    finally:
        client.close()
        server.shutdown()
        server.server_close()

    # 최초 1회 + 재시도 1회. 3회까지 두드리면 IP 평판만 나빠집니다.
    assert len(hits) == 2, f"429 에 {len(hits)}번 요청했습니다."
