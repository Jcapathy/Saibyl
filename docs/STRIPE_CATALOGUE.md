# The product catalogue, for wiring payments

**Written 2026-08-20, for the Stripe conversation.** Everything here is read
out of the pricing code, not from memory — the figures are what the running
product actually charges today.

---

## The headline: Stripe needs far less than "multiple products" implies

There are seven things a founder can buy. **Only four of them are Stripe
objects.** The other three are credit deductions that never touch Stripe.

| What the founder buys | How it is charged | Needs a Stripe price? |
|---|---|---|
| Founder / Growth / Agency plan | Subscription | **Yes — 3 recurring prices** |
| A credit top-up | One-off, variable amount | **No Price ID** — variable amount, already live |
| Website check, USPTO clearance, page revision, answer pack, extra runs | Credits deducted from balance | **No** |

**Credits are the meter; Stripe is the till.** A founder buys credits (by
subscribing or topping up) and the product deducts them per artifact. That
means adding a new paid module — the family-office bank, the outbound
sequence — needs **no Stripe change at all**, which is the property worth
protecting in tomorrow's conversation.

So the ask is: **three recurring prices, plus the variable top-up that already
works.** Not seven products.

---

## What Stripe has today, and why it is wrong

`stripe_service.py` still carries the V1 catalogue:

| Key in code | Stripe price ID | What Stripe charges | What the product advertises |
|---|---|---|---|
| `starter` | `price_1TLd4V…` | **$149/mo** | Founder — **$99/mo** |
| `pro` | `price_1TLd5y…` | **$499/mo** | Growth — **$299/mo** |
| `enterprise` | `price_1TLd6n…` | **$1,499/mo** | Agency — **$999/mo** |

Three separate problems, all live:

1. **Wrong prices.** Stripe would charge $149/$499/$1,499 against a page
   advertising $99/$299/$999. New Products and Prices are needed — this is a
   real migration, not a rename.
2. **Wrong names.** The code maps `starter`/`pro`/`enterprise`; the product
   ships `founder`/`growth`/`agency`. Both vocabularies exist in one codebase.
3. **`PLAN_LIMITS` caps every V2 name at the starter tier** — 15 runs/month.
   An Agency customer paying $999 for 66 runs is cut off at 15 by
   `api/simulations.py`, with a bare 402. This is enforced today and is
   logged as P0-9 in the pre-launch register. **Fix this before anyone can
   subscribe**, or the first paying customer hits a wall a third of the way
   in.

---

## The plan grants, and what they buy

Credits are granted on subscription and spent per artifact.

| Plan | Price | Credit grant | Room cap | Runs it buys |
|---|---|---|---|---|
| Free | $0 | 1,500 | 25 people | **1** full evaluation |
| Founder | $99/mo | 19,800 | 100 people | 6 |
| Growth | $299/mo | 59,800 | 150 people | 19 |
| Agency | $999/mo | 199,800 | 250 people | 66 |

The free grant is sized deliberately: a capped run costs 1,273, so the grant
covers exactly one with 227 spare. **This is the loss leader and must not be
"optimised" upward or downward** — see `DECISIONS_LOG` 2026-08-17.

## Top-ups (live, no Stripe work needed)

Priced at an 85% margin — deliberately above the subscription rate, so that
subscribing is arithmetically the better deal and the page says so in words.

| Amount | Credits | What it buys |
|---|---|---|
| $10 | 1,500 | one capped run, or an answer pack |
| $20 | 3,000 | a website check + an answer pack |
| $50 | 7,500 | a comprehensive USPTO search + change |
| $100 | 15,000 | a working month |

Minimum $10, and a variable "other amount" field. No Price ID — Stripe takes
the amount at checkout.

## Per-artifact prices (credits, never Stripe)

| Artifact | Credits | ≈ at top-up rate | Margin |
|---|---:|---:|---|
| Idea evaluation | 0 | free | the loss leader |
| USPTO — quick | 0 | free | the teaser |
| **Answer pack (new)** | 1,500 | $10 | 80% |
| Website check | 1,750 | ~$12 | 80% |
| USPTO — standard | 2,000 | ~$13 | 80% |
| Page revision | 5,000 | ~$33 | 80% |
| USPTO — comprehensive | 6,000 | ~$40 | 80% |

All priced through one helper at an 80% target margin with a 70% floor, which
is the range the founder set. Adding a module means adding a COGS constant —
nothing else.

---

## Three things worth raising with Stripe

1. **Metered vs. prepaid credits.** Today credits are prepaid and deducted
   internally. Stripe's usage-based billing could meter artifacts directly,
   which would remove the credit abstraction — but it would also remove the
   thing that makes the free tier legible ("you have one run"). Worth asking
   what they recommend for a product where the unit of value is an artifact,
   not a seat or an API call. **Recommendation: keep credits.** They already
   work, they survive new modules without Stripe changes, and they are what
   the UI is built around.
2. **The margin question they will ask.** Internally 1 credit = $0.001 of
   COGS; at the top-up rate a founder pays ~$0.0067 per credit. Those are two
   different units doing two different jobs — cost accounting and retail — and
   the gap is intentional, but be ready to say so plainly, because it reads
   as an inconsistency if it surfaces cold.
3. **Failure and refunds.** Credits are charged when work starts and are not
   refunded if it fails. A free user whose only run dies loses the grant. The
   report step is now recoverable for free, but the underlying policy is
   unwritten. Worth deciding before launch, not after the first complaint —
   Stripe will ask about dispute exposure.

---

## Before anyone can pay, in order

1. **Create three Products and Prices** in Stripe: Founder $99, Growth $299,
   Agency $999, monthly.
2. **Point `PLAN_PRICE_MAP` at the new IDs** and rename the keys to
   `founder`/`growth`/`agency`.
3. **Fix `PLAN_LIMITS`** so paid tiers get their real run counts. Highest risk
   item here — it is enforced, and it silently caps the customers who pay most.
4. **Verify the webhook** writes the new plan names onto the org row, and that
   the grant lands.
5. **Set the statement descriptor to `SAIDO LABS LLC`** (standing decision).
6. **Test the full loop on a live card in test mode**: subscribe → grant lands
   → run something → credits deduct → cancel → access ends correctly.

Steps 1 and 5 are Stripe-side and are the meeting. Steps 2–4 are a morning's
work once the Price IDs exist, and I can do them the moment you have the IDs.
