# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# schema    — FamilyOffice, FirmPerson, InboundPath, Shortlist, MatchReason
# matching  — build_shortlist(context, firms) / partition_by_freshness(...)
# ─────────────────────────────────────────────────────────
"""Access to capital: the family-office recommendation bank.

The founder's decision, on record in `docs/CAPITAL_MODULE.md`, was a curated
recommendation bank matched to a founder's sector, stage and check size — not a
contact dump. This package is that bank and the matching that makes it useful.

**Read `services/gtm/privacy.py` before touching anything here.** It is not a
utility module; it is the boundary between Saibyl being a tool its customer
points at a market and Saibyl being a controller of personal data. This package
ships *inside* that boundary with no change to the gate, which is also the
version that works better: family offices are the most privacy-guarding
investor class there is, and a phone number for one of their principals is a
cold call to someone who guards their privacy for a living. A named person with
a role, an employer and a piece they published is a warm path.

Three rules carry the whole design, and each is enforced in a type or in the
migration rather than by convention:

1. **No personal email, phone or postal address, ever.** `schema.FirmPerson`
   has exactly the fields `privacy.ALLOWED_CONTACT_FIELDS` permits and is
   validated by `privacy.rejects_as_personal_data` itself, so adding a seventh
   field breaks every construction. Free text — a thesis, a firm name — goes
   through the same scan. A firm's *own* published inbound route is firm
   contact information and is allowed, narrowly: see `schema.InboundPath`.

2. **No record without `source_url`**, the rule `gtm/schema.Candidate` already
   states: a lead a founder cannot trace back is a lead they cannot act on.

3. **A record past `stale_after` is withheld, never shown as current.** Encoded
   in `matching.partition_by_freshness` and again in `schema.Shortlist`, whose
   validator refuses to hold a stale record at all. Every commercial investor
   list is partly wrong the day it ships; hiding the date is how a list
   launders decay into confidence.

**The matching is the product, not the list.** Anyone can buy a list. Saibyl
knows things about the founder no list vendor does — the measured objections,
who the buyers actually are, whether the page lands — so every match states its
reason quoting both sides' actual language, and the strongest signal is the
objection bridge: if buyers' top objection is regulatory risk, a firm whose
published thesis names regulated markets is a materially better match than a
generic AI investor, and we can say why in the founder's own evidence.

**Refusals count.** A founder at idea stage is told which firms state they do
not invest pre-revenue, rather than handed a padded list. The product already
refuses to name a winner when intervals overlap; this is the same discipline
pointed at investors.

Web-scraping ingestion is deliberately absent. Sourcing follows `gtm/discovery`
— search, then read what the search returns — and there is no scraper in this
package for the same reason there is none in that one.
"""
