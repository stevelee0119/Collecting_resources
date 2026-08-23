"""DL-RCIS 진입점 (PRD v2.1).

사용 예:
    python main.py run --daily            # 일일 증분 수집
    python main.py run --backfill         # 초기 백필
    python main.py run --reconcile        # 월간 정합성 점검
    python main.py run --source kci arxiv # 특정 소스만
    python main.py schedule               # 스케줄러 데몬
    python main.py doctor                 # 설정·인증정보 점검
    python main.py search "군사법원"       # 수집 자료 전문검색
    python main.py api-guide              # API 발급·연동 가이드 생성
    python main.py export                 # CSV/Excel 재생성
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from src.config_loader import ConfigError, get_secret, load_settings, mask_secret
from src.database import Repository
from src.discovery import Pipeline
from src.logging_setup import setup_logging
from src.models import RunType
from src.notifier import NotificationError, build_notifier
from src.scheduler import SchedulerRunner

logger = logging.getLogger("dlrcis")

# Windows 콘솔 인코딩 대응
if sys.platform == "win32":  # pragma: no cover
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 공통
# ---------------------------------------------------------------------------

def _bootstrap(args: argparse.Namespace):
    settings = load_settings()
    setup_logging(
        level=args.log_level or str(settings.app.get("logging.level", "INFO")),
        log_dir=settings.app.path("logging.dir", "logs"),
        max_bytes=int(settings.app.get("logging.max_bytes", 10_485_760)),
        backup_count=int(settings.app.get("logging.backup_count", 7)),
    )
    repo = Repository(settings.app.path("storage.database_path", "data/metadata/dlrcis.db"))
    return settings, repo


def _run_type_from(args: argparse.Namespace) -> RunType:
    if args.backfill:
        return RunType.BACKFILL
    if args.reconcile:
        return RunType.MONTHLY_RECONCILIATION
    return RunType.DAILY_INCREMENTAL


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    settings, repo = _bootstrap(args)
    run_type = _run_type_from(args)

    try:
        with Pipeline(settings, repo) as pipeline:
            report = pipeline.run(
                run_type,
                since=date.fromisoformat(args.since) if args.since else None,
                until=date.fromisoformat(args.until) if args.until else None,
                only_sources=args.source,
                dry_run=args.dry_run,
            )

        _print_summary(report)

        # 16) 브리핑 발송
        if args.dry_run:
            print("\n[dry-run] 알림을 발송하지 않았습니다.")
        elif args.no_notify:
            print("\n--no-notify 지정으로 알림을 발송하지 않았습니다.")
        else:
            _notify(settings, repo, report)
        return 0
    finally:
        repo.close()


def _notify(settings, repo, report) -> None:
    notifier = build_notifier(settings.app)
    if notifier is None:
        return
    try:
        sent = notifier.send(report, report.resources, collected_on=report.started_at.date())
    except NotificationError as exc:
        logger.error("브리핑 발송 실패: %s", exc)
        repo.log_alert(
            run_id=report.run_id,
            channel=notifier.channel,
            recipient=getattr(notifier, "receiver", ""),
            subject="",
            item_count=len(report.resources),
            status="FAILED",
            detail=str(exc),
        )
        return

    if sent:
        repo.log_alert(
            run_id=report.run_id,
            channel=notifier.channel,
            recipient=getattr(notifier, "receiver", ""),
            subject=f"신규 {report.new_count}건",
            item_count=len(report.resources),
            status="SENT",
        )
        repo.mark_alerted([r.resource_id for r in report.resources])


def _print_summary(report) -> None:
    print()
    print("=" * 62)
    print(f" 실행유형 : {report.run_type.value}")
    print(f" 조회기간 : {report.since} ~ {report.until}")
    print(f" 신규     : {report.new_count}건")
    print(f" 수정     : {report.updated_count}건")
    print("=" * 62)
    header = f"{'소스':<18}{'탐색':>6}{'신규':>6}{'수정':>6}{'중복':>6}{'저장':>6}{'링크':>6}"
    print(header)
    print("-" * 62)
    for source in report.sources:
        if source.error_code:
            print(f"{source.source_id:<18}  [건너뜀] {source.error_code}")
            continue
        if source.skipped_reason:
            print(f"{source.source_id:<18}  [보조소스]")
            continue
        print(
            f"{source.source_id:<18}{source.discovered:>6}{source.new_resources:>6}"
            f"{source.updated_resources:>6}{source.duplicates:>6}"
            f"{source.downloaded:>6}{source.link_only:>6}"
        )
    print("=" * 62)

    if report.failed_sources:
        print("\n[건너뛴 소스 상세]")
        for source in report.failed_sources:
            print(f"  - {source.source_name} ({source.source_id})")
            print(f"    {source.error_message}")


# ---------------------------------------------------------------------------
# schedule
# ---------------------------------------------------------------------------

def cmd_schedule(args: argparse.Namespace) -> int:
    settings, repo = _bootstrap(args)

    def job(run_type: RunType) -> None:
        with Pipeline(settings, repo) as pipeline:
            report = pipeline.run(run_type)
        _notify(settings, repo, report)

    try:
        SchedulerRunner(settings.app, job).start()
        return 0
    finally:
        repo.close()


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------

def cmd_doctor(args: argparse.Namespace) -> int:
    settings, repo = _bootstrap(args)
    try:
        print("\n=== DL-RCIS 설정 점검 ===\n")

        print(f"Source Registry : {settings.sources.registry_version} "
              f"({len(settings.sources.sources)}개 소스, 활성 {len(settings.sources.enabled())}개)")
        print(f"주제 체계       : {settings.topics.version} ({len(settings.topics.topics)}개 주제)")
        print(f"검색어 사전     : {settings.search_terms.dictionary_version} "
              f"({len(settings.search_terms.terms)}개 용어)")

        missing = settings.search_terms.missing_required()
        if missing:
            print(f"\n[경고] 필수 키워드 누락 {len(missing)}개: {', '.join(missing)}")
        else:
            print(f"\n[OK] PRD §3.3 필수 키워드 "
                  f"{len(settings.search_terms.required_baseline)}개 모두 포함")

        no_english = [
            t.canonical_ko
            for t in settings.search_terms.terms
            if "international" in t.source_scope and not t.en_terms and not t.en_acronyms
        ]
        if no_english:
            print(f"[경고] 영문 대응어 없음 ({len(no_english)}개): {', '.join(no_english)}")

        print("\n--- 소스별 인증정보 ---")
        ready = blocked = 0
        for source in settings.sources.enabled():
            statuses = []
            usable = False
            for method in source.access_methods:
                secret = get_secret(method.credential_env_var)
                if not method.endpoint:
                    statuses.append(f"{method.type}=엔드포인트미설정")
                elif method.credential_required and not secret:
                    statuses.append(f"{method.type}=인증정보없음({method.credential_env_var})")
                else:
                    usable = True
                    label = mask_secret(secret) if secret else "인증불필요"
                    statuses.append(f"{method.type}=사용가능({label})")
            mark = "OK  " if usable else "SKIP"
            if usable:
                ready += 1
            else:
                blocked += 1
            print(f"  [{mark}] {source.source_id:<18} {'; '.join(statuses)}")

        print(f"\n사용 가능 소스: {ready}개 / 설정 필요: {blocked}개")
        if blocked:
            print("설정이 필요한 소스는 docs/API_발급_연동_가이드.md 의 절차를 따르세요.")

        print("\n--- 저장소 상태 ---")
        counts = repo.counts()
        print(f"  자료 {counts['resources']}건 (다운로드 {counts['downloaded']} / "
              f"링크만 {counts['link_only']}), 파일 {counts['files']}개")
        print(f"  DOI 보유 {counts['with_doi']}건, 실행 {counts['runs']}회, 오류 {counts['errors']}건")
        print(f"  전문검색(FTS5): {'사용 가능' if repo.fts_enabled else '사용 불가'}")

        print("\n--- 알림 설정 ---")
        transport = settings.app.get("notification.email.transport", "smtp")
        sender = settings.app.get("notification.email.sender_email", "") or get_secret("DLRCIS_SENDER_EMAIL") or ""
        receiver = settings.app.get("notification.email.receiver_email", "") or get_secret("DLRCIS_RECEIVER_EMAIL") or ""
        print(f"  전송방식: {transport} / 발신: {sender or '(미설정)'} → 수신: {receiver or '(미설정)'}")
        if transport == "smtp":
            print(f"  SMTP 비밀번호: {mask_secret(get_secret('DLRCIS_SMTP_PASSWORD'))}")

        print(f"\n요약 공급자: {settings.app.get('summarizer.provider', 'extractive')}")

        if args.probe:
            _probe_sources(settings)

        print()
        return 0
    finally:
        repo.close()


class _LogCapture(logging.Handler):
    """탐색 중 발생한 경고를 모아 실패 원인을 보여줍니다."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.messages.append(record.getMessage())
        except Exception:
            pass


def _probe_sources(settings) -> None:
    """소스마다 실제로 1회 호출해 인증이 통하는지 확인합니다.

    `doctor` 기본 점검은 "값이 있는가"만 보므로, 잘못된 키·만료된 승인·
    잘못된 인증키 형식은 잡아내지 못합니다. 이 점검은 실제 응답을 확인합니다.
    """
    from datetime import date, timedelta

    from src.connectors import ConnectorContext, ConnectorError, build_connector
    from src.discovery.query_expander import QueryExpander
    from src.http_client import build_client

    print("\n--- 실제 호출 점검 (--probe) ---")
    print("  소스마다 1회씩 실제 요청을 보내 인증이 통하는지 확인합니다.\n")

    until = date.today()
    since = until - timedelta(days=30)
    expander = QueryExpander(settings.search_terms)

    ok = failed = skipped = 0
    root = logging.getLogger()
    # 점검 중에는 기존 핸들러 출력을 잠시 낮춰 결과 줄만 보이게 합니다.
    original_levels = [(h, h.level) for h in root.handlers]

    for source in settings.sources.enabled():
        # 호출할 엔드포인트가 하나도 없으면 요청 자체가 나가지 않습니다.
        if not any(m.endpoint for m in source.access_methods):
            print(f"  [건너뜀] {source.source_id:<18} 엔드포인트 미설정 — 호출하지 않음")
            skipped += 1
            continue

        client = None
        capture = _LogCapture()
        previous_level = root.level
        for handler, _ in original_levels:
            handler.setLevel(logging.CRITICAL)
        root.addHandler(capture)
        root.setLevel(logging.WARNING)
        try:
            client = build_client(settings.app, source)
            connector = build_connector(
                source,
                ConnectorContext(app=settings.app, client=client, expander=expander, max_items=1),
            )
            if connector.passive:
                print(f"  [건너뜀] {source.source_id:<18} 다른 소스가 발견한 자료를 흡수하는 소스")
                skipped += 1
                continue

            queries = connector.prepare_queries()[:1]
            items = []
            for item in connector.discover(since, until, queries):
                items.append(item)
                break

            if capture.messages:
                # 탐색 중 경고가 있었다면 인증·요청 문제일 가능성이 높습니다.
                reason = capture.messages[0]
                print(f"  [실패  ] {source.source_id:<18} {reason[:110]}")
                failed += 1
            elif items:
                print(f"  [성공  ] {source.source_id:<18} 응답 수신 (레코드 확인됨)")
                ok += 1
            else:
                print(f"  [응답  ] {source.source_id:<18} 정상 응답이나 이 기간·검색어에 결과 없음")
                ok += 1
        except ConnectorError as exc:
            print(f"  [건너뜀] {source.source_id:<18} {str(exc)[:100]}")
            skipped += 1
        except Exception as exc:
            print(f"  [실패  ] {source.source_id:<18} {type(exc).__name__}: {str(exc)[:90]}")
            failed += 1
        finally:
            root.removeHandler(capture)
            root.setLevel(previous_level)
            for handler, level in original_levels:
                handler.setLevel(level)
            if client is not None:
                client.close()

    print(f"\n  실제 호출 결과: 성공 {ok}개 / 실패 {failed}개 / 건너뜀 {skipped}개")
    if failed:
        print("  실패한 소스는 인증정보 값이 잘못되었거나 API 정책이 바뀌었을 수 있습니다.")


# ---------------------------------------------------------------------------
# search / export / api-guide
# ---------------------------------------------------------------------------

def cmd_search(args: argparse.Namespace) -> int:
    settings, repo = _bootstrap(args)
    try:
        results = repo.search(args.query, limit=args.limit)
        if not results:
            print(f"'{args.query}' 에 해당하는 자료가 없습니다.")
            return 0
        print(f"\n'{args.query}' 검색 결과 {len(results)}건\n")
        for index, resource in enumerate(results, start=1):
            print(f"{index:>3}. [{resource.priority_level.value}/{resource.relevance_score}] "
                  f"{resource.best_title()[:70]}")
            print(f"     {resource.source_id} · {resource.topic_primary} · "
                  f"{resource.publication_date or '발행일미상'}")
            print(f"     {resource.canonical_url()}")
            if resource.file_path:
                print(f"     저장: {resource.file_path}")
            print()
        return 0
    finally:
        repo.close()


def cmd_export(args: argparse.Namespace) -> int:
    settings, repo = _bootstrap(args)
    try:
        from src.storage import ResourceExporter

        exporter = ResourceExporter(
            settings.app.path("storage.csv_path", "data/metadata/list_download_resources.csv"),
            settings.app.path("storage.excel_path", "data/metadata/list_download_resources.xlsx"),
        )
        resources = repo.all_resources()
        exporter.export(resources)
        print(f"{len(resources)}건을 CSV/Excel 로 내보냈습니다.")
        return 0
    finally:
        repo.close()


def cmd_api_guide(args: argparse.Namespace) -> int:
    settings, _repo = _bootstrap(args)
    _repo.close()
    from scripts.generate_api_guide import generate

    paths = generate(settings, include_excel=args.excel)
    for path in paths:
        print(f"생성: {path}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    # --log-level 을 최상위와 하위 명령 어느 쪽에도 붙일 수 있도록 공용 부모를 씁니다.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--log-level", default=None, help="DEBUG / INFO / WARNING / ERROR")

    parser = argparse.ArgumentParser(
        prog="dlrcis",
        description="국방·법률·공공·학술 리서치 자동수집·요약·알림 시스템 (PRD v2.1)",
        parents=[common],
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="수집 실행", parents=[common])
    mode = run.add_mutually_exclusive_group()
    mode.add_argument("--daily", action="store_true", help="일일 증분 수집 (기본)")
    mode.add_argument("--backfill", action="store_true", help="초기 백필")
    mode.add_argument("--reconcile", action="store_true", help="월간 정합성 점검")
    run.add_argument("--since", help="조회 시작일 (YYYY-MM-DD)")
    run.add_argument("--until", help="조회 종료일 (YYYY-MM-DD)")
    run.add_argument("--source", nargs="+", help="특정 source_id 만 실행")
    run.add_argument("--dry-run", action="store_true", help="다운로드·저장 없이 탐색만 수행")
    run.add_argument("--no-notify", action="store_true", help="브리핑 발송 생략")
    run.set_defaults(func=cmd_run)

    schedule = sub.add_parser("schedule", help="스케줄러 데몬 실행", parents=[common])
    schedule.set_defaults(func=cmd_schedule)

    doctor = sub.add_parser("doctor", help="설정·인증정보·저장소 점검", parents=[common])
    doctor.add_argument(
        "--probe",
        action="store_true",
        help="소스마다 실제로 1회 호출해 인증이 통하는지 확인 (네트워크 필요)",
    )
    doctor.set_defaults(func=cmd_doctor)

    search = sub.add_parser("search", help="수집 자료 전문검색", parents=[common])
    search.add_argument("query", help="검색어")
    search.add_argument("--limit", type=int, default=20)
    search.set_defaults(func=cmd_search)

    export = sub.add_parser("export", help="CSV/Excel 재생성", parents=[common])
    export.set_defaults(func=cmd_export)

    guide = sub.add_parser("api-guide", help="API 발급·연동 가이드 생성", parents=[common])
    guide.add_argument("--excel", action="store_true", help="Excel 버전도 함께 생성")
    guide.set_defaults(func=cmd_api_guide)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ConfigError as exc:
        print(f"[설정 오류] {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n중단되었습니다.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
