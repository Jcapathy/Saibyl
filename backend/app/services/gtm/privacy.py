# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# ContactGate, contact_discovery_gate(org_id) -> ContactGate
# set_contact_discovery(org_id, enabled, *, actor_user_id=None) -> ContactGate
# CONTACT_BLOCKED_DOMAINS, ALLOWED_CONTACT_FIELDS
# rejects_as_personal_data(payload) -> str | None
# ─────────────────────────────────────────────────────────
"""Why contact discovery is off by default, and why that is not a setting to
"simplify" later.

**Read this before changing anything in this file.** The gate below looks like
a feature flag. It is not one. It is the boundary between two legal positions,
and removing it moves Saibyl from one to the other silently.

*The position with the gate off.* Discovery finds companies. A company name, a
domain, a headcount band and an industry are not personal data under GDPR or
CCPA. Saibyl is a tool its customer points at a market.

*The position with the gate on.* Discovery finds named people. A name paired
with a job title and an employer **is** personal data, and Saibyl — not its
customer — is the party that decided to go and collect it, stores it, and
serves it. That makes Saibyl a controller for those records, with the
obligations that attach: a lawful basis, a retention position, and the ability
to answer a subject-access or erasure request from a person who never signed up
for anything.

Those obligations are answerable only if three things are true in the data, and
all three are enforced here or in the migration rather than by convention:

1. **The gate is off unless an org turned it on.** `organizations.
   gtm_contact_discovery_enabled` is `NOT NULL DEFAULT FALSE`, so there is no
   "unset" state that a reader could resolve either way. A failed lookup raises
   rather than returning `False` — a database error and a deliberate opt-out
   must not share a value, because the version where they do is the one that
   quietly re-enables collection the day the column is renamed.

2. **Company discovery is complete with the gate off.** This is the part that
   decays first. If contacts-off is a degraded mode, someone eventually turns it
   on for everyone to make the product look better. So the default path returns
   full company candidates with archetype, evidence and source, and the gate
   adds a `contacts` array to them. Nothing about the company list changes.

3. **Every stored personal record carries `source_url` and `retrieved_at`,
   and deletion deletes rows.** `Contact` has no valid state without both
   fields. `store.delete_candidate` and `store.purge_organization` issue
   `DELETE`, not an `UPDATE … SET deleted_at`. A soft delete answers an erasure
   request with "we hid it", which is not what was asked.

**Only public professional information.** Name, role, employer, public profile
URL. No personal email, no phone, no postal address, and nothing inferred —
seniority guessed from a photo, location guessed from a name, anything about
health, politics, ethnicity, religion or union membership. `ALLOWED_CONTACT_FIELDS`
is the whole list and `rejects_as_personal_data` scans every stored string for
the two patterns that most often smuggle the rest in.

**Provider terms are respected by using the provider.** Discovery reads search
results. It does not crawl, it does not fetch pages Saibyl chose, and it does
not authenticate to anything. `CONTACT_BLOCKED_DOMAINS` goes to the search tool
for contact-bearing queries because the sites listed there prohibit exactly this
use in their terms, and "the search engine indexed it" is not a defence for
compiling it into a product. There is no scraper in this package and adding one
would need its own argument, not this file's.
"""
from __future__ import annotations

import structlog
from pydantic import BaseModel

from app.core.database import get_supabase_admin
from app.services.gtm.schema import contains_personal_contact_detail

log = structlog.get_logger()

# The org-level switch. Migration 027.
ORG_SETTING_COLUMN = "gtm_contact_discovery_enabled"

# Everything a stored contact may hold. Adding to this list is a privacy
# decision, not a schema decision.
ALLOWED_CONTACT_FIELDS: tuple[str, ...] = (
    "full_name",
    "role_title",
    "employer",
    "public_profile_url",
    "source_url",
    "retrieved_at",
)

# Domains excluded from contact-bearing searches. These prohibit the automated
# collection and reuse of member profile data in their terms of service, and
# being reachable through a search index does not change that. Passed to the
# search tool's `blocked_domains`, so the provider never returns them for these
# queries — there is nothing to filter afterwards and nothing to be tempted by.
CONTACT_BLOCKED_DOMAINS: tuple[str, ...] = (
    "linkedin.com",
    "www.linkedin.com",
    "facebook.com",
    "instagram.com",
    "rocketreach.co",
    "zoominfo.com",
    "apollo.io",
    "lusha.com",
    "signalhire.com",
)


class ContactGate(BaseModel):
    """Whether an org has opted into storing named contacts.

    `source` says how the answer was reached. It is always `"column"` today —
    the column is NOT NULL — and exists so that a future reader adding a
    fallback has to name it, rather than adding a silent default.
    """

    enabled: bool
    source: str = "column"


class ContactGateUnavailableError(RuntimeError):
    """The gate could not be read.

    Raised rather than defaulting. Discovery refuses to run contact-bearing
    queries it cannot prove were authorised; company discovery is unaffected
    and continues.
    """


def contact_discovery_gate(org_id: str) -> ContactGate:
    """Read the org's contact-discovery setting.

    Raises `ContactGateUnavailableError` if the org is missing or the lookup fails.
    """
    admin = get_supabase_admin()
    try:
        result = (
            admin.table("organizations")
            .select(f"id,{ORG_SETTING_COLUMN}")
            .eq("id", str(org_id))
            .execute()
        )
    except Exception as exc:
        log.exception("gtm_contact_gate_lookup_failed", org_id=str(org_id))
        raise ContactGateUnavailableError(
            "could not read contact-discovery setting; contact discovery is "
            "not permitted while its authorisation is unknown"
        ) from exc

    rows = result.data or []
    if not rows:
        raise ContactGateUnavailableError(f"organization {org_id} not found")

    value = rows[0].get(ORG_SETTING_COLUMN)
    if value is None:
        # The column is NOT NULL, so None means the migration has not been
        # applied or the select was altered. Either way the authorisation is
        # unknown, and unknown is not off — it is unanswerable.
        raise ContactGateUnavailableError(
            f"organizations.{ORG_SETTING_COLUMN} is absent; migration 027 has "
            f"not been applied"
        )

    gate = ContactGate(enabled=bool(value))
    log.info("gtm_contact_gate_read", org_id=str(org_id), enabled=gate.enabled)
    return gate


def set_contact_discovery(
    org_id: str,
    enabled: bool,
    *,
    actor_user_id: str | None = None,
) -> ContactGate:
    """Turn contact discovery on or off for an org.

    Turning it **off** does not delete what was already collected — that is
    `store.purge_organization`, a separate and deliberate act. Conflating the
    two would mean a founder toggling a setting to stop future collection also
    destroys records they may still need, and a founder who wanted them gone
    would have no way to say so without also changing the setting.
    """
    admin = get_supabase_admin()
    updated = (
        admin.table("organizations")
        .update({ORG_SETTING_COLUMN: bool(enabled)})
        .eq("id", str(org_id))
        .execute()
    )
    if not updated.data:
        raise ContactGateUnavailableError(f"organization {org_id} not found")

    log.info(
        "gtm_contact_gate_set",
        org_id=str(org_id),
        enabled=bool(enabled),
        actor_user_id=actor_user_id,
    )
    return ContactGate(enabled=bool(enabled))


def rejects_as_personal_data(payload: dict[str, object]) -> str | None:
    """Reason to drop this contact, or None.

    Scans every string the record would store. A contact whose role title has a
    phone number appended, or whose employer field carries an email address, is
    dropped whole rather than trimmed — a record that needed editing to be
    lawful is a record whose source was the wrong kind of page.
    """
    for field, value in payload.items():
        if field not in ALLOWED_CONTACT_FIELDS:
            return f"field '{field}' is not public professional information"
        if isinstance(value, str) and contains_personal_contact_detail(value):
            return f"field '{field}' contains personal contact detail"
    return None
