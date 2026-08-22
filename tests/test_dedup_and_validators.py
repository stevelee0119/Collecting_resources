"""중복 판별·검증 엔진 테스트 (PRD v2.1 §8, §11)."""

from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

from src.dedup import DedupVerdict, Deduplicator
from src.models import ErrorCode, Resource
from src.normalizers.normalize import (
    build_work_id,
    infer_document_type,
    normalize_doi,
    parse_date,
    text_sha256,
)
from src.validators import FileValidator, LicenseValidator, is_ephemeral_url



# ---------------------------------------------------------------------------
# 정규화
# ---------------------------------------------------------------------------

def test_normalize_doi_variants():
    expected = "10.2139/ssrn.4567890"
    for raw in (
        "https://doi.org/10.2139/ssrn.4567890",
        "http://dx.doi.org/10.2139/SSRN.4567890",
        "doi:10.2139/ssrn.4567890",
        "  10.2139/ssrn.4567890.  ",
    ):
        assert normalize_doi(raw) == expected


def test_normalize_doi_rejects_garbage():
    assert normalize_doi("없는DOI") == ""
    assert normalize_doi(None) == ""


def test_parse_date_formats():
    assert parse_date("2026-08-22") == date(2026, 8, 22)
    assert parse_date("2026.08.22") == date(2026, 8, 22)
    assert parse_date("20260822") == date(2026, 8, 22)
    assert parse_date("2026년 8월 22일") == date(2026, 8, 22)
    assert parse_date("2026-08") == date(2026, 8, 1)
    assert parse_date("2026") == date(2026, 1, 1)
    assert parse_date([[2026, 8, 22]]) == date(2026, 8, 22)
    assert parse_date("") is None


def test_infer_document_type():
    assert infer_document_type("군사법원법 일부개정법률") == "법령"
    assert infer_document_type("대법원 2026도1234 판결") == "판례"
    assert infer_document_type("군사재판 실무제요") == "실무제요"
    assert infer_document_type("arXiv preprint on legal AI") == "프리프린트"


def test_work_id_prefers_doi():
    assert build_work_id(doi="10.1234/x", identifier="kci:1", title="t") == "doi:10.1234/x"
    assert build_work_id(identifier="kci:1", title="t") == "id:kci:1"
    assert build_work_id(title="같은 제목", year=2026) == build_work_id(title="같은  제목", year=2026)


# ---------------------------------------------------------------------------
# §11 중복 판별
# ---------------------------------------------------------------------------

def _resource(**kw) -> Resource:
    base = {
        "source_id": "crossref",
        "title_original": "Evidence Admissibility in Military Courts",
        "publication_date": date(2026, 5, 1),
        "authors": ["Hong Gildong"],
    }
    base.update(kw)
    return Resource(**base)


def test_dedup_by_doi(repo):
    existing = _resource(doi="10.1234/abc")
    repo.save_resource(existing)

    result = Deduplicator(repo).check_metadata(_resource(doi="10.1234/abc"))
    assert result.verdict == DedupVerdict.DUPLICATE
    assert result.matched_by == "doi"


def test_dedup_by_official_identifier(repo):
    existing = _resource(official_identifier="arxiv:2601.00001", source_id="arxiv")
    repo.save_resource(existing)

    result = Deduplicator(repo).check_metadata(
        _resource(official_identifier="arxiv:2601.00001", source_id="arxiv")
    )
    assert result.verdict == DedupVerdict.DUPLICATE
    assert result.matched_by == "official_identifier"


def test_dedup_by_file_hash(repo):
    existing = _resource(doi="10.1234/one", file_sha256="a" * 64)
    repo.save_resource(existing)

    incoming = _resource(doi="10.9999/two", file_sha256="a" * 64)
    result = Deduplicator(repo).check_content(incoming)
    assert result.verdict == DedupVerdict.DUPLICATE
    assert result.matched_by == "file_sha256"


def test_dedup_by_text_hash(repo):
    body = "군사법원의 증거능력 판단 기준에 관한 연구"
    existing = _resource(doi="10.1234/one", text_sha256=text_sha256(body))
    repo.save_resource(existing)

    # 공백만 다른 동일 본문
    incoming = _resource(doi="10.9999/two", text_sha256=text_sha256("군사법원의  증거능력 판단 기준에 관한 연구"))
    result = Deduplicator(repo).check_content(incoming)
    assert result.verdict == DedupVerdict.DUPLICATE
    assert result.matched_by == "text_sha256"


def test_dedup_fuzzy_title_and_year(repo):
    repo.save_resource(_resource(doi="", official_identifier="x:1"))

    incoming = _resource(doi="", official_identifier="y:2")
    result = Deduplicator(repo).check_metadata(incoming)
    assert result.verdict == DedupVerdict.DUPLICATE
    assert result.matched_by == "title+year"


def test_new_version_detected_when_modified_date_advances(repo):
    existing = _resource(doi="10.1234/abc", source_modified_date=date(2026, 5, 1))
    repo.save_resource(existing)

    incoming = _resource(doi="10.1234/abc", source_modified_date=date(2026, 7, 1))
    result = Deduplicator(repo).check_metadata(incoming)
    assert result.verdict == DedupVerdict.NEW_VERSION


def test_url_alone_does_not_decide_duplication(repo):
    """§11.4 — URL 이 달라도 같은 문서일 수 있습니다."""
    repo.save_resource(_resource(doi="10.1234/abc", landing_url="https://a.example/1"))

    incoming = _resource(doi="10.1234/abc", landing_url="https://b.example/2")
    result = Deduplicator(repo).check_metadata(incoming)
    assert result.verdict == DedupVerdict.DUPLICATE


def test_merge_sources_preserves_all_urls(repo):
    existing = _resource(doi="10.1234/abc", landing_url="https://a.example/1")
    repo.save_resource(existing)

    dedup = Deduplicator(repo)
    incoming = _resource(doi="10.1234/abc", landing_url="https://b.example/2", source_id="openalex")
    dedup.merge_sources(incoming, existing)

    rows = repo._conn.execute(
        "SELECT url FROM resource_source_map WHERE resource_id = ?", (existing.resource_id,)
    ).fetchall()
    urls = {r["url"] for r in rows}
    assert "https://a.example/1" in urls
    assert "https://b.example/2" in urls


# ---------------------------------------------------------------------------
# §8.3 파일 무결성
# ---------------------------------------------------------------------------

def test_file_validator_accepts_real_pdf(sample_pdf: Path):
    result = FileValidator().validate(sample_pdf, content_type="application/pdf")
    assert result.valid, result.reason


def test_file_validator_rejects_html_saved_as_pdf(tmp_path: Path):
    """HTML 오류페이지가 PDF 확장자로 저장되는 현상 차단 (§8.3)."""
    fake = tmp_path / "error.pdf"
    fake.write_bytes(b"<!DOCTYPE html><html><head><title>404</title></head>" + b"x" * 2000)

    result = FileValidator().validate(fake, content_type="text/html")
    assert not result.valid
    assert result.error_code == ErrorCode.FILE_NOT_DOCUMENT.value


def test_file_validator_rejects_missing_pdf_magic(tmp_path: Path):
    fake = tmp_path / "broken.pdf"
    fake.write_bytes(b"NOTAPDF" + b"\x01" * 3000)

    result = FileValidator().validate(fake)
    assert not result.valid
    assert result.error_code == ErrorCode.FILE_CORRUPTED.value


def test_file_validator_rejects_too_small(tmp_path: Path):
    tiny = tmp_path / "tiny.pdf"
    tiny.write_bytes(b"%PDF-1.4\n")

    result = FileValidator(min_size_bytes=1024).validate(tiny)
    assert not result.valid


def test_file_validator_quarantines_executable(tmp_path: Path):
    """실행파일은 격리 대상으로 표시합니다 (§13.3)."""
    evil = tmp_path / "payload.pdf"
    evil.write_bytes(b"MZ" + b"\x00" * 4000)

    result = FileValidator().validate(evil)
    assert not result.valid
    assert result.details.get("quarantine") is True


def test_file_validator_accepts_hwpx(tmp_path: Path):
    hwpx = tmp_path / "doc.hwpx"
    with zipfile.ZipFile(hwpx, "w") as zf:
        zf.writestr("Contents/content.hpf", "<?xml version='1.0'?><package/>")
        zf.writestr("Contents/section0.xml", "<?xml version='1.0'?><body>본문</body>" + "x" * 2000)

    result = FileValidator().validate(hwpx)
    assert result.valid, result.reason


# ---------------------------------------------------------------------------
# §7.2 일회성 링크
# ---------------------------------------------------------------------------

def test_ephemeral_url_detection():
    assert is_ephemeral_url("https://a.go.kr/file.do;jsessionid=ABC123")
    assert is_ephemeral_url("https://a.go.kr/down?token=xyz")
    assert is_ephemeral_url("https://a.go.kr/tempfile/1")
    assert not is_ephemeral_url("https://a.go.kr/board/view?id=100")


# ---------------------------------------------------------------------------
# §8.4 라이선스
# ---------------------------------------------------------------------------

def test_license_open_when_creative_commons():
    assessment = LicenseValidator().assess("https://creativecommons.org/licenses/by/4.0/")
    assert assessment.is_open
    assert assessment.redistributable


def test_license_nd_is_open_but_not_redistributable():
    assessment = LicenseValidator().assess("https://creativecommons.org/licenses/by-nc-nd/4.0/")
    assert assessment.is_open
    assert not assessment.redistributable


def test_license_unknown_when_empty():
    resource = Resource(source_id="kci", license="")
    LicenseValidator().apply(resource)
    assert resource.license_unknown is True


def test_kogl_type1_is_redistributable():
    assessment = LicenseValidator().assess("공공누리 제1유형")
    assert assessment.is_open
    assert assessment.redistributable

    restricted = LicenseValidator().assess("공공누리 제4유형")
    assert restricted.is_open
    assert not restricted.redistributable
