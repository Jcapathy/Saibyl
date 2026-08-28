# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# send_email(to, subject, html, text=None) -> SendResult
# SendResult, email_is_configured() -> bool
# ─────────────────────────────────────────────────────────
"""Sending mail, through Resend's REST API.

**The first thing in this product that talks to a person outside the app**, so
the failure rules matter more than the feature:

- **A missing key is not a crash.** `email_is_configured()` is false, `send_email`
  returns a result saying so, and the caller decides. A scheduled job that dies
  because an environment variable is unset takes the whole run of follow-ups
  down for everyone, and does it silently at 3am.
- **A failed send is reported, never swallowed.** The result carries the reason,
  and `followup.py` writes it onto the row. An email nobody knows failed is the
  same defect as a payment nobody knows was uncredited.
- **No SDK.** Resend's send endpoint is one POST, and `httpx` is already a
  dependency. A dependency added for one HTTP call is a dependency to keep
  patched forever.

`from_email` must be on a domain verified in Resend. Until it is, Resend accepts
only `onboarding@resend.dev` and only to the account owner's own address — which
looks exactly like working software right up to the first real founder.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()

_ENDPOINT = "https://api.resend.com/emails"
_TIMEOUT = 15.0


@dataclass(frozen=True)
class SendResult:
    ok: bool
    #: Resend's id for the message, when it took it.
    message_id: str | None = None
    #: A sentence for a log or a database row. Never a stack trace.
    error: str | None = None


def email_is_configured() -> bool:
    """Both halves, because either alone sends nothing."""
    return bool(settings.resend_api_key and settings.email_from)


async def send_email(
    *, to: str, subject: str, html: str, text: str | None = None
) -> SendResult:
    """Send one message. Never raises."""
    if not email_is_configured():
        # Deliberately info, not error: on a machine with no key this is the
        # expected state, and an error-level line every cron tick trains
        # everybody to ignore the log.
        logger.info(
            "email_not_configured",
            detail="RESEND_API_KEY or EMAIL_FROM is unset; nothing was sent",
        )
        return SendResult(ok=False, error="email is not configured")

    payload: dict[str, object] = {
        "from": settings.email_from,
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if text:
        payload["text"] = text
    if settings.email_reply_to:
        payload["reply_to"] = settings.email_reply_to

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(
                _ENDPOINT,
                json=payload,
                headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            )
    except Exception as exc:
        logger.warning("email_send_failed", to=to, error=str(exc)[:200])
        return SendResult(ok=False, error=f"could not reach the mail service: {exc}"[:300])

    if response.status_code >= 400:
        # Resend's own message is the useful one — "domain is not verified" is
        # the failure this will actually hit, and paraphrasing it would hide it.
        detail = response.text[:300]
        logger.warning("email_send_rejected", to=to, status=response.status_code, detail=detail)
        return SendResult(ok=False, error=f"{response.status_code}: {detail}")

    try:
        message_id = response.json().get("id")
    except Exception:
        message_id = None
    logger.info("email_sent", to=to, message_id=message_id)
    return SendResult(ok=True, message_id=message_id)
