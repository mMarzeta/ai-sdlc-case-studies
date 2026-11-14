import json
from pathlib import Path
import yaml
from tools.blogctl import (
    ABOUT_PAGE_HTML,
    extract_markdown_body,
    ingest_sources,
    render_markdown_to_html,
    run_cron_promotions,
    sync_post_to_ghost,
)


def test_cron_run_skips_unapproved_or_unpublished_posts(tmp_path):
    posts_dir = tmp_path / "posts"
    # Post 1: approved=False
    p1 = posts_dir / "2026-11-24-torrent-drop"
    p1.mkdir(parents=True)
    (p1 / "campaign.yaml").write_text(
        "slug: p1\ntitle: P1\napproved: false\ngithub_showcase:\n  enabled: false\npitches: []\n"
    )

    # Post 2: approved=True, but Ghost says status='scheduled'
    p2 = posts_dir / "2026-11-17-tv-screentime"
    p2.mkdir(parents=True)
    (p2 / "campaign.yaml").write_text(
        "slug: p2\ntitle: P2\napproved: true\ngithub_showcase:\n  enabled: false\npitches: []\n"
    )

    class FakeGhost:
        def get_post_by_slug(self, slug):
            return {"slug": slug, "status": "scheduled"}

    promoted = run_cron_promotions(tmp_path, FakeGhost(), smtp_config={}, dry_run=True)
    assert promoted == []


def test_ingest_sources_copies_external_and_symlinks_repo_files(tmp_path):
    repo_root = tmp_path / "Projects"
    docs_dir = repo_root / "docs" / "superpowers" / "specs"
    docs_dir.mkdir(parents=True)
    spec_file = docs_dir / "2026-11-14-spec.md"
    spec_file.write_text("# Spec\n")

    ext_dir = tmp_path / "brain"
    ext_dir.mkdir()
    summary_file = ext_dir / "architecture_decisions_summary.md"
    summary_file.write_text("# Summary\n")

    post_dir = repo_root / "blog" / "posts" / "2026-11-24-topic"
    post_dir.mkdir(parents=True)

    ingested = ingest_sources(post_dir, [spec_file, summary_file], repo_root=repo_root)
    assert len(ingested) == 2
    assert (post_dir / "sources" / "2026-11-14-spec.md").is_symlink()
    assert not (post_dir / "sources" / "architecture_decisions_summary.md").is_symlink()
    assert (post_dir / "sources" / "architecture_decisions_summary.md").read_text() == "# Summary\n"


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
    assert 'id="ai-sdlc-blueprint"' in fake.created_kwargs["html"]
    assert fake.created_kwargs["featured"] is True
    assert fake.created_kwargs["status"] == "draft"
    saved_camp = yaml.safe_load((post_dir / "campaign.yaml").read_text(encoding="utf-8"))
    assert saved_camp["ghost_post_id"] == "created_999"


def test_about_page_includes_amplifier_of_intent_and_goedecke():
    assert "Amplifier of Intent" in ABOUT_PAGE_HTML
    assert "https://www.seangoedecke.com/writing-is-no-longer-proof-of-work/" in ABOUT_PAGE_HTML
    assert "https://blog.marzeta.pl/writing-is-no-longer-proof-of-work-amplifier-of-intent/" in ABOUT_PAGE_HTML
