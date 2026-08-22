"""이메일 알림 (PRD v2.1 §15).

전송 방식:
- `gmail_api` : Gmail API + OAuth 2.0 (권장, §15.4)
- `smtp`      : SMTP + 앱 비밀번호

원문 파일은 첨부하지 않고 공식 링크를 제공합니다 (§18.5).
목록용 Excel 은 옵션으로 첨부할 수 있습니다.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import smtplib
from abc import ABC, abstractmethod
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from ..config_loader import AppConfig, get_secret
from ..models import PriorityLevel, Resource, RunReport
from .templates import render_email, render_text_fallback

logger = logging.getLogger(__name__)


class NotificationError(RuntimeError):
    """알림 발송 실패."""


class Notifier(ABC):
    """알림 채널 어댑터."""

    channel = "base"

    @abstractmethod
    def send(self, report: RunReport, resources: list[Resource]) -> bool:
        """브리핑을 발송합니다."""


class EmailNotifier(Notifier):
    """카드형 HTML 일일 브리핑을 이메일로 발송합니다."""

    channel = "email"

    def __init__(self, app: AppConfig):
        self.app = app
        self.transport = str(app.get("notification.email.transport", "smtp")).lower()
        self.smtp_host = str(app.get("notification.email.smtp_host", "smtp.gmail.com"))
        self.smtp_port = int(app.get("notification.email.smtp_port", 587))
        self.use_starttls = bool(app.get("notification.email.use_starttls", True))
        self.subject_prefix = str(
            app.get("notification.email.subject_prefix", "[DL-RCIS 일일 리서치 브리핑]")
        )
        self.card_priorities = {
            PriorityLevel(p) for p in app.get("notification.card_priorities", ["P1", "P2"])
        }
        self.send_when_empty = bool(app.get("notification.send_when_empty", False))
        self.attach_excel = bool(app.get("notification.attach_excel", True))

        # 주소는 설정 또는 환경변수 어느 쪽에서든 읽습니다.
        self.sender = (
            str(app.get("notification.email.sender_email", "")).strip()
            or get_secret("DLRCIS_SENDER_EMAIL")
            or ""
        )
        self.receiver = (
            str(app.get("notification.email.receiver_email", "")).strip()
            or get_secret("DLRCIS_RECEIVER_EMAIL")
            or ""
        )

    # ------------------------------------------------------------------
    def build_message(
        self, report: RunReport, resources: list[Resource], *, collected_on: date | None = None
    ) -> EmailMessage:
        collected_on = collected_on or date.today()
        cards = [r for r in resources if r.priority_level in self.card_priorities]
        listed = [r for r in resources if r.priority_level not in self.card_priorities]

        html_body = render_email(
            report, card_resources=cards, listed_resources=listed, collected_on=collected_on
        )
        text_body = render_text_fallback(report, cards)

        message = EmailMessage()
        message["Subject"] = (
            f"{self.subject_prefix} {collected_on.isoformat()} "
            f"신규 {report.new_count}건 (P1·P2 {len(cards)}건)"
        )
        message["From"] = self.sender
        message["To"] = self.receiver
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")

        if self.attach_excel:
            self._attach_excel(message)
        return message

    # ------------------------------------------------------------------
    def send(
        self, report: RunReport, resources: list[Resource], *, collected_on: date | None = None
    ) -> bool:
        if not bool(self.app.get("notification.enabled", True)):
            logger.info("알림이 설정에서 비활성화되어 있습니다.")
            return False

        if not resources and not self.send_when_empty and not report.failed_sources:
            logger.info("신규 자료가 없어 브리핑을 발송하지 않습니다(무발송 모드).")
            return False

        if not self.sender or not self.receiver:
            raise NotificationError(
                "발신자 또는 수신자 이메일이 설정되지 않았습니다. "
                "config.yaml 의 notification.email 또는 .env 의 "
                "DLRCIS_SENDER_EMAIL / DLRCIS_RECEIVER_EMAIL 를 확인하세요."
            )

        message = self.build_message(report, resources, collected_on=collected_on)

        if self.transport == "gmail_api":
            return self._send_gmail_api(message)
        return self._send_smtp(message)

    # ------------------------------------------------------------------
    def _send_smtp(self, message: EmailMessage) -> bool:
        password = get_secret("DLRCIS_SMTP_PASSWORD")
        if not password:
            raise NotificationError(
                "SMTP 비밀번호(DLRCIS_SMTP_PASSWORD)가 .env 에 설정되지 않았습니다. "
                "docs/API_발급_연동_가이드.md 의 Gmail 앱 비밀번호 절차를 참고하세요."
            )
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                if self.use_starttls:
                    server.starttls()
                server.login(self.sender, password)
                server.send_message(message)
        except smtplib.SMTPAuthenticationError as exc:
            raise NotificationError(f"SMTP 인증 실패: {exc}") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise NotificationError(f"SMTP 발송 실패: {exc}") from exc

        logger.info("일일 브리핑을 발송했습니다 (SMTP → %s)", self.receiver)
        return True

    def _send_gmail_api(self, message: EmailMessage) -> bool:
        """Gmail API + OAuth 2.0 발송 (§15.4 권장 방식)."""
        try:
            from google.auth.transport.requests import Request  # noqa: PLC0415
            from google.oauth2.credentials import Credentials  # noqa: PLC0415
            from googleapiclient.discovery import build  # noqa: PLC0415
        except ImportError as exc:
            raise NotificationError(
                "Gmail API 라이브러리가 없습니다. "
                "pip install google-api-python-client google-auth-oauthlib 후 사용하거나 "
                "transport 를 smtp 로 변경하세요."
            ) from exc

        token_path = get_secret("GMAIL_TOKEN_FILE")
        if not token_path or not Path(token_path).exists():
            raise NotificationError(
                "Gmail OAuth 토큰 파일이 없습니다. GMAIL_TOKEN_FILE 을 .env 에 설정하고 "
                "docs/API_발급_연동_가이드.md 의 Gmail API 절차로 토큰을 발급하세요."
            )

        try:
            credentials = Credentials.from_authorized_user_file(
                token_path, ["https://www.googleapis.com/auth/gmail.send"]
            )
            if credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            service = build("gmail", "v1", credentials=credentials)
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            service.users().messages().send(userId="me", body={"raw": raw}).execute()
        except Exception as exc:
            raise NotificationError(f"Gmail API 발송 실패: {exc}") from exc

        logger.info("일일 브리핑을 발송했습니다 (Gmail API → %s)", self.receiver)
        return True

    # ------------------------------------------------------------------
    def _attach_excel(self, message: EmailMessage) -> None:
        excel_path = self.app.path("storage.excel_path", "data/metadata/list_download_resources.xlsx")
        if not excel_path.exists():
            return
        # 원문이 아니라 목록 파일만 첨부합니다 (§18.5).
        mime_type, _ = mimetypes.guess_type(str(excel_path))
        maintype, _, subtype = (mime_type or "application/octet-stream").partition("/")
        message.add_attachment(
            excel_path.read_bytes(),
            maintype=maintype,
            subtype=subtype or "octet-stream",
            filename=excel_path.name,
        )


def build_notifier(app: AppConfig) -> Notifier | None:
    """설정에 따라 알림 채널을 만듭니다."""
    if not bool(app.get("notification.enabled", True)):
        return None
    channel = str(app.get("notification.channel", "email")).lower()
    if channel == "email":
        return EmailNotifier(app)
    logger.warning(
        "지원하지 않는 알림 채널입니다: %s. src/notifier/ 에 어댑터를 추가하세요.", channel
    )
    return None
