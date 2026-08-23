"""예의 있는 HTTP 클라이언트 (PRD v2.1 §18.1, §18.2).

- 소스별 rate limit / concurrency 제한
- timeout, exponential backoff, circuit breaker
- robots.txt 준수 (`robots_policy: respect`)
- ETag / Last-Modified 조건부 요청 캐시
- 여러 소스가 같은 호스트를 볼 때의 공유 자원 (`SharedHostState`)

여러 소스가 하나의 API 를 나눠 쓰는 경우가 있습니다. 예를 들어 국가법령정보
공동활용 DRF(`law.go.kr/DRF/lawSearch.do`)는 `law_go_kr`(법령·행정규칙·판례)과
`humanrights`(위원회 결정문)가 target 만 달리해 함께 사용합니다. 소스마다
클라이언트를 따로 만들면 같은 호스트에 rate limit 이 소스 수만큼 곱해지고,
robots.txt 도 중복으로 읽으며, 동일한 요청이 두 번 나갈 수 있습니다.
`SharedHostState` 가 이 셋을 실행 단위로 묶습니다.
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
    """도메인별 robots.txt 를 1회만 읽어 캐시합니다.

    `SharedHostState` 를 통해 소스 간에도 공유되므로, 같은 호스트를 보는
    소스가 여러 개여도 robots.txt 는 실행당 1회만 조회합니다.
    """

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
# 소스 간 공유 자원
# ---------------------------------------------------------------------------

@dataclass
class SharedHostStats:
    """공유 상태가 실제로 아낀 양 (실행 요약에 표시)."""

    deduplicated_requests: int = 0
    robots_lookups_saved: int = 0


class SharedHostState:
    """같은 호스트를 보는 소스들이 함께 쓰는 자원 (실행 1회 단위).

    세 가지를 묶습니다.

    1. **호스트별 rate limiter** — 소스가 몇 개든 호스트가 받는 요청 간격을
       보장합니다. 소스별 limiter 는 그대로 두고 그 위에 겹쳐 적용하므로,
       실효 속도는 둘 중 느린 쪽이 됩니다.
    2. **robots.txt 캐시** — 호스트당 1회만 조회합니다.
    3. **동일 요청 메모** — 한 실행 안에서 완전히 같은 GET/HEAD 요청이
       다시 나오면 이전 응답을 재사용합니다. 같은 엔드포인트를 쓰는 소스가
       우연히 같은 질의를 던져도 네트워크 호출은 한 번만 나갑니다.

    메모는 실행이 끝나면 버립니다. 증분 수집의 신선도를 해치지 않도록
    실행 사이에는 절대 재사용하지 않습니다.
    """

    #: 메모에 담을 응답의 최대 크기. 큰 본문까지 들고 있지 않습니다.
    MAX_MEMO_BYTES = 5 * 1024 * 1024
    #: 메모 항목 수 상한. 넘으면 더 담지 않습니다(오래된 것을 지우지 않음).
    MAX_MEMO_ENTRIES = 500

    def __init__(self, user_agent: str, *, memoize: bool = True):
        self.robots = RobotsCache(user_agent)
        self.memoize = memoize
        self.stats = SharedHostStats()
        self._limiters: dict[str, RateLimiter] = {}
        self._memo: dict[tuple, httpx.Response] = {}
        self._lock = threading.Lock()

    # -- 호스트별 rate limit ------------------------------------------------
    def limiter_for(self, url: str, rps: float) -> RateLimiter | None:
        """호스트 공용 limiter. 여러 소스가 요청하면 가장 느린 rps 를 씁니다."""
        host = urlparse(url).netloc.lower()
        if not host or rps <= 0:
            return None
        with self._lock:
            existing = self._limiters.get(host)
            if existing is None:
                self._limiters[host] = RateLimiter(rps)
                return self._limiters[host]
            # 이미 있으면 더 보수적인(간격이 긴) 쪽으로 맞춥니다.
            interval = 1.0 / rps
            if interval > existing.min_interval:
                existing.min_interval = interval
            return existing

    # -- 동일 요청 메모 -----------------------------------------------------
    def memo_lookup(self, key: tuple) -> httpx.Response | None:
        if not self.memoize:
            return None
        with self._lock:
            response = self._memo.get(key)
            if response is not None:
                self.stats.deduplicated_requests += 1
            return response

    def memo_store(self, key: tuple, response: httpx.Response) -> None:
        if not self.memoize:
            return
        try:
            size = len(response.content)
        except Exception:  # noqa: BLE001 - 스트리밍 등 본문을 읽을 수 없는 응답
            return
        if size > self.MAX_MEMO_BYTES:
            return
        with self._lock:
            if len(self._memo) >= self.MAX_MEMO_ENTRIES:
                return
            self._memo[key] = response

    def clear_memo(self) -> None:
        with self._lock:
            self._memo.clear()


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
        shared: SharedHostState | None = None,
    ):
        self.user_agent = user_agent
        self.timeout = timeout
        self.download_timeout = download_timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.respect_robots = respect_robots
        # 공유 상태가 있으면 robots 캐시를 함께 씁니다 (호스트당 1회 조회).
        self.shared = shared
        self.robots = robots or (shared.robots if shared else RobotsCache(user_agent))
        self.rate_limit_rps = rate_limit_rps
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
        # 같은 실행 안에서 이미 보낸 요청인지 확인합니다(스트리밍 제외).
        memo_key = None
        if self.shared and not stream and method.upper() in ("GET", "HEAD"):
            memo_key = self._memo_key(method, url, headers, kwargs)
            if (cached := self.shared.memo_lookup(memo_key)) is not None:
                logger.debug("동일 요청 재사용: %s %s", method.upper(), cached.url)
                return cached

        if conditional:
            headers.update(self.cache.headers_for(url))

        # 호스트를 공유하는 소스가 여럿이면 호스트 공용 limiter 도 함께 겁니다.
        host_limiter = (
            self.shared.limiter_for(url, self.rate_limit_rps) if self.shared else None
        )

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self.limiter.acquire()
            if host_limiter is not None:
                host_limiter.acquire()
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
            if memo_key is not None and self.shared:
                self.shared.memo_store(memo_key, response)
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
    def _memo_key(self, method: str, url: str, headers: dict, kwargs: dict) -> tuple:
        """요청을 식별하는 키. 파라미터까지 포함한 최종 URL 로 만듭니다.

        인증값이 query 로 들어가는 API 가 많으므로 최종 URL 을 그대로 씁니다.
        따라서 인증정보가 다르면 다른 요청으로 취급되어 메모가 섞이지 않습니다.
        """
        try:
            final_url = str(
                self._client.build_request(method, url, **{
                    k: v for k, v in kwargs.items() if k in ("params",)
                }).url
            )
        except Exception:  # noqa: BLE001 - URL 조립 실패 시 메모하지 않습니다.
            final_url = url
        relevant = tuple(sorted((k.lower(), v) for k, v in headers.items()))
        return (method.upper(), final_url, relevant)

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


def build_client(
    app_config: Any, source: Any, shared: SharedHostState | None = None
) -> PoliteClient:
    """앱 설정과 소스 설정으로 클라이언트를 만듭니다.

    `shared` 를 넘기면 같은 호스트를 보는 다른 소스와 rate limit·robots 캐시·
    동일 요청 메모를 공유합니다 (예: law.go.kr DRF 를 함께 쓰는 소스들).
    """
    return PoliteClient(
        shared=shared,
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
