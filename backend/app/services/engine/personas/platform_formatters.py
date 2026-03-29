# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# format_for_platform(profile: AgentProfile, platform: str) -> dict
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta

from app.services.engine.personas.agent_profile_generator import AgentProfile


def _random_in_range(low: int, high: int, influence: float) -> int:
    """Generate a random int biased by influence weight (0-1)."""
    base = low + int((high - low) * influence)
    jitter = random.randint(-int((high - low) * 0.1), int((high - low) * 0.1))
    return max(low, min(high, base + jitter))


def _random_date(years_back_min: int, years_back_max: int) -> str:
    """Generate a random date string within a range."""
    days_back = random.randint(years_back_min * 365, years_back_max * 365)
    dt = datetime.now() - timedelta(days=days_back)
    return dt.strftime("%Y-%m-%d")


def format_for_platform(profile: AgentProfile, platform: str) -> dict:
    """Route to the correct platform formatter."""
    formatters = {
        "twitter_x": format_for_twitter_x,
        "twitter": format_for_twitter_x,
        "reddit": format_for_reddit,
        "linkedin": format_for_linkedin,
        "instagram": format_for_instagram,
        "hacker_news": format_for_hacker_news,
        "discord": format_for_discord,
    }
    formatter = formatters.get(platform, format_for_custom)
    return formatter(profile)


def format_for_twitter_x(profile: AgentProfile) -> dict:
    """Returns dict matching CAMEL-AI Twitter agent spec."""
    return {
        "user_id": int(hashlib.md5(profile.username.encode()).hexdigest(), 16) % 10**9,
        "username": profile.username,
        "name": profile.display_name,
        "bio": profile.bio[:160],
        "following_count": _random_in_range(50, 5000, profile.influence_weight),
        "follower_count": _random_in_range(10, 50000, profile.influence_weight),
        "verified": profile.influence_weight > 0.7,
        "created_at": _random_date(1, 10),
        "location": profile.country,
        "interests": profile.interests[:5],
        "tweet_count": _random_in_range(100, 50000, profile.influence_weight),
        "persona_type": profile.persona_type,
        "mbti": profile.mbti,
        "political_lean": profile.political_lean,
        "sentiment_baseline": profile.sentiment_baseline,
    }


def format_for_reddit(profile: AgentProfile) -> dict:
    """Returns dict matching CAMEL-AI Reddit agent spec."""
    return {
        "username": profile.username,
        "karma": _random_in_range(100, 50000, profile.influence_weight),
        "post_karma": _random_in_range(50, 30000, profile.influence_weight),
        "comment_karma": _random_in_range(50, 20000, profile.influence_weight),
        "cake_day": _random_date(1, 12),
        "bio": profile.bio,
        "subreddits": [i.lower().replace(" ", "") for i in profile.interests[:8]],
        "account_age_days": random.randint(30, 4000),
        "persona_type": profile.persona_type,
        "mbti": profile.mbti,
        "political_lean": profile.political_lean,
        "sentiment_baseline": profile.sentiment_baseline,
    }


def format_for_linkedin(profile: AgentProfile) -> dict:
    """Returns dict matching CAMEL-AI LinkedIn agent spec."""
    return {
        "username": profile.username,
        "name": profile.display_name,
        "headline": f"{profile.profession} | {profile.interests[0] if profile.interests else ''}",
        "bio": profile.bio,
        "connections": _random_in_range(50, 5000, profile.influence_weight),
        "location": profile.country,
        "industry": profile.interests[0] if profile.interests else "Technology",
        "experience_years": max(1, profile.age - 22),
        "education": profile.profession,
        "skills": profile.interests[:10],
        "persona_type": profile.persona_type,
        "mbti": profile.mbti,
        "sentiment_baseline": profile.sentiment_baseline,
    }


def format_for_instagram(profile: AgentProfile) -> dict:
    """Returns dict for Instagram agent spec."""
    return {
        "username": profile.username,
        "name": profile.display_name,
        "bio": profile.bio[:150],
        "followers": _random_in_range(100, 100000, profile.influence_weight),
        "following": _random_in_range(100, 5000, profile.influence_weight),
        "posts_count": _random_in_range(10, 2000, profile.influence_weight),
        "verified": profile.influence_weight > 0.8,
        "location": profile.country,
        "interests": profile.interests[:5],
        "persona_type": profile.persona_type,
        "sentiment_baseline": profile.sentiment_baseline,
    }


def format_for_hacker_news(profile: AgentProfile) -> dict:
    """Returns dict for Hacker News agent spec."""
    return {
        "username": profile.username,
        "karma": _random_in_range(10, 20000, profile.influence_weight),
        "created": _random_date(1, 15),
        "about": profile.bio[:200],
        "submissions": _random_in_range(1, 500, profile.influence_weight),
        "interests": profile.interests[:5],
        "persona_type": profile.persona_type,
        "mbti": profile.mbti,
        "sentiment_baseline": profile.sentiment_baseline,
    }


def format_for_discord(profile: AgentProfile) -> dict:
    """Returns dict for Discord agent spec."""
    discriminator = random.randint(1000, 9999)
    return {
        "username": f"{profile.username}#{discriminator}",
        "display_name": profile.display_name,
        "bio": profile.bio[:190],
        "roles": [profile.persona_type],
        "joined_at": _random_date(0, 3),
        "message_count": _random_in_range(50, 10000, profile.influence_weight),
        "interests": profile.interests[:5],
        "persona_type": profile.persona_type,
        "sentiment_baseline": profile.sentiment_baseline,
    }


def format_for_custom(profile: AgentProfile) -> dict:
    """Generic format for unknown platforms."""
    return {
        "username": profile.username,
        "display_name": profile.display_name,
        "bio": profile.bio,
        "influence_weight": profile.influence_weight,
        "interests": profile.interests,
        "persona_type": profile.persona_type,
        "mbti": profile.mbti,
        "political_lean": profile.political_lean,
        "sentiment_baseline": profile.sentiment_baseline,
    }
