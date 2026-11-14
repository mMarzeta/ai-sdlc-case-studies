import json
from pathlib import Path
import pytest
from tools.mailer import (
    render_execution_summary_email,
    send_campaign_pitches,
)
from tools.syndicator import build_social_launch_kit


def test_pitch_loop_persists_state_after_each_email(tmp_path):
    post_dir = tmp_path / "2026-11-17-tv-screentime"
    post_dir.mkdir()
    campaign = {
        "slug": "ios-screen-time-sony-bravia-home-assistant-adb",
        "title": "iOS-Style Screen Time for Sony Bravia",
        "pitches": [
            {"newsletter_id": "python_weekly", "enabled": True, "subject": "Subj 1", "body": "Body 1"},
            {"newsletter_id": "tldr_ai", "enabled": True, "subject": "Subj 2", "body": "Body 2"},
        ],
    }
    newsletters = {
        "python_weekly": {"name": "Python Weekly", "to_email": "rahim@pythonweekly.com", "active": True},
        "tldr_ai": {"name": "TLDR AI", "to_email": "submissions@tldr.tech", "active": True},
    }
    sent_calls = []

    def flaky_send(msg, smtp_cfg):
        sent_calls.append(msg["To"])
        if len(sent_calls) == 2:
            raise RuntimeError("Simulated SMTP drop on 2nd pitch")

    with pytest.raises(RuntimeError):
        send_campaign_pitches(
            post_dir,
            campaign,
            newsletters,
            {"from_email": "blog@newsletter.marzeta.pl", "reply_to": "contact@marzeta.pl"},
            send_fn=flaky_send,
        )

    state = json.loads((post_dir / "state.json").read_text())
    assert "python_weekly" in state["pitches_sent"]
    assert "tldr_ai" not in state["pitches_sent"]

    # Retry should only send the 2nd one
    send_campaign_pitches(
        post_dir,
        campaign,
        newsletters,
        {"from_email": "blog@newsletter.marzeta.pl", "reply_to": "contact@marzeta.pl"},
        send_fn=lambda m, c: sent_calls.append(m["To"]),
    )
    assert len(sent_calls) == 3
    assert sent_calls[-1] == "submissions@tldr.tech"


def test_summary_email_contains_verbatim_sent_emails_and_hn_link():
    campaign = {
        "slug": "test-post",
        "title": "Test AI SDLC Post",
        "social_kit": {
            "hacker_news": {"title": "Show HN: Test AI SDLC Post"},
            "reddit": [{"subreddit": "r/ExperiencedDevs", "title": "Reddit Title", "body_markdown": "Reddit Body"}],
        },
    }
    kit = build_social_launch_kit(
        campaign,
        "https://blog.marzeta.pl/test-post/",
        "https://github.com/mMarzeta/ai-sdlc-case-studies",
    )
    assert "news.ycombinator.com/submitlink?" in kit["hacker_news_submit_url"]

    subj, txt, html = render_execution_summary_email(
        campaign=campaign,
        actions={
            "post_url": "https://blog.marzeta.pl/test-post/",
            "github_url": "https://github.com/mMarzeta/ai-sdlc-case-studies/tree/main/case-studies/test",
        },
        pitch_results=[
            {
                "newsletter_id": "python_weekly",
                "newsletter_name": "Python Weekly",
                "to_email": "rahim@pythonweekly.com",
                "subject": "Exact Pitch Subject",
                "body": "Exact verbatim pitch body sent to editor.",
                "status": "sent",
                "sent_at": "2026-11-17T08:05:02Z",
            }
        ],
        launch_kit=kit,
    )
    assert "rahim@pythonweekly.com" in txt
    assert "Exact Pitch Subject" in txt
    assert "Exact verbatim pitch body sent to editor." in txt
    assert "Exact verbatim pitch body sent to editor." in html
    assert "news.ycombinator.com/submitlink?" in html


def test_build_social_launch_kit_preserves_subreddit_starting_with_r():
    campaign = {
        "slug": "rust-post",
        "title": "Rust Post",
        "social_kit": {
            "reddit": [{"subreddit": "r/rust", "title": "T", "body_markdown": "B"}],
        },
    }
    kit = build_social_launch_kit(campaign, "https://blog.marzeta.pl/rust-post/", "https://github.com/mMarzeta/ai-sdlc-case-studies")
    assert kit["reddit_posts"][0]["subreddit"] == "r/rust"
    assert "https://www.reddit.com/r/rust/submit?" in kit["reddit_posts"][0]["submit_url"]
