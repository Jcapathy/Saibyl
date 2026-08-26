"""The production domains must be allowed however the config is set.

**Written after taking the live site down.** `render.yaml` carried
`https://saibyl.com` in `CORS_ORIGINS`, committed and merged before DNS moved.
It never took effect: Render's GitHub integration deploys code on push, while
Blueprint configuration needs a separate sync. The domain went live pointing at
a backend that refused its origin, so the marketing pages worked perfectly and
everything behind the login failed. Nothing in the test suite could have caught
it, because nothing here had an opinion about which origins are allowed.

The lesson is narrower than "test CORS". It is that a control which only exists
in a deploy path you have not verified is not a control. The product's own
domains now live in code, which deploys on push, and this pins them there.
"""
from __future__ import annotations

import pytest


def _origins(configured: str) -> list[str]:
    """The origin list `create_app` would build for a given config value."""
    from app.core.config import settings

    original = settings.cors_origins
    settings.cors_origins = configured
    try:
        from app.main import create_app

        app = create_app()
        for middleware in app.user_middleware:
            options = getattr(middleware, "kwargs", {}) or {}
            if "allow_origins" in options:
                return list(options["allow_origins"])
        raise AssertionError("no CORS middleware found on the app")
    finally:
        settings.cors_origins = original


PRODUCTION = ("https://saibyl.com", "https://www.saibyl.com")


@pytest.mark.parametrize(
    "configured",
    [
        "https://saibyl-frontend.onrender.com",
        "http://localhost:3000",
        "https://saibyl.com,https://www.saibyl.com,https://saibyl-frontend.onrender.com",
        "",
    ],
    ids=["render-subdomain-only", "local-default", "fully-configured", "empty"],
)
def test_the_production_domains_are_always_allowed(configured):
    """Including when config names none of them, which is the case that broke.

    The `render-subdomain-only` parameter is the exact production value on the
    day `saibyl.com` went live.
    """
    allowed = _origins(configured)

    for origin in PRODUCTION:
        assert origin in allowed, (
            f"{origin} is not allowed when CORS_ORIGINS is {configured!r}. "
            f"The site would load and every API call would fail."
        )


def test_configured_origins_are_still_honoured():
    """Code adds to config, it does not replace it. Staging and preview hosts
    only ever arrive through the environment."""
    allowed = _origins("https://staging.example.com,https://preview.example.com")

    assert "https://staging.example.com" in allowed
    assert "https://preview.example.com" in allowed


def test_no_origin_is_listed_twice():
    """A duplicate is harmless to the browser and a sign the merge logic is
    wrong, which matters the next time somebody edits it."""
    allowed = _origins(
        "https://saibyl.com,https://saibyl-frontend.onrender.com,https://saibyl.com"
    )

    assert len(allowed) == len(set(allowed)), allowed


def test_an_unrelated_origin_is_not_allowed():
    """The guard has to still be a guard. If this ever passes with a wildcard,
    the middleware is allowing everything and the tests above prove nothing."""
    allowed = _origins("https://saibyl-frontend.onrender.com")

    assert "https://evil.example" not in allowed
    assert "*" not in allowed
