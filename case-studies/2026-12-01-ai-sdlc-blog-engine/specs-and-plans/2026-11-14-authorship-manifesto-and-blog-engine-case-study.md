# Authorship Manifesto & Autonomous Blog Engine Case Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add global AI-SDLC authorship disclosure ("An Amplifier of Intent, Not a Source of Ideas"), extend `blogctl ghost-sync` to create new Ghost posts from Markdown, publish the out-of-order Manifesto post immediately, and schedule the `2026-12-01` `blogctl` technical case study.

**Architecture:** We extend `tools/ghost_client.py`, `tools/blogctl.py`, and `tools/github_showcase.py` with global authorship disclosure blocks and Markdown-to-Ghost post creation (`POST /ghost/api/admin/posts/?source=html`). We then author two self-contained post packages (`posts/2026-11-14-writing-is-not-proof-of-work/` published immediately and `posts/2026-12-01-ai-sdlc-blog-engine/` scheduled for `2026-12-01T08:00:00.000Z`), ingest their specs/plans, and sync all posts, `/about/`, and the GitHub showcase repository.

**Tech Stack:** Python 3.13, `python-markdown` (`fenced_code`, `tables`, `sane_lists`), `PyYAML`, `pytest`, Ghost 6 Admin API (HS256 JWT).

**Spec:** `~/projects/docs/superpowers/specs/2026-11-14-authorship-manifesto-and-blog-engine-case-study-design.md`

## Global Constraints

- Key punchline across Blueprint, `/about/`, GitHub README, and Manifesto: `"An Amplifier of Intent (Not a Source of Ideas)"` / `"an amplifier of intent, not a source of ideas"`.
- Never use `"genius savant"`; frame AI agents as `"50 hyper-literal contractors with encyclopedic memory and zero agency"`.
- Cite and link Sean Goedecke's essay: `https://www.seangoedecke.com/writing-is-no-longer-proof-of-work/`.
- Link to live Manifesto URL: `https://blog.marzeta.pl/writing-is-no-longer-proof-of-work-amplifier-of-intent/`.

## Review Focus

- `extract_markdown_body(md_text)` when `## Post Body` is absent: must gracefully fall back to stripping the `# Ghost Blog Post:` metadata block up to the first `---` horizontal rule or returning the full markdown.
- `GhostAdminClient.create_post_html()` with `status="scheduled"`: Ghost 6 requires `published_at` in ISO-8601 UTC format when creating or updating a scheduled post.
- `sync_post_to_ghost()` idempotency: when `ghost_post_id` is written back to `campaign.yaml`, subsequent runs must update the existing post rather than attempting a duplicate `POST`.
- HTML escaping in `render_blueprint_html()`: all dynamic metrics and URLs must remain escaped while static links (`writing-is-no-longer-proof-of-work-amplifier-of-intent` and `seangoedecke.com`) render valid `<a>` tags.
- Scrubber safety on `2026-12-01-ai-sdlc-blog-engine`: exporting `tools/` and `tests/` (which contain regex patterns for blocked secrets in `github_showcase.py`) must not trigger a false-positive `ScrubberSecurityError` on the regex definition itself.

---

### Task 1: Global Blueprint Disclosure & Ghost Post Creation in `tools/ghost_client.py`

**Files:**
- Modify: `tools/ghost_client.py:41-165`
- Test: `tests/test_ghost_client.py`

**Interfaces:**
- Consumes: `make_ghost_jwt(api_key: str) -> str`
- Produces:
  - `MANIFESTO_URL = "https://blog.marzeta.pl/writing-is-no-longer-proof-of-work-amplifier-of-intent/"`
  - `GOEDECKE_URL = "https://www.seangoedecke.com/writing-is-no-longer-proof-of-work/"`
  - `GhostAdminClient.create_post_html(self, title: str, slug: str, html: str, status: str = "draft", tags: list[dict[str, str]] | None = None, custom_excerpt: str | None = None, featured: bool = False, published_at: str | None = None) -> dict[str, Any]`

- [ ] **Step 1: Write the failing tests in `tests/test_ghost_client.py`**

```python
def test_render_blueprint_html_includes_amplifier_of_intent_and_goedecke_link():
    bp = render_blueprint_html(
        metrics={"code_loc": 1326, "test_count": 21, "specs_count": 2, "plans_count": 2},
        case_study_url="https://github.com/mMarzeta/ai-sdlc-case-studies/tree/main/case-studies/2026-12-01-ai-sdlc-blog-engine",
    )
    assert "amplifier of intent, not a source of ideas" in bp.lower()
    assert "https://www.seangoedecke.com/writing-is-no-longer-proof-of-work/" in bp
    assert "https://blog.marzeta.pl/writing-is-no-longer-proof-of-work-amplifier-of-intent/" in bp


def test_create_post_html_sends_source_html_and_scheduled_published_at(monkeypatch):
    key_id = "68d253434949d60001d061a0"
    secret_hex = "ab" * 32
    captured = {}

    def fake_urlopen(req, timeout=20):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["body"] = json.loads(req.data.decode("utf-8"))

        class Resp:
            def read(self):
                return b'{"posts": [{"id": "new_post_123", "slug": "test-slug", "status": "scheduled"}]}'

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        return Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = GhostAdminClient(f"{key_id}:{secret_hex}")
    created = client.create_post_html(
        title="Test Title",
        slug="test-slug",
        html="<p>Hello</p>",
        status="scheduled",
        tags=[{"name": "AI-SDLC"}],
        custom_excerpt="Short excerpt",
        featured=True,
        published_at="2026-12-01T08:00:00.000Z",
    )
    assert created["id"] == "new_post_123"
    assert "source=html" in captured["url"]
    assert captured["method"] == "POST"
    post_payload = captured["body"]["posts"][0]
    assert post_payload["title"] == "Test Title"
    assert post_payload["slug"] == "test-slug"
    assert post_payload["status"] == "scheduled"
    assert post_payload["published_at"] == "2026-12-01T08:00:00.000Z"
    assert post_payload["featured"] is True
    assert post_payload["custom_excerpt"] == "Short excerpt"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_ghost_client.py -v`
Expected: FAIL (`AssertionError` on `amplifier of intent` and `AttributeError: 'GhostAdminClient' object has no attribute 'create_post_html'`)

- [ ] **Step 3: Implement Blueprint disclosure and `create_post_html` in `tools/ghost_client.py`**

Update `render_blueprint_html()` to include the **Authorship & Proof-of-Work Disclosure** paragraph and add `create_post_html()` to `GhostAdminClient`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ghost_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/ghost_client.py tests/test_ghost_client.py
git commit -m "feat(ghost): add Amplifier of Intent disclosure and create_post_html API"
```

---

### Task 2: Markdown-to-Ghost Creation, `/about/` Update & Portfolio README Disclosure (`tools/blogctl.py` & `tools/github_showcase.py`)

**Files:**
- Modify: `tools/blogctl.py:36-74,138-173`
- Modify: `tools/github_showcase.py:259-299`
- Test: `tests/test_blogctl_cron.py`, `tests/test_github_showcase.py`

**Interfaces:**
- Consumes: `GhostAdminClient.create_post_html`
- Produces:
  - `extract_markdown_body(md_text: str) -> str` in `tools/blogctl.py`
  - `render_markdown_to_html(md_text: str) -> str` in `tools/blogctl.py`
  - Updated `sync_post_to_ghost(post_dir: Path, ghost_client: GhostAdminClient) -> dict[str, Any]` that creates missing Ghost posts from `post.md` and saves `ghost_post_id` into `campaign.yaml`.
  - Updated `ABOUT_PAGE_HTML` and `update_portfolio_readme()` containing the `"An Amplifier of Intent (Not a Source of Ideas)"` section, the 50-engineers thought experiment, and links to Sean Goedecke and the Manifesto post.

- [ ] **Step 1: Write the failing tests in `tests/test_blogctl_cron.py` and `tests/test_github_showcase.py`**

```python
# In tests/test_blogctl_cron.py:
from tools.blogctl import ABOUT_PAGE_HTML, extract_markdown_body, render_markdown_to_html, sync_post_to_ghost

def test_extract_and_render_markdown_body_strips_metadata_header():
    raw_md = (
        "# Ghost Blog Post: Test\n\n"
        "- **Proposed Title:** Test\n"
        "- **Proposed Slug:** `test`\n\n"
        "---\n\n"
        "## Post Body\n\n"
        "Paragraph with **bold** text.\n\n"
        "| Col A | Col B |\n|---|---|\n| 1 | 2 |\n"
    )
    body = extract_markdown_body(raw_md)
    assert "Proposed Title" not in body
    assert "## Post Body" not in body
    html = render_markdown_to_html(raw_md)
    assert "<strong>bold</strong>" in html
    assert "<table>" in html


def test_sync_post_to_ghost_creates_missing_post_and_persists_id(tmp_path):
    post_dir = tmp_path / "2026-11-14-manifesto"
    post_dir.mkdir()
    (post_dir / "post.md").write_text(
        "# Ghost Blog Post: Manifesto\n\n---\n\n## Post Body\n\nHello **world**.\n",
        encoding="utf-8",
    )
    (post_dir / "campaign.yaml").write_text(
        yaml.safe_dump({
            "slug": "writing-is-no-longer-proof-of-work-amplifier-of-intent",
            "title": "Yes, AI Wrote This Blog",
            "custom_excerpt": "Manifesto excerpt",
            "status": "published",
            "featured": True,
            "ghost_post_id": None,
            "tags": ["AI-SDLC", "Architecture"],
            "sdlc_metrics": {"code_loc": "1,450 LOC", "test_count": "25 tests", "specs_count": 2, "plans_count": 2},
        }),
        encoding="utf-8",
    )

    class FakeGhostCreate:
        def __init__(self):
            self.created_kwargs = None

        def get_post_by_id(self, post_id):
            return None

        def get_post_by_slug(self, slug):
            return None

        def ensure_tags(self, tags):
            return tags

        def create_post_html(self, **kwargs):
            self.created_kwargs = kwargs
            return {"id": "created_999", "slug": kwargs["slug"], "status": kwargs["status"]}

    fake = FakeGhostCreate()
    res = sync_post_to_ghost(post_dir, fake)
    assert res["id"] == "created_999"
    assert "<strong>world</strong>" in fake.created_kwargs["html"]
    assert "id=\"ai-sdlc-blueprint\"" in fake.created_kwargs["html"]
    assert fake.created_kwargs["featured"] is True
    saved_camp = yaml.safe_load((post_dir / "campaign.yaml").read_text(encoding="utf-8"))
    assert saved_camp["ghost_post_id"] == "created_999"


def test_about_page_includes_amplifier_of_intent_and_goedecke():
    assert "Amplifier of Intent" in ABOUT_PAGE_HTML
    assert "https://www.seangoedecke.com/writing-is-no-longer-proof-of-work/" in ABOUT_PAGE_HTML
    assert "https://blog.marzeta.pl/writing-is-no-longer-proof-of-work-amplifier-of-intent/" in ABOUT_PAGE_HTML
```

And in `tests/test_github_showcase.py`:
```python
def test_portfolio_readme_includes_amplifier_of_intent_manifesto(tmp_path):
    from tools.github_showcase import update_portfolio_readme
    readme_path = update_portfolio_readme(tmp_path, [], git_push=False)
    text = readme_path.read_text(encoding="utf-8")
    assert "Amplifier of Intent" in text
    assert "https://www.seangoedecke.com/writing-is-no-longer-proof-of-work/" in text
    assert "https://blog.marzeta.pl/writing-is-no-longer-proof-of-work-amplifier-of-intent/" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_blogctl_cron.py tests/test_github_showcase.py -v`
Expected: FAIL (`ImportError: cannot import name 'extract_markdown_body'` and `AssertionError` on `Amplifier of Intent`)

- [ ] **Step 3: Implement `extract_markdown_body`, `render_markdown_to_html`, `sync_post_to_ghost` creation flow, `ABOUT_PAGE_HTML`, and `update_portfolio_readme`**

 Also inspect `tools/github_showcase.py` `DEFAULT_RULES` / `config/scrubber_rules.yaml` so that when `tools/github_showcase.py` itself is exported as part of a case study, its regex pattern string doesn't match itself (which it already doesn't because the regex requires `= <value>`, whereas the pattern definition has `\s*=\s*`). Add a unit test verifying `scrub_content` succeeds on `tools/github_showcase.py`'s own source text.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/blogctl.py tools/github_showcase.py tests/test_blogctl_cron.py tests/test_github_showcase.py
git commit -m "feat(blogctl): support markdown-to-Ghost post creation and global Amplifier of Intent manifesto links"
```

---

### Task 3: Author Post #1 (Immediate Out-of-Order Manifesto) & Post #2 (`2026-12-01` Blog Engine Case Study) and Sync to Ghost & GitHub

**Files:**
- Create: `posts/2026-11-14-writing-is-not-proof-of-work/post.md`
- Create: `posts/2026-11-14-writing-is-not-proof-of-work/campaign.yaml`
- Create: `posts/2026-11-14-writing-is-not-proof-of-work/state.json`
- Create: `posts/2026-12-01-ai-sdlc-blog-engine/post.md`
- Create: `posts/2026-12-01-ai-sdlc-blog-engine/campaign.yaml`
- Create: `posts/2026-12-01-ai-sdlc-blog-engine/state.json`
- Modify: `posts/2026-11-24-torrent-drop/post.md` (if needed, or keep `2026-11-24` as is)
- Test: `tests/test_blogctl_cron.py`

**Interfaces:**
- Consumes: `ingest_sources`, `sync_post_to_ghost`, `sync_all_github_case_studies`, `run_site_setup`
- Produces:
  - Published Ghost post `https://blog.marzeta.pl/writing-is-no-longer-proof-of-work-amplifier-of-intent/`
  - Scheduled Ghost post `https://blog.marzeta.pl/zero-touch-ai-sdlc-blog-publishing-outreach-engine/` (`2026-12-01T08:00:00.000Z`)
  - Updated Blueprints on all published/scheduled Ghost posts, updated `/about/` page, and updated `github.com/mMarzeta/ai-sdlc-case-studies` repository.

- [ ] **Step 1: Write a verification test for the new post packages and self-scrubbing of `tools/`**

Add `test_self_export_of_blog_engine_passes_scrubber` in `tests/test_github_showcase.py` verifying that `tools/github_showcase.py` and `tools/blogctl.py` pass `scrub_content()` cleanly without raising `ScrubberSecurityError`.

- [ ] **Step 2: Create and ingest sources for `posts/2026-11-14-writing-is-not-proof-of-work` and `posts/2026-12-01-ai-sdlc-blog-engine`**

Write `post.md`, `campaign.yaml`, and `state.json` for both posts following `PLAYBOOK.md` and the Spec, then run `blogctl.py ingest` to link their specs and plans into `sources/`.

- [ ] **Step 3: Run `pytest`, `site-setup`, `ghost-sync` across all posts, and `github-sync`**

Run:
1. `pytest -v`
2. `python3 tools/blogctl.py site-setup`
3. `python3 tools/blogctl.py ghost-sync posts/2026-11-14-writing-is-not-proof-of-work`
4. `python3 tools/blogctl.py ghost-sync posts/2026-10-27-cve-watchdog`
5. `python3 tools/blogctl.py ghost-sync posts/2026-11-03-homelab-64bit`
6. `python3 tools/blogctl.py ghost-sync posts/2026-11-10-bravia65-debloat`
7. `python3 tools/blogctl.py ghost-sync posts/2026-11-17-tv-screentime`
8. `python3 tools/blogctl.py ghost-sync posts/2026-12-01-ai-sdlc-blog-engine`
9. `python3 tools/blogctl.py github-sync`

- [ ] **Step 4: Verify live HTTP responses and commit**

Verify `https://blog.marzeta.pl/writing-is-no-longer-proof-of-work-amplifier-of-intent/` and `https://blog.marzeta.pl/about/` return HTTP 200 and contain the expected manifesto and Blueprint links, then commit all changes.
