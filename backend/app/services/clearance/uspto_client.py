# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# AppRecord, SearchResult, TrademarkStatus  — normalized record shapes
# UsptoClient                               — async client over three USPTO surfaces
# ClearanceConfigError                      — a key this call needs is not configured
# UsptoApiError                             — a USPTO response that is a real failure
# TRADEMARK_SEARCH_LINK                     — the official word-mark search UI
# ─────────────────────────────────────────────────────────
"""USPTO client for the IP clearance stage (PRD_V3 §11).

Ported from the founder's `uspto-patent-mcp` TypeScript server (the reference
client named in the PRD), covering three surfaces:

    ODP REST   patents, continuity, PTAB proceedings   — X-API-KEY header
    DSAPI      office-action rejections (Lucene POST)  — same ODP key
    TSDR       trademark status by serial number       — separate key + header

Quirks the reference server verified against the live API, honored here:

- **ODP search answers HTTP 404 for zero hits.** That is a result, not an
  error: `search_applications` returns ``SearchResult(total=0, items=[])`` and
  the by-number lookups return ``None``.
- **Date formats are chaotic** (ISO dates, ``"2025-09-23 00:57:53"``,
  date-only strings, sometimes per-field within one record). Dates stay raw
  strings end to end; nothing here parses them.
- **Null vs empty arrays**: some endpoints return ``null`` where ``[]`` is
  meant. Every bag read tolerates both.
- **XML downloads are limited to ~20 per URL per YEAR**, so downloaded
  grant/pgpub XML is cached for 24 hours where JSON gets 5 minutes.
- **API keys never appear in errors, logs, or repr** — masked to
  ``[MASKED]`` (port of the reference's ``maskSensitiveText``).

**The trademark decision.** TSDR is a STATUS/DOCUMENT retrieval API keyed by
serial or registration number — there is no public word-mark search API. The
reference server's `search_trademark` tool (``src/tools/trademark.ts``) does
not implement word-mark search some other way: TESS was retired, and its
replacement (tmsearch.uspto.gov) sits behind cookie + AWS WAF browser-challenge
auth with no published spec, so the tool resolves number-like input via TSDR
and returns an honest ``[NO_PUBLIC_API]`` message with a deep link for word
marks. This client therefore exposes `get_trademark_status` (by serial) only,
plus the `TRADEMARK_SEARCH_LINK` constant; the track layer reports NOT_SEARCHED
with the official link for word-mark availability (skill Track A rule 4) —
never "clear" without an actual search result.

Missing keys degrade honestly: the corresponding ``*_available`` property is
False and calls raise `ClearanceConfigError` instead of guessing.
"""
from __future__ import annotations

import asyncio
import random
import re
import time
from html import unescape
from typing import Any
from urllib.parse import quote

import httpx
import structlog
from pydantic import BaseModel

from app.core.config import settings

log = structlog.get_logger()

# The official USPTO word-mark search UI (no public API — see module docstring).
TRADEMARK_SEARCH_LINK = "https://tmsearch.uspto.gov/search/search-information"

ODP_BASE = "https://api.uspto.gov"
TSDR_BASE = "https://tsdrapi.uspto.gov"

_SEARCH_PATH = "/api/v1/patent/applications/search"
_DSAPI_REJECTIONS_PATH = "/api/v1/patent/oa/oa_rejections/v2/records"
_PTAB_SEARCH_PATH = "/api/v1/patent/trials/proceedings/search"

_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_DEFAULT_TIMEOUT = 30.0
# TSDR occasionally hangs; the reference keeps its timeout short for that reason.
_TSDR_TIMEOUT = 12.0
_XML_TIMEOUT = 60.0

_CACHE_TTL = 5 * 60.0
_XML_CACHE_TTL = 24 * 60 * 60.0
_CACHE_MAX_ENTRIES = 256

# 50KB-equivalent sanity cap: claims text is the one unbounded payload here.
_MAX_CLAIMS_CHARS = 50_000

_KEY_PARAM_RE = re.compile(
    r"([?&](?:api_key|apiKey|apikey|key|X-API-KEY|USPTO-API-KEY)=)[^&\s]+", re.IGNORECASE
)
_CLAIMS_RE = re.compile(r"<claims\b[^>]*>(.*?)</claims>", re.DOTALL | re.IGNORECASE)
_CLAIM_RE = re.compile(r"<claim\b[^>]*>(.*?)</claim>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


class ClearanceConfigError(Exception):
    """A USPTO API key this call needs is not configured.

    Callers must degrade honestly — report the check as NOT_SEARCHED, never
    swallow this into an empty (which reads as "clear") result.
    """


class UsptoApiError(Exception):
    """A USPTO response that is a real failure (404 = zero hits is not one)."""

    def __init__(self, status: int, message: str, detail: str = ""):
        self.status = status
        self.detail = detail
        super().__init__(f"{message} — {detail}" if detail else message)


class AppRecord(BaseModel):
    """One patent application, normalized from an ODP file-wrapper record."""

    app_number: str
    title: str | None
    assignee: str | None
    inventor: str | None
    filed: str | None  # raw string — USPTO date formats are chaotic, never parsed
    status: str | None  # e.g. "Patented Case", "Pending", "Abandoned"
    grant_number: str | None
    publication_number: str | None
    cpc: list[str]
    raw: dict  # the source record


class SearchResult(BaseModel):
    total: int
    items: list[AppRecord]


class TrademarkStatus(BaseModel):
    serial: str
    mark: str | None
    live: bool | None
    status_text: str | None
    owner: str | None
    classes: list[str]
    goods_services: str | None
    raw: dict


# ---------------------------------------------------------------------------
# Normalization helpers — tolerant of every documented shape quirk
# ---------------------------------------------------------------------------

def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_bag_name(meta: dict, bag_key: str, name_key: str) -> str | None:
    bag = meta.get(bag_key) or []
    if isinstance(bag, list):
        for entry in bag:
            if isinstance(entry, dict):
                name = _coerce_str(entry.get(name_key))
                if name:
                    return name
    return None


def _cpc_list(meta: dict) -> list[str]:
    bag = meta.get("cpcClassificationBag") or []
    if not isinstance(bag, list):
        return []
    out: list[str] = []
    for entry in bag:
        if isinstance(entry, str):
            text = entry.strip()
        elif isinstance(entry, dict):
            # Verified live shape is a list of strings, but the swagger spec
            # has documented object-vs-array mismatches — take the first
            # string-ish value rather than failing the whole record.
            text = next(
                (v.strip() for v in entry.values() if isinstance(v, str) and v.strip()), ""
            )
        else:
            text = ""
        if text:
            out.append(text)
    return out


def _normalize_wrapper(wrapper: dict) -> AppRecord:
    meta = wrapper.get("applicationMetaData")
    if not isinstance(meta, dict):
        meta = {}
    return AppRecord(
        app_number=(
            _coerce_str(wrapper.get("applicationNumberText"))
            or _coerce_str(meta.get("applicationNumberText"))
            or ""
        ),
        title=_coerce_str(meta.get("inventionTitle")),
        assignee=(
            _coerce_str(meta.get("firstApplicantName"))
            or _first_bag_name(meta, "applicantBag", "applicantNameText")
        ),
        inventor=(
            _coerce_str(meta.get("firstInventorName"))
            or _first_bag_name(meta, "inventorBag", "inventorNameText")
        ),
        filed=_coerce_str(meta.get("filingDate")),
        status=_coerce_str(meta.get("applicationStatusDescriptionText")),
        grant_number=_coerce_str(meta.get("patentNumber")),
        publication_number=_coerce_str(meta.get("earliestPublicationNumber")),
        cpc=_cpc_list(meta),
        raw=wrapper,
    )


def _normalize_search(payload: Any, limit: int) -> SearchResult:
    if not isinstance(payload, dict):
        return SearchResult(total=0, items=[])
    bag = payload.get("patentFileWrapperDataBag") or []
    if not isinstance(bag, list):
        bag = []
    items = [_normalize_wrapper(w) for w in bag[:limit] if isinstance(w, dict)]
    count = payload.get("count")
    total = count if isinstance(count, int) else len(items)
    return SearchResult(total=total, items=items)


def _file_location_uri(raw: dict) -> str | None:
    """Grant XML first, pgpub XML second — same preference as the reference."""
    for meta_key in ("grantDocumentMetaData", "pgpubDocumentMetaData"):
        meta = raw.get(meta_key)
        if isinstance(meta, dict):
            uri = _coerce_str(meta.get("fileLocationURI"))
            if uri:
                return uri
    return None


def _clean_xml_text(fragment: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG_RE.sub(" ", fragment))).strip()


def _extract_claims_text(xml: str) -> str | None:
    """The <claims>…</claims> section of grant/pgpub XML as plain text.

    One paragraph per <claim>. This is deliberately not a full ICE DTD parser —
    inline markup (<claim-text>, <claim-ref>, <b>, <i>, …) is stripped and its
    text kept in document order, which is all a claim deep-read needs.
    """
    section = _CLAIMS_RE.search(xml)
    if not section:
        return None
    inner = section.group(1)
    blocks = [_clean_xml_text(b) for b in _CLAIM_RE.findall(inner)]
    if not blocks:
        blocks = [_clean_xml_text(inner)]
    blocks = [b for b in blocks if b]
    if not blocks:
        return None
    text = "\n\n".join(blocks)
    if len(text) > _MAX_CLAIMS_CHARS:
        text = text[:_MAX_CLAIMS_CHARS] + "\n\n[truncated]"
    return text


def _normalize_trademark(serial: str, payload: Any) -> TrademarkStatus | None:
    """Normalize the TSDR case-status JSON (shape verified live by the reference)."""
    marks = payload.get("trademarks") if isinstance(payload, dict) else None
    if not isinstance(marks, list) or not marks or not isinstance(marks[0], dict):
        return None
    tm = marks[0]
    st = tm.get("status")
    if not isinstance(st, dict):
        st = {}

    live: bool | None = None
    for probe in (st.get("liveDeadIndicator"), tm.get("liveDeadIndicator")):
        if isinstance(probe, str) and probe.strip():
            live = probe.strip().upper().startswith("L")
            break
    if live is None and _coerce_str(st.get("dateAbandoned")):
        live = False

    classes: list[str] = []
    goods_parts: list[str] = []
    gs = tm.get("gsList") or []
    if isinstance(gs, list):
        for entry in gs:
            if not isinstance(entry, dict):
                continue
            for cls in entry.get("internationalClasses") or []:
                if isinstance(cls, dict):
                    code = _coerce_str(cls.get("code"))
                    if code and code not in classes:
                        classes.append(code)
            desc = _coerce_str(entry.get("description"))
            if desc:
                goods_parts.append(desc)

    owners: list[str] = []
    parties = tm.get("parties")
    groups = parties.get("ownerGroups") if isinstance(parties, dict) else None
    if isinstance(groups, dict):
        for group in groups.values():
            if not isinstance(group, list):
                continue
            for owner in group:
                if isinstance(owner, dict):
                    name = _coerce_str(owner.get("name"))
                    if name and name not in owners:
                        owners.append(name)

    return TrademarkStatus(
        serial=_coerce_str(st.get("serialNumber")) or serial,
        mark=_coerce_str(st.get("markElement")),
        live=live,
        status_text=_coerce_str(st.get("extStatusDesc")) or _coerce_str(st.get("tm5StatusDesc")),
        owner="; ".join(owners) if owners else None,
        classes=classes,
        goods_services="; ".join(goods_parts) if goods_parts else None,
        raw=tm,
    )


# ---------------------------------------------------------------------------
# TTL cache — port of the reference's SimpleCache, kept to a dict + timestamps
# ---------------------------------------------------------------------------

class _TtlCache:
    def __init__(self, max_entries: int = _CACHE_MAX_ENTRIES) -> None:
        self._entries: dict[tuple, tuple[float, Any]] = {}
        self._max = max_entries

    def get(self, key: tuple) -> Any | None:
        hit = self._entries.get(key)
        if hit is None:
            return None
        expires_at, value = hit
        if time.monotonic() > expires_at:
            del self._entries[key]
            return None
        return value

    def set(self, key: tuple, value: Any, ttl: float = _CACHE_TTL) -> None:
        if len(self._entries) >= self._max and key not in self._entries:
            oldest = min(self._entries, key=lambda k: self._entries[k][0])
            del self._entries[oldest]
        self._entries[key] = (time.monotonic() + ttl, value)


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------

class UsptoClient:
    """Async USPTO client. One instance per clearance run is fine; the cache
    is per-instance, so shared instances also share the 5-minute GET cache."""

    def __init__(self, odp_key: str | None = None, tsdr_key: str | None = None):
        self._odp_key = settings.uspto_odp_api_key if odp_key is None else odp_key
        self._tsdr_key = settings.uspto_tsdr_api_key if tsdr_key is None else tsdr_key
        self._cache = _TtlCache()
        self._retry_base_delay = 1.0  # seconds; tests set 0 to skip backoff waits

    def __repr__(self) -> str:  # keys must never leak through repr
        return (
            f"UsptoClient(odp_available={self.odp_available}, "
            f"tsdr_available={self.tsdr_available})"
        )

    @property
    def odp_available(self) -> bool:
        return bool(self._odp_key)

    @property
    def tsdr_available(self) -> bool:
        return bool(self._tsdr_key)

    # ------------------------------------------------------------- plumbing

    def _mask(self, text: str) -> str:
        """Mask API keys anywhere they could leak into errors or logs."""
        if not text:
            return text
        out = _KEY_PARAM_RE.sub(r"\1[MASKED]", text)
        for key in (
            self._odp_key,
            self._tsdr_key,
            settings.uspto_odp_api_key,
            settings.uspto_tsdr_api_key,
        ):
            if key and len(key) >= 8:
                out = out.replace(key, "[MASKED]")
        return out

    def _require_odp(self) -> str:
        if not self._odp_key:
            raise ClearanceConfigError(
                "USPTO ODP API key not configured — set USPTO_ODP_API_KEY "
                "(register at https://data.uspto.gov/apis/getting-started)"
            )
        return self._odp_key

    def _require_tsdr(self) -> str:
        if not self._tsdr_key:
            raise ClearanceConfigError(
                "USPTO TSDR API key not configured — set USPTO_TSDR_API_KEY (separate from "
                "the ODP key; register at https://account.uspto.gov/profile/api-manager)"
            )
        return self._tsdr_key

    async def _send_once(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        json_body: Any = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> httpx.Response:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.request(
                method, url, headers=headers, params=params, data=data, json=json_body
            )

    async def _send(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        json_body: Any = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> httpx.Response:
        """Retry 5xx/429 and timeouts with exponential backoff, 3 attempts."""
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = await self._send_once(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    data=data,
                    json_body=json_body,
                    timeout=timeout,
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == _MAX_ATTEMPTS:
                    raise UsptoApiError(
                        0, "USPTO request failed after retries", self._mask(str(exc))
                    ) from exc
                log.warning(
                    "uspto_request_retry",
                    url=self._mask(url),
                    attempt=attempt,
                    error=self._mask(str(exc)),
                )
            else:
                if response.status_code not in _RETRY_STATUSES or attempt == _MAX_ATTEMPTS:
                    return response
                log.warning(
                    "uspto_request_retry",
                    url=self._mask(url),
                    attempt=attempt,
                    status=response.status_code,
                )
            delay = self._retry_base_delay * (2 ** (attempt - 1))
            await asyncio.sleep(delay + random.random() * delay * 0.5)
        raise UsptoApiError(0, "USPTO request failed after retries")  # unreachable

    def _parse_json_response(self, response: httpx.Response, label: str) -> Any:
        text = response.text
        if response.status_code >= 400:
            detail = ""
            try:
                parsed = response.json()
                if isinstance(parsed, dict):
                    detail = parsed.get("detailedMessage") or parsed.get("message") or ""
            except ValueError:
                detail = text[:200]
            if response.status_code == 404:
                # ODP answers 404 for zero hits — callers translate, never surface.
                raise UsptoApiError(404, "No matching records found", self._mask(detail))
            raise UsptoApiError(
                response.status_code,
                f"{label} error (HTTP {response.status_code})",
                self._mask(detail),
            )
        if not text.strip():
            raise UsptoApiError(502, f"Empty response from {label} (possibly transient)")
        return response.json()

    async def _odp_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, str] | None = None,
        json_body: Any = None,
    ) -> Any:
        key = self._require_odp()
        url = f"{ODP_BASE}{path}"
        cache_key: tuple | None = None
        if method == "GET":
            cache_key = (method, url, tuple(sorted((params or {}).items())))
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached
        response = await self._send(
            method,
            url,
            headers={"X-API-KEY": key, "Accept": "application/json"},
            params=params,
            data=data,
            json_body=json_body,
        )
        payload = self._parse_json_response(response, "USPTO API")
        if cache_key is not None:
            self._cache.set(cache_key, payload)
        return payload

    # ------------------------------------------------------------ ODP: patents

    async def search_applications(
        self,
        query: str,
        limit: int = 25,
        offset: int = 0,
        sort: str = "applicationMetaData.filingDate desc",
    ) -> SearchResult:
        """GET /api/v1/patent/applications/search — 404 means zero hits."""
        params = {"q": query, "limit": limit, "offset": offset, "sort": sort}
        try:
            payload = await self._odp_json("GET", _SEARCH_PATH, params=params)
        except UsptoApiError as exc:
            if exc.status == 404:
                log.info("uspto_search_zero_hits", query=query)
                return SearchResult(total=0, items=[])
            raise
        result = _normalize_search(payload, limit)
        log.info("uspto_search", query=query, total=result.total, returned=len(result.items))
        return result

    async def get_application(self, app_number: str) -> AppRecord | None:
        try:
            payload = await self._odp_json(
                "GET", f"/api/v1/patent/applications/{quote(app_number, safe='')}"
            )
        except UsptoApiError as exc:
            if exc.status == 404:
                return None
            raise
        bag = payload.get("patentFileWrapperDataBag") if isinstance(payload, dict) else None
        if not isinstance(bag, list) or not bag or not isinstance(bag[0], dict):
            return None
        return _normalize_wrapper(bag[0])

    async def get_continuity(self, app_number: str) -> dict | None:
        """The patent-family (parent/child continuity) record, raw."""
        try:
            payload = await self._odp_json(
                "GET", f"/api/v1/patent/applications/{quote(app_number, safe='')}/continuity"
            )
        except UsptoApiError as exc:
            if exc.status == 404:
                return None
            raise
        if not isinstance(payload, dict):
            return None
        bag = payload.get("patentFileWrapperDataBag")
        if isinstance(bag, list) and bag and isinstance(bag[0], dict):
            return bag[0]
        return payload

    async def get_claims_text(self, record: AppRecord) -> str | None:
        """Claims text from the grant/pgpub XML, or None when unavailable.

        None is honest: full text exists only for granted patents and published
        applications — unpublished filings have no public text to read.
        """
        uri = _file_location_uri(record.raw)
        if not uri:
            return None
        if not uri.startswith(ODP_BASE):
            # The URI comes from the API itself and points at the ODP host;
            # anything else is refused rather than fetched with our key.
            log.warning("uspto_xml_unexpected_host", uri=self._mask(uri))
            return None
        key = self._require_odp()
        cache_key = ("GET", uri, ())
        xml = self._cache.get(cache_key)
        if xml is None:
            response = await self._send(
                "GET", uri, headers={"X-API-KEY": key}, timeout=_XML_TIMEOUT
            )
            if response.status_code >= 400:
                log.warning(
                    "uspto_xml_download_failed",
                    uri=self._mask(uri),
                    status=response.status_code,
                )
                return None
            xml = response.text
            # USPTO limits XML downloads to ~20 per URL per YEAR — cache long.
            self._cache.set(cache_key, xml, ttl=_XML_CACHE_TTL)
        return _extract_claims_text(xml)

    # ------------------------------------------------------------------ TSDR

    async def get_trademark_status(self, serial: str) -> TrademarkStatus | None:
        """TSDR case status by 8-digit serial number. None when no record exists.

        This is the only programmatic trademark surface — see the module
        docstring for why word-mark search is NOT_SEARCHED + TRADEMARK_SEARCH_LINK.
        """
        key = self._require_tsdr()
        digits = re.sub(r"[,\s]", "", serial)
        url = f"{TSDR_BASE}/ts/cd/casestatus/sn{digits}/info.json"
        cache_key = ("GET", url, ())
        payload = self._cache.get(cache_key)
        if payload is None:
            response = await self._send(
                "GET", url, headers={"USPTO-API-KEY": key}, timeout=_TSDR_TIMEOUT
            )
            if response.status_code == 404:
                return None
            if response.status_code >= 400:
                raise UsptoApiError(
                    response.status_code,
                    f"TSDR API error (HTTP {response.status_code})",
                    self._mask(response.text[:200]),
                )
            try:
                payload = response.json()
            except ValueError as exc:  # TSDR defaults to XML off the .json path
                raise UsptoApiError(
                    502, "TSDR returned a non-JSON response", self._mask(response.text[:200])
                ) from exc
            self._cache.set(cache_key, payload)
        return _normalize_trademark(digits, payload)

    # ----------------------------------------------------------------- DSAPI

    async def search_rejections(self, query: str, limit: int = 20) -> list[dict]:
        """Office-action rejections (101/102/103/112/DP flags), Lucene criteria.

        Form-encoded POST — the DSAPI pattern, same ODP key. 404 = zero hits.
        """
        try:
            payload = await self._odp_json(
                "POST",
                _DSAPI_REJECTIONS_PATH,
                data={"criteria": query or "*:*", "start": "0", "rows": str(limit)},
            )
        except UsptoApiError as exc:
            if exc.status == 404:
                return []
            raise
        block = payload.get("response") if isinstance(payload, dict) else None
        docs = block.get("docs") if isinstance(block, dict) else None
        if not isinstance(docs, list):
            return []
        return [d for d in docs if isinstance(d, dict)][:limit]

    # ------------------------------------------------------------------ PTAB

    async def search_ptab(self, query: str, limit: int = 20) -> list[dict]:
        """PTAB proceedings (IPR/PGR/CBM) matching an ODP query. 404 = zero hits."""
        body = {"q": query, "pagination": {"offset": 0, "limit": limit}}
        try:
            payload = await self._odp_json("POST", _PTAB_SEARCH_PATH, json_body=body)
        except UsptoApiError as exc:
            if exc.status == 404:
                return []
            raise
        bag = payload.get("patentTrialProceedingDataBag") if isinstance(payload, dict) else None
        if not isinstance(bag, list):
            return []
        return [d for d in bag if isinstance(d, dict)][:limit]
