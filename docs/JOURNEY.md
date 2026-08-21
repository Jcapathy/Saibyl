# The journey — how a founder is moved from one module to the next

**Written 2026-08-20.** The platform is becoming a pipeline: idea → is it
ownable → does the page say it → how do I sell it → who funds it. The rail
already guides a founder *within* a product (five steps, each declaring what
it inherited and what is missing). Nothing guides them *between modules*, and
the modules are where the revenue is.

This is the design for that. It is deliberately not a checklist.

## The rule the whole design rests on

**A handoff is earned by evidence, never scheduled.**

The product may only suggest the next module when the founder's own data has
raised the question that module answers — and the suggestion must quote that
data as its reason. "You are on step 3, consider the IP check" is a nag. "Four
of the twenty-five buyers said a competitor already does this — here is who
actually owns the idea" is the founder's own result handing them the next
question.

This is the same law `AttentionLine` already states for the product card:
*never invented to fill the card.* A product with nothing to report shows
nothing. Extending that rule across modules is the entire mechanism.

Three consequences, all enforceable:

1. **One next action, never a menu.** A list of five things to buy is a
   pricing page. One thing, with the reason, is advice.
2. **The reason is a quotation, not a claim.** Every suggestion carries the
   measured fact that produced it — the objection, the score, the count.
3. **When nothing is earned, nothing is shown.** Silence is a valid state and
   is what keeps the mechanism trusted the rest of the time.

## The chain, and what earns each link

| The founder has | Which raises | So offer | The reason it quotes |
|---|---|---|---|
| A finished evaluation with objections | "Is this even mine to build?" | **IP check** | "Buyers pushed back N times on this being solved already." |
| Objections naming a rival, or a rival in their material | "How do I win that comparison?" | **IP check + the battlecard** | The rival's name, from their own quotes. |
| A clear IP result and a live site | "Does my page say what my pitch says?" | **Website check** | "Your pitch answered X; a stranger has nine seconds on your page." |
| A website score below the bar | "How do I fix it?" | **Revision + the proof re-run** | The lowest-scoring dimension, named. |
| Measured objections and no sales script | "It came up on a call, what do I say?" | **Answer pack** (GTM) | The top objection, with the buyer's sentence. |
| An answer pack and a buyer list | "Who do I send it to?" | **Outbound sequence** over the discovered companies | The archetype and how many companies matched. |
| Traction, or a clear IP position and a story | "Who funds this?" | **Capital: family offices** | Their sector and stage, matched to a firm's stated thesis. |

The chain is a preference order, not a gate. A founder who arrives with a live
site skips to the website check; the rule is only that we never suggest a link
whose precondition their data has not met.

## Where it renders

Exactly three places, and no others — each one a moment the founder is already
looking for what to do next:

1. **The end of a finished run** (`WhatNext`, shipped). After the evidence,
   never before it.
2. **The product card on home.** One line, in the existing `attention` list,
   with `weight: 'high'` when it is the earned next action. It already renders
   what the system genuinely knows; this is one more thing it knows.
3. **The stage a founder lands on with nothing to do.** A completed stage
   currently just sits there. That is the cheapest unused surface in the app.

Not in the sidebar, not as a banner, not as a modal, and never more than one at
a time. A suggestion that follows a founder around is an advertisement.

## The implementation, when it is built

One function, server-side, beside the code that already computes stage state:

```python
def next_best_action(product_state, org_state) -> Action | None:
    """The one thing this founder's own data says would help most next."""
```

It belongs in `services/stages/product_state.py` because that module already
loads everything it needs — stages, runs, objections, documents — and because a
second place that decides what a founder should do next is a second source of
truth for the product's opinion of them.

It returns `None` freely. Every branch carries the measured fact in the
`Action`, so the client renders the reason rather than composing one, and a
suggestion can never appear without the evidence that earned it.

## What this is not

- Not a progress bar. The founder is not completing our funnel, they are
  answering their own questions in the order the answers arrive.
- Not an upsell that fires on a timer, a login count, or a trial day. Those
  are the mechanics of a product that has nothing to say.
- Not a place to put the module we most want sold. The order above is the
  order the questions actually occur to a founder; selling against that order
  is how the suggestion stops being read.
