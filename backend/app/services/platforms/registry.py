# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# get_adapter(platform_id: str) -> BasePlatformAdapter
# list_available_platforms() -> list[PlatformInfo]
# register_adapter(adapter_class: type) -> None
# ─────────────────────────────────────────────────────────
from __future__ import annotations

from pydantic import BaseModel

from app.services.platforms.base_adapter import BasePlatformAdapter

PLATFORM_REGISTRY: dict[str, type[BasePlatformAdapter]] = {}


class PlatformInfo(BaseModel):
    platform_id: str
    platform_name: str
    supports_reactions: bool
    supports_dms: bool
    max_post_length: int
    max_comment_length: int


def register_adapter(adapter_class: type[BasePlatformAdapter]):
    """Decorator to register a platform adapter."""
    PLATFORM_REGISTRY[adapter_class.platform_id] = adapter_class
    return adapter_class


def get_adapter(platform_id: str) -> BasePlatformAdapter:
    """Instantiate and return a platform adapter by ID."""
    cls = PLATFORM_REGISTRY.get(platform_id)
    if not cls:
        raise ValueError(f"Unknown platform: {platform_id}. Available: {list(PLATFORM_REGISTRY)}")
    return cls()


def list_available_platforms() -> list[PlatformInfo]:
    """List all registered platform adapters."""
    platforms = []
    for cls in PLATFORM_REGISTRY.values():
        platforms.append(PlatformInfo(
            platform_id=cls.platform_id,
            platform_name=cls.platform_name,
            supports_reactions=cls.supports_reactions,
            supports_dms=cls.supports_dms,
            max_post_length=cls.max_post_length,
            max_comment_length=cls.max_comment_length,
        ))
    return platforms


def load_all_adapters():
    """Import all adapter modules to trigger registration."""
    from app.services.platforms.adapters import (  # noqa: F401
        custom,
        discord,
        facebook,
        hacker_news,
        instagram,
        linkedin,
        news_comments,
        reddit,
        threads,
        tiktok,
        twitter_x,
        youtube,
    )
