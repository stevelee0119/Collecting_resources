"""접근정책·중요도·알림 테스트 (PRD v2.1 §4.2 B, §4.4 H, §7.3, §12, §15)."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.classifier import RelevanceScorer
from src.config_loader import load_topics
from src.connectors import ConnectorContext, build_connector
from src.connectors.riss import RissConnector, is_riss_resource
from src.connectors.ssrn import SsrnConnector, is_ssrn_resource, ssrn_abstract_id
from src.discovery.query_expander import QueryExpander
from src.models import (
    AccessMode,
    CandidateKind,
    DownloadCandidate,
    PriorityLevel,
    Resource,
    RunReport,
    RunType,
    SummaryBasis,
)
from src.notifier import EmailNotifier, render_email

from .conftest import CONFIG_DIR


@pytest.fixture
def ctx(settings, monkeypatch):
    class _StubClient:
        def close(self):
            pass

    return ConnectorContext(
        app=settings.app,
        client=_StubClient(),  # type: ignore[arg-type]
        expander=QueryExpander(settings.search_terms),
    )


def connector_for(settings, ctx, source_id: str):
    return build_connector(settings.sources.get(source_id), ctx)


# ---------------------------------------------------------------------------
# SSRN (§4.4 H, §7.3)
# ---------------------------------------------------------------------------

def test_ssrn_detection_by_doi_and_url():
    assert is_ssrn_resource(Resource(source_id="openalex", doi="10.2139/ssrn.4567890"))
    assert is_ssrn_resource(
        Resource(source_id="crossref", landing_url="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4567890")
    )
    assert not is_ssrn_resource(Resource(source_id="arxiv", doi="10.1234/other"))


def test_ssrn_abstract_id_extracted():
    assert ssrn_abstract_id(Resource(source_id="x", doi="10.2139/ssrn.4567890")) == "4567890"
    assert (
        ssrn_abstract_id(
            Resource(source_id="x", landing_url="https://papers.ssrn.com/sol3/papers.cfm?abstract_id=123")
        )
        == "123"
    )


def test_ssrn_adopt_sets_canonical_landing_page(settings, ctx):
    connector = connector_for(settings, ctx, "ssrn")
    assert isinstance(connector, SsrnConnector)

    resource = Resource(
        source_id="openalex",
        doi="10.2139/ssrn.4567890",
        title_original="Military legal education and AI",
        download_url="https://papers.ssrn.com/sol3/Delivery.cfm/xyz.pdf",
        license_unknown=True,
    )
    adopted = connector.adopt(resource)

    assert adopted.landing_url == "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4567890"
    assert adopted.official_identifier == "ssrn:4567890"
    # 라이선스 불명확 → 자동 다운로드 후보를 제거하고 링크만 보존
    assert adopted.download_url == ""
    assert adopted.access_mode == AccessMode.LINK_ONLY


def test_ssrn_never_downloads_from_ssrn_domain(settings, ctx):
    connector = connector_for(settings, ctx, "ssrn")
    decision = connector.check_access_policy(
        DownloadCandidate(
            url="https://papers.ssrn.com/sol3/Delivery.cfm/xyz.pdf",
            kind=CandidateKind.DIRECT_FILE,
            is_open_access=True,
            license="CC-BY",
        )
    )
    assert not decision.allowed
    assert decision.error_code == "POLICY_BLOCKED"


def test_ssrn_is_passive_and_does_not_crawl(settings, ctx):
    connector = connector_for(settings, ctx, "ssrn")
    assert connector.passive is True
    assert list(connector.discover(date(2026, 1, 1), date(2026, 8, 22), [])) == []


# ---------------------------------------------------------------------------
# RISS (§4.2 B)
# ---------------------------------------------------------------------------

def test_riss_not_approved_does_not_crawl(settings, ctx):
    connector = connector_for(settings, ctx, "riss")
    assert isinstance(connector, RissConnector)
    assert connector.approved() is False
    assert list(connector.discover(date(2026, 1, 1), date(2026, 8, 22), [])) == []


def test_riss_domain_download_is_blocked(settings, ctx):
    connector = connector_for(settings, ctx, "riss")
    decision = connector.check_access_policy(
        DownloadCandidate(
            url="https://www.riss.kr/link?id=T12345",
            kind=CandidateKind.DIRECT_FILE,
            is_open_access=True,
            license="CC-BY",
        )
    )
    assert not decision.allowed
    assert "Landing Page" in decision.reason


def test_riss_adopt_keeps_link_only(settings, ctx):
    connector = connector_for(settings, ctx, "riss")
    resource = Resource(
        source_id="crossref",
        landing_url="https://www.riss.kr/search/detail/DetailView.do?control_no=ABC123",
        download_url="https://www.riss.kr/pdf/ABC123",
    )
    assert is_riss_resource(resource)

    adopted = connector.adopt(resource)
    assert adopted.official_identifier == "riss:ABC123"
    assert adopted.download_url == ""
    assert adopted.access_mode == AccessMode.LINK_ONLY


# ---------------------------------------------------------------------------
# 중요도 (§12.2, §12.3)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def topics():
    return load_topics(CONFIG_DIR / "topics.yaml")


def test_score_is_bounded(app_config, topics):
    scorer = RelevanceScorer(app_config, topics)
    resource = Resource(
        source_id="law_go_kr",
        title_ko="군사법원법 실무 매뉴얼",
        topic_primary="01_군사법_군사사법",
        document_type="법령",
        publication_date=date.today(),
        access_mode=AccessMode.DOWNLOADED,
        score_breakdown={"topic_confidence": 0.9},
    )
    scored = scorer.score(resource)
    assert 0 <= scored.relevance_score <= 100
    assert scored.score_breakdown["total"] == scored.relevance_score


def test_recent_trusted_document_scores_higher(app_config, topics):
    scorer = RelevanceScorer(app_config, topics)

    strong = scorer.score(
        Resource(
            source_id="law_go_kr",
            title_ko="군사법원법 개정 실무 지침",
            topic_primary="01_군사법_군사사법",
            document_type="법령",
            publication_date=date.today(),
            access_mode=AccessMode.DOWNLOADED,
            score_breakdown={"topic_confidence": 0.9},
        )
    )
    weak = scorer.score(
        Resource(
            source_id="zenodo",
            title_original="Unrelated dataset",
            topic_primary="99_미분류_검토필요",
            document_type="기타",
            publication_date=date(2015, 1, 1),
            license_unknown=True,
        )
    )
    assert strong.relevance_score > weak.relevance_score
    assert strong.priority_level in (PriorityLevel.P1, PriorityLevel.P2)
    assert weak.priority_level in (PriorityLevel.P3, PriorityLevel.P4)


def test_unclassified_is_penalised(app_config, topics):
    scorer = RelevanceScorer(app_config, topics)
    resource = scorer.score(
        Resource(
            source_id="law_go_kr",
            topic_primary="99_미분류_검토필요",
            document_type="법령",
            publication_date=date.today(),
        )
    )
    assert resource.score_breakdown["topic_fit"] < 10


# ---------------------------------------------------------------------------
# 알림 (§15)
# ---------------------------------------------------------------------------

def _report_with(resources: list[Resource]) -> RunReport:
    report = RunReport(
        run_type=RunType.DAILY_INCREMENTAL,
        started_at=datetime.now(),
        since=date(2026, 8, 19),
        until=date(2026, 8, 22),
        dictionary_version="2026.08.22-1",
        resources=resources,
    )
    return report


def _p1() -> Resource:
    return Resource(
        source_id="kci",
        title_ko="군사법원 증거능력 판단 기준",
        title_original="Evidence Admissibility in Military Courts",
        publisher="한국형사·법무정책연구원",
        authors=["홍길동"],
        publication_date=date(2026, 8, 20),
        topic_primary="01_군사법_군사사법",
        relevance_score=88,
        priority_level=PriorityLevel.P1,
        summary_basis=SummaryBasis.FULLTEXT,
        summary_ko=(
            "**한줄 핵심**: 군사법원의 증거능력 판단 기준을 정리한다.\n\n"
            "**핵심 내용**\n- 위법수집증거 배제법칙 적용 범위\n- 디지털포렌식 증거의 요건\n\n"
            "**법무교육 활용 포인트**\n- 군 법무 교육 사례로 활용 가능\n\n"
            "**요약 근거수준**: FULLTEXT"
        ),
        landing_url="https://example.org/paper",
        file_path="/data/library/01_군사법_군사사법/260822_KCI_군사법원.pdf",
        license="공공누리 제1유형",
        license_unknown=False,
    )


def _p3() -> Resource:
    return Resource(
        source_id="arxiv",
        title_original="Some tangential preprint",
        priority_level=PriorityLevel.P3,
        relevance_score=40,
        landing_url="https://arxiv.org/abs/2608.00001",
    )


def test_email_html_contains_key_sections():
    html = render_email(
        _report_with([]), card_resources=[_p1()], listed_resources=[_p3()],
        collected_on=date(2026, 8, 22),
    )
    assert "DL-RCIS 일일 리서치 브리핑" in html
    assert "군사법원 증거능력 판단 기준" in html
    assert "P1" in html
    assert "원문 전체 분석" in html          # 요약 근거수준 표시 (§14.2)
    assert "참고 목록" in html               # P3 이하는 목록으로 (§15.3)
    assert "260822_KCI_군사법원.pdf" in html


def test_email_is_mobile_friendly():
    """가로스크롤 없이 읽히도록 반응형 메타와 max-width 를 사용합니다 (§15.2)."""
    import re

    html = render_email(
        _report_with([]), card_resources=[_p1()], listed_resources=[],
        collected_on=date(2026, 8, 22),
    )
    assert 'name="viewport"' in html
    assert "max-width:640px" in html

    # 폭이 고정된 요소가 있으면 좁은 화면에서 가로스크롤이 생깁니다.
    fixed_widths = [int(w) for w in re.findall(r"[^-]width:\s*(\d+)px", html)]
    assert all(w <= 640 for w in fixed_widths), f"고정 폭이 너무 큽니다: {fixed_widths}"

    # 본문 카드는 테이블 레이아웃이 아니라 블록 요소로 구성되어야 합니다.
    body = html.split("</head>", 1)[1]
    assert body.count("<table") <= 1, "헤더 통계 외에 레이아웃 테이블을 쓰지 않습니다."


def test_email_warns_on_unknown_license():
    resource = _p1()
    resource.license_unknown = True
    html = render_email(
        _report_with([]), card_resources=[resource], listed_resources=[],
        collected_on=date(2026, 8, 22),
    )
    assert "라이선스 불명확" in html
    assert "외부 재배포 금지" in html


def test_email_shows_failed_sources():
    from src.models import SourceRunReport

    report = _report_with([])
    report.sources.append(
        SourceRunReport(
            source_id="nkis",
            source_name="NKIS 국가정책연구포털",
            error_code="CREDENTIAL_MISSING",
            error_message="인증정보가 없어 수집을 건너뜁니다.",
        )
    )
    html = render_email(
        report, card_resources=[], listed_resources=[], collected_on=date(2026, 8, 22)
    )
    assert "수집 실패" in html
    assert "CREDENTIAL_MISSING" in html


def test_notifier_skips_when_no_new_resources(app_config):
    app_config.raw["notification"]["enabled"] = True
    app_config.raw["notification"]["send_when_empty"] = False
    notifier = EmailNotifier(app_config)
    notifier.sender = "a@example.org"
    notifier.receiver = "b@example.org"

    assert notifier.send(_report_with([]), []) is False


def test_notifier_message_has_html_and_text_parts(app_config):
    app_config.raw["notification"]["enabled"] = True
    notifier = EmailNotifier(app_config)
    notifier.sender = "a@example.org"
    notifier.receiver = "b@example.org"
    notifier.attach_excel = False

    message = notifier.build_message(_report_with([_p1()]), [_p1()], collected_on=date(2026, 8, 22))
    types = {part.get_content_type() for part in message.walk()}

    assert "text/plain" in types
    assert "text/html" in types
    assert "2026-08-22" in message["Subject"]


def test_notifier_does_not_attach_source_documents(app_config):
    """원문을 이메일 첨부로 재배포하지 않습니다 (§18.5)."""
    app_config.raw["notification"]["enabled"] = True
    notifier = EmailNotifier(app_config)
    notifier.sender = "a@example.org"
    notifier.receiver = "b@example.org"

    message = notifier.build_message(_report_with([_p1()]), [_p1()], collected_on=date(2026, 8, 22))
    attachments = [
        part.get_filename() for part in message.walk() if part.get_filename()
    ]
    assert not any(str(name).endswith(".pdf") for name in attachments)
