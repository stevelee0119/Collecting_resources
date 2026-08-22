"""스케줄러 (PRD v2.1 §16).

- `DAILY_INCREMENTAL`      : 매일 1회
- `MONTHLY_RECONCILIATION` : 매월 1회 최근 30~45일 재검증
- timezone 은 `Asia/Seoul` 을 명시적으로 사용합니다.

APScheduler 를 우선 사용하며(§16.4), 설치되어 있지 않으면 간단한 루프로 대체합니다.
운영 환경에서는 Windows Task Scheduler 등록(`scripts/setup_scheduler.bat`)을 권장합니다.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..config_loader import AppConfig
from ..models import RunType

logger = logging.getLogger(__name__)


class SchedulerRunner:
    """일일/월간 작업을 예약 실행합니다."""

    def __init__(self, app: AppConfig, job: Callable[[RunType], None]):
        self.app = app
        self.job = job
        self.timezone = ZoneInfo(str(app.get("scheduler.timezone", "Asia/Seoul")))

    # ------------------------------------------------------------------
    def start(self) -> None:
        """스케줄러를 시작하고 블로킹합니다."""
        try:
            self._start_apscheduler()
        except ImportError:
            logger.warning(
                "APScheduler 가 설치되어 있지 않아 단순 루프 스케줄러를 사용합니다. "
                "운영 환경에서는 pip install apscheduler 또는 OS 스케줄러 등록을 권장합니다."
            )
            self._start_simple_loop()

    # ------------------------------------------------------------------
    def _start_apscheduler(self) -> None:
        from apscheduler.schedulers.blocking import BlockingScheduler  # noqa: PLC0415
        from apscheduler.triggers.cron import CronTrigger  # noqa: PLC0415

        scheduler = BlockingScheduler(timezone=self.timezone)

        daily = self.app.get("scheduler.daily_incremental", {}) or {}
        if daily.get("enabled", True):
            scheduler.add_job(
                self._run_daily,
                CronTrigger(
                    hour=int(daily.get("hour", 7)),
                    minute=int(daily.get("minute", 30)),
                    timezone=self.timezone,
                ),
                id="daily_incremental",
                name="일일 증분 수집",
                # 실행을 놓쳤을 때 1시간 이내면 따라잡습니다.
                misfire_grace_time=3600,
                coalesce=True,
                max_instances=1,
            )
            logger.info(
                "일일 증분 수집 예약: 매일 %02d:%02d (%s)",
                int(daily.get("hour", 7)),
                int(daily.get("minute", 30)),
                self.timezone,
            )

        monthly = self.app.get("scheduler.monthly_reconciliation", {}) or {}
        if monthly.get("enabled", True):
            scheduler.add_job(
                self._run_monthly,
                CronTrigger(
                    day=int(monthly.get("day", 1)),
                    hour=int(monthly.get("hour", 5)),
                    minute=int(monthly.get("minute", 0)),
                    timezone=self.timezone,
                ),
                id="monthly_reconciliation",
                name="월간 정합성 점검",
                misfire_grace_time=7200,
                coalesce=True,
                max_instances=1,
            )
            logger.info(
                "월간 정합성 점검 예약: 매월 %d일 %02d:%02d (%s)",
                int(monthly.get("day", 1)),
                int(monthly.get("hour", 5)),
                int(monthly.get("minute", 0)),
                self.timezone,
            )

        logger.info("스케줄러 대기 중입니다. 종료하려면 Ctrl+C 를 누르세요.")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("스케줄러를 종료합니다.")

    # ------------------------------------------------------------------
    def _start_simple_loop(self) -> None:
        """APScheduler 가 없을 때의 대체 구현 (1분 간격 확인)."""
        daily = self.app.get("scheduler.daily_incremental", {}) or {}
        monthly = self.app.get("scheduler.monthly_reconciliation", {}) or {}
        last_daily: str | None = None
        last_monthly: str | None = None

        logger.info("단순 루프 스케줄러 대기 중입니다. 종료하려면 Ctrl+C 를 누르세요.")
        try:
            while True:
                now = datetime.now(self.timezone)
                today_key = now.strftime("%Y-%m-%d")
                month_key = now.strftime("%Y-%m")

                if (
                    daily.get("enabled", True)
                    and last_daily != today_key
                    and now.hour == int(daily.get("hour", 7))
                    and now.minute >= int(daily.get("minute", 30))
                ):
                    last_daily = today_key
                    self._run_daily()

                if (
                    monthly.get("enabled", True)
                    and last_monthly != month_key
                    and now.day == int(monthly.get("day", 1))
                    and now.hour == int(monthly.get("hour", 5))
                    and now.minute >= int(monthly.get("minute", 0))
                ):
                    last_monthly = month_key
                    self._run_monthly()

                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("스케줄러를 종료합니다.")

    # ------------------------------------------------------------------
    def _run_daily(self) -> None:
        self._safe_run(RunType.DAILY_INCREMENTAL)

    def _run_monthly(self) -> None:
        self._safe_run(RunType.MONTHLY_RECONCILIATION)

    def _safe_run(self, run_type: RunType) -> None:
        """작업 실패가 스케줄러를 중단시키지 않도록 감쌉니다 (§16.3)."""
        started = datetime.now(self.timezone)
        logger.info("[Scheduler] %s 실행 (%s)", run_type.value, started.isoformat())
        try:
            self.job(run_type)
        except Exception as exc:
            logger.exception("[Scheduler] %s 실행 중 오류: %s", run_type.value, exc)
        else:
            elapsed = datetime.now(self.timezone) - started
            logger.info("[Scheduler] %s 완료 (소요 %s)", run_type.value, _fmt(elapsed))


def _fmt(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}시간 {minutes}분 {seconds}초"
    if minutes:
        return f"{minutes}분 {seconds}초"
    return f"{seconds}초"
