# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# process_article(source_url: str | None, html_content: str | None) -> ProcessedAsset
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import re

import httpx
import structlog

logger = structlog.get_logger()


def _extract_text_from_html(html: str) -> dict:
    """Extract article body text from HTML using simple heuristics."""
    # Strip script/style tags
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)

    # Extract title
    title = ""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL)
    if title_match:
        title = title_match.group(1).strip()

    # Extract meta description
    description = ""
    desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']', html)
    if desc_match:
        description = desc_match.group(1).strip()

    # Extract paragraph text
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL)
    body_text = "\n\n".join(
        re.sub(r"<[^>]+>", "", p).strip()
        for p in paragraphs
        if len(re.sub(r"<[^>]+>", "", p).strip()) > 50
    )

    # Extract h1/h2 headings
    headings = re.findall(r"<h[12][^>]*>(.*?)</h[12]>", html, re.DOTALL)
    heading_text = "\n".join(re.sub(r"<[^>]+>", "", h).strip() for h in headings)

    return {
        "title": title,
        "description": description,
        "headings": heading_text,
        "body": body_text,
    }


async def process_article(
    source_url: str | None = None,
    html_content: str | None = None,
) -> dict:
    """Extract article text from a URL or raw HTML."""
    html = html_content or ""

    if source_url and not html:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                response = await client.get(source_url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; SaibylBot/1.0)",
                })
                response.raise_for_status()
                html = response.text
        except Exception as e:
            logger.error("article_fetch_failed", url=source_url, error=str(e))
            return {
                "extracted_text": f"Failed to fetch article from {source_url}: {e}",
                "metadata": {"source_url": source_url, "error": str(e)},
            }

    if not html:
        return {"extracted_text": "", "metadata": {"error": "No content provided"}}

    extracted = _extract_text_from_html(html)

    parts = []
    if extracted["title"]:
        parts.append(f"# {extracted['title']}")
    if extracted["description"]:
        parts.append(f"*{extracted['description']}*")
    if extracted["headings"]:
        parts.append(extracted["headings"])
    if extracted["body"]:
        parts.append(extracted["body"])

    full_text = "\n\n".join(parts)

    logger.info("article_processed", url=source_url, chars=len(full_text))
    return {
        "extracted_text": full_text,
        "metadata": {
            "source_url": source_url,
            "title": extracted["title"],
            "word_count": len(full_text.split()),
        },
    }
