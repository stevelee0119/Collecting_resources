"""수집 파이프라인 (PRD v2.1 §6.1).

처리 순서:
 1. Scheduler 실행              2. Source Registry 에서 활성 소스 로드
 3. 소스별 공식 API/OAI/RSS 호출  4. 메타데이터 정규화
 5. 접근정책·라이선스 검사        6. DOI/공식 ID 기반 1차 중복 판별
 7. OA Resolver 실행             8. 다운로드 후보 URL 검증
 9. 허용된 원문만 다운로드        10. 파일 해시·텍스트 해시 계산
11. 문서 형식·무결성 검사        12. 주제 분류 및 중요도 산정
13. 주제별 최종 저장소로 이동     14. 일자별 Manifest 및 DB 기록
15. 요약 생성                   16. 이메일/메신저 브리핑 발송

소스별 실패가 전체 작업을 중단시키지 않습니다 (§16.3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from ..classifier import RelevanceScorer, TopicClassifier
from ..config_loader import Settings
from ..connectors import (
    ConnectorContext,
    ConnectorError,
    SourceConnector,
    build_connector,
)
from ..connectors.core import CoreConnector
from ..connectors.crossref import CrossrefConnector, CrossrefResolver
from ..connectors.riss import RissConnector, is_riss_resource
from ..connectors.scienceon import ScienceOnConnector
from ..connectors.ssrn import SsrnConnector, is_ssrn_resource
from ..connectors.unpaywall import UnpaywallConnector
from ..database import Repository
from ..dedup import DedupVerdict, Deduplicator
from ..downloader import Downloader, OpenAccessResolver
from ..extractors import ExtractedText, TextExtractor
from ..http_client import SharedHostState, build_client
from ..models import (
    AccessMode,
    CandidateKind,
    ErrorCode,
    Resource,
    ResourceStatus,
    RunReport,
    RunType,
    SourceConfig,
    SourceRunReport,
)
from ..normalizers.normalize import text_sha256
from ..storage import Library, ManifestWriter, ResourceExporter
from ..summarizer import Summarizer, build_summarizer
from ..validators import FileValidator, LicenseValidator, LinkValidator
from .query_expander import QueryExpander

logger = logging.getLogger(__name__)

#: 연속 실패가 이 횟수를 넘으면 관리자 알림 대상 (§16.3)
FAILURE_ALERT_THRESHOLD = 5


@dataclass
class ProcessOutcome:
    """자료 1건 처리 결과."""

    resource: Resource | None = None
    outcome: str = "SKIPPED"


class Pipeline:
    """일일/월간 수집 전체를 조율합니다."""

    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.app = settings.app
        self.repo = repo

        self.expander = QueryExpander(settings.search_terms)
        self.classifier = TopicClassifier(
            settings.topics,
            min_confidence=float(self.app.get("classification.min_confidence", 0.25)),
            multi_topic_margin=float(self.app.get("classification.multi_topic_margin", 0.15)),
        )
        self.scorer = RelevanceScorer(self.app, settings.topics)
        self.library = Library(
            self.app.path("storage.library_dir", "data/library"),
            settings.topics,
            max_filename=int(self.app.get("storage.max_filename_length", 160)),
        )
        self.manifest = ManifestWriter(self.app.path("storage.manifest_dir", "data/manifests"))
        self.exporter = ResourceExporter(
            self.app.path("storage.csv_path", "data/metadata/list_download_resources.csv"),
            self.app.path("storage.excel_path", "data/metadata/list_download_resources.xlsx"),
        )
        self.downloader = Downloader(
            self.app.path("storage.staging_dir", "data/staging"),
            max_file_size_mb=int(self.app.get("download.max_file_size_mb", 200)),
            allowed_extensions=tuple(
                self.app.get("download.allowed_extensions", [".pdf", ".hwp", ".hwpx", ".docx"])
            ),
        )
        self.file_validator = FileValidator(
            min_size_bytes=int(self.app.get("download.min_file_size_bytes", 1024)),
            max_size_mb=int(self.app.get("download.max_file_size_mb", 200)),
        )
        self.license_validator = LicenseValidator()
        self.extractor = TextExtractor()
        self.summarizer: Summarizer = build_summarizer(self.app)
        self.deduplicator = Deduplicator(repo)

        self.download_enabled = bool(self.app.get("download.enabled", True))
        self.download_threshold = int(self.app.get("run.download_relevance_threshold", 55))
        self.summarize_threshold = int(self.app.get("run.summarize_relevance_threshold", 40))
        self.max_items = int(self.app.get("run.max_items_per_source", 200))
        self.quarantine_dir = self.app.path("storage.quarantine_dir", "data/quarantine")

        # 같은 호스트를 보는 소스들이 rate limit·robots 캐시·동일 요청 메모를
        # 공유합니다. 예: law.go.kr DRF 를 target 만 달리해 쓰는 law_go_kr / humanrights.
        self._shared_http = SharedHostState(
            user_agent=str(self.app.get("http.user_agent", "DL-RCIS/2.1")),
            memoize=bool(self.app.get("http.deduplicate_requests", True)),
        )
        self._clients: dict[str, object] = {}
        self._connectors: dict[str, SourceConnector] = {}
        self._oa_resolver: OpenAccessResolver | None = None
        self._crossref_resolver: CrossrefResolver | None = None

    # ==================================================================
    # 실행 진입점
    # ==================================================================
    def run(
        self,
        run_type: RunType = RunType.DAILY_INCREMENTAL,
        *,
        since: date | None = None,
        until: date | None = None,
        only_sources: list[str] | None = None,
        dry_run: bool = False,
    ) -> RunReport:
        window = self._resolve_window(run_type, since, until)
        report = RunReport(
            run_type=run_type,
            started_at=datetime.now(),
            since=window[0],
            until=window[1],
            dictionary_version=self.settings.search_terms.dictionary_version,
        )
        self.repo.start_run(report)
        self.repo.sync_sources(self.settings.sources.sources)
        self.repo.sync_topics(self.settings.topics.topics)

        logger.info(
            "=== 수집 시작 [%s] %s ~ %s (검색어사전 %s) ===",
            run_type.value,
            window[0].isoformat(),
            window[1].isoformat(),
            report.dictionary_version,
        )
        self._warn_missing_required_terms()

        sources = self._sources_for(run_type, only_sources)
        self._prepare_resolvers(sources)

        for source in sources:
            source_report = self._run_source(source, window[0], window[1], report, dry_run=dry_run)
            report.sources.append(source_report)

        report.finished_at = datetime.now()

        if not dry_run:
            self._persist_outputs(report)

        status = "SUCCEEDED" if not report.failed_sources else "PARTIAL"
        self.repo.finish_run(report, status)

        logger.info(
            "=== 수집 종료: 신규 %d건 / 수정 %d건 / 실패 소스 %d개 (%s) ===",
            report.new_count,
            report.updated_count,
            len(report.failed_sources),
            status,
        )
        return report

    # ==================================================================
    # 소스 단위 처리
    # ==================================================================
    def _run_source(
        self,
        source: SourceConfig,
        since: date,
        until: date,
        report: RunReport,
        *,
        dry_run: bool,
    ) -> SourceRunReport:
        result = SourceRunReport(source_id=source.source_id, source_name=source.name)
        logger.info("[%s] 수집 시작 (%s)", source.source_id, source.name)

        try:
            connector = self._connector_for(source)
        except ConnectorError as exc:
            return self._fail_source(result, source, report, exc.error_code, str(exc))

        if connector.passive:
            result.skipped_reason = "다른 소스가 발견한 자료를 흡수하는 소스입니다."
            logger.info("[%s] %s", source.source_id, result.skipped_reason)
            return result

        # 소스별 look-back 을 개별 적용합니다.
        source_since = min(since, until - timedelta(days=max(0, source.lookback_days - 1)))

        try:
            queries = connector.prepare_queries()
            raw_items = list(connector.discover(source_since, until, queries))
        except ConnectorError as exc:
            return self._fail_source(result, source, report, exc.error_code, str(exc))
        except Exception as exc:
            return self._fail_source(
                result, source, report, ErrorCode.DISCOVERY_FAILED.value, f"탐색 실패: {exc}"
            )

        result.discovered = len(raw_items)
        logger.info("[%s] %d건 탐색", source.source_id, len(raw_items))

        for raw in raw_items:
            try:
                outcome = self._process_item(connector, raw, report, dry_run=dry_run)
            except Exception as exc:
                logger.exception("[%s] 자료 처리 중 오류: %s", source.source_id, exc)
                self.repo.log_error(
                    run_id=report.run_id,
                    source_id=source.source_id,
                    error_code=ErrorCode.DISCOVERY_FAILED.value,
                    message=str(exc),
                )
                result.failed += 1
                continue

            self._tally(result, outcome, report)

        self.repo.record_source_attempt(source.source_id, success=True)
        logger.info(
            "[%s] 완료 — 신규 %d / 수정 %d / 중복 %d / 다운로드 %d / 링크만 %d",
            source.source_id,
            result.new_resources,
            result.updated_resources,
            result.duplicates,
            result.downloaded,
            result.link_only,
        )
        return result

    def _tally(self, result: SourceRunReport, outcome: ProcessOutcome, report: RunReport) -> None:
        resource = outcome.resource
        if outcome.outcome == "NEW":
            result.new_resources += 1
        elif outcome.outcome == "UPDATED":
            result.updated_resources += 1
        elif outcome.outcome == "DUPLICATE":
            result.duplicates += 1
        elif outcome.outcome == "FAILED":
            result.failed += 1

        if resource is None:
            return
        if resource.access_mode == AccessMode.DOWNLOADED:
            result.downloaded += 1
        elif resource.access_mode == AccessMode.LINK_ONLY:
            result.link_only += 1

        if outcome.outcome in ("NEW", "UPDATED"):
            report.resources.append(resource)

    def _fail_source(
        self,
        result: SourceRunReport,
        source: SourceConfig,
        report: RunReport,
        error_code: str,
        message: str,
    ) -> SourceRunReport:
        result.error_code = error_code
        result.error_message = message
        logger.warning("[%s] %s", source.source_id, message)
        self.repo.log_error(
            run_id=report.run_id,
            source_id=source.source_id,
            error_code=error_code,
            message=message,
        )
        failures = self.repo.record_source_attempt(source.source_id, success=False, reason=message)
        if failures >= FAILURE_ALERT_THRESHOLD:
            logger.error(
                "[%s] 연속 %d회 실패 — 소스를 일시 비활성화하고 관리자 확인이 필요합니다.",
                source.source_id,
                failures,
            )
        return result

    # ==================================================================
    # 자료 1건 처리 (§6.1 4~15단계)
    # ==================================================================
    def _process_item(
        self, connector: SourceConnector, raw, report: RunReport, *, dry_run: bool
    ) -> ProcessOutcome:
        # 4) 메타데이터 정규화
        resource = connector.normalize(raw)
        if resource is None:
            return ProcessOutcome(outcome="SKIPPED")

        source = connector.config
        resource.source_id = source.source_id

        # 5) 접근정책·라이선스 검사
        self.license_validator.apply(resource, source_download_policy=source.download_policy.value)

        # 접근정책이 복잡한 소스(SSRN·RISS)는 전용 정책으로 재정리 (§4.2 B, §4.4 H)
        policy_connector = self._policy_connector_for(resource, connector)
        if policy_connector is not connector and hasattr(policy_connector, "adopt"):
            resource = policy_connector.adopt(resource)

        # DOI 기준 서지 보강 (Crossref 를 기준축으로 사용)
        if self._crossref_resolver and resource.doi and source.source_id != "crossref":
            resource = self._crossref_resolver.enrich(resource)

        # 6) DOI/공식 ID 기반 1차 중복 판별
        dedup = self.deduplicator.check_metadata(resource)
        if dedup.verdict == DedupVerdict.DUPLICATE and dedup.existing:
            # 같은 자료를 다른 출처에서 찾은 경우 URL 만 보존 (§11.2)
            self.deduplicator.merge_sources(resource, dedup.existing)
            self.repo.add_run_item(
                report.run_id,
                source.source_id,
                "DUPLICATE",
                resource_id=dedup.existing.resource_id,
                detail=f"matched_by={dedup.matched_by}",
            )
            return ProcessOutcome(resource=dedup.existing, outcome="DUPLICATE")

        if dedup.verdict == DedupVerdict.NEW_VERSION and dedup.existing:
            self.deduplicator.link_version(resource, dedup.existing)
            resource.status = ResourceStatus.UPDATED
        else:
            resource.status = ResourceStatus.NEW

        resource.first_seen_at = resource.first_seen_at or datetime.now()
        resource.last_seen_at = datetime.now()

        # 12-a) 1차 분류·점수 — 다운로드 대상 선별에 사용 (§6.3 3차 우선순위 필터)
        self.classifier.apply(resource)
        self.scorer.score(resource)

        extracted: ExtractedText | None = None

        if not dry_run:
            # 7~11) OA 탐색 → 정책검사 → 다운로드 → 해시 → 무결성 검사
            extracted = self._acquire_fulltext(resource, policy_connector, report)

            # 12-b) 원문을 확보했으면 본문을 반영해 재분류·재채점
            if extracted and not extracted.failed:
                self.classifier.apply(resource, extracted.text)
                self.scorer.score(resource)

            # 13) 주제별 최종 저장소로 이동
            self._store_if_downloaded(resource)

        # 15) 요약 생성
        if resource.relevance_score >= self.summarize_threshold:
            try:
                self.summarizer.apply(resource, extracted)
            except Exception as exc:
                logger.warning("요약 생성 실패 (%s): %s", resource.best_title()[:40], exc)
                self.repo.log_error(
                    run_id=report.run_id,
                    source_id=source.source_id,
                    resource_id=resource.resource_id,
                    error_code=ErrorCode.SUMMARY_FAILED.value,
                    message=str(exc),
                )

        if resource.access_mode == AccessMode.PENDING:
            resource.access_mode = AccessMode.LINK_ONLY

        # 14) DB 기록 — files 는 resources 를 참조하므로 자료를 먼저 저장합니다.
        if not dry_run:
            self.repo.save_resource(resource)
            if resource.access_mode == AccessMode.DOWNLOADED and resource.file_path:
                final_path = Path(resource.file_path)
                self.repo.register_file(
                    file_sha256=resource.file_sha256,
                    resource_id=resource.resource_id,
                    file_path=resource.file_path,
                    file_size=resource.file_size,
                    content_type="",
                    extension=final_path.suffix,
                )
                self.repo.add_run_item(
                    report.run_id,
                    source.source_id,
                    "DOWNLOADED",
                    resource_id=resource.resource_id,
                )
            if extracted and extracted.text:
                self.repo.index_fulltext(resource, extracted.text)
            self.repo.add_run_item(
                report.run_id,
                source.source_id,
                resource.status.value,
                resource_id=resource.resource_id,
                detail=f"score={resource.relevance_score} topic={resource.topic_primary}",
            )

        return ProcessOutcome(resource=resource, outcome=resource.status.value)

    # ==================================================================
    # 원문 확보 (§6.1 7~11단계)
    # ==================================================================
    def _acquire_fulltext(
        self, resource: Resource, connector: SourceConnector, report: RunReport
    ) -> ExtractedText | None:
        if not self.download_enabled:
            resource.access_mode = AccessMode.LINK_ONLY
            return None

        # 관련성이 낮은 자료는 원문을 받지 않고 링크만 보존합니다 (§6.3).
        if resource.relevance_score < self.download_threshold:
            resource.access_mode = AccessMode.LINK_ONLY
            return None

        # 7) 다운로드 후보 결정 — Connector 우선, 없으면 OA Resolver
        candidate = connector.resolve_download(resource)
        if candidate is None and self._oa_resolver:
            candidate = self._oa_resolver.resolve(resource)
        if candidate is None:
            resource.access_mode = AccessMode.LINK_ONLY
            return None

        # 정책 검사 (§7.1, §7.2)
        decision = connector.check_access_policy(candidate)
        if not decision.allowed:
            logger.info("[%s] 링크 보존: %s", resource.source_id, decision.reason)
            resource.access_mode = AccessMode.LINK_ONLY
            self.repo.log_error(
                run_id=report.run_id,
                source_id=resource.source_id,
                resource_id=resource.resource_id,
                error_code=decision.error_code or ErrorCode.POLICY_BLOCKED.value,
                message=decision.reason,
                url=candidate.url,
            )
            return None

        # 8) 후보 URL 검증 (1~2단계)
        client = self._client_for(connector.config)
        link_validator = LinkValidator(client)
        access = link_validator.validate_access(candidate.url)
        if not access.valid:
            logger.info("[%s] 링크 검증 실패: %s", resource.source_id, access.reason)
            resource.access_mode = AccessMode.LINK_ONLY
            resource.error_code = access.error_code
            resource.error_message = access.reason
            self.repo.log_error(
                run_id=report.run_id,
                source_id=resource.source_id,
                resource_id=resource.resource_id,
                error_code=access.error_code,
                message=access.reason,
                url=candidate.url,
            )
            return None

        body = str(access.details.get("body", ""))
        if body:
            match = link_validator.validate_match(
                resource, body, str(access.details.get("final_url", ""))
            )
            if not match.valid:
                logger.info("[%s] 자료 일치 확인 실패: %s", resource.source_id, match.reason)
                resource.access_mode = AccessMode.LINK_ONLY
                resource.error_code = match.error_code
                resource.error_message = match.reason
                return None
            # HTML 이 돌아왔다면 원문 파일이 아니므로 링크로 보존합니다.
            if candidate.kind == CandidateKind.LANDING_PAGE:
                resource.access_mode = AccessMode.LINK_ONLY
                return None

        # 9) 다운로드
        connector.attach_downloader(self.downloader)
        result = connector.download(candidate)
        if not result.success:
            logger.info("[%s] 다운로드 실패: %s", resource.source_id, result.error_message)
            resource.access_mode = AccessMode.LINK_ONLY
            resource.error_code = result.error_code
            resource.error_message = result.error_message
            self.repo.log_error(
                run_id=report.run_id,
                source_id=resource.source_id,
                resource_id=resource.resource_id,
                error_code=result.error_code,
                message=result.error_message,
                url=candidate.url,
            )
            return None

        # 11) 문서 형식·무결성 검사
        validation = self.file_validator.validate(
            result.staged_path, content_type=result.content_type
        )
        if not validation.valid:
            if validation.details.get("quarantine"):
                self.downloader.quarantine(result.staged_path, self.quarantine_dir)
                resource.status = ResourceStatus.QUARANTINED
            else:
                self.downloader.discard(result.staged_path)
            logger.info("[%s] 파일 검증 실패: %s", resource.source_id, validation.reason)
            resource.access_mode = AccessMode.LINK_ONLY
            resource.error_code = validation.error_code
            resource.error_message = validation.reason
            self.repo.log_error(
                run_id=report.run_id,
                source_id=resource.source_id,
                resource_id=resource.resource_id,
                error_code=validation.error_code,
                message=validation.reason,
                url=candidate.url,
            )
            return None

        # 10) 파일 해시 — 동일 binary 는 다시 저장하지 않습니다 (§11.2)
        resource.file_sha256 = result.file_sha256
        resource.file_size = result.file_size
        resource.download_url = candidate.url

        content_dup = self.deduplicator.check_content(resource)
        if content_dup.verdict == DedupVerdict.DUPLICATE and content_dup.existing:
            self.downloader.discard(result.staged_path)
            self.deduplicator.merge_sources(resource, content_dup.existing)
            resource.access_mode = AccessMode.LINK_ONLY
            resource.file_path = content_dup.existing.file_path
            resource.error_code = ErrorCode.DUPLICATE_FILE.value
            resource.error_message = (
                f"동일 파일이 이미 보관되어 있습니다 ({content_dup.matched_by})."
            )
            logger.info("[%s] 동일 파일 중복 — 재저장하지 않습니다.", resource.source_id)
            return None

        # 텍스트 추출 (§13)
        extracted = self.extractor.extract(result.staged_path)
        if extracted.failed:
            resource.text_extract_failed = True
            if extracted.needs_ocr:
                logger.info("[%s] 스캔본 추정 — OCR 후보로 표시합니다.", resource.source_id)
            self.repo.log_error(
                run_id=report.run_id,
                source_id=resource.source_id,
                resource_id=resource.resource_id,
                error_code=ErrorCode.TEXT_EXTRACTION_FAILED.value,
                message=extracted.reason,
            )
        else:
            resource.text_sha256 = text_sha256(extracted.text)
            text_dup = self.deduplicator.check_content(resource)
            if text_dup.verdict == DedupVerdict.DUPLICATE and text_dup.existing:
                self.downloader.discard(result.staged_path)
                self.deduplicator.merge_sources(resource, text_dup.existing)
                resource.access_mode = AccessMode.LINK_ONLY
                resource.file_path = text_dup.existing.file_path
                resource.error_code = ErrorCode.DUPLICATE_FILE.value
                resource.error_message = "동일 본문이 이미 보관되어 있습니다(text_sha256)."
                return None

        resource.downloaded_at = datetime.now()
        resource.access_mode = AccessMode.DOWNLOADED
        # staging 경로를 임시 보관 — _store_if_downloaded 가 최종 위치로 옮깁니다.
        resource.file_path = result.staged_path
        return extracted

    # ------------------------------------------------------------------
    def _store_if_downloaded(self, resource: Resource) -> None:
        """13) staging → 주제별 최종 저장소로 원자적 이동."""
        if resource.access_mode != AccessMode.DOWNLOADED or not resource.file_path:
            return
        staged = Path(resource.file_path)
        if not staged.exists():
            return

        final_path = self.library.store(
            staged, resource, downloaded_on=(resource.downloaded_at or datetime.now()).date()
        )
        resource.file_path = str(final_path)

    # ==================================================================
    # 산출물
    # ==================================================================
    def _persist_outputs(self, report: RunReport) -> None:
        """14) Manifest 및 CSV/Excel 갱신."""
        collected_on = report.started_at.date()
        if report.resources:
            self.manifest.write(report.resources, collected_on=collected_on, run_id=report.run_id)
        try:
            self.exporter.export(self.repo.all_resources(), today=collected_on)
        except Exception as exc:
            logger.warning("CSV/Excel 산출물 생성 실패: %s", exc)

    # ==================================================================
    # 준비 작업
    # ==================================================================
    def _resolve_window(
        self, run_type: RunType, since: date | None, until: date | None
    ) -> tuple[date, date]:
        """실행 유형에 따른 조회 기간을 결정합니다."""
        until = until or date.today()
        if since:
            return since, until

        if run_type == RunType.BACKFILL or not self.repo.has_any_run():
            start = self.app.get("run.backfill_start_date", "2026-01-01")
            return date.fromisoformat(str(start)), until

        if run_type == RunType.MONTHLY_RECONCILIATION:
            days = int(self.app.get("run.reconciliation_lookback_days", 45))
            return until - timedelta(days=days), until

        # 일일 증분 — 마지막 실행 이후 + look-back
        lookback = int(self.app.get("run.daily_lookback_days", 3))
        last_run = self.repo.last_successful_run()
        base = last_run.date() if last_run else until - timedelta(days=1)
        return min(base, until) - timedelta(days=lookback), until

    def _sources_for(
        self, run_type: RunType, only_sources: list[str] | None
    ) -> list[SourceConfig]:
        sources = self.settings.sources.enabled()
        if only_sources:
            wanted = set(only_sources)
            sources = [s for s in sources if s.source_id in wanted]
            missing = wanted - {s.source_id for s in sources}
            for source_id in sorted(missing):
                logger.warning("요청한 소스를 찾을 수 없거나 비활성화되어 있습니다: %s", source_id)

        if run_type == RunType.MONTHLY_RECONCILIATION:
            # 일일 수집에 실패했던 소스를 우선 재시도합니다 (§16.2).
            since = datetime.now() - timedelta(days=int(self.app.get("run.reconciliation_lookback_days", 45)))
            failed = set(self.repo.failed_sources_since(since))
            sources.sort(key=lambda s: (s.source_id not in failed, s.priority))
        return sources

    def _client_for(self, source: SourceConfig):
        if source.source_id not in self._clients:
            self._clients[source.source_id] = build_client(
                self.app, source, shared=self._shared_http
            )
        return self._clients[source.source_id]

    def _connector_for(self, source: SourceConfig) -> SourceConnector:
        if source.source_id not in self._connectors:
            ctx = ConnectorContext(
                app=self.app,
                client=self._client_for(source),  # type: ignore[arg-type]
                expander=self.expander,
                max_items=self.max_items,
            )
            self._connectors[source.source_id] = build_connector(source, ctx)
        return self._connectors[source.source_id]

    def _prepare_resolvers(self, sources: list[SourceConfig]) -> None:
        """OA Resolver 와 Crossref 기준축을 준비합니다."""
        registry = self.settings.sources

        def optional(source_id: str, expected_type: type):
            config = registry.get(source_id)
            if not config or not config.enabled:
                return None
            try:
                connector = self._connector_for(config)
            except ConnectorError as exc:
                logger.info("[%s] 보조 Connector 를 사용할 수 없습니다: %s", source_id, exc)
                return None
            return connector if isinstance(connector, expected_type) else None

        self._oa_resolver = OpenAccessResolver(
            unpaywall=optional("unpaywall", UnpaywallConnector),
            core=optional("core", CoreConnector),
            scienceon=optional("scienceon", ScienceOnConnector),
        )
        crossref = optional("crossref", CrossrefConnector)
        self._crossref_resolver = CrossrefResolver(crossref) if crossref else None

    def _policy_connector_for(
        self, resource: Resource, connector: SourceConnector
    ) -> SourceConnector:
        """SSRN·RISS 자료는 해당 소스의 접근정책을 적용합니다."""
        if is_ssrn_resource(resource):
            special = self._optional_connector("ssrn", SsrnConnector)
            if special:
                return special
        if is_riss_resource(resource):
            special = self._optional_connector("riss", RissConnector)
            if special:
                return special
        return connector

    def _optional_connector(self, source_id: str, expected_type: type) -> SourceConnector | None:
        config = self.settings.sources.get(source_id)
        if not config or not config.enabled:
            return None
        try:
            connector = self._connector_for(config)
        except ConnectorError:
            return None
        return connector if isinstance(connector, expected_type) else None

    def _warn_missing_required_terms(self) -> None:
        """§3.3 필수 키워드 누락을 자동 검사합니다 (§23.1)."""
        missing = self.settings.search_terms.missing_required()
        if missing:
            logger.warning(
                "검색어 사전에 필수 키워드가 누락되었습니다 (%d개): %s",
                len(missing),
                ", ".join(missing),
            )
        if self.expander.unresolved:
            logger.info(
                "영문 대응어가 없어 영문 소스 검색에서 제외된 용어: %s",
                ", ".join(sorted(set(self.expander.unresolved))),
            )

    # ------------------------------------------------------------------
    def close(self) -> None:
        saved = self._shared_http.stats.deduplicated_requests
        if saved:
            logger.info("동일 요청 재사용으로 아낀 호출: %d건", saved)
        # 메모는 실행 단위입니다. 다음 실행이 낡은 응답을 보지 않도록 비웁니다.
        self._shared_http.clear_memo()
        for client in self._clients.values():
            try:
                client.close()  # type: ignore[attr-defined]
            except Exception:
                pass
        self._clients.clear()

    def __enter__(self) -> Pipeline:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
