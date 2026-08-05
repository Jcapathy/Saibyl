# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# StageId, STAGE_ORDER   — the five steps, in the order they consume each other
# ProductState           — one product's rail, its moment, and its attention lines
# StageState             — one stage: what it inherited, what is missing, the cost
# build_product_state    — assemble one product's state from what is actually stored
# build_product_states   — the same for every product in an org, in one pass
# ─────────────────────────────────────────────────────────
"""What each stage of the rail inherited, and what a missing input will cost.

The rail is open: no stage is locked. That is a deliberate product decision and
it carries a matching obligation — a stage that runs without what it needed
produces a thin answer, and the founder concludes the *product* is thin. So the
rule this module exists to serve is:

    Never a grey button. A stage either runs and states what the answer will be
    missing, or it is blocked with the button that unblocks it.

Both halves of that sentence are computed here rather than in the client,
because both are statements about stored data and a client that assembled them
from six endpoints would be assembling a second implementation of the rule. The
frontend renders what this returns; it decides nothing.

**Nothing here is invented.** Every field traces to a row. Where there is no
row, the field is absent — not zero, not an empty string that renders as a
measurement of nothing. `attention` in particular is drawn only from things the
system genuinely knows: a completed run, an unresolved comparison, a stale
candidate list, a document still processing. A product with nothing to report
gets an empty list and the client says so.
"""
from app.services.stages.product_state import (
    STAGE_ORDER,
    ProductState,
    StageId,
    StageState,
    build_product_state,
    build_product_states,
)

__all__ = [
    "STAGE_ORDER",
    "ProductState",
    "StageId",
    "StageState",
    "build_product_state",
    "build_product_states",
]
