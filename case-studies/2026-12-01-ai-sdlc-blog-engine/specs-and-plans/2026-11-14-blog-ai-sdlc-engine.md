# Blog AI-SDLC Workspace & Promotion Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform `~/projects/blog` on the Raspberry Pi into a unified AI-SDLC publishing and promotion engine (`blogctl`) that positions `blog.marzeta.pl` and `github.com/mMarzeta/ai-sdlc-case-studies` for CTO / Head of AI roles, automates Tuesday `08:05 UTC` GitHub case-study exports and Mailgun newsletter pitches, and emails a full verbatim execution report to `contact@marzeta.pl`.

**Architecture:** A modular, stdlib + `PyYAML` Python 3 package under `~/projects/blog/tools/` consisting of `ghost_client.py` (Ghost 6 Admin API via HS256 JWT), `github_showcase.py` (secret/IP scrubber + isolated Git exporter to `mMarzeta/ai-sdlc-case-studies`), `mailer.py` (idempotent Mailgun SMTP newsletter pitcher + HTML/text audit report mailer), `syndicator.py` (Dev.to/Hashnode canonical cross-poster + 1-click HN/Lobste.rs/Reddit kit generator), and `blogctl.py` (CLI + cron entry point). All posts live in self-contained directories under `~/projects/blog/posts/<YYYY-MM-DD-slug>/`.

**Tech Stack:** Python 3.13 (`urllib.request`, `smtplib`, `email`, `hmac`, `hashlib`, `json`, `re`, `subprocess`, `pathlib`, `PyYAML`), `pytest`, Ghost 6 Admin API, Mailgun SMTP (`smtp.eu.mailgun.org:587`), Git / GitHub (`mMarzeta/ai-sdlc-case-studies`).

**Spec:** `~/projects/docs/superpowers/specs/2026-11-14-blog-ai-sdlc-engine-design.md`

## Global Constraints

- **Target host & path:** Raspberry Pi (`raspberrypi` / `192.0.2.10`, `~/projects/blog`).
- **Zero virtualenv dependency for cron:** Only Python 3 standard library + system `PyYAML` (`yaml`) allowed in `tools/*.py`.
- **Ghost 6 local API headers:** Every request to `http://127.0.0.1:2368/ghost/api/admin/` MUST include `X-Forwarded-Proto: https` and `Authorization: Ghost <jwt>`. HTML updates MUST pass `?source=html`.
- **GitHub isolation:** All git commits/pushes for the public portfolio happen strictly inside `~/projects/blog/.github-showcase-repo/` (`git@github.com:mMarzeta/ai-sdlc-case-studies.git`), never in `~/projects`.
- **Email headers:** Newsletter pitches send via `smtp.eu.mailgun.org:587` with `From: "Maciej Marzęta" <blog@newsletter.marzeta.pl>` and `Reply-To: contact@marzeta.pl`. Audit summary reports send to `contact@marzeta.pl`.
- **Zero bot submissions to HN/Reddit:** Never POST automatically to Hacker News or Reddit; generate 1-click `submitlink` URLs and copy-paste markdown in the summary report email.
- **Fail-closed secret scrubbing:** Abort GitHub export with `ScrubberSecurityError` if any high-entropy token or private credential pattern remains after path/IP replacement.

## Review Focus

1. **Ghost Admin API 301 redirect on localhost:** Requests to `http://127.0.0.1:2368` without `X-Forwarded-Proto: https` trigger a 301 redirect that strips the `Authorization` header; pinned by `test_ghost_client_sets_forwarded_proto_and_jwt` in Task 1.
2. **Idempotent AI-SDLC Blueprint injection into Ghost post HTML:** Running `inject_blueprint_html` multiple times on a post must replace the existing `<section id="ai-sdlc-blueprint">...</section>` block rather than appending duplicate blocks; pinned by `test_inject_blueprint_html_is_idempotent` in Task 1.
3. **Secret or LAN IP leakage in exported GitHub files:** A file containing `192.0.2.10`, `./src/...`, or an API token (`ghp_<token>`, `GHOST_DB_PASSWORD=<secret>`) must have LAN IPs/paths normalized and must raise `ScrubberSecurityError` on secret patterns; pinned by `test_scrubber_normalizes_paths_ips_and_blocks_secrets` in Task 2.
4. **Partial SMTP failure during newsletter pitch loop:** If SMTP fails on the 2nd newsletter after the 1st succeeded, `state.json` must persist the 1st newsletter in `pitches_sent` immediately so re-running does not double-send to the 1st editor; pinned by `test_pitch_loop_persists_state_after_each_email` in Task 3.
5. **Premature cron execution on unapproved or unpublished posts:** `cron-run` must skip any post where `approved` is `false` or Ghost API reports `status != "published"` (e.g. `scheduled` or `draft`); pinned by `test_cron_run_skips_unapproved_or_unpublished_posts` in Task 4.

---

### Task 1: Ghost Admin API Client & Blueprint HTML Injector (`tools/ghost_client.py`)

**Files:**
- Create: `~/projects/blog/tools/__init__.py`
- Create: `~/projects/blog/tools/ghost_client.py`
- Test: `~/projects/blog/tests/test_ghost_client.py`

**Interfaces:**
- Produces:
  - `make_ghost_jwt(api_key: str, now: int | None = None) -> str`
  - `render_blueprint_html(metrics: dict, case_study_url: str, summary_points: list[str]) -> str`
  - `inject_blueprint_html(existing_html: str, blueprint_html: str) -> str`
  - `class GhostAdminClient`:
    - `__init__(self, api_key: str, base_url: str = "http://127.0.0.1:2368")`
    - `get_post_by_slug(self, slug: str) -> dict | None`
    - `get_post_by_id(self, post_id: str) -> dict`
    - `update_post_html(self, post_id: str, html: str, tags: list[dict] | None = None, custom_excerpt: str | None = None) -> dict`
    - `update_page_html(self, slug: str, title: str, html: str, status: str = "published") -> dict`
    - `ensure_tags(self, tags: list[dict]) -> list[dict]`

- [ ] **Step 1: Write the failing tests in `~/projects/blog/tests/test_ghost_client.py`**

```python
import base64
import json
import pytest
from tools.ghost_client import (
    GhostAdminClient,
    inject_blueprint_html,
    make_ghost_jwt,
    render_blueprint_html,
)


def test_ghost_client_sets_forwarded_proto_and_jwt(monkeypatch):
    key_id = "68d253434949d60001d061a0"
    secret_hex = "ab" * 32
    token = make_ghost_jwt(f"{key_id}:{secret_hex}", now=1700000000)
    header_b64, payload_b64, _ = token.split(".")
    header = json.loads(base64.urlsafe_b64decode(header_b64 + "=="))
    payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
    assert header == {"alg": "HS256", "typ": "JWT", "kid": key_id}
    assert payload == {"iat": 1700000000, "exp": 1700000300, "aud": "/admin/"}

    captured = {}

    def fake_urlopen(req, timeout=15):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())

        class Resp:
            def read(self):
                return b'{"posts": [{"id": "p1", "slug": "test", "updated_at": "2026-11-14T00:00:00.000Z"}]}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        return Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = GhostAdminClient(f"{key_id}:{secret_hex}")
    post = client.get_post_by_slug("test")
    assert post["id"] == "p1"
    assert captured["headers"].get("X-forwarded-proto") == "https"
    assert captured["headers"].get("Authorization", "").startswith("Ghost ")


def test_inject_blueprint_html_is_idempotent():
    bp1 = render_blueprint_html(
        metrics={"code_loc": 2120, "test_count": 136, "specs_count": 3, "plans_count": 2, "models_used": ["Gemini 4 Argon"]},
        case_study_url="https://github.com/mMarzeta/ai-sdlc-case-studies/tree/main/case-studies/2026-11-24-torrent-drop",
        summary_points=["Spec-first design eliminated network race conditions."],
    )
    original = "<p>Intro paragraph.</p><p>Conclusion.</p>"
    once = inject_blueprint_html(original, bp1)
    assert 'id="ai-sdlc-blueprint"' in once
    assert once.count('id="ai-sdlc-blueprint"') == 1

    bp2 = render_blueprint_html(
        metrics={"code_loc": 2500, "test_count": 140, "specs_count": 3, "plans_count": 2, "models_used": ["Gemini 4 Argon"]},
        case_study_url="https://github.com/mMarzeta/ai-sdlc-case-studies/tree/main/case-studies/2026-11-24-torrent-drop",
        summary_points=["Updated metric point."],
    )
    twice = inject_blueprint_html(once, bp2)
    assert twice.count('id="ai-sdlc-blueprint"') == 1
    assert "2,500" in twice or "2500" in twice
    assert "Updated metric point." in twice
```

- [ ] **Step 2: Run pytest on Raspberry Pi to verify it fails**

Run: `ssh raspberrypi 'cd ~/projects/blog && python3 -m pytest tests/test_ghost_client.py -v'`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools'`

- [ ] **Step 3: Implement `~/projects/blog/tools/ghost_client.py`**

Implement HS256 JWT signing (`hmac.new(bytes.fromhex(secret_hex), signing_input, hashlib.sha256)`), `GhostAdminClient` methods using `urllib.request.Request` with `X-Forwarded-Proto: https` and `?source=html` on `PUT` calls (fetching current `updated_at` first to satisfy Ghost's optimistic locking), and `render_blueprint_html` / `inject_blueprint_html` wrapped in `<!-- AI-SDLC-BLUEPRINT-START --><section id="ai-sdlc-blueprint">...</section><!-- AI-SDLC-BLUEPRINT-END -->` markers for clean regex replacement.

- [ ] **Step 4: Run pytest to verify Task 1 passes**

Run: `ssh raspberrypi 'cd ~/projects/blog && python3 -m pytest tests/test_ghost_client.py -v'`
Expected: PASS (2 passed)

---

### Task 2: GitHub Showcase Scrubber & Exporter (`tools/github_showcase.py`, `config/scrubber_rules.yaml`)

**Files:**
- Create: `~/projects/blog/config/scrubber_rules.yaml`
- Create: `~/projects/blog/tools/github_showcase.py`
- Test: `~/projects/blog/tests/test_github_showcase.py`

**Interfaces:**
- Produces:
  - `class ScrubberSecurityError(Exception)`
  - `scrub_content(text: str, rules: dict) -> str`
  - `export_case_study(post_dir: Path, repo_dir: Path, rules: dict, git_push: bool = False) -> dict`
  - `update_portfolio_readme(repo_dir: Path, case_studies: list[dict]) -> Path`

- [ ] **Step 1: Write the failing tests in `~/projects/blog/tests/test_github_showcase.py`**

```python
from pathlib import Path
import pytest
from tools.github_showcase import (
    ScrubberSecurityError,
    export_case_study,
     loaded_default_rules,
    scrub_content,
    update_portfolio_readme,
)


def test_scrubber_normalizes_paths_ips_and_blocks_secrets():
    rules = loaded_default_rules()
    raw = (
        "Host at 192.0.2.10 in ~/projects/torrent-drop.\n"
        "See [Spec](./specs-and-plans/2026-11-13-vpn-torrent-drop-design.md)."
    )
    cleaned = scrub_content(raw, rules)
    assert "192.0.2.10" not in cleaned
    assert "192.0.2.10" in cleaned
    assert "~/projects" not in cleaned
    assert "file://~" not in cleaned

    with pytest.raises(ScrubberSecurityError):
        scrub_content("GHOST_DB_PASSWORD" + "=super_secret_prod_pass_12345", rules)

    with pytest.raises(ScrubberSecurityError):
        scrub_content("token = 'ghp_" + "1234567890abcdefghijklmnopqrstuvwx'", rules)


def test_export_case_study_copies_sources_and_updates_readme(tmp_path):
    post_dir = tmp_path / "posts" / "2026-11-24-torrent-drop"
    sources_dir = post_dir / "sources"
    sources_dir.mkdir(parents=True)
    (sources_dir / "spec.md").write_text("# Spec on 192.0.2.10\n")
    (post_dir / "campaign.yaml").write_text(
        "slug: vpn-torrent-drop\n"
        "title: Torrent Drop AI SDLC\n"
        "status: published\n"
        "sdlc_metrics:\n  code_loc: 2120\n  test_count: 136\n  specs_count: 3\n  plans_count: 2\n"
        "github_showcase:\n  enabled: true\n  case_study_dir: case-studies/2026-11-24-torrent-drop\n"
        "  summary: VPN media pipeline\n  include_paths: []\n"
    )
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    result = export_case_study(post_dir, repo_dir, loaded_default_rules(), git_push=False)
    exported_spec = repo_dir / "case-studies/2026-11-24-torrent-drop/specs-and-plans/spec.md"
    assert exported_spec.exists()
    assert "192.0.2.10" in exported_spec.read_text()
    readme = update_portfolio_readme(repo_dir, [result])
    assert "Torrent Drop AI SDLC" in readme.read_text()
    assert "136" in readme.read_text()
```

- [ ] **Step 2: Run pytest on Raspberry Pi to verify it fails**

Run: `ssh raspberrypi 'cd ~/projects/blog && python3 -m pytest tests/test_github_showcase.py -v'`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.github_showcase'`

- [ ] **Step 3: Implement `config/scrubber_rules.yaml` and `tools/github_showcase.py`**

Resolve symlinks in `sources/` when exporting (`Path.resolve()`), skip ignored names (`.env*`, `__pycache__`, `*.db`, `*.sqlite*`, `.pytest_cache`, `*.egg-info`, `*.pyc`, `downloads`, `data`), scrub all text files, generate per-case-study `README.md` + root portfolio `README.md`, and run `git add -A && git commit && git push origin main` inside `repo_dir` when `git_push=True` and `git status --porcelain` is non-empty.

- [ ] **Step 4: Run pytest to verify Task 2 passes**

Run: `ssh raspberrypi 'cd ~/projects/blog && python3 -m pytest tests/test_github_showcase.py -v'`
Expected: PASS

---

### Task 3: Newsletter Pitch Mailer, Launch Kit & Executive Summary Report (`tools/mailer.py`, `tools/syndicator.py`, `config/newsletters.yaml`)

**Files:**
- Create: `~/projects/blog/config/newsletters.yaml`
- Create: `~/projects/blog/tools/syndicator.py`
- Create: `~/projects/blog/tools/mailer.py`
- Test: `~/projects/blog/tests/test_mailer_and_syndicator.py`

**Interfaces:**
- Produces:
  - `build_social_launch_kit(campaign: dict, post_url: str, github_url: str) -> dict` (returns `hacker_news_submit_url`, `lobsters_submit_url`, `reddit_posts`)
  - `send_campaign_pitches(post_dir: Path, campaign: dict, newsletters: dict, smtp_config: dict, dry_run: bool = False, send_fn=None) -> list[dict]`
  - `render_execution_summary_email(campaign: dict, actions: dict, pitch_results: list[dict], launch_kit: dict) -> tuple[str, str, str]` (returns `(subject, text_body, html_body)`)
  - `send_execution_summary_email(smtp_config: dict, subject: str, text_body: str, html_body: str, dry_run: bool = False, send_fn=None) -> dict`

- [ ] **Step 1: Write the failing tests in `~/projects/blog/tests/test_mailer_and_syndicator.py`**

```python
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
        send_campaign_pitches(post_dir, campaign, newsletters, {"from_email": "blog@newsletter.marzeta.pl", "reply_to": "contact@marzeta.pl"}, send_fn=flaky_send)

    state = json.loads((post_dir / "state.json").read_text())
    assert "python_weekly" in state["pitches_sent"]
    assert "tldr_ai" not in state["pitches_sent"]

    # Retry should only send the 2nd one
    results = send_campaign_pitches(post_dir, campaign, newsletters, {"from_email": "blog@newsletter.marzeta.pl", "reply_to": "contact@marzeta.pl"}, send_fn= lambda m, c: sent_calls.append(m["To"]))
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
    kit = build_social_launch_kit(campaign, "https://blog.marzeta.pl/test-post/", "https://github.com/mMarzeta/ai-sdlc-case-studies")
    assert "news.ycombinator.com/submitlink?" in kit["hacker_news_submit_url"]

    subj, txt, html = render_execution_summary_email(
        campaign=campaign,
        actions={"post_url": "https://blog.marzeta.pl/test-post/", "github_url": "https://github.com/mMarzeta/ai-sdlc-case-studies/tree/main/case-studies/test"},
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
```

- [ ] **Step 2: Run pytest on Raspberry Pi to verify it fails**

Run: `ssh raspberrypi 'cd ~/projects/blog && python3 -m pytest tests/test_mailer_and_syndicator.py -v'`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `config/newsletters.yaml`, `tools/syndicator.py`, and `tools/mailer.py`**

Implement `config/newsletters.yaml` (Python Weekly, PyCoder's Weekly, TLDR AI/Dev, Pointer.io, Changelog News, Self-Hosted Weekly), `build_social_launch_kit` with URL-encoded `submitlink` parameters, `send_campaign_pitches` with immediate `state.json` persistence after each email and `Reply-To: contact@marzeta.pl`, and `render_execution_summary_email` producing both plaintext and rich inline-CSS HTML containing every recipient and verbatim email body.

- [ ] **Step 4: Run pytest to verify Task 3 passes**

Run: `ssh raspberrypi 'cd ~/projects/blog && python3 -m pytest tests/test_mailer_and_syndicator.py -v'`
Expected: PASS

---

### Task 4: CLI Orchestrator (`tools/blogctl.py`), Cron Runner, `PLAYBOOK.md` & Post Packages Migration

**Files:**
- Create: `~/projects/blog/tools/blogctl.py`
- Create: `~/projects/blog/PLAYBOOK.md`
- Modify: `~/projects/blog/GEMINI.md`
- Test: `~/projects/blog/tests/test_blogctl_cron.py`

**Interfaces:**
- Consumes: `GhostAdminClient`, `export_case_study`, `update_portfolio_readme`, `send_campaign_pitches`, `build_social_launch_kit`, `render_execution_summary_email`, `send_execution_summary_email`
- Produces:
  - `run_cron_promotions(blog_root: Path, ghost_client, smtp_config: dict, dry_run: bool = False) -> list[dict]`
  - `ingest_sources(post_dir: Path, paths: list[Path], copy_external: bool = True) -> list[Path]`
  - CLI subcommands in `blogctl.py`: `ingest`, `site-setup`, `ghost-sync`, `github-sync`, `promote`, `cron-run`

- [ ] **Step 1: Write the failing test in `~/projects/blog/tests/test_blogctl_cron.py`**

```python
import json
from pathlib import Path
from tools.blogctl import run_cron_promotions


def test_cron_run_skips_unapproved_or_unpublished_posts(tmp_path):
    posts_dir = tmp_path / "posts"
    # Post 1: approved=False
    p1 = posts_dir / "2026-11-24-torrent-drop"
    p1.mkdir(parents=True)
    (p1 / "campaign.yaml").write_text("slug: p1\ntitle: P1\napproved: false\ngithub_showcase:\n  enabled: false\npitches: []\n")

    # Post 2: approved=True, but Ghost says status='scheduled'
    p2 = posts_dir / "2026-11-17-tv-screentime"
    p2.mkdir(parents=True)
    (p2 / "campaign.yaml").write_text("slug: p2\ntitle: P2\napproved: true\ngithub_showcase:\n  enabled: false\npitches: []\n")

    class FakeGhost:
        def get_post_by_slug(self, slug):
            return {"slug": slug, "status": "scheduled"}

    promoted = run_cron_promotions(tmp_path, FakeGhost(), smtp_config={}, dry_run=True)
    assert promoted == []
```

- [ ] **Step 2: Run pytest on Raspberry Pi to verify it fails**

Run: `ssh raspberrypi 'cd ~/projects/blog && python3 -m pytest tests/test_blogctl_cron.py -v'`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.blogctl'`

- [ ] **Step 3: Implement `tools/blogctl.py`, `PLAYBOOK.md`, `GEMINI.md`, and organize the 5 post directories under `posts/`**

1. Implement `blogctl.py` with subcommands:
   - `ingest <post-dir> <file-or-dir>...` (copies artifacts from `~/.gemini/...` and symlinks/copies `docs/superpowers/` specs/plans into `posts/<post-dir>/sources/`).
   - `site-setup` (updates `/about/` Executive Profile, sets `/about-2/` to `draft`, updates Ghost `title`, `description`, `meta_description`, `navigation`, author `bio`, and creates tags `AI-SDLC` and `Architecture`).
   - `ghost-sync <post-dir>` (injects/updates `"The AI-SDLC Blueprint"` HTML block and tags on the Ghost post).
   - `github-sync [--all | <post-dir>]` (scrubs and exports enabled case studies to `.github-showcase-repo` and pushes to `origin/main`).
   - `promote <post-dir> [--dry-run]` and `cron-run [--dry-run]`.
2. Author `~/projects/blog/PLAYBOOK.md` and update `~/projects/blog/GEMINI.md`.
3. Create/migrate the 5 post packages in `~/projects/blog/posts/`:
   - `2026-10-27-cve-watchdog` (`promoted: true`, sources linked from `docs/SECURITY.md`, `scan_critical_cves.sh`, `docs/superpowers/specs/2026-11-11-rss-cve-autopatch-design.md`)
   - `2026-11-03-homelab-64bit` (`promoted: true`, sources linked from `docs/DOCKER_COMPOSE_AUDIT_64BIT.md`, `docs/WALKTHROUGH_64BIT_MODERNIZATION.md`, `docs/RASPBERRY_PI_ENHANCEMENT_REPORT.md`)
   - `2026-11-10-bravia65-debloat` (`promoted: true`, migrated from `drafts/ghost_blog_post_bravia65_draft.md` + `docs/bravia65-tvs/` specs/plans)
   - `2026-11-17-tv-screentime` (`approved: true`, `promoted: false`, migrated from `drafts/ghost_blog_post_tv_screentime.md` + `docs/bravia65-tvs/2026-11-08-tv-usage-tracking-ha*` + full `campaign.yaml` ready for Tuesday `2026-11-17 08:05 UTC`)
   - `2026-11-24-torrent-drop` (`approved: false`, `promoted: false`, migrated from `drafts/torrent-drop` with `sources/` and pre-filled `campaign.yaml` template)

- [ ] **Step 4: Run full pytest suite on Raspberry Pi**

Run: `ssh raspberrypi 'cd ~/projects/blog && python3 -m pytest -v'`
Expected: PASS (all unit and integration tests green)

---

### Task 5: Live Rollout (GitHub Repo, Ghost Overhaul, Blueprint Backfill, `/llms.txt`, and Cron Installation)

**Files:**
- Create: `~/projects/blog/.env` (and `.env.example`)
- Create: `~/projects/content/themes/dawn_star/llms.txt`
- Modify: `~/projects/.gitignore` (ensure `blog/.github-showcase-repo/` and `blog/.env` are ignored)

**Interfaces:**
- Consumes: `blogctl.py` CLI subcommands (`site-setup`, `ghost-sync`, `github-sync`, `promote --dry-run`)

- [ ] **Step 1: Create public GitHub repository `mMarzeta/ai-sdlc-case-studies` and clone into `~/projects/blog/.github-showcase-repo`**

Run on Mac: `gh repo create mMarzeta/ai-sdlc-case-studies --public --description "Production AI-Native SDLC Case Studies: Design Specs, Implementation Plans, Architecture Trade-offs & Tested Code — by Maciej Marzęta (blog.marzeta.pl)"`
Run on Pi: `ssh raspberrypi 'git clone git@github.com:mMarzeta/ai-sdlc-case-studies.git ~/projects/blog/.github-showcase-repo'`

- [ ] **Step 2: Provision `.env` on Raspberry Pi and deploy `/llms.txt`**

Configure `~/projects/blog/.env` with `GHOST_ADMIN_API_KEY` (from Ghost `api_keys`), `SMTP_HOST=smtp.eu.mailgun.org`, `SMTP_PORT=587`, `SMTP_USER=blog@newsletter.marzeta.pl`, `SMTP_PASSWORD` (from `~/Projects/.env` `GHOST_MAILGUN_PASSWD`), `NOTIFY_FROM=blog@newsletter.marzeta.pl`, `REPLY_TO=contact@marzeta.pl`, `NOTIFY_TO=contact@marzeta.pl`. Write `~/projects/content/themes/dawn_star/llms.txt` and restart Ghost container if needed so `https://blog.marzeta.pl/llms.txt` returns `200 OK`.

- [ ] **Step 3: Execute `blogctl site-setup`, `blogctl ghost-sync`, and `blogctl github-sync --all`**

Run on Pi:
```bash
cd ~/projects/blog
python3 tools/blogctl.py site-setup
python3 tools/blogctl.py ghost-sync posts/2026-10-27-cve-watchdog
python3 tools/blogctl.py ghost-sync posts/2026-11-03-homelab-64bit
python3 tools/blogctl.py ghost-sync posts/2026-11-10-bravia65-debloat
python3 tools/blogctl.py ghost-sync posts/2026-11-17-tv-screentime
python3 tools/blogctl.py github-sync --all
```

- [ ] **Step 4: Install Tuesday `08:05 UTC` cron job and test `promote --dry-run` on `2026-11-17-tv-screentime`**

Add `5 8 * * 2 /usr/bin/python3 ~/projects/blog/tools/blogctl.py cron-run >> ~/projects/blog/cron.log 2>&1` to `mmarzeta`'s crontab.
Verify live endpoints (`https://blog.marzeta.pl/about/`, `https://blog.marzeta.pl/llms.txt`, `https://github.com/mMarzeta/ai-sdlc-case-studies`) and run `python3 tools/blogctl.py promote posts/2026-11-17-tv-screentime --dry-run`.
