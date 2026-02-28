"""
Dispatch layer — channel-specific message delivery.

send_via_resend  — real email delivery through the Resend SDK.
send_via_meta    — WhatsApp stub (Meta Business API not yet integrated).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import resend

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resend configuration – loaded once at import time
# ---------------------------------------------------------------------------
resend.api_key = os.getenv("RESEND_API_KEY", "")

_FROM_ADDRESS = "UROG Automation <onboarding@resend.dev>"


# ---------------------------------------------------------------------------
# Email — Resend
# ---------------------------------------------------------------------------
def send_via_resend(email: str, content: str, subject: str = "UROG Update") -> bool:
    """Send an email via the Resend API.

    Returns True on success, False on failure (never raises).
    """
    try:
        params: resend.Emails.SendParams = {
            "from": _FROM_ADDRESS,
            "to": [email],
            "subject": subject,
            "html": content,
        }
        result = resend.Emails.send(params)
        logger.info("Resend OK → id=%s to=%s", result.get("id"), email)
        return True
    except Exception:
        logger.exception("Resend FAILED → to=%s", email)
        return False


# ---------------------------------------------------------------------------
# WhatsApp — Meta Business API (stub)
# ---------------------------------------------------------------------------
def send_via_meta(
    phone: str, content: str, template_name: Optional[str] = None
) -> bool:
    """Send a WhatsApp message via the Meta Business API.

    Stub: prints the action and returns True.
    """
    print(f"[DISPATCH:WHATSAPP] To: {phone} | Template: {template_name or 'freeform'}")
    print(f"  Body preview: {content[:120]}...")
    return True
