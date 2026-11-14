from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any


def build_social_launch_kit(
    campaign: dict[str, Any],
    post_url: str,
    github_url: str,
) -> dict[str, Any]:
    social = campaign.get("social_kit", {})
    hn_cfg = social.get("hacker_news", {})
    hn_title = hn_cfg.get("title") or f"Show HN: {campaign.get('title', '')}"

    hn_params = urllib.parse.urlencode({"u": post_url, "t": hn_title})
    hn_submit_url = f"https://news.ycombinator.com/submitlink?{hn_params}"

    lobsters_params = urllib.parse.urlencode({"url": post_url, "title": hn_title})
    lobsters_submit_url = f"https://lobste.rs/stories/new?{lobsters_params}"

    reddit_posts = []
    for item in social.get("reddit", []):
        sub = item.get("subreddit", "r/ExperiencedDevs")
        sub_clean = sub.removeprefix("r/").removeprefix("/")
        r_title = item.get("title", campaign.get("title", ""))
        r_body = item.get("body_markdown", "")
        r_params = urllib.parse.urlencode({"title": r_title, "text": r_body})
        reddit_posts.append(
            {
                "subreddit": f"r/{sub_clean}",
                "title": r_title,
                "body_markdown": r_body,
                "submit_url": f"https://www.reddit.com/r/{sub_clean}/submit?{r_params}",
            }
        )

    return {
        "hacker_news_title": hn_title,
        "hacker_news_submit_url": hn_submit_url,
        "lobsters_submit_url": lobsters_submit_url,
        "reddit_posts": reddit_posts,
        "github_url": github_url,
    }


def syndicate_to_devto(
    campaign: dict[str, Any],
    markdown_body: str,
    post_url: str,
    api_key: str | None,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not api_key:
        return {"status": "skipped", "reason": "DEVTO_API_KEY not set"}
    if dry_run:
        return {"status": "dry-run", "canonical_url": post_url}

    tags = [t.lower().replace("-", "")[:20] for t in campaign.get("tags", [])[:4]]
    payload = {
        "article": {
            "title": campaign["title"],
            "published": True,
            "body_markdown": markdown_body,
            "canonical_url": post_url,
            "tags": tags,
        }
    }
    req = urllib.request.Request(
        "https://dev.to/api/articles",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    req.add_header("api-key", api_key)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "MarzTech-BlogCtl/1.0")
    with urllib.request.urlopen(req, timeout=20) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return {"status": "published", "url": res.get("url")}
