"""
Dispatch layer — channel-specific message delivery stubs.

Each function accepts the message content and a destination, attempts delivery,
and returns True (success) or False (failure).  These are stub implementations
that will be replaced with real Resend / Meta SDK calls later.
"""

from typing import Optional


def send_via_resend(email: str, content: str, subject: str = "UROG Update") -> bool:
    """
    Send an email via the Resend API.

    Stub: prints the action and returns True.
    """
    print(f"[DISPATCH:EMAIL] To: {email} | Subject: {subject}")
    print(f"  Body preview: {content[:120]}...")
    return True


def send_via_meta(
    phone: str, content: str, template_name: Optional[str] = None
) -> bool:
    """
    Send a WhatsApp message via the Meta Business API.

    Stub: prints the action and returns True.
    """
    print(f"[DISPATCH:WHATSAPP] To: {phone} | Template: {template_name or 'freeform'}")
    print(f"  Body preview: {content[:120]}...")
    return True
