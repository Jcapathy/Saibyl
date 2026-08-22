"""The clearance module never scanned for personal data. Nothing did.

`grep` for `reject_personal_data` or `rejects_as_personal_data` across
`services/clearance/*.py` and `api/clearance.py` returned nothing, while
`GET /api/clearance/{run_id}` served its stored USPTO artifact verbatim. USPTO
file wrappers and TSDR owner records carry inventor and attorney names,
correspondence addresses, telephone numbers and email addresses, and a live
QUICK run produced a 7,583-character report through that path.

**What it cost.** Every clearance run wrote whatever the register handed back
into `clearance_runs.artifact`, flattened it into `clearance_findings`, and
served it again on request. Saibyl became the keeper of a contact database
assembled from people who never signed up for anything — the position
`gtm/privacy.py` opens by calling "the boundary between two legal positions",
entered by accident and with no opt-in behind it.

**And the fix that would have been worse than the defect.** The rest of this
codebase refuses a record carrying personal data whole. Applied here that would
delete the findings: an inventor's name paired with a patent number is not a
leaked contact, it is the answer the founder paid for, and a clearance report
that silently drops the one reference that blocks you is worse than no report.
So the rule is redact-not-reject, and the two halves are tested with equal
weight below — the second block is the important one, exactly as it is in
`test_founder_messages.py`.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api import clearance as clearance_api
from app.core.auth import get_current_org
from app.services.clearance.artifact import build_artifact
from app.services.clearance.privacy import (
    REDACTION_MARKER,
    redact_personal_contact_detail,
    scrub_clearance_artifact,
    scrub_clearance_report,
)
from app.services.clearance.tracks import (
    ArtEntry,
    ClearanceResult,
    PendingApp,
    QueryRecord,
    TrademarkConflict,
    TrademarkFindings,
    WatchItem,
)
from app.services.gtm.schema import contains_personal_contact_detail

ORG = "11111111-1111-1111-1111-111111111111"
RUN = "44444444-4444-4444-4444-444444444444"


# ---------------------------------------------------------------------------
# The contact channels, which Saibyl must not become the keeper of
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", [
    # A TSDR owner block with the attorney's address appended.
    "ACME CORPORATION, 1600 AMPHITHEATRE PARKWAY, MOUNTAIN VIEW, CA 94043",
    # ODP correspondence data, in the shapes USPTO actually returns.
    "Jane Q. Doe, jdoe@examplefirm.com",
    "Correspondence: 100 Main Street, Suite 400",
    "P.O. Box 1450, Alexandria, VA 22313",
    "Tel: (650) 555-1234",
    "phone 650-555-1234",
    "+1 650-555-1234",
    "Fax: 6505551234",
])
def test_a_contact_channel_never_survives_the_pass(raw):
    redacted = redact_personal_contact_detail(raw)
    assert REDACTION_MARKER in redacted, f"nothing was removed from {raw!r}"
    assert "@" not in redacted
    assert "555" not in redacted


def test_an_email_this_module_leaves_is_one_the_gtm_gate_would_have_caught():
    """The anti-drift check between two modules that scan for the same thing.

    `capital/schema` reuses `gtm/privacy`'s function rather than re-implementing
    its regexes, because "two copies drift, and the copy that drifts is the one
    nobody re-reads". This module cannot reuse it — that one returns a reason to
    reject, this one has to substitute — so the invariant is asserted instead:
    text this module has cleaned must no longer read as personal to the gate
    that guards every stored contact in the product.
    """
    raw = "Represented by John Smith, jsmith@patentfirm.example"
    assert contains_personal_contact_detail(raw), "the fixture proves nothing"
    assert not contains_personal_contact_detail(redact_personal_contact_detail(raw))


def test_the_pass_is_idempotent():
    """The serving boundary re-scrubs rows the write boundary already cleaned.

    If a second pass changed anything, every read of a clean run would corrupt
    it a little further.
    """
    once = redact_personal_contact_detail("A. Inventor, ainv@example.com, 100 Main St")
    assert redact_personal_contact_detail(once) == once


# ---------------------------------------------------------------------------
# The register, which is the finding and must survive intact
# ---------------------------------------------------------------------------
#
# This is the half that stops the fix being worse than the defect. A false
# positive here does not cost a dropped record the way it does in the GTM
# module — it silently rewrites a prior-art finding a founder is about to take
# to counsel.

@pytest.mark.parametrize("register", [
    # Names of record. Public by statute, and the substance of the finding.
    "Jane Q. Doe",
    "Acme Corporation",
    "INTERNATIONAL BUSINESS MACHINES CORPORATION",
    'firstApplicantName:"Jane Q. Doe"',
    # Identifiers and dates — the fields a naive phone matcher eats.
    "US 11,222,333 B2",
    "US-11222333-B2",
    "18/123456",
    "97123456",
    "filed 2021-03-01, earliest priority 2019-11-30",
    "2026-08-15T10:05:00+00:00",
    "cpcClassificationBag:G06F16/2455 AND synthetic",
    # Units of measure that share their abbreviation with a street suffix. This
    # product searches every discipline, so all three of these are real claims.
    "Claim 1 requires a beverage container of 12 fl oz capacity.",
    "A gemstone of 1 ct set in a 3 mm bezel.",
    "The transform applies 2 ln x to each sample.",
    # Ordinary report prose.
    "Of 12 records screened, 5 were read at claim level.",
    "Dr. Smith reviewed claim 3.",
])
def test_the_register_passes_through_untouched(register):
    assert redact_personal_contact_detail(register) == register


def test_an_inventors_name_is_kept_and_their_address_is_not():
    """The whole decision, in one string.

    Blanket-stripping personal data would take the name with the address and
    leave a finding nobody can act on: a founder who cannot see who filed
    cannot tell a competitor from a troll from their own former employer.
    """
    redacted = redact_personal_contact_detail(
        "Jane Q. Doe, 100 Main Street, Palo Alto, CA 94301"
    )
    assert "Jane Q. Doe" in redacted
    assert "Main Street" not in redacted
    assert "94301" not in redacted


# ---------------------------------------------------------------------------
# The write boundary: nothing personal is ever stored
# ---------------------------------------------------------------------------

def _result_with_contact_detail() -> ClearanceResult:
    """A USPTO result with an attorney block leaking into every free-text field."""
    return ClearanceResult(
        tracks_run=["trademark", "patents", "pending_landscape"],
        trademark=TrademarkFindings(
            status="CONFLICTS_FOUND",
            marks_checked=["SAIBYL"],
            conflicts=[TrademarkConflict(
                mark="SAIBYL",
                serial_or_reg="97123456",
                owner="Acme Corp, 1600 Amphitheatre Parkway, Mountain View, CA 94043",
                live=True,
                classes=["009"],
                goods_services="Software. Enquiries to hello@acme.example.",
            )],
            official_search_link="https://tmsearch.uspto.gov/search/search-information",
        ),
        overall_risk="YELLOW",
        records_screened=42,
        closest_art=[ArtEntry(
            number="US-11222333-B2",
            title="Synthetic audience engine",
            assignee="Jane Q. Doe, jdoe@examplefirm.com",
            filed="2021-03-01",
            priority="2019-11-30",
            status="Patented Case",
            claim_requirements="Claim 1 requires a sensor array. Tel: (650) 555-1234.",
            differences="No sensor array. Correspondence: P.O. Box 1450.",
            risk="YELLOW",
        )],
        whitespace_signals=[],
        crowded_areas=[],
        notable_pending=[PendingApp(
            app="18/123456",
            title="Audience prediction method",
            assignee="Example Inc, 100 Main Street, Suite 400",
            status="Pending",
        )],
        blind_spot_date="2025-02-15",
        queries_run=[QueryRecord(
            track="patents", query='firstApplicantName:"Jane Q. Doe"', hits=7
        )],
        watch_list=[WatchItem(
            target="Jane Q. Doe, jdoe@examplefirm.com",
            reason="a repeat filer in this art",
        )],
    )


def test_the_artifact_is_stored_clean_not_cleaned_on_the_way_out():
    """The write boundary, which is what makes erasure answerable.

    The worker writes `build_artifact`'s return straight into `clearance_runs`,
    flattens it into `clearance_findings`, and composes the report from it. All
    three are covered by scrubbing here, and "we never held it" is a different
    and much better answer to a subject-access request than "we deleted it".
    """
    artifact = build_artifact(
        "a synthetic market engine", "STANDARD", "2026-08-15", [], _result_with_contact_detail()
    )

    blob = repr(artifact)
    assert "@examplefirm.com" not in blob
    assert "hello@acme.example" not in blob
    assert "555-1234" not in blob
    assert "Amphitheatre" not in blob
    assert "Main Street" not in blob
    assert "P.O. Box" not in blob
    assert "94043" not in blob

    # And the finding is still a finding.
    art = artifact["patents"]["closest_art"][0]
    assert art["number"] == "US-11222333-B2"
    assert art["filed"] == "2021-03-01"
    assert art["priority"] == "2019-11-30"
    assert "Jane Q. Doe" in art["assignee"], "the name of record was destroyed"
    assert "Acme Corp" in artifact["trademark"]["conflicts"][0]["owner"]
    assert artifact["queries_run"][0]["query"] == 'firstApplicantName:"Jane Q. Doe"'
    assert artifact["patents"]["records_screened"] == 42


def test_the_founders_own_submission_is_left_alone():
    """`item` is the caller's own text, stored verbatim in its own column too.

    Rewriting a founder's words in the copy we hand back — while keeping the
    original in `clearance_runs.item` next to it — would be theatre, not
    protection. The exclusion is deliberate and is stated in the module.
    """
    artifact = build_artifact(
        "my product, reachable at me@myco.example", "QUICK", "2026-08-15", [],
        ClearanceResult(blind_spot_date="2025-02-15"),
    )
    assert artifact["item"] == "my product, reachable at me@myco.example"


# ---------------------------------------------------------------------------
# The serving boundary: the rows written before any of this existed
# ---------------------------------------------------------------------------

class _Admin:
    def __init__(self, row: dict):
        self._row = row

    def table(self, _name: str):
        return self

    def select(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def limit(self, _n):
        return self

    def execute(self):
        return SimpleNamespace(data=[dict(self._row)], count=1)


@pytest.fixture
def authed_client(app):
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_current_org] = lambda: {"org_id": ORG, "role": "owner"}
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_org, None)


LEGACY_ROW = {
    "id": RUN,
    "organization_id": ORG,
    "status": "complete",
    "artifact": {
        "item": "Saibyl",
        "patents": {
            "overall_risk": "YELLOW",
            "closest_art": [{
                "number": "US-11222333-B2",
                "title": "Synthetic audience engine",
                "assignee": "Jane Q. Doe, jdoe@examplefirm.com",
                "filed": "2021-03-01",
                "status": "Patented Case",
                "claim_requirements": "Tel: (650) 555-1234",
                "differences": "",
                "risk": "YELLOW",
            }],
        },
    },
    "report_markdown": (
        "# Clearance report\n\nJane Q. Doe, jdoe@examplefirm.com, "
        "100 Main Street, Palo Alto, CA 94301. Filed 2021-03-01.\n"
    ),
}


def test_a_run_stored_before_the_scrub_existed_is_still_served_clean(
    authed_client, monkeypatch
):
    """The reason the write boundary alone is not enough.

    Completed runs are served from storage, not rebuilt, so every row written
    before this module landed would keep serving what the register handed back
    forever. That includes the live QUICK run whose 7,583-character report is
    what surfaced this finding.
    """
    monkeypatch.setattr(
        clearance_api, "get_supabase_admin", lambda: _Admin(LEGACY_ROW)
    )

    response = authed_client.get(f"/api/clearance/{RUN}")

    assert response.status_code == 200, response.text
    body = response.text
    assert "jdoe@examplefirm.com" not in body
    assert "555-1234" not in body
    assert "Main Street" not in body
    assert "94301" not in body

    run = response.json()
    art = run["artifact"]["patents"]["closest_art"][0]
    assert "Jane Q. Doe" in art["assignee"], "the finding was destroyed, not cleaned"
    assert art["filed"] == "2021-03-01"
    assert "Jane Q. Doe" in run["report_markdown"]
    assert "2021-03-01" in run["report_markdown"]


def test_the_stored_row_itself_is_not_rewritten(authed_client, monkeypatch):
    """Serving scrubs a copy. A read must never mutate the record it read.

    The row is evidence: a disputed finding is reconstructed from it, and a
    read path that edits storage makes the audit trail depend on who looked.
    """
    stored = {**LEGACY_ROW}
    monkeypatch.setattr(clearance_api, "get_supabase_admin", lambda: _Admin(stored))

    authed_client.get(f"/api/clearance/{RUN}")

    assert "jdoe@examplefirm.com" in repr(stored["artifact"])


def test_scrubbing_survives_a_row_with_a_missing_or_odd_section():
    """A privacy pass that raises on an old shape is a 500 on a paid run."""
    assert scrub_clearance_artifact({}) == {}
    assert scrub_clearance_artifact({"patents": None}) == {"patents": None}
    assert scrub_clearance_artifact({"queries_run": "not a list"}) == {
        "queries_run": "not a list"
    }
    assert scrub_clearance_report("") == ""
    assert scrub_clearance_report(None) == ""
