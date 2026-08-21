# Access to capital — the family-office recommendation bank

**Design, 2026-08-20. Founder's decision on record: route (b).** A curated
recommendation bank of family offices, matched to the founder's sector, stage
and check size — *not* a contact dump. His words: a recommendation bank "would
actually be better than a contact dump to serve my clients."

He is right, and the reason is worth stating because it also happens to be the
reason this is buildable at all.

## The finding that makes this easy

The instinct is that this module needs personal contact data — names, emails,
phone numbers — and that collecting it is the hard part. It is the hard part,
and **we do not need it.**

`services/gtm/privacy.py` already drew this line, deliberately, and opens by
saying so: *"The gate below looks like a feature flag. It is not one. It is the
boundary between two legal positions."* Its `ALLOWED_CONTACT_FIELDS` permits:

    full_name · role_title · employer · public_profile_url · source_url · retrieved_at

and forbids personal email, phone and postal address. It also blocks
LinkedIn, ZoomInfo, Apollo and RocketReach from contact-bearing searches
because their terms prohibit exactly this use, and it states there is no
scraper in the package and that adding one "would need its own argument."

**The permitted set is precisely what makes a recommendation useful.** "Ana
Ruiz, Principal at Verrill Family Office, who wrote publicly about backing
pre-seed AI infrastructure last quarter — here is the piece" is a warm path. A
phone number is not; it is a cold call to someone who guards their privacy for
a living, and family offices are the most privacy-guarding investor class
there is. So the module ships **inside the existing legal position, with no
change to the gate** — which is also the version that works better.

## What a record is

Firm-level, modelled on `gtm/schema.Candidate`, whose rule already fits: no
valid state without `source_url`, because a lead a founder cannot trace back
is a lead they cannot act on.

| Field | Notes |
|---|---|
| `firm_name`, `domain`, `firm_type` | single-family / multi-family / foundation |
| `thesis` | in the firm's own published words, quoted not paraphrased |
| `sectors`, `stages` | from the firm's own stated focus |
| `check_size_low`, `check_size_high` | only when the firm publishes a range; `None` beats a guess |
| `geography` | where they state they invest |
| `notable_investments` | evidenced, from the firm's own page or a filing |
| `inbound_path` | **the firm's own published route** — submission form, `info@`-style firm address, or "warm intro only" stated honestly |
| `people` | `full_name`, `role_title`, `employer`, `public_profile_url` — the permitted set, nothing more |
| `source_url`, `retrieved_at` | required, per the existing rule |
| `verified_at`, `stale_after` | theses change; see freshness below |

`rejects_as_personal_data` already scans stored strings for smuggled emails
and phones. It is reused unchanged, so a personal detail cannot enter this
table even by accident in a `thesis` blob.

## The matching is the product, not the list

Anyone can buy a list. The defensible part is that Saibyl knows things about
the founder no list vendor does — the measured objections, who the buyers
actually are, the IP position, whether the page lands. So the match is:

1. **Sector and stage** — the ordinary filter, and the table stakes.
2. **Thesis against the founder's own material** — the firm's published words
   compared to the product's, with the overlap quoted both ways. The same
   reference-anchored idea as the website check's "the look" critic: findings
   carry both sides' actual language.
3. **The objection bridge** — the strongest signal and unique to this product.
   If buyers' top objection is regulatory risk, a firm whose thesis names
   regulated markets is a materially better match than a generic AI investor,
   and we can say *why* in the founder's own evidence.
4. **Refusals count.** A founder at idea stage with no traction gets told which
   firms state they do not invest pre-revenue, rather than a padded list. The
   product already refuses to name a winner when intervals overlap; this is the
   same discipline pointed at investors.

## Freshness, which is where investor databases die

Every commercial investor list is partly wrong the day it ships. Two rules:

- **Every record carries `retrieved_at` and renders it.** A founder sees how
  old the claim is and can weigh it. Hiding the date is how a list launders
  decay into confidence.
- **A record past `stale_after` is re-verified or withheld, never shown
  stale.** Withheld is honest; stale is a wrong pitch sent to a real firm with
  our name on the recommendation.

## Sourcing — built, not licensed (settled 2026-08-21)

**Founder's decision: we build the discovery pipeline ourselves.** Not Fintrx,
not any licensed feed. The matching is the moat; buying coverage would rent
the part that is not the product, and licensed data carries redistribution
terms that collected data does not.

`services/capital/discovery.py`. Same shape as `gtm/discovery` — search, then
read what the search returns — and the same two-half split: `propose_firms`
makes the model call, `verify_firms` is pure and decides what survives, so
"a field must be evidenced" is a test rather than a live-run observation.

**Two stages, because the open web forced it.** The first live pass returned
zero firms, three times over, and each cause was invisible behind the same
empty list:

1. The turn was truncated, not empty — the model spent a 4,000-token budget in
   extended thinking and emitted no tool call. Raised to 16,000, and
   `stop_reason` is now logged: a truncated turn must not be able to
   impersonate an exhausted web.
2. The obvious queries returned journalism. `"family office" "investment
   thesis" healthcare` gave CNBC, a trade magazine and a competitor's
   listicle. Journalists write about family offices in the third person; a
   firm writes *"we are a single family office"*. Every template is now first
   person.
3. Given a listicle, the model quoted a competitor's **paraphrase** as the
   firm's thesis. A paraphrase of a paraphrase cannot be quoted back to a
   founder as "here is what they say they fund", which is the whole mechanism.

So: **stage one harvests names from anything that names firms** — directories
are excellent at names — **and stage two builds the record only from that
firm's own site**, matched by domain label so a directory at
`firm.example.directory.com` cannot pass as `firm.example`. A firm that
publishes no thesis anywhere does not enter the bank.

Measured on the first working pass: 15 names harvested, 9 firms verified. The
gap is the honest price of the rule, and `names_found` is reported beside the
firm count so it stays visible.

**Where an unstated posture lands.** All nine verified firms defaulted to
`no_inbound`, because none of them published an inbound position the search
surfaced. That is the conservative real answer, not a gap: guessing that a
family office accepts submissions causes a real approach to a firm that never
invited one. `inbound_unevidenced_defaulted` counts it every time.

**Running it:** `python scripts/curate_family_offices.py --sectors healthcare
fintech`. Service role only, charges nobody, takes no founder input; the model
spend still lands in the cost ledger. Re-running grows the bank rather than
doubling it — stored firms are passed back as `known_domains`.

## Pricing

Credit model, at the 80% target margin through `_clearance_price_credits`, like
every other paid artifact. COGS is search plus extraction plus one matching
pass — the same cost shape as `gtm` discovery, so its pricing module is the
precedent rather than a new scheme. Priced **per matched shortlist**, not per
seat and not per record: a founder pays for the answer to "who would fund
this", which is one question with one answer, and per-record pricing would
reward padding the list.

## What this is not

- Not a CRM, and not an outreach sender. We recommend and evidence; the
  founder makes contact through the firm's own stated route. The moment we
  send on their behalf, deliverability, consent and reputation become ours.
- Not a guarantee of access. Family offices are private by design and many
  take no inbound at all. Where that is the firm's stated position, that is
  what the record says.
