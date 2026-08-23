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
