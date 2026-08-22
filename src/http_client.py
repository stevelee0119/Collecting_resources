"""예의 있는 HTTP 클라이언트 (PRD v2.1 §18.1, §18.2).

- 소스별 rate limit / concurrency 제한
- timeout, exponential backoff, circuit breaker
- robots.txt 준수 (`robots_policy: respect`)
- ETag / Last-Modified 조건부 요청 캐시
"""

from __future__ import annotations

import logging
import threading
import time
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


class RateLimitedError(RuntimeError):
    """429 등 호출량 초과."""


class CircuitOpenError(RuntimeError):
    """연속 실패로 소스가 일시 비활성화된 상태."""


class RobotsDisallowedError(RuntimeError):
    """robots.txt 가 해당 경로 수집을 금지."""


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class RateLimiter:
    """초당 요청 수(rps)를 최소 간격으로 환산해 강제합니다."""

    def __init__(self, rps: float):
        self.min_interval = 1.0 / rps if rps > 0 else 0.0
        self._lock = threading.Lock()
        self._last_call = 0.0

    def acquire(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            wait = self.min_interval - elapsed
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()


# ---------------------------------------------------------------------------
# Circuit breaker
# ---------------------------------------------------------------------------

@dataclass
class CircuitBreaker:
    """연속 실패가 임계값을 넘으면 해당 소스 호출을 일정 시간 차단합니다 (§16.3)."""

    threshold: int = 5
    cooldown_seconds: float = 900.0
    failures: int = 0
    opened_at: float | None = None

    def before_call(self) -> None:
        if self.opened_at is None:
            return
        if time.monotonic() - self.opened_at < self.cooldown_seconds:
            raise CircuitOpenError(
                f"연속 {self.failures}회 실패로 일시 비활성화되었습니다. "
                f"{int(self.cooldown_seconds)}초 후 재시도합니다."
            )
        # 쿨다운 경과 → half-open
        self.opened_at = None
        self.failures = 0

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold and self.opened_at is None:
            self.opened_at = time.monotonic()
            logger.warning("Circuit breaker 열림 (연속 실패 %d회)", self.failures)


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

class RobotsCache:
    """도메인별 robots.txt 를 1회만 읽어 캐시합니다."""

    def __init__(self, user_agent: str, timeout: float = 10.0):
        self.user_agent = user_agent
        self.timeout = timeout
        self._cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._lock = threading.Lock()

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if not parsed.scheme.startswith("http"):
            return False
        origin = f"{parsed.scheme}://{parsed.netloc}"
        with self._lock:
            if origin not in self._cache:
                self._cache[origin] = self._fetch(origin)
            parser = self._cache[origin]
        if parser is None:
            # robots.txt 를 읽지 못하면 차단하지 않되, 호출 측 정책으로 통제합니다.
            return True
        return parser.can_fetch(self.user_agent, url)

    def _fetch(self, origin: str) -> urllib.robotparser.RobotFileParser | None:
        parser = urllib.robotparser.RobotFileParser()
        try:
            resp = httpx.get(
                f"{origin}/robots.txt",
                timeout=self.timeout,
                headers={"User-Agent": self.user_agent},
                follow_redirects=True,
            )
            if resp.status_code >= 400:
                return None
            parser.parse(resp.text.splitlines())
            return parser
        except httpx.HTTPError as exc:
            logger.debug("robots.txt 조회 실패 (%s): %s", origin, exc)
            return None


# ---------------------------------------------------------------------------
# 조건부 요청 캐시
# ---------------------------------------------------------------------------

@dataclass
class ConditionalCache:
    """ETag / Last-Modified 를 보관해 재조회 비용을 줄입니다 (§18.2)."""

    entries: dict[str, dict[str, str]] = field(default_factory=dict)

    def headers_for(self, url: str) -> dict[str, str]:
        entry = self.entries.get(url)
        if not entry:
            return {}
        headers = {}
        if etag := entry.get("etag"):
            headers["If-None-Match"] = etag
        if last_modified := entry.get("last_modified"):
            headers["If-Modified-Since"] = last_modified
        return headers

    def remember(self, url: str, response: httpx.Response) -> None:
        etag = response.headers.get("ETag")
        last_modified = response.headers.get("Last-Modified")
        if etag or last_modified:
            self.entries[url] = {"etag": etag or "", "last_modified": last_modified or ""}


# ---------------------------------------------------------------------------
# 클라이언트
# ---------------------------------------------------------------------------

class PoliteClient:
    """소스 1개에 대응하는 HTTP 클라이언트."""

    RETRYABLE_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}

    def __init__(
        self,
        *,
        user_agent: str,
        rate_limit_rps: float = 0.5,
        timeout: float = 30.0,
        download_timeout: float = 120.0,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        backoff_max: float = 60.0,
        max_redirects: int = 5,
        verify_tls: bool = True,
        respect_robots: bool = True,
        robots: RobotsCache | None = None,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.download_timeout = download_timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.respect_robots = respect_robots
        self.robots = robots or RobotsCache(user_agent)
        self.limiter = RateLimiter(rate_limit_rps)
        self.breaker = CircuitBreaker()
        self.cache = ConditionalCache()
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout,
            follow_redirects=True,
            max_redirects=max_redirects,
            verify=verify_tls,
        )

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PoliteClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- core --------------------------------------------------------------
    def request(
        self,
        method: str,
        url: str,
        *,
        conditional: bool = False,
        stream: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        """재시도·rate limit·robots 검사를 적용한 요청."""
        if self.respect_robots and not self.robots.allowed(url):
            raise RobotsDisallowedError(f"robots.txt 가 수집을 허용하지 않습니다: {url}")

        self.breaker.before_call()

        headers = dict(kwargs.pop("headers", {}) or {})
        if conditional:
            headers.update(self.cache.headers_for(url))

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self.limiter.acquire()
            try:
                timeout = self.download_timeout if stream else self.timeout
                if stream:
                    response = self._client.send(
                        self._client.build_request(method, url, headers=headers, timeout=timeout, **kwargs),
                        stream=True,
                    )
                else:
                    response = self._client.request(method, url, headers=headers, timeout=timeout, **kwargs)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                self._sleep_backoff(attempt)
                continue

            if response.status_code in self.RETRYABLE_STATUSES:
                # 429 는 즉시 우회하지 않고 backoff 후 재시도 (§8.1)
                retry_after = self._retry_after_seconds(response)
                if stream:
                    response.close()
                if attempt >= self.max_retries:
                    self.breaker.record_failure()
                    if response.status_code == 429:
                        raise RateLimitedError(f"호출량 초과(429): {url}")
                    response.raise_for_status()
                self._sleep_backoff(attempt, retry_after)
                continue

            self.breaker.record_success()
            if conditional:
                self.cache.remember(url, response)
            return response

        self.breaker.record_failure()
        raise last_error or httpx.HTTPError(f"요청 실패: {url}")

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def get_json(self, url: str, **kwargs: Any) -> Any:
        response = self.get(url, **kwargs)
        response.raise_for_status()
        return response.json()

    def stream_get(self, url: str, **kwargs: Any) -> httpx.Response:
        """다운로드용 스트리밍 응답. 호출자가 `close()` 해야 합니다."""
        return self.request("GET", url, stream=True, **kwargs)

    def head(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("HEAD", url, **kwargs)

    # -- helpers -----------------------------------------------------------
    def _sleep_backoff(self, attempt: int, retry_after: float | None = None) -> None:
        if retry_after is not None:
            delay = min(retry_after, self.backoff_max)
        else:
            delay = min(self.backoff_base * (2**attempt), self.backoff_max)
        logger.debug("재시도 대기 %.1fs (시도 %d)", delay, attempt + 1)
        time.sleep(delay)

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float | None:
        raw = response.headers.get("Retry-After")
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None


def build_client(app_config: Any, source: Any) -> PoliteClient:
    """앱 설정과 소스 설정으로 클라이언트를 만듭니다."""
    return PoliteClient(
        user_agent=app_config.get("http.user_agent", "DL-RCIS/2.1"),
        rate_limit_rps=float(getattr(source, "rate_limit_rps", 0.5)),
        timeout=float(app_config.get("http.timeout_seconds", 30)),
        download_timeout=float(app_config.get("http.download_timeout_seconds", 120)),
        max_retries=int(app_config.get("http.max_retries", 3)),
        backoff_base=float(app_config.get("http.backoff_base_seconds", 2.0)),
        backoff_max=float(app_config.get("http.backoff_max_seconds", 60.0)),
        max_redirects=int(app_config.get("http.max_redirects", 5)),
        verify_tls=bool(app_config.get("http.verify_tls", True)),
        respect_robots=str(getattr(source, "robots_policy", "respect")) == "respect",
    )
