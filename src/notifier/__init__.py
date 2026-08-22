"""알림 채널 (PRD v2.1 §15)."""

from .email_notifier import EmailNotifier, NotificationError, Notifier, build_notifier
from .templates import render_email, render_text_fallback

__all__ = [
    "EmailNotifier",
    "NotificationError",
    "Notifier",
    "build_notifier",
    "render_email",
    "render_text_fallback",
]
