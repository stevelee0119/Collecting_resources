"""파일 무결성 검증 3단계 (PRD v2.1 §8.3, §13.3).

- Content-Type 확인
- PDF magic bytes `%PDF-`
- HWP/HWPX 구조 검사
- 파일 크기 최소/최대값
- HTML 오류페이지가 PDF 확장자로 저장되는 현상 차단
- 매크로·실행파일 등 비문서 파일은 quarantine 대상으로 표시
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from ..models import ErrorCode, ValidationResult

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"
#: HWP 5.x = OLE 복합문서, HWPX = ZIP
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"PK\x03\x04"
#: 실행파일 시그니처 (§13.3 보안)
EXECUTABLE_MAGICS = (b"MZ", b"\x7fELF", b"\xca\xfe\xba\xbe", b"#!")

HTML_MARKERS = (b"<!doctype html", b"<html", b"<head", b"<script")

DOCUMENT_CONTENT_TYPES = (
    "application/pdf",
    "application/x-pdf",
    "application/haansofthwp",
    "application/vnd.hancom.hwp",
    "application/vnd.hancom.hwpx",
    "application/octet-stream",
    "application/zip",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)


class FileValidator:
    """다운로드된 파일이 실제 문서인지 검증합니다."""

    def __init__(self, *, min_size_bytes: int = 1024, max_size_mb: int = 200):
        self.min_size_bytes = min_size_bytes
        self.max_size_bytes = max_size_mb * 1024 * 1024

    # ------------------------------------------------------------------
    def validate(self, path: str | Path, *, content_type: str = "") -> ValidationResult:
        file_path = Path(path)
        if not file_path.exists():
            return ValidationResult(
                valid=False,
                stage="file",
                reason="파일이 존재하지 않습니다.",
                error_code=ErrorCode.FILE_CORRUPTED.value,
            )

        size = file_path.stat().st_size
        if size < self.min_size_bytes:
            return ValidationResult(
                valid=False,
                stage="file",
                reason=f"파일이 너무 작습니다 ({size} bytes). 오류페이지일 가능성이 높습니다.",
                error_code=ErrorCode.FILE_NOT_DOCUMENT.value,
            )
        if size > self.max_size_bytes:
            return ValidationResult(
                valid=False,
                stage="file",
                reason=f"파일 크기 상한을 초과했습니다 ({size} bytes).",
                error_code=ErrorCode.FILE_NOT_DOCUMENT.value,
            )

        with file_path.open("rb") as f:
            header = f.read(2048)

        # 실행파일·스크립트는 격리 대상 (§13.3)
        if any(header.startswith(magic) for magic in EXECUTABLE_MAGICS):
            return ValidationResult(
                valid=False,
                stage="file",
                reason="실행파일 시그니처가 감지되었습니다. 격리합니다.",
                error_code=ErrorCode.FILE_NOT_DOCUMENT.value,
                details={"quarantine": True},
            )

        # HTML 오류페이지가 문서 확장자로 저장된 경우 차단
        lowered = header.lower()
        if any(marker in lowered for marker in HTML_MARKERS):
            return ValidationResult(
                valid=False,
                stage="file",
                reason="문서가 아니라 HTML 페이지가 반환되었습니다.",
                error_code=ErrorCode.FILE_NOT_DOCUMENT.value,
            )

        suffix = file_path.suffix.lower()
        if suffix == ".pdf":
            return self._validate_pdf(header, content_type)
        if suffix == ".hwpx":
            return self._validate_hwpx(file_path)
        if suffix == ".hwp":
            return self._validate_hwp(header)
        if suffix == ".docx":
            return self._validate_zip_document(file_path, "word/document.xml")

        # 확장자를 모르면 Content-Type 으로 최소 확인
        if content_type and not any(ct in content_type.lower() for ct in DOCUMENT_CONTENT_TYPES):
            return ValidationResult(
                valid=False,
                stage="file",
                reason=f"문서 형식이 아닙니다 (Content-Type: {content_type}).",
                error_code=ErrorCode.FILE_NOT_DOCUMENT.value,
            )
        return ValidationResult(valid=True, stage="file", reason="형식 확인 완료")

    # ------------------------------------------------------------------
    def _validate_pdf(self, header: bytes, content_type: str) -> ValidationResult:
        if not header.startswith(PDF_MAGIC):
            return ValidationResult(
                valid=False,
                stage="file",
                reason="PDF 시그니처(%PDF-)가 없습니다.",
                error_code=ErrorCode.FILE_CORRUPTED.value,
                details={"content_type": content_type},
            )
        return ValidationResult(valid=True, stage="file", reason="PDF 시그니처 확인")

    def _validate_hwp(self, header: bytes) -> ValidationResult:
        if header.startswith(OLE_MAGIC):
            return ValidationResult(valid=True, stage="file", reason="HWP(OLE) 구조 확인")
        if header.startswith(ZIP_MAGIC):
            # 확장자만 .hwp 인 HWPX 파일
            return ValidationResult(valid=True, stage="file", reason="ZIP 기반 한글 문서 확인")
        return ValidationResult(
            valid=False,
            stage="file",
            reason="HWP 문서 구조가 아닙니다.",
            error_code=ErrorCode.FILE_CORRUPTED.value,
        )

    def _validate_hwpx(self, path: Path) -> ValidationResult:
        return self._validate_zip_document(path, "Contents/content.hpf", alt_prefix="Contents/")

    @staticmethod
    def _validate_zip_document(
        path: Path, expected_entry: str, alt_prefix: str = ""
    ) -> ValidationResult:
        try:
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                if expected_entry in names:
                    return ValidationResult(valid=True, stage="file", reason="ZIP/XML 문서 구조 확인")
                if alt_prefix and any(n.startswith(alt_prefix) for n in names):
                    return ValidationResult(valid=True, stage="file", reason="ZIP/XML 문서 구조 확인")
        except zipfile.BadZipFile:
            return ValidationResult(
                valid=False,
                stage="file",
                reason="ZIP 구조가 손상되었습니다.",
                error_code=ErrorCode.FILE_CORRUPTED.value,
            )
        return ValidationResult(
            valid=False,
            stage="file",
            reason="예상한 문서 구조를 찾지 못했습니다.",
            error_code=ErrorCode.FILE_CORRUPTED.value,
        )
