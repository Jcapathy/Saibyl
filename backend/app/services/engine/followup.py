# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# STAGES, StageSpec, DueRun
# runs_due(now) -> list[DueRun]
# send_followups(now, *, dry_run=False) -> FollowupReport
# ─────────────────────────────────────────────────────────
"""Asking founders, two and four weeks on, whether the room was right.

`outcomes.py` can measure prediction accuracy the moment there are answers.
This is what produces the answers, and without it that table stays empty and
the credibility critical on saibyl.com stays open forever.

**Two asks, not one and not five.** Two weeks is early enough that the run is
still fresh and late enough that something has happened. Four weeks catches the
launch that slipped, which is most of them. A third would be nagging, and the
cost of nagging is not a lower reply rate — it is a founder who stops reading
anything we send, including the one that matters.

**The idempotency rule, which is the whole design.** This runs from a daily
cron, so "which runs are due?" is asked every day and the same run is due for
many days running. `followup_sends` has a unique constraint on
`(simulation_id, stage)`, and the row is **claimed before the send is
attempted**. A crash between sending and recording therefore costs one missing
email, which somebody can fix by hand; the alternative ordering costs a founder
the same email every morning, which no one can fix at all.

**What the email must not do.** It must not tell the founder what we predicted
before asking what happened — that is leading the witness, and the answers are
the evidence base for a public accuracy claim. It names the product and the run,
and asks an open question.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog

from app.core.config import settings
from app.core.database import get_supabase_admin
from app.services.email.sender import email_is_configured, send_email

logger = structlog.get_logger()


@dataclass(frozen=True)
class StageSpec:
    key: str
    after_days: int
    #: How wide a window counts as due. A cron that misses a day (a deploy, an
    #: outage) must still catch the run the next morning rather than skipping
    #: that founder silently for ever.
    window_days: int
    subject: str


STAGES: tuple[StageSpec, ...] = (
    StageSpec(
        key="two_week",
        after_days=14,
        window_days=7,
        subject="Did any of that actually come up?",
    ),
    StageSpec(
        key="four_week",
        after_days=28,
        window_days=14,
        subject="One more question about your Saibyl run",
    ),
)


@dataclass(frozen=True)
class DueRun:
    simulation_id: str
    organization_id: str
    stage: StageSpec
    email: str
    product_name: str | None = None


@dataclass
class FollowupReport:
    considered: int = 0
    sent: int = 0
    skipped_already_asked: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def sentence(self) -> str:
        return (
            f"{self.considered} due, {self.sent} sent, "
            f"{self.skipped_already_asked} already asked, {self.failed} failed"
        )


def _owner_email(admin, organization_id: str) -> tuple[str | None, str | None]:
    """The owner's address, and their name if we have one.

    The owner rather than every member: this is a question about what happened
    in the market, and asking four people the same question produces one answer
    and three annoyances.
    """
    try:
        members = (
            admin.table("organization_members")
            .select("user_id, role")
            .eq("organization_id", organization_id)
            .eq("role", "owner")
            .limit(1)
            .execute()
            .data
        ) or []
        if not members:
            return None, None
        user = admin.auth.admin.get_user_by_id(members[0]["user_id"]).user
        return getattr(user, "email", None), None
    except Exception:
        logger.warning("followup_owner_lookup_failed", organization_id=organization_id)
        return None, None


def runs_due(now: datetime | None = None) -> list[DueRun]:
    """Completed runs whose two- or four-week ask is due and unsent."""
    now = now or datetime.now(UTC)
    admin = get_supabase_admin()
    due: list[DueRun] = []

    for stage in STAGES:
        opens = now - timedelta(days=stage.after_days + stage.window_days)
        closes = now - timedelta(days=stage.after_days)
        try:
            runs = (
                admin.table("simulations")
                .select("id, organization_id, name, status, completed_at")
                .eq("status", "complete")
                .gte("completed_at", opens.isoformat())
                .lte("completed_at", closes.isoformat())
                .limit(500)
                .execute()
                .data
            ) or []
        except Exception:
            logger.warning("followup_due_query_failed", stage=stage.key, exc_info=True)
            continue

        for run in runs:
            email, _name = _owner_email(admin, run["organization_id"])
            if not email:
                continue
            due.append(
                DueRun(
                    simulation_id=str(run["id"]),
                    organization_id=str(run["organization_id"]),
                    stage=stage,
                    email=email,
                    product_name=run.get("name"),
                )
            )
    return due


def _body(run: DueRun) -> tuple[str, str]:
    """The ask. Open question first, no reminder of what we predicted."""
    product = run.product_name or "your product"
    link = f"{settings.frontend_url}/app/simulations/{run.simulation_id}/report"
    text = (
        f"You ran {product} through a Saibyl room a few weeks ago.\n\n"
        "One question, and a real answer helps more than a kind one: since then, "
        "what have actual buyers pushed back on?\n\n"
        "Just reply to this email. A sentence is plenty, and \"nothing yet\" is "
        "a useful answer.\n\n"
        "We ask because the honest test of a synthetic room is whether the "
        "objections it raised turned out to be the ones you met. We would rather "
        "measure that than claim it.\n\n"
        f"Your run: {link}\n"
    )
    html = (
        f"<p>You ran <strong>{product}</strong> through a Saibyl room a few weeks ago.</p>"
        "<p>One question, and a real answer helps more than a kind one: "
        "since then, <strong>what have actual buyers pushed back on?</strong></p>"
        "<p>Just reply to this email. A sentence is plenty, and &ldquo;nothing "
        "yet&rdquo; is a useful answer.</p>"
        "<p>We ask because the honest test of a synthetic room is whether the "
        "objections it raised turned out to be the ones you met. We would rather "
        "measure that than claim it.</p>"
        f'<p><a href="{link}">Your run</a></p>'
    )
    return text, html


async def send_followups(
    now: datetime | None = None, *, dry_run: bool = False
) -> FollowupReport:
    """Ask everybody who is due, once.

    Safe to run repeatedly: the claim row is what makes a second run a no-op.
    """
    report = FollowupReport()
    if not email_is_configured() and not dry_run:
        report.errors.append(
            "email is not configured (RESEND_API_KEY / EMAIL_FROM); nothing sent"
        )
        logger.warning("followup_skipped_unconfigured")
        return report

    admin = get_supabase_admin()
    for run in runs_due(now):
        report.considered += 1
        if dry_run:
            continue

        # Claim first. The unique constraint on (simulation_id, stage) is what
        # turns a daily cron into a single email; a claim that fails means
        # somebody already asked, which is a skip and not an error.
        try:
            admin.table("followup_sends").insert({
                "organization_id": run.organization_id,
                "simulation_id": run.simulation_id,
                "stage": run.stage.key,
                "sent_to": run.email,
            }).execute()
        except Exception:
            report.skipped_already_asked += 1
            continue

        text, html = _body(run)
        result = await send_email(
            to=run.email, subject=run.stage.subject, html=html, text=text
        )
        if result.ok:
            report.sent += 1
            admin.table("followup_sends").update({
                "sent_at": datetime.now(UTC).isoformat(),
            }).eq("simulation_id", run.simulation_id).eq(
                "stage", run.stage.key
            ).execute()
        else:
            # The row stays, holding the reason. It is not retried automatically:
            # a send that failed for a bad address will fail identically tomorrow,
            # and a loop that keeps trying turns one bad row into a daily alarm.
            report.failed += 1
            report.errors.append(f"{run.simulation_id}: {result.error}")
            admin.table("followup_sends").update({
                "error": (result.error or "unknown")[:300],
            }).eq("simulation_id", run.simulation_id).eq(
                "stage", run.stage.key
            ).execute()

    logger.info("followup_run_complete", detail=report.sentence)
    return report
