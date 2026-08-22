# Saibyl as an MCP server — design

**Saido Labs LLC** · Written 2026-08-22 · Status: **proposal, not approved**

Protocol facts here were fetched from `modelcontextprotocol.io` on 2026-08-22
against spec revision **2026-07-28**, not recalled. Where a claim rests on
client behaviour rather than the spec, it says so. Where I could not verify
something, §11 lists it rather than guessing.

---

## 1. The argument, and the moment it belongs to

A founder using Saibyl is, by `PRD_V3.md` §1, one of "the millions of people who
can now build products with Claude Code, Codex, and similar tools." Saibyl
already produces two artifacts built expressly for those tools:

- `compose_fix_prompts` (`services/website/revise.py:533`) returns
  `[{title, scope, prompt}]` — a paste-ready instruction block per failing
  dimension, plus one block embedding the whole DESIGN.md brief, fenced.
  Deterministic, no model call. PRD_V3 §4d calls this "a first-class report
  section, not an appendix."
- The design DNA itself — the refero-shaped DESIGN.md of §4b² — which rides
  inside that last prompt block.

Today the delivery mechanism for both is `navigator.clipboard.writeText`
(`frontend/src/components/website/SiteRevision.tsx:93`). The founder reads the
finding in a browser tab, clicks copy, alt-tabs, pastes. An MCP server deletes
the alt-tab. That is the whole of the near-term value and it is worth being
plain about how small a change it is: **the first useful version of this is a
rename of a copy button.**

`SEO_AEO.md` is the closest thing the repo has to a prior claim on this
channel, and it is worth quoting exactly rather than overstating. It says
*"agentic browser modes run real Chromium — but those are user-driven sessions,
not crawlers, and cannot be optimized for like one."* It names the surface and
then correctly declines to treat it as an SEO problem. That is the right read,
and it points at the actual mechanism: **you do not get onto the agentic surface
by being crawlable. You get onto it by being installed.** An MCP server is the
install.

### 1a. The strongest argument against, stated before the design

**Saibyl has not passed its own quality gate, and the last general-purpose API
this codebase shipped was deleted as residue eighteen days ago.**

Commit `ef11ba7` ("Give the dashboard the job it was missing, and delete the V1
API", 2026-08-05) removed `score.py`, `api_keys.py`, `verify_api_key`, the
`X-API-Key` header and its CORS allowance, with the reason: *"Confirmed V1
residue."* The `api_keys` table was kept only because dropping it is
destructive. Proposing an org-scoped API credential is proposing to reverse
that deletion, and the failure mode is identical: a credential surface, a
support obligation, and a revocation path built for a consumer that never
arrives.

Meanwhile `PRD_V3.md` §9 puts Phase D — *"the founder reads all five reports and
would pay for each — then, and only then, the first email"* — ahead of
everything in Phase E. An MCP server is Phase-E-shaped work.

The counter is real but weaker than it sounds. The consumer is not hypothetical
in the way `/api/score` was: PRD §1 asserts the audience already lives inside
Claude Code. But *"our users use Claude Code"* is not *"our users will install
our MCP server"*, and nothing in this repo measures the second. So:

**Recommendation: build the four-tool slice in §9, ship it unpromoted — keys
issued by hand to a handful of founders — and do not let it onto the critical
path for Phase D. Go further only if those founders use it.** The slice is
small enough that it does not compete with Phase D for engineering time. The
*surface* it opens does compete for attention, permanently, and that is the
cost being accepted.

If that measurement comes back empty, the correct action is to revoke the keys
and delete the server, which is cheap precisely because it is a separate
process reading a public API and nothing else depends on it.

---

## 2. The architectural decision everything else follows from

**The MCP server is a client of Saibyl's HTTP API. It is not a second reader of
Saibyl's database.**

This is not a style preference. Org isolation in this codebase is not enforced
by Postgres. `core/database.py` gives the backend `get_supabase_admin()` — the
service-role client, which **bypasses RLS** — and every route re-establishes
isolation by hand with an explicit `.eq("organization_id", auth["org_id"])`
filter, or a `simulations!inner(organization_id)` join for the report routes.
The RLS policies exist and are real defence-in-depth for anything talking to
Postgres as a user, but nothing in the backend talks to Postgres as a user.

So org isolation is, today, a per-route convention held by about a hundred
individually-written filters. It has failed at least three times on record:

- `ws.py::_assert_owns_simulation` exists because both SSE endpoints depended on
  `get_current_org` and then never used `auth` — a cross-tenant leak, now
  guarded and logged as `sse_cross_org_denied`.
- `personas.py::get_pack_details` records that `get_pack(pack_id, ...)` was
  called without the org, "resolving a tenant-owned slug across every
  organization and serving another org's audience."
- `SECURITY_AUDIT_2026-03-30.md` §408 records the same class on report export.

A convention with that history must not be re-implemented. An MCP server that
issues its own queries would be a fourth place to get it wrong, in a process
where a machine — not a human clicking links — enumerates identifiers. Going
through the HTTP routes means the MCP server inherits every filter that exists
and can never drift from them, at the cost of one extra network hop that is
noise next to the model call the founder's agent is already making.

One consequence worth naming: this also means **the MCP server cannot expose
anything the web app cannot already show that founder.** That is a feature. It
makes the blast radius of the whole project exactly zero new data.

---

## 3. What is exposed — tools versus resources

The spec draws the line by *who decides*:

> Tools in MCP are designed to be **model-controlled** … the language model can
> discover and invoke tools automatically.
> Resources in MCP are designed to be **application-driven**, with host
> applications determining how to incorporate context.

Those are two different moments in a founder's day, and Saibyl has both:

- *The founder knows which thing.* "Attach my last website check to this
  conversation" — an `@`-mention picker. **Resource.**
- *The agent is mid-task and needs a fact.* It just rewrote the hero section and
  should know that four of twenty-five buyers said the pricing was the problem.
  **Tool.**

**Recommendation: expose both over one address space, with tools as the
guaranteed path.** Every resource has a tool that returns the same body, because
resource support across Claude Code, Cursor and Codex is uneven (§11). Tools
additionally return `resource_link` content blocks pointing at the resource URI,
which is exactly what that content type is for, so a client with resource
support gets addressability for free and one with none loses nothing.

### 3a. Resources

Custom scheme `saibyl://`, RFC 3986-conformant. Resource templates
(RFC 6570) for the addressable bodies; `resources/list` returns the org's most
recent **completed** artifacts, bounded at 50, newest first.

| URI template | Backed by | Why a resource |
|---|---|---|
| `saibyl://run/{simulation_id}/objections` | `GET /api/simulations/{id}/objections` | The founder picks a run by name; the body is stable once measured |
| `saibyl://run/{simulation_id}/report` | `GET /api/reports/by-simulation/{id}` | A finished document, immutable in practice |
| `saibyl://website-check/{snapshot_id}/critique` | `GET /api/website/check/{snapshot_id}` | "A snapshot is immutable" — PRD §4a states it |
| `saibyl://website-revision/{revision_id}/fix-prompts` | `GET /api/website/revision/{revision_id}` | The artifact the founder means when they say "the fixes" |
| `saibyl://answer-pack/{pack_id}` | `GET /api/answer-pack/{pack_id}` | Finished, immutable |
| `saibyl://org/state` | `GET /api/products` | The rail. One small document; good ambient context |

`mimeType` is `application/json` for all of them except the fix prompts, which
are served `text/markdown` — the point of that artifact is to be read as prose
by a coding agent, and wrapping it in JSON adds an unwrapping step for no gain.

**Not subscribing in phase 1.** `resources/updated` on a completing website
check is genuinely the right notification, but a stdio server's lifetime is the
editor session and the check outlives it. Polling a status tool is honest and
costs nothing; a subscription that silently stops working when the editor
restarts is worse than no subscription. Revisit with the remote transport.

### 3b. Tools

All eleven are reads. Annotations, per the `ToolAnnotations` interface in
`schema/2026-07-28/schema.ts`: `readOnlyHint: true`, `destructiveHint: false`,
`idempotentHint: true`, `openWorldHint: false`. Every one declares an
`outputSchema` and returns `structuredContent`, plus the serialized JSON in a
text block for backwards compatibility as the spec recommends.

| Tool | Route | Returns (real fields) |
|---|---|---|
| `saibyl_list_products` | `GET /api/products` | `ProductState`: `id`, `name`, `moment{id,label,source}`, `stages[]` (`id`, `number`, `label`, `runnable`, `produced`, `inherited[]`, `missing[]`, `stale`), `stages_ready`, `attention[]{kind,text,href,weight}` |
| `saibyl_list_runs` | `GET /api/simulations` | `{items[], total, limit, offset}`; items carry `id`, `name`, `prediction_goal`, `status`, `agent_count`, `max_rounds`, `platforms`, `variants`, `lens`, `founder_stage`, `created_at` |
| `saibyl_get_objections` | `GET /api/simulations/{id}/objections` | `canonical_objections` rows: `objection_key`, `label`, `summary`, `quotes`, `event_ids`, `agent_count`, `event_count`, `first_round_seen`, `originating_cohort`, `cohort_spread`, `propagation`, `mean_intensity`, `load_bearing_score` |
| `saibyl_get_evidence` | `GET /api/simulations/{id}/evidence?event_ids=` | events with `content`, `valence`, `stance`, `intensity`, `intent`, `is_novel_claim`, and nested `agent{username, display_name, archetype}` |
| `saibyl_get_report` | `GET /api/reports/by-simulation/{id}` | `sections[]{title,content}`, `full_markdown`, `polarization{controversy_score, polarization_ratio, valence_switching_pct}` |
| `saibyl_list_website_checks` | `GET /api/website/check` | `{items, total, limit}`; items carry `id`, `url`, `status`, `overall_score`, `design_gallery_id`, `created_at` |
| `saibyl_get_website_check` | `GET /api/website/check/{snapshot_id}` | the `critique` object — per-dimension `score` plus findings typed `{dimension, severity, region, verbatim_quote, finding, fix_instruction}` — and `overall_score` |
| **`saibyl_get_fix_prompts`** | `GET /api/website/revision/{revision_id}` | `fix_prompts[]{title, scope, prompt}`, `scores_before`, `scores_after`, `rounds`, `best_round` |
| `saibyl_get_answer_pack` | `GET /api/answer-pack/by-simulation/{id}` | `rows[]{objection_key, label, agents_raising, load_bearing_score, evidence_quotes, acknowledge, explore, respond, confirm, when_to_walk}`, `battlecards[]{rival, they_say, the_honest_read, where_we_win, proof_needed}` |
| `saibyl_get_messaging_doc` | `GET /api/messaging-doc/by-simulation/{id}` | `document`: `problem`, `solution`, `icp`, `value_props[]`, `differentiators[]`, `elevator_pitch`, `objections[]{…, how_the_messaging_answers_it}`, `message_test{verdict, named_a_winner}` |
| `saibyl_get_credits` | `GET /api/billing/credits` + `/prices` | `credits_balance`, `plan`, `capped_run_credits`, and the per-artifact price table with `affordable`/`shortfall` per entry |

`saibyl_get_fix_prompts` is the flagship and the others are supporting cast.
Note what it already contains: `compose_fix_prompts` appends a final block
whose `prompt` is the whole DESIGN.md fenced in markdown. **The design brief
needs no route of its own to reach a coding tool — it is already inside the
fix-prompt payload.**

Two deliberate inclusions that look like padding and are not:

- `saibyl_list_products` is the orientation tool. `ProductState` carries
  `missing[]` and `runnable` per stage, so an agent that asks "what does this
  founder have" gets told *"there is no website check yet and here is why"*
  rather than guessing a UUID. Without it every other tool needs an ID the
  model cannot know, and the model will invent one.
- `saibyl_get_credits` is included **precisely because phase 1 spends nothing**.
  Making the balance visible to a read-only agent is how the agent learns to say
  "this would cost 1,750 credits and you have 3,200 — do it in the app" instead
  of silently doing nothing. See §6.

### 3c. What is not a tool and not a resource

`prompts/` — MCP prompts are user-triggered templates. Saibyl has no template
worth shipping: the fix prompts *are* the content, not a shape to fill. Adding a
prompts capability would be surface for its own sake.

---

## 4. Authentication and org scoping

This is the part most likely to be got wrong, so start from what exists.

### 4a. What exists today

`core/auth.py` is 65 lines and has exactly two dependencies.
`get_current_user` calls `supabase.auth.get_user(token)` over the network on
every request — no local JWT verification, no JWKS cache. `get_current_org`
then resolves the caller's org by:

> ordering is load-bearing, not cosmetic … The choice is oldest membership
> first … This is determinism, not org selection.

That docstring is correct and it is also the reason **an MCP client must not use
this path.** A browser session is a human who can see which org they are in. An
MCP client is a config file. Handing a long-lived credential to a process whose
org is resolved as "oldest membership, ordered for determinism" means a founder
who joins a second org gets a credential whose meaning was decided by a
`joined_at` tiebreak they never saw. There is a live instance of the same bug
already: `ws.py::_validate_ws_token` does `.limit(1)` with **no `.order()`**, so
a multi-org user can get a different `org_id` on the WebSocket than on their
REST calls.

There is no API-key code. There is an `api_keys` table (migration 002) with
exactly the right columns and no reader:

```
id, organization_id, created_by, name, key_hash, key_prefix,
last_used_at, expires_at, revoked_at, scopes TEXT[], created_at
```

Rate limiting exists (`core/rate_limit.py`, Redis, fails **closed** by default —
a good default, and the docstring explains why) but is applied only to
`/api/auth/signup|login|refresh`. **No billing, document, export, admin or
website route is rate limited at all.**

### 4b. The credential: what, issued how, revoked how

**Recommendation: a first-party, org-pinned, scoped API key, stored hashed,
revived on the `api_keys` table that already exists.**

- **Shape.** `sbyl_live_<32 bytes base62>`. Only `key_prefix` (the first 12
  chars) is stored in the clear and shown after creation; `key_hash` is
  SHA-256 of the whole key. Shown once at creation, never again — the same
  discipline `SECURITY_AUDIT_2026-03-30.md` §530 records the V1 keys having.
- **Issued** from a settings page in the app, by a user whose role is `owner` or
  `admin`. This is a deliberate tightening: `organizations.py` already gates
  invite and rename on `role in ("owner","admin")`, and issuing a credential
  that outlives a session is at least as consequential as renaming the org.
  Note that today **no route anywhere checks role before spending credits** —
  a `viewer` can start a run. That is a separate defect; this design does not
  inherit it.
- **Pinned.** `organization_id` is written at creation from the creating user's
  active org and is immutable. The key means one org, forever, explicitly.
  This is strictly better than the JWT path and it is the single clearest
  argument for a key over reusing Supabase sessions.
- **Expiry.** `expires_at` defaults to 90 days, and is `NOT NULL` in effect —
  the creation form has no "never" option. The spec's own guidance is that
  authorization servers *"SHOULD issue short-lived access tokens"*; 90 days is
  not short-lived, and the honest reason it is not shorter is that a founder
  re-pasting a key into their editor config every fortnight will instead pick
  the longest option available, or stop using the product. 90 days with a
  visible expiry date is the compromise, and it is a compromise.
- **Revoked** by setting `revoked_at`, checked on every request. Revocation is
  immediate and total because there is no token to expire — the key *is* the
  credential. This is one place where a static key beats OAuth: revoking an
  OAuth grant does not invalidate an already-issued access token until it
  expires. Also revoke on org-membership removal of `created_by`, and — this
  needs saying because it is easy to skip — **on password reset**, since a key
  is a credential the compromised account created.
- **Observability.** `last_used_at` updated on use (write-behind, not
  synchronously in the hot path). Every authenticated key request logs
  `key_id`, `org_id` and the tool name. Without this a leaked key looks
  identical to a working one.

**What stops one org reading another's runs** is three things stacked, and only
the first is new:

1. The key carries `organization_id`, so the principal cannot be wrong about
   which org it is.
2. The routes are unchanged. Every one still does its own
   `.eq("organization_id", ...)`, and a request from a key with org A hits
   exactly the same filter a browser session for org A hits. §2's decision —
   HTTP client, not database client — is what makes this true rather than
   aspirational.
3. RLS on every table remains as it always was: not load-bearing today, and the
   thing that catches a mistake if anyone ever swaps the admin client out.

### 4c. Transport, and where this deviates from the spec

The spec is explicit about both transports:

> Implementations using an HTTP-based transport **SHOULD** conform to this
> specification [OAuth 2.1 + RFC 9728 + RFC 8414 + RFC 7591 + RFC 8707 + PKCE].
> Implementations using an STDIO transport **SHOULD NOT** follow this
> specification, and instead retrieve credentials from the environment.

**Recommendation: phase 1 is stdio.** A small local process the founder installs
and configures with `SAIBYL_API_KEY` in their MCP client config. This is not a
workaround — it is the path the spec names for exactly this case, and it means
phase 1 ships with **no new public HTTP surface at all**. The only thing that
changes on the internet is that some existing GET routes learn to accept a
second credential type.

The cost, stated plainly:

- It does not work for hosted clients. claude.ai's web connectors need a remote
  server. A team install needs a remote server. So this reaches Claude Code,
  Cursor and Codex desktop, and nothing else.
- It puts a long-lived secret in a plaintext config file on the founder's
  machine, readable by anything that runs as them. That is the same trust model
  as every other credential in that file, which is an explanation, not a
  defence.

**Phase 2 is Streamable HTTP with OAuth 2.1 done properly**, and "properly" is
not negotiable if it happens: the spec requires the MCP server to publish
RFC 9728 protected-resource metadata, to return `WWW-Authenticate` on 401
pointing at it, to validate that tokens name it in the audience per RFC 8707,
and to **never** pass a client's token through to an upstream API. Saibyl would
be the resource server; the authorization server is either Supabase's or a thin
one Saibyl runs in front of it. Deciding that is real work and it is §11's first
open question, not something to hand-wave here.

**A static bearer over a public HTTPS MCP endpoint is the option to refuse.** It
looks like the cheap middle path — remote transport, no OAuth build — and it is
a documented deviation from a `SHOULD` with no compensating control: no
audience binding, no consent step, no short-lived token. If remote is needed,
build OAuth. If OAuth is too expensive right now, stay on stdio.

### 4d. Scope enforcement, and why it lives in the routes

`api_keys.scopes` already exists as `TEXT[]` with a default of
`{"simulations:read","simulations:write"}`. Vocabulary for phase 1:

`runs:read` · `website:read` · `gtm:read` · `billing:read`

and no write scope exists yet, because no write tool exists yet.

The mechanism: a new dependency factory — `Depends(principal("runs:read"))` —
that accepts *either* a Supabase JWT (resolving org the existing way) or a key
(resolving org from the row), returns the identical `{org_id, role, org, user}`
dict, and 403s when the scope is absent. One line per route, and the scope is
declared at the route where a reader will see it.

Two properties of that shape matter more than the shape itself:

- **Scope checks are server-side, in the routes, never in the MCP server.** A
  scope enforced by the client is not enforced.
- **A route that has not been given the new dependency does not accept keys at
  all.** New routes therefore default to key-inaccessible. That is the correct
  default and it is why an allowlist beats a denylist here: a denylist is a
  file someone has to remember to edit.

The spec permits the tool list itself to narrow by credential —

> The set **MAY** vary by the authorization presented on the request — for
> example, returning only the tools the caller's granted scopes permit — since
> credentials are per-request input, not connection state.

— so a key without `website:read` should see no website tools in `tools/list`
at all. A tool the model cannot see is a tool it cannot try, fail at, and
retry.

---

## 5. What must never be exposed

Three categories, each argued.

### 5a. Anything carrying personal contact data

**Never exposed:**

- `GET /api/gtm/candidates/{id}` — returns `contacts[]`: `full_name`,
  `role_title`, `employer`, `public_profile_url`, `source_url`,
  `retrieved_at`. Real named people at real companies.
- `GET /api/capital/firms` and `/firms/{firm_id}` — return
  `FamilyOffice.people[]` (named investors, same six fields) and
  `inbound_path.value`, which when `kind == "firm_address"` **is a literal
  email address**.
- `PATCH /api/gtm/settings` — the contact-discovery gate itself. See §5c.
- `GET /api/clearance/{run_id}` — see the caveat below.

`services/gtm/privacy.py` opens by saying the gate *"is not a feature flag. It
is the boundary between two legal positions"*, and names what those positions
cost: with contacts on, **Saibyl is the controller** for those records, owing a
lawful basis, a retention position, and the ability to answer a subject-access
or erasure request from a person who never signed up for anything. It then
enforces the third of its three rules mechanically:

> `store.delete_candidate` and `store.purge_organization` issue `DELETE`, not
> an `UPDATE … SET deleted_at`. A soft delete answers an erasure request with
> "we hid it", which is not what was asked.

**That sentence is the whole argument against exposing contacts over MCP, and it
is decisive.** An MCP read copies the record into a coding agent's context,
which becomes that agent's transcript, which becomes — depending on the client
— a third-party model provider's request log and possibly its retention window.
Saibyl deleting its rows no longer deletes the record. The best answer Saibyl
could give an erasure request becomes *"we deleted our copy"*, which is the
exact answer `privacy.py` refuses to accept from a soft delete. Building a hard
delete and then handing the rows to an unbounded set of downstream stores makes
the hard delete decorative.

Note this is a stronger constraint than "the API already shows it to the
founder." It does — the web app renders these contacts to a logged-in human. The
difference is that a browser render is a bounded copy the founder made and
controls, and an MCP read is an unbounded copy into a pipeline neither of them
controls. That distinction is doing real work here and it should not be smoothed
over.

**Two consequences:**

- **The capital module is not exposed at all in phase 1.** A projection that
  strips `people[]` and `inbound_path` would leave the genuinely valuable part —
  the thesis quotes, the match reasons, the objection bridge, all of which carry
  no personal data. But a projection is new code between a privacy rule and a
  response, and a projection that drifts is a leak with no test to catch it. If
  capital is ever exposed, the projection must be a Pydantic type validated by
  `privacy.rejects_as_personal_data` *itself*, the way `capital/schema.py`
  already does it — "the schema is enforced by the privacy rule rather than
  merely agreeing with it, which is the difference between a boundary and a
  comment." Until that type exists, no capital tools.

- **Clearance is deferred pending a scan.** `GET /api/clearance/{run_id}`
  returns `artifact` verbatim via `.select("*")`, and that artifact is USPTO
  output, which routinely carries inventor names, assignee names, and
  attorney/correspondent names and addresses. **No privacy scan is applied
  anywhere in `api/clearance.py` or its worker** — no import of
  `rejects_as_personal_data`. This is a pre-existing gap, not one MCP creates,
  but MCP is the wrong moment to inherit it. Expose clearance only after the
  artifact passes the same gate everything else does, and expose the verdict
  fields (`risk`, tier, `overall_risk`) before the raw artifact.

### 5b. Anything that spends without an explicit human decision

Never exposed in phase 1. Two lists, and the second is the surprising one.

**Routes that charge the founder's credits:**

| Route | Price |
|---|---|
| `POST /api/simulations/{id}/start` | ~3,014 at the 100-agent reference |
| `POST /api/website/check` | 1,750 |
| `POST /api/website/revision` | 5,000 |
| `POST /api/answer-pack` | 1,500 |
| `POST /api/messaging-doc` | 1,500 |
| `POST /api/capital/shortlist` | 3,000 |
| `POST /api/clearance` (STANDARD / COMPREHENSIVE) | 2,000 / 6,000 |
| `POST /api/gtm/discover` | per query, quoted |
| `POST /api/icp/synthesize`, `POST /api/inoculation/{id}/assets` | budget-checked |

**Routes that make uncharged model calls** — these spend *Saibyl's* money, not
the founder's, and none of them is metered:

- `POST /api/simulations/{id}/interview/batch` — one LLM call per entry in
  `agent_ids`, and **`agent_ids` has no length cap.**
- `POST /api/simulations/{id}/interview` and `/interview/by-persona`
- `POST /api/compare` — an uncharged completion over up to 5 runs, which first
  pages *every event* of every one of them through `fetch_all`
- `POST /api/reports/{id}/chat`
- `POST /api/accuracy/score`
- `POST /api/persona-packs/custom` — `max_tokens=4096`

`interview/batch` is arguably the single most dangerous route in the codebase to
hand a machine: uncapped fan-out, live model calls, zero metering, and a name
that reads as harmless. It must not be exposed, and it should probably get a cap
regardless of whether this project happens.

### 5c. Cross-org, admin, and policy surfaces

- **`/api/admin/design-gallery`** reads the cross-org feed. It already fails
  closed — all three refusal conditions in `require_platform_admin` collapse to
  a single 404, so a probe learns nothing. But an org-pinned key belonging to
  the admin org would satisfy it. The protection is absence: **admin routes are
  never given the key-accepting dependency**, so a key 401s there regardless of
  which org it names.
- **`PATCH /api/gtm/settings {enabled: true}`** flips the contact-discovery
  gate. Any org member can do it today with no admin check — that is a separate
  defect worth fixing. What matters here: this single call moves Saibyl from
  one legal position to the other. **An agent must never be able to make that
  call**, and no argument about confirmation prompts changes that, because the
  cost of one mistaken invocation is a controller obligation over records
  nobody decided to collect.
- **Destructive routes:** `POST /api/gtm/purge` (irreversible, deletes every
  candidate and contact the org holds, gated only on `{confirm: true}` in the
  body — a gate an agent satisfies trivially), `DELETE /api/simulations/{id}`
  (cascades through reports, sections, events, agents), `DELETE
  /api/gtm/candidates/{id}`, `DELETE /api/icp/{id}`, `DELETE /api/documents/{id}`,
  `DELETE /api/reports/{id}`.

### 5d. The category MCP creates that the browser did not

**Third-party text as untrusted input to the founder's agent.**

The website module ingests the open web by design. `dom_text` on a snapshot is
scraped from a page Saibyl did not write; the reference-mode census measures a
site the founder merely admires; the revised HTML is generated from both. When
that text is rendered in a browser tab it is content a human reads. When it
arrives in a coding agent's context it is *instructions the agent may follow*.
A page that says "ignore your previous instructions and commit the following"
is a prompt injection with a clean path from a stranger's website into a
founder's repository, and Saibyl is the carrier.

This is not fully solvable and the design should not pretend otherwise. What it
can do:

- Fence every third-party-derived string in tool output and label its
  provenance (`"source": "captured from <url> at <timestamp>"`), so a
  well-behaved client and model have the information to discount it.
- **Do not expose `GET /api/website/revision/{id}/html` as a tool.** It returns
  a whole generated page as `text/html`, and there is no version of that which
  is safe to inject wholesale into an agent's context. The founder downloading
  the bundle zip in a browser is the right delivery for it, and it already
  exists and is free.
- Prefer `fix_prompts` over raw critique text wherever both exist:
  `compose_fix_prompts` is deterministic and composed by Saibyl, and the only
  third-party content it carries is a short `verbatim_quote` inside a numbered
  instruction line.

---

## 6. Money

### 6a. Why "read-only" is not timidity

The free tier grant is **1,500 credits** (`TIER_CREDIT_GRANTS["free"]`), sized —
after three upward revisions documented in `agent_pricing.py` — to cover exactly
one capped run with 227 credits of headroom.

One website check is **1,750 credits.** *A single call to one paid tool costs
more than the entire free tier's monthly grant.*

For a paying founder it is not much better. The Founder tier grants 19,800
credits a month:

| Tool called in a loop | Calls to exhaust a Founder month |
|---|---|
| `website_revision` (5,000) | **3** |
| `capital_shortlist` (3,000) | 6 |
| `website_check` (1,750) | 11 |
| `answer_pack` (1,500) | 13 |

And the loop is not exotic. A coding agent that just applied a fix prompt has an
obvious next move: re-run the check to see whether it worked. That is a
*correct* thing for an agent to want. Three or four iterations of an entirely
sensible improve-and-verify loop is a month's credits.

**Charge-at-create makes every one of those permanent.** `refund_credits`
exists but is deliberately narrow, and its docstring says why:

> this is for failures **before any model spend**. A job that failed halfway
> through its critics has consumed real compute and is not refunded; saying so
> plainly is better than a rule that quietly sometimes pays.

So the loop does not just spend fast. It spends irreversibly.

### 6b. Why the client's confirmation prompt is not the control

The spec is clear about the intent —

> For trust & safety and security, there **SHOULD** always be a human in the
> loop with the ability to deny tool invocations.

— and equally clear that it cannot make it so: *"MCP itself cannot enforce these
security principles at the protocol level."* Three specific failures:

1. **Annotations are hints.** `ToolAnnotations` says so in the schema, and the
   spec instructs clients to *"consider tool annotations to be untrusted."* A
   server marking a tool `destructiveHint: true` is asking, not telling.
2. **Users turn confirmation off.** Every major client has a per-tool
   "don't ask again" or an auto-approve mode, and a founder iterating on their
   landing page will reach for it by the fourth prompt. The protection with the
   highest UI friction is the one most likely to be disabled.
3. **It protects the wrong thing.** A confirmation dialog asks "run this tool?".
   It does not say "this costs 1,750 credits and leaves you 200."

### 6c. The recommendation

**Phase 1: no spend tools exist, and the guarantee is structural.** The charging
routes are never given the key-accepting dependency, so a key presented to
`POST /api/website/check` gets a 401 from the existing `HTTPBearer` before any
handler runs. Not a policy, not a budget, not a prompt — **an absence**. This is
the same move `capital/schema.py` makes when it validates `FirmPerson` with
`privacy.rejects_as_personal_data` itself rather than restating its rules: make
the wrong thing impossible to construct rather than agreed-not-to-do.

`saibyl_get_credits` is exposed precisely so the read-only agent can be *useful*
about spend: it can tell the founder what a check would cost and that they can
afford it, and point them at the app. An agent that knows the price and cannot
pay it is a better outcome than an agent that can pay and does not know.

**Phase 2, if spend tools are ever added: three controls, all of them, because
each alone fails.**

1. **An explicit opt-in scope**, off by default, granted at key creation, with
   the creation UI listing the price of every tool it unlocks. Fails alone
   because it is granted once and then forgotten.
2. **A per-key credit ceiling** — a `credits_budget` and `credits_spent` column
   on `api_keys`, decremented server-side, enforced in the same unit the product
   already meters. When exhausted the tool returns `isError: true` with a
   sentence saying so. **This is the only control that survives auto-approve**,
   because it is on Saibyl's side of the wire. Fails alone because a founder who
   sets it high once has set it high forever.
3. **Server-side confirmation via `InputRequiredResult`.** The 2026-07-28 spec
   lets a tool return `resultType: "input_required"` with an `inputRequests` map
   carrying an `elicitation/create` form and an opaque `requestState`; the
   client must retry with `inputResponses` before the server proceeds. Unlike a
   client-side dialog **the server refuses to act without the answer**, so it
   cannot be auto-approved away. Fails alone because client support for
   elicitation is uneven (§11) — a client that does not implement it simply
   cannot call the tool, which is a safe failure but a broken feature.

Illustrative shape, not an implementation:

```json
{
  "resultType": "input_required",
  "inputRequests": {
    "confirm_spend": {
      "method": "elicitation/create",
      "params": {
        "mode": "form",
        "message": "A website check costs 1,750 credits. Your balance is 3,200; you would have 1,450 left. This is charged when the check starts and is not refunded once the critics run.",
        "requestedSchema": {
          "type": "object",
          "properties": { "confirmed": { "type": "boolean" } },
          "required": ["confirmed"]
        }
      }
    }
  },
  "requestState": "<opaque>"
}
```

### 6d. Reads are not free either

A read-only server still costs money and still needs limits. `POST /api/compare`
pages every event of up to five runs on every call.
`GET /api/simulations/{id}/agents` is unpaginated and returns 250 full profile
blobs for a large run. `GET /api/projects` counts documents per project per
request. And today **rate limiting exists only on the three auth routes.**

So phase 1 requires a per-key rate limit — `core/rate_limit.py` already does the
work, keyed on IP; keying it on `key_id` instead is a small change. Without it
the first agent that puts a Saibyl tool in a retry loop is a self-inflicted
load test. The spec lists this as a server obligation, not an option: *"Servers
MUST … Rate limit tool invocations."*

---

## 7. What this does not change

`CAPITAL_MODULE.md` draws the line:

> Not a CRM, and not an outreach sender. We recommend and evidence; the founder
> makes contact through the firm's own stated route. The moment we send on
> their behalf, deliverability, consent and reputation become ours.

`api/outbound.py` says the same thing about its own module in its docstring:
*"Saibyl stores no contacts, no list and no suppression state… The founder sends
from their own inbox, to their own list."*

**Does an MCP server threaten that line? No — but it moves the edge, and the new
edge is worth naming precisely.**

The line is about *sending*, and nothing here sends. But the founder's agent is
not only Saibyl's client. If Saibyl exposes an outbound sequence and that same
Claude Code session has a Gmail MCP server connected, then the *composition of
two servers* is an outreach sender, and Saibyl supplied the copy. Saibyl did not
send — and yet the clipboard, which was a human bottleneck, is gone. Previously
a founder had to read the copy to move it. Now it can be piped.

**Where exactly is the edge: it is contact data, not copy.** An `OutboundStep`
carries `subject`, `body`, `objection_key`, `evidence_quotes`, `angle` and
`placeholders_to_fill` — and no recipient. It is unaddressable. A send tool
needs an address, and Saibyl's MCP server will never supply one, because §5a
excludes `contacts[]` absolutely. **So the line holds for the same reason it has
always held: Saibyl has no list to hand over.** The composition produces an
agent that can write a good email and has no idea who to send it to.

That argument is only as strong as the exclusion is absolute, which is why §5a
is stated as "never" rather than "not yet". The moment a later phase exposes
`contacts[].full_name` next to a company `domain`, the composition becomes an
outreach sender and Saibyl becomes its list vendor. Company `domain` alone is
fine — it is public company information and a guessed address is not Saibyl
handing one over. The joinable pair is the thing.

**A second line to draw now, before anyone asks for it: Saibyl does not write to
the founder's repository.** There will be a request for a `saibyl_apply_fix`
tool, and it should be refused, for the CAPITAL_MODULE reason transposed: the
moment Saibyl edits the code, "did Saibyl break my site" becomes Saibyl's
problem in exactly the shape "did Saibyl's email get me blacklisted" would have
been. Saibyl measures and prescribes; the founder's own tool applies. The
handoff is the product boundary and MCP is a better courier for it, not a
reason to cross it.

---

## 8. Effort and risk

### 8a. Genuinely hard

1. **One principal, two credential kinds, no drift.** `get_current_org` resolves
   org by oldest membership; a key pins it. Two paths producing "the same" dict
   is precisely the two-sources-of-truth class this codebase names elsewhere.
   Mitigation: one dependency, one construction site for the dict, and a test
   asserting both paths yield identical keys and types. Small in lines, easy to
   get subtly wrong.
2. **Keeping the allowlist honest.** Deciding once, per route, whether it may
   see a key. The default is right (a new route accepts no keys until someone
   adds the dependency) but the review discipline has to survive contact with a
   busy week.
3. **The clearance PII scan** (§5a). Not MCP work strictly, but MCP is blocked
   on it and it is the kind of task that expands once someone reads what USPTO
   actually returns.
4. **Third-party text provenance** (§5d). Labelling is easy; the injection risk
   is not solvable and the honest deliverable is a disclosure, not a fix.

### 8b. Routine

- **The server itself.** Eleven tools, each one HTTP GET plus a JSON Schema. A
  stdio process in Python (reuses the backend's models) or TypeScript (better
  SDK ergonomics). One to two days including the schemas.
- **Key issuance UI.** Create / list / revoke, show-once. The table exists.
- **Per-key rate limiting.** `check_rate_limit` already exists; change the key.
- **One small new read route** if the design DNA should be reachable without
  paying for a revision: `design_gallery` has a `design_md` column and no
  per-org reader — only the platform-admin feed. Not needed for the first
  slice, because the DESIGN.md already rides inside `fix_prompts`.

### 8c. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| Key leaks from a plaintext editor config | High | 90-day expiry, instant revoke, `last_used_at`, per-key logs |
| A route gains a key dependency and loses its org filter | High | Routes unchanged; §2's HTTP-client decision; existing filters are the only ones |
| Prompt injection via captured third-party page text | Medium | Fence and label; never expose `/revision/{id}/html`; prefer `fix_prompts` |
| Read loop generates load | Medium | Per-key rate limit before launch |
| Nobody installs it; it becomes V1 residue again | Medium | Ship unpromoted; delete on a null result — cheap, by construction |
| Scope creep into spend tools | Medium | §6c's three controls are the price of admission, not phase-1 work |

---

## 9. Phasing

### Slice one — four tools, ship this or nothing

`saibyl_list_products` · `saibyl_list_runs` · `saibyl_get_objections` ·
`saibyl_get_fix_prompts`

Plus: the key issuance page, the `principal()` dependency on those four routes,
per-key rate limiting, and a stdio server package.

Those four answer the two questions a founder actually asks their coding tool:
*"what did the market say about this"* and *"what exactly do I change"*. The
second is the one already built for this purpose. Everything else in §3b is an
addition to a working thing, which is a much better position than a broad
launch.

**Gate:** one founder, on a real project, applies a Saibyl fix prompt through
their coding tool without opening a browser tab. If that does not happen, stop.

### Slice two

The remaining seven read tools, resources and templates, `resources/list`,
scope-varying `tools/list`, and the design-gallery read route.

### Phase two — a different decision, not a continuation

Remote Streamable HTTP with OAuth 2.1 done to spec (§4c). Spend tools behind
all three controls (§6c). The Tasks extension for long-running work — a website
check takes minutes and `io.modelcontextprotocol/tasks` is designed for exactly
this, returning a durable `taskId` with `ttlMs` and `pollIntervalMs` instead of
blocking a connection. Clearance, after the scan. Capital, only with a
privacy-validated projection type.

None of phase two should start until slice one has a founder using it.

---

## 10. Changes required in the existing codebase

Everything the design needs, honestly listed. Nothing here is speculative.

| # | Change | Where | Size |
|---|---|---|---|
| 1 | `principal(scope)` dependency accepting a Supabase JWT **or** an `api_keys` row, returning the existing `{org_id, role, org, user}` shape | `core/auth.py` (new function, existing ones untouched) | ~60 lines |
| 2 | Apply it to the four slice-one read routes; nothing else | `products.py`, `simulations.py`, `analysis.py`, `website.py` | 4 lines |
| 3 | Key issuance/list/revoke routes + settings page, `owner`/`admin` only | new `api/keys.py`, frontend | small |
| 4 | Per-key rate limiting | `core/rate_limit.py` — key on `key_id` not IP | small |
| 5 | Scan the clearance `artifact` through `rejects_as_personal_data` before it is stored or served | `workers/clearance_tasks.py`, `api/clearance.py` | small, **blocks clearance exposure** |
| 6 | Cap `agent_ids` on `POST /api/simulations/{id}/interview/batch` | `api/simulations.py` | 2 lines |

Two pre-existing defects this design surfaced but does not fix, recorded so they
are not lost:

- **`ws.py::_validate_ws_token` resolves org with `.limit(1)` and no
  `.order()`**, so a multi-org user can get a different `org_id` on the
  WebSocket than on their REST calls. `get_current_org`'s docstring explains at
  length why that ordering is load-bearing; the WebSocket path does not have it.
- **No route checks `role` before spending credits.** A `viewer` can start a
  paid run, order a 5,000-credit revision, or purge every contact the org holds.
  `role` is returned by `get_current_org` and read by exactly two files
  (`billing.py`, `organizations.py`), neither of which is a spend path.

Also worth noting for whoever writes the tool schemas: **no route in the backend
declares a FastAPI `response_model=`**, so the generated OpenAPI describes every
response as `{}`. MCP `outputSchema` cannot be derived from it and must be
written by hand, which is a small but real per-tool cost and a reason to keep
the tool count low.

---

## 11. What I could not verify, and open questions

Stated rather than guessed.

1. **Which authorization server phase 2 would use.** Supabase's own OAuth
   endpoints versus a thin AS Saibyl runs in front of it. RFC 9728 requires the
   MCP server to *name* an authorization server in its protected-resource
   metadata, and the two answers have different operational costs. Unresolved,
   and it is the first thing to settle if remote transport is ever wanted.
2. **Client support for elicitation / `InputRequiredResult`.** The spec defines
   it in revision 2026-07-28 and it is the mechanism §6c leans on for
   server-side spend confirmation. I did not verify which of Claude Code,
   Cursor and Codex implement it today; the spec's own client matrix is the
   place to check before designing a spend tool around it.
3. **Client support for resources and resource templates.** §3's split assumes
   it is uneven, which is why every resource has a mirroring tool. That
   assumption should be checked rather than trusted.
4. **Client support for the Tasks extension.** It is an opt-in extension, the
   spec says servers must never return a task to a client that did not declare
   support, and the docs note support varies. A website check takes minutes, so
   the fallback shape — return a handle immediately, poll with a status tool —
   should be designed regardless.
5. **Whether the founder wants this at all before Phase D.** §1a argues it can
   be built without competing for Phase D's time. That judgement is the
   founder's, not this document's.

---

## 12. Recommendation, in one paragraph

Build a **read-only stdio MCP server** authenticated by a **first-party,
org-pinned, scoped API key** on the `api_keys` table that already exists,
talking to Saibyl's **existing HTTP routes** so it inherits every org filter
rather than re-implementing one. Ship **four tools** — the rail, the run list,
the objections, and the fix prompts — because the fix prompts are already built
to be pasted into a coding tool and this removes the paste. Expose **nothing**
carrying personal contact data, **nothing** that spends, and **nothing**
cross-org, and make each of those an absence in the routing rather than a rule
in a document. Ship it unpromoted, to a handful of founders, and let whether
they use it decide whether phase two exists.

The single strongest reason not to do this is that Saibyl has one distribution
motion, has not yet cleared the gate that unlocks it, and deleted its last
general-purpose API as residue three weeks ago. That reason is good enough to
keep the scope at four tools. It is not good enough to skip a change that
deletes an alt-tab from the product's own flagship promise.
