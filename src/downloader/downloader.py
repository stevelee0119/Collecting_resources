"""원문 다운로더 (PRD v2.1 §7, §9.1, §18.1).

staging → validation → atomic move 구조를 사용합니다.
이 모듈은 파일을 `data/staging/YYMMDD/` 에 받아 해시만 계산하고,
최종 주제별 저장소로의 이동은 `storage.library` 가 담당합니다.
"""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse

from ..http_client import CircuitOpenError, PoliteClient, RateLimitedError, RobotsDisallowedError
from ..models import DownloadCandidate, DownloadResult, ErrorCode

logger = logging.getLogger(__name__)

CONTENT_TYPE_EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/x-pdf": ".pdf",
    "application/haansofthwp": ".hwp",
    "application/vnd.hancom.hwp": ".hwp",
    "application/vnd.hancom.hwpx": ".hwpx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}

FILENAME_RE = re.compile(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', re.IGNORECASE)

CHUNK_SIZE = 65536


class Downloader:
    """검증된 후보 URL 의 원문을 staging 으로 받습니다."""

    def __init__(
        self,
        staging_dir: str | Path,
        *,
        max_file_size_mb: int = 200,
        allowed_extensions: tuple[str, ...] = (".pdf", ".hwp", ".hwpx", ".docx"),
    ):
        self.staging_dir = Path(staging_dir)
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_file_size_mb * 1024 * 1024
        self.allowed_extensions = tuple(e.lower() for e in allowed_extensions)

    # ------------------------------------------------------------------
    def download(self, candidate: DownloadCandidate, *, client: PoliteClient) -> DownloadResult:
        """후보 URL 을 스트리밍으로 내려받습니다."""
        url = candidate.url
        if not url:
            return DownloadResult(
                success=False,
                error_code=ErrorCode.DOWNLOAD_FAILED.value,
                error_message="다운로드 URL 이 비어 있습니다.",
            )

        try:
            response = client.stream_get(url)
        except RobotsDisallowedError as exc:
            return DownloadResult(
                success=False, error_code=ErrorCode.POLICY_BLOCKED.value, error_message=str(exc)
            )
        except RateLimitedError as exc:
            return DownloadResult(
                success=False, error_code=ErrorCode.API_RATE_LIMIT.value, error_message=str(exc)
            )
        except CircuitOpenError as exc:
            return DownloadResult(
                success=False, error_code=ErrorCode.DOWNLOAD_FAILED.value, error_message=str(exc)
            )
        except Exception as exc:
            return DownloadResult(
                success=False,
                error_code=ErrorCode.DOWNLOAD_FAILED.value,
                error_message=f"다운로드 요청 실패: {exc}",
            )

        try:
            if response.status_code in (401, 403):
                return DownloadResult(
                    success=False,
                    error_code=ErrorCode.LOGIN_REQUIRED.value,
                    error_message=f"인증이 필요한 자료입니다 (HTTP {response.status_code}).",
                    final_url=str(response.url),
                )
            if response.status_code != 200:
                return DownloadResult(
                    success=False,
                    error_code=ErrorCode.DOWNLOAD_FAILED.value,
                    error_message=f"HTTP {response.status_code}",
                    final_url=str(response.url),
                )

            content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
            declared_length = response.headers.get("Content-Length")
            if declared_length and int(declared_length) > self.max_bytes:
                return DownloadResult(
                    success=False,
                    error_code=ErrorCode.FILE_NOT_DOCUMENT.value,
                    error_message=f"파일 크기 상한 초과 ({declared_length} bytes)",
                    final_url=str(response.url),
                )

            extension = self._guess_extension(
                content_type, response.headers.get("Content-Disposition", ""), str(response.url)
            )
            temp_path = self.staging_dir / f"{uuid.uuid4().hex}{extension}"

            digest = hashlib.sha256()
            written = 0
            with temp_path.open("wb") as f:
                for chunk in response.iter_bytes(CHUNK_SIZE):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > self.max_bytes:
                        f.close()
                        temp_path.unlink(missing_ok=True)
                        return DownloadResult(
                            success=False,
                            error_code=ErrorCode.FILE_NOT_DOCUMENT.value,
                            error_message="전송 중 파일 크기 상한을 초과했습니다.",
                            final_url=str(response.url),
                        )
                    digest.update(chunk)
                    f.write(chunk)

            return DownloadResult(
                success=True,
                staged_path=str(temp_path),
                file_sha256=digest.hexdigest(),
                file_size=written,
                content_type=content_type,
                final_url=str(response.url),
            )
        finally:
            response.close()

    # ------------------------------------------------------------------
    def discard(self, staged_path: str | Path) -> None:
        """검증에 실패한 staging 파일을 정리합니다."""
        Path(staged_path).unlink(missing_ok=True)

    def quarantine(self, staged_path: str | Path, quarantine_dir: str | Path) -> str:
        """비문서·실행파일을 격리 폴더로 옮깁니다 (§13.3)."""
        target_dir = Path(quarantine_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        source = Path(staged_path)
        target = target_dir / source.name
        shutil.move(str(source), str(target))
        logger.warning("비문서 파일을 격리했습니다: %s", target)
        return str(target)

    # ------------------------------------------------------------------
    def _guess_extension(self, content_type: str, disposition: str, url: str) -> str:
        """Content-Type → Content-Disposition → URL 순으로 확장자를 추정합니다."""
        if ext := CONTENT_TYPE_EXTENSIONS.get(content_type.lower()):
            return ext

        if disposition and (match := FILENAME_RE.search(disposition)):
            name = unquote(match.group(1))
            suffix = Path(name).suffix.lower()
            if suffix in self.allowed_extensions:
                return suffix

        path = urlparse(url).path
        suffix = Path(unquote(path)).suffix.lower()
        if suffix in self.allowed_extensions:
            return suffix

        # 알 수 없으면 PDF 로 가정하되, 파일 검증기가 최종 판정합니다.
        return ".pdf"


def sha256_of_file(path: str | Path) -> str:
    """파일 SHA256 계산."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
