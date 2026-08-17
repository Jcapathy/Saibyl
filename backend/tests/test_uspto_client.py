"""The USPTO client must be honest about nothing before it is useful at all.

Every behavior pinned here is one the clearance report's credibility rests on,
and each was verified against the live API by the founder's reference server
(`uspto-patent-mcp`) before being ported:

- ODP answers HTTP 404 for a search with zero hits. Treating that as an error
  (or worse, as data) is how a report fabricates or hides prior art.
- 5xx and timeouts are transient — retried with backoff, not surfaced as
  "USPTO is down" on the first blip.
- API keys must never appear in exception text, logs, or repr. A masked key in
  an error that later lands in Sentry or a founder-visible message is a leak.
- Missing keys raise ClearanceConfigError so the track layer reports
  NOT_SEARCHED — a missing key silently returning [] would read as "clear",
  which is the one lie the skill forbids (Track A rule 4, Track C honesty).
- USPTO dates arrive in several formats, sometimes within one record. They
  stay raw strings; a strict parse would drop real prior art on a cosmetic
  mismatch.

No test here touches the network: the transport seam (`_send_once`) is
replaced, everything above it — retries, caching, masking, normalization —
runs for real.
"""
from __future__ import annotations

import httpx
import pytest

from app.services.clearance.uspto_client import (
    ODP_BASE,
    TRADEMARK_SEARCH_LINK,
    AppRecord,
    ClearanceConfigError,
    SearchResult,
    UsptoApiError,
    UsptoClient,
)

ODP_KEY = "odp-test-key-1234567890"
TSDR_KEY = "tsdr-test-key-0987654321"


# ---------------------------------------------------------------------------
# Transport seam — canned responses in, recorded requests out
# ---------------------------------------------------------------------------

def _client(odp_key: str = ODP_KEY, tsdr_key: str = TSDR_KEY) -> UsptoClient:
    client = UsptoClient(odp_key=odp_key, tsdr_key=tsdr_key)
    client._retry_base_delay = 0.0  # no real backoff waits in tests
    return client


def _install_transport(
    client: UsptoClient, responses: list[httpx.Response | Exception]
) -> list[dict]:
    """Replace `_send_once` with a script of responses; return the call log.

    The last entry repeats, so "always 500" is a one-element script.
    """
    calls: list[dict] = []

    async def fake_send_once(method, url, *, headers, params=None, data=None,
                             json_body=None, timeout=30.0):
        calls.append({
            "method": method, "url": url, "headers": headers,
            "params": params, "data": data, "json": json_body,
        })
        result = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(result, Exception):
            raise result
        return result

    client._send_once = fake_send_once  # type: ignore[method-assign]
    return calls


# ---------------------------------------------------------------------------
# Fixtures — realistic payloads, quirks included on purpose
# ---------------------------------------------------------------------------

ODP_SEARCH_PAYLOAD = {
    "count": 2,
    "patentFileWrapperDataBag": [
        {
            "applicationNumberText": "17248024",
            "applicationMetaData": {
                "inventionTitle": "Bidirectional ML classifier proxy for LLM security",
                # Datetime-suffixed date — one of the documented formats.
                "filingDate": "2025-09-23 00:57:53",
                "applicationStatusDescriptionText": "Patented Case",
                "patentNumber": "12130917",
                "earliestPublicationNumber": "US20260089190A1",
                "firstApplicantName": "CyberShield Inc.",
                "firstInventorName": "Jane Q. Inventor",
                "cpcClassificationBag": ["G06F21/554", "G06N3/08"],
            },
            "grantDocumentMetaData": {
                "fileLocationURI": f"{ODP_BASE}/api/v1/download/products/ptgrxml/12130917.xml"
            },
        },
        {
            "applicationNumberText": "18999999",
            "applicationMetaData": {
                "inventionTitle": "Adversarial input detection",
                "filingDate": "2024-02-28",
                "applicationStatusDescriptionText": "Pending",
                # null-instead-of-[] quirk, and first* names absent so the
                # bag fallbacks are what produce assignee/inventor.
                "cpcClassificationBag": None,
                "applicantBag": [{"applicantNameText": "OpenAI, Inc."}],
                "inventorBag": [{"inventorNameText": "John Smith"}],
            },
        },
    ],
}

CLAIMS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<us-patent-grant lang="EN" dtd-version="v4.6 2022-02-17">
  <claims id="claims">
    <claim id="CLM-00001" num="00001">
      <claim-text>1. A method for detecting prompt injection, comprising:
        <claim-text>receiving an input &amp; classifying it; and</claim-text>
        <claim-text>blocking the input when the classifier fires.</claim-text>
      </claim-text>
    </claim>
    <claim id="CLM-00002" num="00002">
      <claim-text>2. The method of <claim-ref idref="CLM-00001">claim 1</claim-ref>,
        wherein the classifier is bidirectional.</claim-text>
    </claim>
  </claims>
</us-patent-grant>
"""

TSDR_PAYLOAD = {
    "trademarks": [
        {
            "status": {
                "serialNumber": "97123456",
                "markElement": "PARRYAI",
                "extStatusDesc": "Registered",
                "liveDeadIndicator": "LIVE",
                "filingDate": "2023-11-15",
            },
            "parties": {
                "ownerGroups": {
                    "10": [{"name": "Saido Labs LLC", "entityType": "LLC"}]
                }
            },
            "gsList": [
                {
                    "internationalClasses": [{"code": "009"}, {"code": "042"}],
                    "description": "Downloadable software for AI security",
                }
            ],
        }
    ]
}


# ---------------------------------------------------------------------------
# 404 = zero hits, never an error
# ---------------------------------------------------------------------------

async def test_search_404_is_a_zero_hit_result_not_an_error():
    client = _client()
    _install_transport(client, [
        httpx.Response(404, json={"detailedMessage": "No matching records found"})
    ])

    result = await client.search_applications("nonexistent widget frobnicator")

    assert result == SearchResult(total=0, items=[])


async def test_by_number_lookups_translate_404_to_none():
    client = _client()
    _install_transport(client, [httpx.Response(404, text="Not Found")])

    assert await client.get_application("99999999") is None
    assert await client.get_continuity("99999999") is None
    assert await client.search_rejections("patentApplicationNumber:99999999") == []
    assert await client.search_ptab("trialNumber:IPR2099-99999") == []


# ---------------------------------------------------------------------------
# Retries
# ---------------------------------------------------------------------------

async def test_5xx_is_retried_and_the_third_attempt_succeeds():
    client = _client()
    calls = _install_transport(client, [
        httpx.Response(500, text="Internal Server Error"),
        httpx.Response(503, text="Service Unavailable"),
        httpx.Response(200, json=ODP_SEARCH_PAYLOAD),
    ])

    result = await client.search_applications("prompt injection")

    assert result.total == 2
    assert len(calls) == 3


async def test_a_timeout_is_retried_like_a_5xx():
    client = _client()
    calls = _install_transport(client, [
        httpx.ReadTimeout("timed out"),
        httpx.Response(200, json=ODP_SEARCH_PAYLOAD),
    ])

    result = await client.search_applications("prompt injection")

    assert result.total == 2
    assert len(calls) == 2


async def test_a_4xx_other_than_404_is_not_retried():
    """403 (bad key) must fail fast — retrying it would burn 3 attempts on
    every call of a run that can never succeed."""
    client = _client()
    calls = _install_transport(client, [httpx.Response(403, text="Forbidden")])

    with pytest.raises(UsptoApiError) as exc:
        await client.search_applications("anything")

    assert exc.value.status == 403
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Key masking
# ---------------------------------------------------------------------------

async def test_the_api_key_never_appears_in_error_text_or_repr():
    client = _client()
    # A hostile-worst-case body: the key echoed verbatim AND as a query param.
    _install_transport(client, [
        httpx.Response(500, text=f"upstream error for key {ODP_KEY} url=/x?api_key={ODP_KEY}")
    ])

    with pytest.raises(UsptoApiError) as exc:
        await client.search_applications("anything")

    message = str(exc.value)
    assert ODP_KEY not in message
    assert "[MASKED]" in message
    assert ODP_KEY not in repr(client)
    assert TSDR_KEY not in repr(client)


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

async def test_a_repeated_search_is_served_from_cache():
    client = _client()
    calls = _install_transport(client, [httpx.Response(200, json=ODP_SEARCH_PAYLOAD)])

    first = await client.search_applications("prompt injection")
    second = await client.search_applications("prompt injection")

    assert len(calls) == 1, "the second identical GET must not hit the API"
    assert second == first


async def test_different_params_are_different_cache_entries():
    client = _client()
    calls = _install_transport(client, [httpx.Response(200, json=ODP_SEARCH_PAYLOAD)])

    await client.search_applications("prompt injection")
    await client.search_applications("prompt injection", offset=25)

    assert len(calls) == 2


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

async def test_normalization_of_a_realistic_odp_payload():
    client = _client()
    _install_transport(client, [httpx.Response(200, json=ODP_SEARCH_PAYLOAD)])

    result = await client.search_applications("prompt injection")

    granted, pending = result.items
    assert granted.app_number == "17248024"
    assert granted.title == "Bidirectional ML classifier proxy for LLM security"
    assert granted.assignee == "CyberShield Inc."
    assert granted.inventor == "Jane Q. Inventor"
    assert granted.filed == "2025-09-23 00:57:53", "dates stay raw — never parsed"
    assert granted.status == "Patented Case"
    assert granted.grant_number == "12130917"
    assert granted.publication_number == "US20260089190A1"
    assert granted.cpc == ["G06F21/554", "G06N3/08"]
    assert granted.raw == ODP_SEARCH_PAYLOAD["patentFileWrapperDataBag"][0]

    assert pending.cpc == [], "a null bag reads as empty, not as a crash"
    assert pending.assignee == "OpenAI, Inc."
    assert pending.inventor == "John Smith"
    assert pending.grant_number is None
    assert pending.publication_number is None


async def test_items_are_capped_at_the_requested_limit():
    """The API can return more rows than asked; the client never relays an
    unbounded payload upward."""
    client = _client()
    _install_transport(client, [httpx.Response(200, json=ODP_SEARCH_PAYLOAD)])

    result = await client.search_applications("prompt injection", limit=1)

    assert len(result.items) == 1
    assert result.total == 2, "the true hit count is still reported"


# ---------------------------------------------------------------------------
# Missing keys degrade honestly
# ---------------------------------------------------------------------------

async def test_missing_keys_raise_clearance_config_error_before_any_request():
    client = UsptoClient(odp_key="", tsdr_key="")
    calls = _install_transport(client, [httpx.Response(200, json={})])

    assert client.odp_available is False
    assert client.tsdr_available is False
    with pytest.raises(ClearanceConfigError, match="USPTO_ODP_API_KEY"):
        await client.search_applications("anything")
    with pytest.raises(ClearanceConfigError, match="USPTO_TSDR_API_KEY"):
        await client.get_trademark_status("97123456")
    assert calls == [], "an unconfigured client must never reach the network"


def test_the_official_word_mark_search_link_is_pinned():
    """Track A rule 4: no word-mark API exists, so the track layer reports
    NOT_SEARCHED with this exact official link."""
    assert TRADEMARK_SEARCH_LINK == "https://tmsearch.uspto.gov/search/search-information"


# ---------------------------------------------------------------------------
# Claims full text
# ---------------------------------------------------------------------------

def _granted_record() -> AppRecord:
    wrapper = ODP_SEARCH_PAYLOAD["patentFileWrapperDataBag"][0]
    return AppRecord(
        app_number="17248024", title=None, assignee=None, inventor=None,
        filed=None, status=None, grant_number=None, publication_number=None,
        cpc=[], raw=wrapper,
    )


async def test_get_claims_text_extracts_the_claims_from_grant_xml():
    client = _client()
    calls = _install_transport(client, [httpx.Response(200, text=CLAIMS_XML)])

    text = await client.get_claims_text(_granted_record())

    assert text is not None
    assert "A method for detecting prompt injection" in text
    assert "blocking the input when the classifier fires" in text
    assert "&" in text and "&amp;" not in text, "entities are unescaped"
    assert "wherein the classifier is bidirectional" in text
    assert "\n\n" in text, "each claim is its own paragraph"
    assert "<" not in text, "no markup survives"
    assert calls[0]["url"].startswith(ODP_BASE), "downloads only from the ODP host"


async def test_get_claims_text_is_none_when_no_xml_document_exists():
    """Unpublished applications have no public text — None, never a guess."""
    client = _client()
    calls = _install_transport(client, [httpx.Response(200, text=CLAIMS_XML)])

    record = _granted_record().model_copy(update={"raw": {"applicationNumberText": "18999999"}})

    assert await client.get_claims_text(record) is None
    assert calls == []


# ---------------------------------------------------------------------------
# Trademark status (TSDR)
# ---------------------------------------------------------------------------

async def test_trademark_status_normalizes_the_verified_tsdr_shape():
    client = _client()
    calls = _install_transport(client, [httpx.Response(200, json=TSDR_PAYLOAD)])

    status = await client.get_trademark_status("97123456")

    assert status is not None
    assert status.serial == "97123456"
    assert status.mark == "PARRYAI"
    assert status.live is True
    assert status.status_text == "Registered"
    assert status.owner == "Saido Labs LLC"
    assert status.classes == ["009", "042"]
    assert status.goods_services == "Downloadable software for AI security"
    assert calls[0]["headers"]["USPTO-API-KEY"] == TSDR_KEY
    assert calls[0]["url"].endswith("/ts/cd/casestatus/sn97123456/info.json")


async def test_trademark_status_404_is_none_not_an_error():
    client = _client()
    _install_transport(client, [httpx.Response(404, text="Not Found")])

    assert await client.get_trademark_status("99999999") is None
