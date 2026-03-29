# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# process_image(image_bytes: bytes, filename: str) -> ProcessedAsset
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import base64

import structlog

from app.core.llm_client import llm_complete

logger = structlog.get_logger()

VISION_PROMPT = """Describe this image in detail including all visible text, people, objects, context, sentiment, and any information that would be relevant for predicting social media reactions. Be comprehensive but concise."""


async def process_image(image_bytes: bytes, filename: str) -> dict:
    """Use Claude vision API to generate text description of an image."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    media_type = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "png": "image/png", "gif": "image/gif", "webp": "image/webp",
    }.get(ext, "image/png")

    b64 = base64.b64encode(image_bytes).decode()

    # Use litellm with vision content
    description = await llm_complete(
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
                {"type": "text", "text": VISION_PROMPT},
            ],
        }],
        max_tokens=2000,
    )

    logger.info("image_processed", filename=filename, desc_length=len(description))
    return {
        "extracted_text": description,
        "metadata": {
            "media_type": media_type,
            "file_size": len(image_bytes),
            "description_tokens": len(description.split()),
        },
    }
