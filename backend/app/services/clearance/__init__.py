# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# uspto_client — UsptoClient + AppRecord / SearchResult / TrademarkStatus,
#                ClearanceConfigError, UsptoApiError, TRADEMARK_SEARCH_LINK
# ─────────────────────────────────────────────────────────
"""IP clearance (PRD_V3 §11): USPTO trademarks, prior art, pending landscape.

This package holds the API surface the clearance tracks are built on. The
USPTO client is the only module today; track logic, report composition, and
pricing live elsewhere and code against the shapes exported here.
"""
from app.services.clearance.uspto_client import (
    TRADEMARK_SEARCH_LINK,
    AppRecord,
    ClearanceConfigError,
    SearchResult,
    TrademarkStatus,
    UsptoApiError,
    UsptoClient,
)

__all__ = [
    "TRADEMARK_SEARCH_LINK",
    "AppRecord",
    "ClearanceConfigError",
    "SearchResult",
    "TrademarkStatus",
    "UsptoApiError",
    "UsptoClient",
]
