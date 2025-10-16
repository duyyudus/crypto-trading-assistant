"""Telegram alerting utility."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests

from core.utils import Settings, logger

TELEGRAM_API_URL = "https://api.telegram.org"


@dataclass(slots=True)
class TelegramConfig:
    token: str
    chat_id: str


class TelegramBot:
    """Minimal Telegram Bot API wrapper for sending alerts."""

    def __init__(self, config: TelegramConfig) -> None:
        self.config = config
        self.session = requests.Session()

    @classmethod
    def from_settings(cls, settings: Settings) -> "TelegramBot":
        if not settings.telegram_token or not settings.telegram_chat_id:
            raise ValueError("Telegram credentials missing in settings")
        return cls(TelegramConfig(settings.telegram_token, settings.telegram_chat_id))

    def send_message(self, text: str, parse_mode: Optional[str] = None) -> None:
        url = f"{TELEGRAM_API_URL}/bot{self.config.token}/sendMessage"
        payload = {"chat_id": self.config.chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        logger.info("Sending Telegram alert: %s", text)
        response = self.session.post(url, json=payload, timeout=10)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            logger.error("Failed to send Telegram message: %s", exc)
            raise
