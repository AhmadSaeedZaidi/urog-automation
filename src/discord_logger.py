"""
Discord Audit Logger — posts structured messages to a Discord webhook.

Usage:
    from src.discord_logger import send_audit_message
    send_audit_message("Batch Complete", "Processed 12 inbox items.")

If ``DISCORD_WEBHOOK_URL`` is not set the call silently returns.
"""

from __future__ import annotations

import logging
import os

import requests

logger = logging.getLogger(__name__)

_WEBHOOK_URL: str | None = os.getenv("DISCORD_WEBHOOK_URL")


def send_audit_message(title: str, description: str) -> None:
    """Fire-and-forget a Discord embed to the configured webhook."""
    if not _WEBHOOK_URL:
        return

    payload = {
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": 3447003,  # blue
            }
        ]
    }

    try:
        requests.post(_WEBHOOK_URL, json=payload, timeout=5)
    except Exception:
        logger.exception("Discord webhook delivery failed")
