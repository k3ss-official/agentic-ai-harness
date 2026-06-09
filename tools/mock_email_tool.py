"""Mock email sender — external action, REQUIRES approval."""
from __future__ import annotations
import logging
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

_sent_emails = []


def send_email(
    to: str,
    subject: str,
    body: str,
    cc: Optional[List[str]] = None,
) -> dict:
    """
    Send an email. In this mock implementation, the email is logged
    but not actually sent. In production this would call an email API.
    """
    if not to or "@" not in to:
        raise ValueError(f"Invalid recipient address: {to}")

    email_record = {
        "to": to,
        "subject": subject,
        "body": body[:1000],
        "cc": cc or [],
        "sent_at": datetime.utcnow().isoformat(),
        "status": "sent_mock",
    }
    _sent_emails.append(email_record)
    logger.info("MOCK EMAIL SENT: to=%s subject='%s'", to, subject)
    return {
        "status": "ok",
        "message": f"Email queued for delivery to {to}",
        "record": email_record,
    }


def get_sent_emails() -> list:
    return list(_sent_emails)
