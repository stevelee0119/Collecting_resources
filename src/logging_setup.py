"""로깅 설정 (PRD v2.1 §18.3, §19.1).

표준 logging + rotating file handler 를 사용하며,
로그에서 인증값이 노출되지 않도록 마스킹 필터를 적용합니다.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

#: 로그에서 가려야 할 값의 패턴
SECRET_PATTERNS = (
    re.compile(r"(api[_-]?key=)([^&\s\"']+)", re.IGNORECASE),
    re.compile(r"(serviceKey=)([^&\s\"']+)", re.IGNORECASE),
    re.compile(r"(access_token=)([^&\s\"']+)", re.IGNORECASE),
    re.compile(r"(apiKey=)([^&\s\"']+)", re.IGNORECASE),
    re.compile(r"(&key=)([^&\s\"']+)", re.IGNORECASE),
    re.compile(r"(token=)([^&\s\"']+)", re.IGNORECASE),
    re.compile(r"(OC=)([^&\s\"']+)", re.IGNORECASE),
    re.compile(r"(Bearer\s+)(\S+)", re.IGNORECASE),
)

#: 환경변수에 담긴 실제 비밀값도 직접 마스킹합니다.
SECRET_ENV_VARS = (
    "KCI_API_KEY",
    "RISS_API_KEY",
    "NKIS_API_KEY",
    "KKNOWLEDGE_API_KEY",
    "SCIENCEON_API_KEY",
    "DATA_GO_KR_API_KEY",
    "LAW_GO_KR_OC",
    "CORE_API_KEY",
    "SEMANTIC_SCHOLAR_API_KEY",
    "OPENALEX_API_KEY",
    "DOAJ_API_KEY",
    "ZENODO_API_KEY",
    "ANTHROPIC_API_KEY",
    "DLRCIS_SMTP_PASSWORD",
    "GMAIL_CLIENT_SECRET",
)


class SecretMaskingFilter(logging.Filter):
    """로그 메시지에서 인증값을 가립니다."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True

        masked = message
        for pattern in SECRET_PATTERNS:
            masked = pattern.sub(r"\1***", masked)
        for var in SECRET_ENV_VARS:
            value = os.environ.get(var, "").strip()
            if value and len(value) >= 6 and value in masked:
                masked = masked.replace(value, "***")

        if masked != message:
            record.msg = masked
            record.args = ()
        return True


def setup_logging(
    *, level: str = "INFO", log_dir: str | Path = "logs", max_bytes: int = 10_485_760,
    backup_count: int = 7, filename: str = "dlrcis.log",
) -> None:
    """콘솔 + 회전 파일 로깅을 설정합니다."""
    directory = Path(log_dir)
    directory.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    mask = SecretMaskingFilter()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(mask)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        directory / filename, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(mask)
    root.addHandler(file_handler)

    # 외부 라이브러리의 과도한 디버그 로그를 억제합니다.
    for noisy in ("httpx", "httpcore", "urllib3", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
