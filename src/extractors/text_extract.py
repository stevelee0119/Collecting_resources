"""PDF/HWP/HWPX 텍스트 추출 (PRD v2.1 §13).

- PDF: 텍스트 레이어가 있으면 직접 추출하고 페이지 번호를 유지해
  요약 근거를 추적할 수 있게 합니다.
- HWPX: ZIP/XML 구조 기반 추출.
- HWP(5.x, OLE): 선택 라이브러리가 있을 때만 시도하고, 실패하면 원문은 보존한 채
  `text_extract_failed=True` 로 표시합니다.
- 스캔본은 텍스트 추출 실패 시 OCR 후보로만 표시하며 자동 OCR 하지 않습니다.
"""

from __future__ import annotations

import logging
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

#: 텍스트 레이어가 있다고 볼 최소 글자 수 (페이지당 평균)
MIN_CHARS_PER_PAGE = 40

XML_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class ExtractedText:
    """추출 결과. 페이지별 텍스트를 유지해 근거 추적을 지원합니다."""

    text: str = ""
    pages: list[str] = field(default_factory=list)
    page_count: int = 0
    failed: bool = False
    needs_ocr: bool = False
    reason: str = ""

    def page_of(self, needle: str) -> int | None:
        """어떤 문장이 몇 페이지에서 나왔는지 되짚습니다 (§13.1)."""
        if not needle:
            return None
        probe = needle.strip()[:60].lower()
        for index, page in enumerate(self.pages, start=1):
            if probe and probe in page.lower():
                return index
        return None


class TextExtractor:
    """확장자에 따라 적절한 추출기를 고릅니다."""

    def __init__(self, max_chars: int = 400_000):
        self.max_chars = max_chars

    # ------------------------------------------------------------------
    def extract(self, path: str | Path) -> ExtractedText:
        file_path = Path(path)
        if not file_path.exists():
            return ExtractedText(failed=True, reason="파일이 존재하지 않습니다.")

        suffix = file_path.suffix.lower()
        try:
            if suffix == ".pdf":
                return self._extract_pdf(file_path)
            if suffix in (".hwpx", ".docx"):
                return self._extract_zip_xml(file_path, suffix)
            if suffix == ".hwp":
                return self._extract_hwp(file_path)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:
            # PDF/HWP 라이브러리는 네이티브 확장을 쓰기 때문에 Exception 이 아닌
            # BaseException(예: pyo3 PanicException)으로 실패할 수 있습니다.
            # 텍스트 추출 실패가 수집 전체를 중단시켜서는 안 되므로 여기서 흡수하고
            # 원문은 보존한 채 text_extract_failed 로 표시합니다 (§13.2, §16.3).
            logger.warning("텍스트 추출 실패 (%s): %s", file_path.name, exc)
            return ExtractedText(failed=True, reason=f"{type(exc).__name__}: {exc}")

        return ExtractedText(failed=True, reason=f"지원하지 않는 형식: {suffix}")

    # ------------------------------------------------------------------
    def _extract_pdf(self, path: Path) -> ExtractedText:
        pages = self._pdf_pages_pymupdf(path)
        if pages is None:
            pages = self._pdf_pages_pypdf(path)
        if pages is None:
            return ExtractedText(
                failed=True, reason="PDF 텍스트 추출 라이브러리를 사용할 수 없습니다."
            )

        text = "\n\n".join(pages)[: self.max_chars]
        page_count = len(pages)
        stripped = text.strip()

        if not stripped or (page_count and len(stripped) / page_count < MIN_CHARS_PER_PAGE):
            # 스캔본으로 추정 — 자동 OCR 하지 않고 후보로만 표시합니다.
            return ExtractedText(
                text=stripped,
                pages=pages,
                page_count=page_count,
                failed=True,
                needs_ocr=True,
                reason="텍스트 레이어가 없어 스캔본으로 추정됩니다(OCR 후보).",
            )

        return ExtractedText(text=stripped, pages=pages, page_count=page_count)

    @staticmethod
    def _pdf_pages_pymupdf(path: Path) -> list[str] | None:
        try:
            import fitz  # noqa: PLC0415  (PyMuPDF)
        except ImportError:
            return None
        with fitz.open(str(path)) as doc:
            return [page.get_text() or "" for page in doc]

    @staticmethod
    def _pdf_pages_pypdf(path: Path) -> list[str] | None:
        try:
            from pypdf import PdfReader  # noqa: PLC0415
        except ImportError:
            return None
        reader = PdfReader(str(path))
        return [(page.extract_text() or "") for page in reader.pages]

    # ------------------------------------------------------------------
    def _extract_zip_xml(self, path: Path, suffix: str) -> ExtractedText:
        """HWPX / DOCX 의 XML 본문에서 텍스트를 뽑습니다."""
        if suffix == ".docx":
            targets = ("word/document.xml",)
        else:
            targets = ()

        chunks: list[str] = []
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if targets:
                selected = [n for n in targets if n in names]
            else:
                # HWPX 본문은 Contents/section*.xml 에 있습니다.
                selected = sorted(
                    n for n in names if n.startswith("Contents/") and n.endswith(".xml")
                )
            for name in selected:
                raw = zf.read(name).decode("utf-8", errors="ignore")
                chunks.append(_xml_to_text(raw))

        text = "\n\n".join(c for c in chunks if c).strip()[: self.max_chars]
        if not text:
            return ExtractedText(failed=True, reason="본문 XML 에서 텍스트를 찾지 못했습니다.")
        return ExtractedText(text=text, pages=[text], page_count=len(chunks) or 1)

    # ------------------------------------------------------------------
    def _extract_hwp(self, path: Path) -> ExtractedText:
        """HWP 5.x(OLE) — 선택 라이브러리가 있을 때만 시도합니다."""
        try:
            import olefile  # noqa: PLC0415
        except ImportError:
            return ExtractedText(
                failed=True,
                reason=(
                    "HWP(OLE) 추출 라이브러리(olefile)가 없습니다. "
                    "원문은 보존되며 text_extract_failed 로 표시됩니다."
                ),
            )

        if not olefile.isOleFile(str(path)):
            # 확장자만 .hwp 인 HWPX 파일일 수 있습니다.
            if zipfile.is_zipfile(path):
                return self._extract_zip_xml(path, ".hwpx")
            return ExtractedText(failed=True, reason="HWP OLE 구조가 아닙니다.")

        ole = olefile.OleFileIO(str(path))
        try:
            streams = [s for s in ole.listdir() if s and s[0] == "BodyText"]
            if not streams:
                return ExtractedText(failed=True, reason="BodyText 스트림이 없습니다.")

            import zlib  # noqa: PLC0415

            chunks: list[str] = []
            for stream in streams:
                data = ole.openstream(stream).read()
                try:
                    data = zlib.decompress(data, -15)
                except zlib.error:
                    pass
                # HWP 레코드에서 인쇄 가능한 UTF-16 문자만 골라냅니다.
                decoded = data.decode("utf-16-le", errors="ignore")
                cleaned = "".join(ch for ch in decoded if ch.isprintable() or ch in "\n\t ")
                if cleaned.strip():
                    chunks.append(cleaned.strip())
        finally:
            ole.close()

        text = "\n\n".join(chunks).strip()[: self.max_chars]
        if not text:
            return ExtractedText(failed=True, reason="HWP 본문에서 텍스트를 찾지 못했습니다.")
        return ExtractedText(text=text, pages=[text], page_count=len(chunks) or 1)


def _xml_to_text(xml: str) -> str:
    """XML 태그를 제거하고 텍스트만 남깁니다."""
    text = XML_TAG_RE.sub(" ", xml)
    return re.sub(r"\s+", " ", text).strip()
