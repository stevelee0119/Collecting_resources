"""MVP 수용기준 검증 (PRD v2.1 §23.1).

각 체크리스트 항목이 실제로 충족되는지 확인합니다.
"""

from __future__ import annotations

import re

import pytest

from src.config_loader import load_search_terms, load_sources, load_topics
from src.connectors import CONNECTOR_REGISTRY
from src.discovery.query_expander import QueryExpander
from src.models import DownloadPolicy, SourceMode

from .conftest import CONFIG_DIR, PROJECT_ROOT


@pytest.fixture(scope="module")
def registry():
    return load_sources(CONFIG_DIR / "sources.yaml")


@pytest.fixture(scope="module")
def dictionary():
    return load_search_terms(CONFIG_DIR / "search_terms.yaml")


# ---------------------------------------------------------------------------
# 소스 연동
# ---------------------------------------------------------------------------

def test_kci_registered_with_oai_and_open_api(registry):
    """[ ] KCI Open API/OAI-PMH 수집 가능"""
    kci = registry.get("kci")
    assert kci is not None and kci.enabled
    assert kci.method("OAI_PMH") is not None
    assert kci.method("OPEN_API") is not None
    # OAI-PMH 는 키 없이 사용할 수 있는 경로로 우선 검토되어야 합니다.
    assert kci.method("OAI_PMH").credential_required is False
    assert CONNECTOR_REGISTRY[kci.connector].__name__ == "KciConnector"


def test_nkis_registered(registry):
    """[ ] NKIS Open API 수집 가능"""
    nkis = registry.get("nkis")
    assert nkis is not None and nkis.enabled
    assert nkis.method("OPEN_API") is not None
    assert nkis.method("OPEN_API").credential_env_var == "NKIS_API_KEY"


def test_kknowledge_registered(registry):
    """[ ] 디지털집현전(국가지식정보 통합플랫폼) 수집 대상 등록"""
    kk = registry.get("kknowledge")
    assert kk is not None and kk.enabled
    method = kk.method("OPEN_API")
    assert method is not None
    assert method.credential_env_var == "KKNOWLEDGE_API_KEY"
    assert CONNECTOR_REGISTRY[kk.connector].__name__ == "KKnowledgeConnector"
    # 집계 플랫폼의 원문은 원 기관에 있으므로 기본은 링크 보존입니다.
    assert kk.download_policy == "link_only"


def test_every_source_has_a_registered_connector(registry):
    """sources.yaml 의 connector 는 모두 CONNECTOR_REGISTRY 에 있어야 합니다."""
    for source in registry.sources:
        assert source.connector in CONNECTOR_REGISTRY, (
            f"{source.source_id}: connector '{source.connector}' 가 "
            f"src/connectors/__init__.py 에 등록되지 않았습니다."
        )


def test_law_openapi_registered(registry):
    """[ ] 국가법령정보 공동활용 Open API 수집 가능"""
    law = registry.get("law_go_kr")
    assert law is not None and law.enabled
    assert law.method("OPEN_API") is not None
    # 공포일·시행일·개정일 구분을 위해 여러 target 을 조회합니다.
    assert set(getattr(law, "law_targets", [])) >= {"law", "prec"}


def test_at_least_two_of_crossref_openalex_unpaywall(registry):
    """[ ] Crossref/OpenAlex/Unpaywall 중 최소 2개 연동"""
    enabled = [
        s for s in ("crossref", "openalex", "unpaywall")
        if (source := registry.get(s)) and source.enabled
    ]
    assert len(enabled) >= 2, f"연동된 소스: {enabled}"
    for source_id in enabled:
        assert CONNECTOR_REGISTRY[registry.get(source_id).connector]


def test_ssrn_discovered_via_external_metadata_and_link_only(registry):
    """[ ] SSRN 논문을 외부 학술 메타데이터로 발견하고 공식 Landing Page 연결 가능"""
    ssrn = registry.get("ssrn")
    assert ssrn is not None and ssrn.enabled
    assert ssrn.download_policy == DownloadPolicy.LINK_ONLY
    assert SourceMode.LINK_ONLY in ssrn.mode

    discovery_via = set(getattr(ssrn, "discovery_via", []))
    assert discovery_via, "SSRN 은 다른 소스를 통해 발견되어야 합니다."
    assert discovery_via <= {s.source_id for s in registry.sources}


def test_riss_switches_between_api_and_link_only(registry):
    """[ ] RISS 는 Open API 승인 여부에 따라 API/Link-only 로 동작 가능"""
    riss = registry.get("riss")
    assert riss is not None
    assert SourceMode.QUERY in riss.mode and SourceMode.LINK_ONLY in riss.mode
    # 승인 전 기본값은 link_only 여야 합니다.
    assert riss.download_policy == DownloadPolicy.LINK_ONLY


# ---------------------------------------------------------------------------
# 검색어
# ---------------------------------------------------------------------------

def test_required_keywords_included(dictionary):
    """[ ] 국내 검색어 사전에 §3.3 필수 키워드가 포함됨"""
    assert dictionary.missing_required() == []


def test_english_expansion_for_en_sources(registry, dictionary):
    """[ ] query_language=en 소스에서 한국어를 검수된 영문 학술용어로 변환·확장"""
    en_sources = [s for s in registry.enabled() if s.query_language == "en"]
    assert en_sources, "영문 소스가 등록되어 있지 않습니다."

    expander = QueryExpander(dictionary)
    queries = expander.build_queries(language="en", scope="international")
    assert queries
    for query in queries:
        assert not re.search(r"[가-힣]", query.query_string)
        assert query.expanded_terms


def test_query_provenance_is_recordable(dictionary):
    """[ ] 검색에 실제 사용된 번역·확장 Query 와 사전 버전을 DB/Manifest 에 기록"""
    from src.storage.manifest import MANIFEST_COLUMNS

    expander = QueryExpander(dictionary)
    query = expander.build_queries(language="en", scope="international")[0]
    assert query.dictionary_version and query.expanded_terms

    for column in ("발견검색어", "검색어사전버전", "확장검색어"):
        assert column in MANIFEST_COLUMNS

    from src.database.schema import DDL_STATEMENTS

    resources_ddl = next(d for d in DDL_STATEMENTS if "CREATE TABLE IF NOT EXISTS resources" in d)
    for column in (
        "query_original", "query_language", "query_terms_expanded",
        "query_dictionary_version", "discovered_by_query",
    ):
        assert column in resources_ddl


# ---------------------------------------------------------------------------
# 저장 구조
# ---------------------------------------------------------------------------

def test_yymmdd_prefix_rule_applied():
    """[ ] `YYMMDD_` 접두사 파일명 규칙 100% 적용"""
    from datetime import date

    from src.storage import build_filename

    for source_id, title in (
        ("KCI", "군사재판절차 개선방안"),
        ("SSRN", "AI and Military Legal Education"),
        ("NKIS", "공공부문 AI 법제연구"),
    ):
        name = build_filename(
            downloaded_on=date(2026, 8, 22), source_id=source_id, title=title, extension=".pdf"
        )
        assert re.match(r"^\d{6}_", name), name
        assert name.startswith("260822_")


def test_manifest_and_topic_library_coexist():
    """[ ] 일자별 Manifest 와 주제별 최종저장 구조 동시 구현"""
    from src.storage import Library, ManifestWriter

    assert Library is not None and ManifestWriter is not None

    topics = load_topics(CONFIG_DIR / "topics.yaml")
    # §9.2 가 요구하는 주제 폴더가 모두 정의되어야 합니다.
    required = {
        "01_군사법_군사사법", "02_군인사_복무_징계", "03_국방정책_행정법",
        "04_국방계약_조달법제", "05_형사_수사_사법", "06_헌법_인권",
        "07_국제법_작전법_국제인도법", "08_AI_법률AI_디지털법",
        "09_법무교육_교육방법론", "10_비교법_해외법제",
        "90_복수주제", "99_미분류_검토필요",
    }
    assert required <= set(topics.ids())


def test_dedup_uses_doi_and_file_hash():
    """[ ] DOI/파일 해시 기반 중복차단"""
    import inspect

    from src.dedup import Deduplicator

    metadata_src = inspect.getsource(Deduplicator.check_metadata)
    content_src = inspect.getsource(Deduplicator.check_content)

    assert "find_by_doi" in metadata_src
    assert "find_by_file_hash" in content_src
    assert "find_by_text_hash" in content_src


# ---------------------------------------------------------------------------
# 알림·추적
# ---------------------------------------------------------------------------

def test_daily_briefing_is_configured():
    """[ ] 매일 신규자료 요약 이메일 발송"""
    from src.config_loader import load_app_config

    app = load_app_config(CONFIG_DIR / "config.yaml")
    assert app.get("scheduler.daily_incremental.enabled") is True
    assert app.get("scheduler.timezone") == "Asia/Seoul"
    assert app.get("notification.channel") == "email"


def test_provenance_fields_exist():
    """[ ] 출처·원문·라이선스·요약근거 추적 가능"""
    from src.models import Resource

    fields = set(Resource.model_fields)
    for name in (
        "source_id", "landing_url", "download_url", "oa_url",
        "license", "license_unknown", "summary_basis", "summary_generated_at",
        "discovered_at", "downloaded_at", "file_sha256", "text_sha256",
        "version_of", "score_breakdown",
    ):
        assert name in fields, f"누락된 필드: {name}"


# ---------------------------------------------------------------------------
# API 가이드 산출물 (§5.1)
# ---------------------------------------------------------------------------

def test_api_guide_generated_and_lists_every_credentialed_source(tmp_path, registry):
    """[ ] 인증이 필요한 모든 Connector 에 대해 가이드 생성 및 확인일 기록"""
    from scripts.generate_api_guide import build_markdown
    from src.config_loader import Settings, load_app_config

    settings = Settings(
        app=load_app_config(CONFIG_DIR / "config.yaml"),
        sources=registry,
        topics=load_topics(CONFIG_DIR / "topics.yaml"),
        search_terms=load_search_terms(CONFIG_DIR / "search_terms.yaml"),
    )
    markdown = build_markdown(settings)

    for source in registry.sources:
        for method in source.access_methods:
            if method.credential_required and method.credential_env_var:
                assert method.credential_env_var in markdown, (
                    f"{source.source_id} 의 {method.credential_env_var} 가 가이드에 없습니다."
                )

    # 16개 필수 기재항목이 표에 존재해야 합니다.
    for item in (
        "1. 서비스/기관명", "4. 공식 발급/신청 페이지", "7. 서비스 목적 예시",
        "9. 무료/유료 및 쿼터", "10. OAuth Scope/권한", "11. Redirect URI 필요 여부",
        "12. 환경변수명", "13. 동작 확인 방법", "14. 키 만료·갱신·회수",
        "16. 공식 문서 최종 확인일",
    ):
        assert item in markdown, f"필수 기재항목 누락: {item}"

    # Gmail 인증 절차도 포함되어야 합니다.
    assert "Gmail API" in markdown
    assert "gmail.send" in markdown


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),          # 일반 API Key 형태
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),          # Google API Key
    re.compile(r"ya29\.[0-9A-Za-z_\-]+"),            # Google OAuth 토큰
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]


def test_api_guide_contains_no_real_secrets():
    """[ ] API 가이드와 .env.example 에 실제 비밀키/토큰이 포함되지 않음"""
    guide = PROJECT_ROOT / "docs" / "API_발급_연동_가이드.md"
    if not guide.exists():
        pytest.skip("가이드가 아직 생성되지 않았습니다. python main.py api-guide 를 실행하세요.")

    content = guide.read_text(encoding="utf-8")
    for pattern in SECRET_PATTERNS:
        assert not pattern.search(content), f"가이드에 비밀값으로 보이는 문자열이 있습니다: {pattern.pattern}"


def test_env_example_has_no_values():
    """`.env.example` 에는 변수명과 설명만 있어야 합니다 (§5.1 보안 원칙)."""
    example = PROJECT_ROOT / ".env.example"
    assert example.exists()

    content = example.read_text(encoding="utf-8")
    for pattern in SECRET_PATTERNS:
        assert not pattern.search(content)

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        assert "=" in line, line
        _, _, value = line.partition("=")
        assert value.strip() == "", f"실제 값이 들어 있습니다: {line}"


def test_env_is_gitignored():
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in gitignore
    assert "!.env.example" in gitignore


def test_no_search_engine_html_scraping():
    """§4.1 — 검색엔진 HTML 결과 스크래핑을 핵심 수집수단으로 쓰지 않습니다."""
    banned = ("duckduckgo", "google.com/search", "bing.com/search", "html.duckduckgo")
    for path in (PROJECT_ROOT / "src").rglob("*.py"):
        content = path.read_text(encoding="utf-8").lower()
        for needle in banned:
            assert needle not in content, f"{path} 에 검색엔진 스크래핑 흔적이 있습니다: {needle}"


def test_no_paywall_bypass_helpers():
    """§7.3 — 로그인/CAPTCHA/Paywall 우회 기능이 없어야 합니다."""
    banned = ("captcha_solve", "bypass_paywall", "solve_captcha", "anticaptcha", "2captcha")
    for path in (PROJECT_ROOT / "src").rglob("*.py"):
        content = path.read_text(encoding="utf-8").lower()
        for needle in banned:
            assert needle not in content, f"{path} 에 우회 기능이 있습니다: {needle}"


# ---------------------------------------------------------------------------
# 엔드포인트·검증 근거의 정직성 (§5.1 최신성 원칙, §18.4 감사가능성)
# ---------------------------------------------------------------------------

def test_verified_methods_cite_a_source(registry):
    """VERIFIED 로 표시하려면 확인근거 URL·일자·경로가 있어야 합니다."""
    for source in registry.sources:
        for method in source.access_methods:
            if method.verification_status != "VERIFIED":
                continue
            label = f"{source.source_id}/{method.type}"
            assert method.verified_source, f"{label}: 확인근거 URL 이 없습니다."
            assert method.verified_at, f"{label}: 확인 일자가 없습니다."
            assert method.verified_method in ("official_doc", "web_search", "operator_input"), (
                f"{label}: 확인 경로가 기록되지 않았습니다."
            )


def test_verified_source_is_on_an_official_domain(registry):
    """확인근거는 해당 기관 또는 공식 포털의 도메인이어야 합니다."""
    from urllib.parse import urlparse

    # 공식 포털을 통해 제공되는 소스(공공데이터포털 경유 등)의 예외 도메인
    official_portals = ("data.go.kr", "openalex.org", "crossref.org", "doaj.org", "ssrn.com")

    for source in registry.sources:
        for method in source.access_methods:
            if not method.verified_source:
                continue
            host = urlparse(method.verified_source).netloc.lower()
            base = source.base_domain.lower()
            ok = (
                base in host
                or host.endswith(base)
                or any(p in host for p in official_portals)
                # api.core.ac.uk ↔ core.ac.uk 처럼 상위 도메인이 같은 경우
                or ".".join(base.split(".")[-2:]) in host
            )
            assert ok, (
                f"{source.source_id}: 확인근거({method.verified_source})가 "
                f"공식 도메인({source.base_domain})이 아닙니다."
            )


def test_unverified_sources_have_no_guessed_endpoint(registry):
    """확인되지 않은 소스에 추측한 엔드포인트를 넣지 않습니다 (URL 환각 금지).

    운영자가 자기 계정으로 확인해 직접 입력한 값(`verified_method: operator_input`)은
    추측이 아니므로 허용합니다. 다만 공식 문서 대조 전까지는
    `verification_status` 를 PENDING_VERIFICATION 로 유지해야 합니다.
    """
    for source in registry.sources:
        for method in source.access_methods:
            if method.verification_status == "VERIFIED":
                continue
            if method.verified_method == "operator_input":
                # 출처와 입력 일자는 남겨야 추적이 가능합니다.
                assert method.verified_source, (
                    f"{source.source_id}/{method.type}: operator_input 인데 근거가 없습니다."
                )
                assert method.verified_at, (
                    f"{source.source_id}/{method.type}: operator_input 인데 입력 일자가 없습니다."
                )
                continue
            assert not method.endpoint, (
                f"{source.source_id}/{method.type}: 확인되지 않았는데 endpoint 가 "
                f"채워져 있습니다 ({method.endpoint}). 운영자가 직접 넣은 값이라면 "
                f"verified_method 를 operator_input 으로 표시하십시오."
            )


def test_openalex_requires_api_key(registry):
    """OpenAlex 는 2026-02-13 부터 API Key 가 필수입니다."""
    openalex = registry.get("openalex")
    method = openalex.method("OPEN_API")
    assert method.credential_required is True
    assert method.credential_env_var == "OPENALEX_API_KEY"

    # 폐지된 polite pool 파라미터를 더 이상 보내지 않아야 합니다.
    # (설명 주석이 아니라 실제 요청 파라미터로 쓰이는지를 확인합니다)
    source = (PROJECT_ROOT / "src" / "connectors" / "openalex.py").read_text(encoding="utf-8")
    assert '"mailto"' not in source


def test_riss_has_no_bibliographic_search_endpoint(registry):
    """RISS 공개 API 에는 일반 학술 서지 검색이 없어 endpoint 를 비워 둡니다."""
    riss = registry.get("riss")
    assert riss.method("OPEN_API").endpoint == ""
    assert riss.download_policy == DownloadPolicy.LINK_ONLY


# ---------------------------------------------------------------------------
# 인증정보 배선 (환경변수 → Connector → 요청)
# ---------------------------------------------------------------------------

CREDENTIAL_TARGETS = [
    ("kci", "OPEN_API", "KCI_API_KEY"),
    ("law_go_kr", "OPEN_API", "LAW_GO_KR_OC"),
    ("prism", "OPEN_API", "DATA_GO_KR_API_KEY"),
    ("scienceon", "OPEN_API", "SCIENCEON_API_KEY"),
    ("core", "OPEN_API", "CORE_API_KEY"),
    ("openalex", "OPEN_API", "OPENALEX_API_KEY"),
    ("semantic_scholar", "OPEN_API", "SEMANTIC_SCHOLAR_API_KEY"),
    ("zenodo", "OPEN_API", "ZENODO_API_KEY"),
    ("doaj", "OPEN_API", "DOAJ_API_KEY"),
]


@pytest.mark.parametrize(("source_id", "method_type", "env_var"), CREDENTIAL_TARGETS)
def test_credential_env_var_reaches_the_request(
    source_id, method_type, env_var, monkeypatch, credential_probe
):
    """`.env` 의 값이 실제 HTTP 요청까지 전달되어야 합니다."""
    from datetime import date

    secret = f"PROBE-{source_id.upper()}"
    monkeypatch.setenv(env_var, secret)
    if source_id == "scienceon":
        monkeypatch.setenv("SCIENCEON_CLIENT_ID", "PROBE-CLIENT")

    requests = credential_probe(source_id, method_type, date(2026, 8, 1), date(2026, 8, 22))
    assert requests, f"{source_id}: 요청이 전송되지 않았습니다."

    import json

    # KCI 처럼 인증 불필요 경로(OAI-PMH)를 먼저 시도하는 소스가 있으므로
    # 첫 요청이 아니라 전체 요청 중 하나에 값이 실렸는지 확인합니다.
    blob = json.dumps(requests, ensure_ascii=False)
    assert secret in blob, (
        f"{source_id}: {len(requests)}건의 요청 어디에도 {env_var} 값이 실리지 않았습니다."
    )


def test_scienceon_sends_client_id_with_token(monkeypatch, credential_probe):
    """ScienceON 은 token 과 client_id 를 함께 보내야 합니다."""
    from datetime import date

    monkeypatch.setenv("SCIENCEON_API_KEY", "PROBE-TOKEN")
    monkeypatch.setenv("SCIENCEON_CLIENT_ID", "PROBE-CLIENT")

    requests = credential_probe("scienceon", "OPEN_API", date(2026, 8, 1), date(2026, 8, 22))
    assert requests
    queries = [r["query"] for r in requests]
    assert any(q.get("token") == "PROBE-TOKEN" for q in queries), "token 미전송"
    assert any(q.get("client_id") == "PROBE-CLIENT" for q in queries), "client_id 미전송"


def test_missing_credential_is_not_sent_as_empty_string(monkeypatch, credential_probe):
    """인증정보가 없으면 빈 값으로 호출하지 않고 소스를 건너뜁니다."""
    from datetime import date

    from src.connectors import CredentialMissingError

    monkeypatch.delenv("CORE_API_KEY", raising=False)
    with pytest.raises(CredentialMissingError):
        credential_probe("core", "OPEN_API", date(2026, 8, 1), date(2026, 8, 22))


# ---------------------------------------------------------------------------
# GitHub Actions 워크플로 ↔ 프로그램 환경변수 정합성
# ---------------------------------------------------------------------------

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "credential-check.yml"

#: sources.yaml 에 없지만 프로그램이 읽는 환경변수
EXTRA_ENV_VARS = {
    "SCIENCEON_CLIENT_ID",
    "DLRCIS_SENDER_EMAIL",
    "DLRCIS_RECEIVER_EMAIL",
    "DLRCIS_SMTP_PASSWORD",
    "ANTHROPIC_API_KEY",
}


def _workflow_env() -> dict:
    import yaml

    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return data["jobs"]["check"]["env"]


def test_credential_check_workflow_exists():
    """Secrets 는 워크플로가 있어야 프로그램에 전달됩니다."""
    assert WORKFLOW.exists(), "credential-check.yml 이 없으면 Secrets 가 사용되지 않습니다."


def test_workflow_injects_every_env_var_the_program_reads(registry):
    """프로그램이 읽는 모든 환경변수를 워크플로가 주입해야 합니다."""
    needed = {
        m.credential_env_var
        for s in registry.sources
        for m in s.access_methods
        if m.credential_env_var
    } | EXTRA_ENV_VARS

    injected = set(_workflow_env())
    missing = sorted(needed - injected)
    assert not missing, f"워크플로에 빠진 환경변수: {missing}"


def test_workflow_maps_names_to_matching_secrets():
    """환경변수 이름과 Secret 이름이 1:1 로 대응해야 혼동이 없습니다."""
    import re

    for env_name, expression in _workflow_env().items():
        match = re.fullmatch(r"\$\{\{\s*secrets\.([A-Z0-9_]+)\s*\}\}", str(expression))
        assert match, f"{env_name}: secrets 참조 형식이 아닙니다 ({expression})"
        assert match.group(1) == env_name, (
            f"{env_name}: Secret 이름({match.group(1)})이 환경변수 이름과 다릅니다."
        )


def test_workflow_installs_what_its_steps_need():
    """워크플로가 실행하는 명령의 의존성이 설치 단계에 포함되어야 합니다.

    pytest 는 런타임 의존성이 아니라 requirements.txt 에 없습니다.
    설치 단계가 requirements.txt 만 설치하면 테스트 단계가
    `No module named pytest` 로 실패합니다.
    """
    import yaml

    root = PROJECT_ROOT
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = data["jobs"]["check"]["steps"]
    commands = " ".join(str(step.get("run", "")) for step in steps)

    installed = " ".join(
        str(step.get("run", "")) for step in steps if "pip install" in str(step.get("run", ""))
    )
    assert installed, "의존성 설치 단계가 없습니다."

    # 설치 단계가 가리키는 requirements 파일들을 -r 포함관계까지 따라갑니다.
    def declared_packages(name: str, seen: set[str] | None = None) -> str:
        seen = seen if seen is not None else set()
        if name in seen:
            return ""
        seen.add(name)
        path = root / name
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("-r "):
                text += declared_packages(line[3:].strip(), seen)
        return text

    available = ""
    for req in re.findall(r"pip install -r ([\w.-]+)", installed):
        available += declared_packages(req)

    if "pytest" in commands:
        assert "pytest" in available, (
            "워크플로가 pytest 를 실행하지만 설치 단계가 pytest 를 설치하지 않습니다. "
            "requirements-dev.txt 를 설치하도록 고치십시오."
        )


def test_workflow_is_manual_only():
    """점검 워크플로가 예고 없이 자동 실행되지 않아야 합니다."""
    import yaml

    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML 은 YAML 1.1 규칙으로 `on:` 을 True 로 파싱합니다.
    triggers = data.get("on", data.get(True))
    assert set(triggers) == {"workflow_dispatch"}, f"예상치 못한 트리거: {triggers}"
