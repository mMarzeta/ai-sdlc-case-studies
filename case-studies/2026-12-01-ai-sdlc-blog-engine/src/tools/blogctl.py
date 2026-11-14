#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any
import markdown
import yaml

BLOG_ROOT = Path(__file__).resolve().parent.parent
if str(BLOG_ROOT) not in sys.path:
    sys.path.insert(0, str(BLOG_ROOT))

from tools.ghost_client import (
    GhostAdminClient,
    inject_blueprint_html,
    render_blueprint_html,
)
from tools.github_showcase import (
    export_case_study,
    loaded_default_rules,
    update_portfolio_readme,
)
from tools.mailer import (
    render_execution_summary_email,
    send_campaign_pitches,
    send_execution_summary_email,
)
from tools.syndicator import build_social_launch_kit, syndicate_to_devto


ABOUT_PAGE_HTML = """
<p class="lead"><strong>I design and build high-reliability software systems and lead engineering teams through the transition to deterministic, AI-Native Software Development Life Cycles (AI-SDLC).</strong></p>

<p>Over nearly a decade in production backend engineering—including serving as a <strong>Python Technical Leader at a unicorn startup</strong>—I have focused on distributed systems, high-throughput APIs (Python, FastAPI, Rust, Go), and zero-trust infrastructure.</p>

<p>Today, my primary focus is solving the hardest problem in modern engineering leadership: <strong>how to turn autonomous AI coding agents into a 10x engineering multiplier without drowning in architectural drift, security regressions, or unmaintainable "AI slop."</strong></p>

<hr>

<h2>The Deterministic AI-SDLC Methodology</h2>
<p>Every project documented on <strong>MarzTech</strong> and in my public GitHub portfolio is built using a repeatable, audit-ready engineering pipeline:</p>
<ul>
  <li><strong>1. Spec-First Architecture &amp; Threat Modeling:</strong> Before an agent writes a single line of application code, adversarial design specs lock down boundaries, state machines, failure modes, and security invariants.</li>
  <li><strong>2. Bite-Sized TDD Implementation Plans:</strong> Specifications are decomposed into atomic Red-Green-Refactor tasks with explicit interface contracts.</li>
  <li><strong>3. Multi-Agent Orchestration &amp; Verification Gates:</strong> Autonomous implementation subagents execute under strict automated test suites (<code>pytest</code>, integration harnesses, CVE scanners) and independent code-review passes.</li>
</ul>

<p><strong>Explore the Proof of Work:</strong> All raw design specs, implementation plans, architectural trade-off analyses, and production code from my articles are published openly in my <a href="https://github.com/mMarzeta/ai-sdlc-case-studies"><strong>GitHub AI-SDLC Case Studies Repository &rarr;</strong></a></p>

<hr>

<h2>Why AI Writes the Prose (And Why It’s Not "AI Slop"): An Amplifier of Intent, Not a Source of Ideas</h2>
<p>Every article and codebase on this blog is drafted and implemented through AI agents—and none of it is "AI slop." Every action taken, every problem diagnosed, every architectural constraint, and every creative leap originates from the depths of my own mind. I hold the system on the rails, define the rules and direction, and enforce verification gates.</p>

<p>Consider a simple pre-2022 thought experiment: <strong>what would you have done if someone suddenly handed you 50 senior engineers working 24/7 who would build whatever you asked?</strong> Most people quickly realize that raw coding capacity was never the real bottleneck. Without vision, problem selection, strict boundaries, and ruthless verification, 50 hyper-literal contractors with encyclopedic memory and zero agency will simply manufacture chaos at 50x speed. AI is <strong>an amplifier of intent, not a source of ideas</strong>.</p>

<p>As Sean Goedecke argues in <a href="https://www.seangoedecke.com/writing-is-no-longer-proof-of-work/"><em>Writing Is No Longer Proof of Work</em></a>, manually wordsmithing sentences or sitting in front of an editor for hours is no longer proof of engineering labor. Real proof of work is effectiveness, working systems, and verifiable outcomes. <a href="https://blog.marzeta.pl/writing-is-no-longer-proof-of-work-amplifier-of-intent/"><strong>Read my full manifesto: Yes, AI Wrote This Blog. No, It’s Not Slop &rarr;</strong></a></p>

<hr>

<h2>Advisory, Speaking &amp; Executive Roles (CTO / Head of AI / VP Engineering)</h2>
<p>I work with founders, executive teams, and engineering organizations on:</p>
<ul>
  <li><strong>AI-Native SDLC Transformation:</strong> Deploying structured agentic workflows (Spec &rarr; Plan &rarr; Subagent TDD &rarr; Automated Review) across engineering teams.</li>
  <li><strong>Architecture &amp; Technical Leadership:</strong> Scaling Python/backend platforms, eliminating legacy technical debt, and hardening self-hosted or cloud infrastructure.</li>
  <li><strong>Conference Keynotes &amp; Engineering Workshops:</strong> Pragmatic war stories from production backend systems and agentic software engineering.</li>
</ul>

<p><em>Note: By design, I do not maintain a LinkedIn profile. I believe in verifiable engineering artifacts over social-feed algorithms.</em></p>

<ul>
  <li><strong>Direct Email:</strong> <a href="mailto:contact@marzeta.pl"><code>contact@marzeta.pl</code></a></li>
  <li><strong>GitHub Portfolio:</strong> <a href="https://github.com/mMarzeta/ai-sdlc-case-studies"><code>github.com/mMarzeta/ai-sdlc-case-studies</code></a></li>
  <li><strong>Personal Site:</strong> <a href="https://marzeta.pl"><code>marzeta.pl</code></a></li>
</ul>
""".strip()


def load_env(env_path: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    target = env_path or (BLOG_ROOT / ".env")
    if target.exists():
        for raw_line in target.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def build_smtp_config(env: dict[str, str]) -> dict[str, Any]:
    return {
        "host": env.get("SMTP_HOST", "smtp.eu.mailgun.org"),
        "port": int(env.get("SMTP_PORT", "587")),
        "user": env.get("SMTP_USER", "blog@newsletter.marzeta.pl"),
        "password": env.get("SMTP_PASSWORD", ""),
        "from_email": env.get("NOTIFY_FROM", "blog@newsletter.marzeta.pl"),
        "reply_to": env.get("REPLY_TO", "contact@marzeta.pl"),
        "notify_to": env.get("NOTIFY_TO", "contact@marzeta.pl"),
    }


def load_newsletters(blog_root: Path = BLOG_ROOT) -> dict[str, dict[str, Any]]:
    nl_path = blog_root / "config" / "newsletters.yaml"
    if not nl_path.exists():
        return {}
    data = yaml.safe_load(nl_path.read_text(encoding="utf-8")) or {}
    return data.get("newsletters", data)


def ingest_sources(
    post_dir: Path,
    paths: list[Path],
    repo_root: Path | None = None,
) -> list[Path]:
    if repo_root is None:
        repo_root = BLOG_ROOT.parent
    repo_root = repo_root.resolve()
    sources_dir = post_dir / "sources"
    sources_dir.mkdir(parents=True, exist_ok=True)

    ingested: list[Path] = []
    for p in paths:
        abs_p = p.expanduser().resolve()
        if not abs_p.exists():
            raise FileNotFoundError(f"Source file not found: {p}")
        dest = sources_dir / abs_p.name
        if dest.exists() or dest.is_symlink():
            dest.unlink()

        try:
            abs_p.relative_to(repo_root)
            rel_target = os.path.relpath(abs_p, sources_dir.resolve())
            dest.symlink_to(rel_target)
        except ValueError:
            shutil.copy2(abs_p, dest)
        ingested.append(dest)
    return ingested


def extract_markdown_body(md_text: str) -> str:
    marker_match = re.search(r"^##\s+Post Body\s*$", md_text, flags=re.MULTILINE)
    if marker_match:
        body = md_text[marker_match.end():].strip()
    else:
        hr_match = re.search(r"^---\s*$", md_text, flags=re.MULTILINE)
        body = md_text[hr_match.end():].strip() if hr_match else md_text.strip()

    bp_heading = re.search(r"^##\s+The AI-SDLC Blueprint\b.*$", body, flags=re.MULTILINE | re.DOTALL)
    if bp_heading:
        body = body[:bp_heading.start()].rstrip()
        body = re.sub(r"\n---\s*$", "", body).rstrip()
    return body


def render_markdown_to_html(md_text: str) -> str:
    body = extract_markdown_body(md_text)
    return markdown.markdown(body, extensions=["fenced_code", "tables", "sane_lists"])


def sync_post_to_ghost(post_dir: Path, ghost_client: GhostAdminClient) -> dict[str, Any]:
    camp_path = post_dir / "campaign.yaml"
    campaign = yaml.safe_load(camp_path.read_text(encoding="utf-8"))
    slug = campaign["slug"]
    post_id = campaign.get("ghost_post_id")
    post = ghost_client.get_post_by_id(post_id) if post_id else ghost_client.get_post_by_slug(slug)

    case_study_rel = campaign.get("github_showcase", {}).get("case_study_dir", f"case-studies/{post_dir.name}")
    github_url = f"https://github.com/mMarzeta/ai-sdlc-case-studies/tree/main/{case_study_rel}"
    blueprint_html = render_blueprint_html(
        metrics=campaign.get("sdlc_metrics", {}),
        case_study_url=github_url,
        summary_points=campaign.get("blueprint_highlights", []),
    )

    desired_tag_names = campaign.get("tags", [])
    tag_defs = [{"name": t, "slug": t.lower().replace(" ", "-")} for t in desired_tag_names]
    if tag_defs:
        ghost_client.ensure_tags(tag_defs)

    md_path = post_dir / "post.md"
    if not post:
        if not md_path.exists():
            raise RuntimeError(f"Post not found in Ghost for slug={slug} and no post.md exists to create it")
        rendered_body = render_markdown_to_html(md_path.read_text(encoding="utf-8"))
        full_html = inject_blueprint_html(rendered_body, blueprint_html)
        status = campaign.get("status", "draft")
        published_at = campaign.get("scheduled_for") if status == "scheduled" else None
        created = ghost_client.create_post_html(
            title=campaign["title"],
            slug=slug,
            html=full_html,
            status=status,
            tags=[{"name": t} for t in desired_tag_names],
            custom_excerpt=campaign.get("custom_excerpt"),
            featured=bool(campaign.get("featured", False)),
            published_at=published_at,
        )
        campaign["ghost_post_id"] = created["id"]
        camp_path.write_text(yaml.safe_dump(campaign, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return created

    base_html = post.get("html", "")
    if (not base_html or campaign.get("sync_markdown_body", False)) and md_path.exists():
        base_html = render_markdown_to_html(md_path.read_text(encoding="utf-8"))
    updated_html = inject_blueprint_html(base_html, blueprint_html)

    existing_tags = [{"name": t["name"]} for t in post.get("tags", []) if not t["name"].startswith("#Import")]
    existing_names_lower = {t["name"].lower() for t in existing_tags}
    for t_name in desired_tag_names:
        if t_name.lower() not in existing_names_lower:
            existing_tags.append({"name": t_name})

    return ghost_client.update_post_html(
        post["id"],
        html=updated_html,
        tags=existing_tags,
        custom_excerpt=campaign.get("custom_excerpt"),
        featured=campaign.get("featured"),
    )


def sync_all_github_case_studies(
    blog_root: Path,
    git_push: bool = True,
) -> list[dict[str, Any]]:
    repo_dir = blog_root / ".github-showcase-repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    rules = loaded_default_rules(blog_root / "config" / "scrubber_rules.yaml")
    posts_root = blog_root / "posts"

    exported: list[dict[str, Any]] = []
    if not posts_root.exists():
        return exported

    for post_dir in sorted(posts_root.iterdir()):
        camp_file = post_dir / "campaign.yaml"
        if not post_dir.is_dir() or not camp_file.exists():
            continue
        campaign = yaml.safe_load(camp_file.read_text(encoding="utf-8"))
        if not campaign.get("github_showcase", {}).get("enabled", False):
            continue
        if not campaign.get("github_showcase", {}).get("publish_now", True):
            continue
        res = export_case_study(post_dir, repo_dir, rules=rules, git_push=False)
        exported.append(res)

    update_portfolio_readme(repo_dir, exported, git_push=git_push)
    return exported


def promote_post(
    post_dir: Path,
    blog_root: Path,
    ghost_client: GhostAdminClient | None,
    smtp_config: dict[str, Any],
    dry_run: bool = False,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = env or {}
    campaign = yaml.safe_load((post_dir / "campaign.yaml").read_text(encoding="utf-8"))
    slug = campaign["slug"]
    post_url = f"https://blog.marzeta.pl/{slug}/"
    case_study_rel = campaign.get("github_showcase", {}).get("case_study_dir", f"case-studies/{post_dir.name}")
    github_url = f"https://github.com/mMarzeta/ai-sdlc-case-studies/tree/main/{case_study_rel}"

    # 1. Sync case study to GitHub
    if campaign.get("github_showcase", {}).get("enabled", False) and not dry_run:
        campaign["status"] = "published"
        campaign["github_showcase"]["publish_now"] = True
        (post_dir / "campaign.yaml").write_text(yaml.safe_dump(campaign, sort_keys=False, allow_unicode=True), encoding="utf-8")
        sync_all_github_case_studies(blog_root, git_push=True)

    # 2. Send newsletter pitches via Mailgun SMTP
    newsletters = load_newsletters(blog_root)
    pitch_results = send_campaign_pitches(
        post_dir=post_dir,
        campaign=campaign,
        newsletters=newsletters,
        smtp_config=smtp_config,
        dry_run=dry_run,
    )

    # 3. Optional Dev.to syndication + Social Launch Kit
    launch_kit = build_social_launch_kit(campaign, post_url=post_url, github_url=github_url)
    md_path = post_dir / "post.md"
    md_body = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    devto_res = syndicate_to_devto(
        campaign=campaign,
        markdown_body=md_body,
        post_url=post_url,
        api_key=env.get("DEVTO_API_KEY"),
        dry_run=dry_run,
    )

    # 4. Send Executive Summary Report Email to contact@marzeta.pl
    actions = {
        "post_url": post_url,
        "github_url": github_url,
        "devto": devto_res,
    }
    subj, txt_body, html_body = render_execution_summary_email(
        campaign=campaign,
        actions=actions,
        pitch_results=pitch_results,
        launch_kit=launch_kit,
    )
    summary_res = send_execution_summary_email(
        smtp_config=smtp_config,
        subject=subj,
        text_body=txt_body,
        html_body=html_body,
        dry_run=dry_run,
    )

    if not dry_run:
        state_path = post_dir / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        state["promoted"] = True
        state["github_synced"] = True
        state["summary_email_sent"] = summary_res
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "slug": slug,
        "post_url": post_url,
        "github_url": github_url,
        "pitch_results": pitch_results,
        "summary_email": summary_res,
        "summary_text_preview": txt_body,
    }


def run_cron_promotions(
    blog_root: Path,
    ghost_client: Any,
    smtp_config: dict[str, Any],
    dry_run: bool = False,
    env: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    posts_root = blog_root / "posts"
    promoted_list: list[dict[str, Any]] = []
    if not posts_root.exists():
        return promoted_list

    for post_dir in sorted(posts_root.iterdir()):
        camp_path = post_dir / "campaign.yaml"
        if not post_dir.is_dir() or not camp_path.exists():
            continue
        campaign = yaml.safe_load(camp_path.read_text(encoding="utf-8")) or {}
        if not campaign.get("approved", False):
            continue

        state_path = post_dir / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        if state.get("promoted", False):
            continue

        slug = campaign["slug"]
        ghost_post = ghost_client.get_post_by_slug(slug)
        if not ghost_post or ghost_post.get("status") != "published":
            continue

        res = promote_post(
            post_dir=post_dir,
            blog_root=blog_root,
            ghost_client=ghost_client,
            smtp_config=smtp_config,
            dry_run=dry_run,
            env=env,
        )
        promoted_list.append(res)

    return promoted_list


def run_site_setup(ghost_client: GhostAdminClient, env: dict[str, str]) -> dict[str, Any]:
    # 1. Ensure AI-SDLC & Architecture tags
    ghost_client.ensure_tags(
        [
            {
                "name": "AI-SDLC",
                "slug": "ai-sdlc",
                "description": "Deterministic, spec-driven AI Software Development Life Cycle (Specs, Plans, Multi-Agent TDD & Verification).",
            },
            {
                "name": "Architecture",
                "slug": "architecture",
                "description": "Production systems architecture, trade-offs, security hardening, and high-reliability backend engineering.",
            },
        ]
    )

    # 2. Update /about/ with Executive Profile and unpublish /about-2/
    about_page = ghost_client.update_page_html(
        slug="about",
        title="About Maciej Marzęta — AI-Native Architecture & Agentic SDLC",
        html=ABOUT_PAGE_HTML,
        status="published",
    )
    about2 = ghost_client.get_page_by_slug("about-2")
    if about2 and about2.get("status") == "published":
        ghost_client.update_page_html(
            slug="about-2",
            title=about2.get("title", "About me (Archive)"),
            html=about2.get("html", "<p>Archived bio.</p>"),
            status="draft",
        )

    return {"about_page_id": about_page["id"], "status": "updated"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MarzTech AI-SDLC Blog & Promotion Engine CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="Ingest specs, plans, and AGY summaries into a post's sources/ directory")
    p_ingest.add_argument("post_dir", type=Path)
    p_ingest.add_argument("files", nargs="+", type=Path)

    sub.add_parser("site-setup", help="Update Ghost /about/ page, tags, and positioning")

    p_ghost = sub.add_parser("ghost-sync", help="Inject/update AI-SDLC Blueprint and tags in Ghost post")
    p_ghost.add_argument("post_dir", type=Path)

    p_gh = sub.add_parser("github-sync", help="Scrub and export AI-SDLC case studies to GitHub")
    p_gh.add_argument("--no-push", action="store_true")

    p_prom = sub.add_parser("promote", help="Run GitHub sync, newsletter pitches, and send summary email")
    p_prom.add_argument("post_dir", type=Path)
    p_prom.add_argument("--dry-run", action="store_true")

    p_cron = sub.add_parser("cron-run", help="Check newly published approved posts and run full promotion")
    p_cron.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    env = load_env()

    if args.cmd == "ingest":
        post_dir = args.post_dir if args.post_dir.is_absolute() else (BLOG_ROOT / args.post_dir)
        added = ingest_sources(post_dir, args.files)
        for item in added:
            print(f"Ingested: {item}")
        return 0

    if args.cmd == "github-sync":
        exported = sync_all_github_case_studies(BLOG_ROOT, git_push=not args.no_push)
        print(f"Synced {len(exported)} case studies to GitHub showcase repo.")
        return 0

    api_key = env.get("GHOST_ADMIN_API_KEY", "")
    ghost_client = GhostAdminClient(api_key, base_url=env.get("GHOST_ADMIN_URL", "http://127.0.0.1:2368")) if api_key else None
    smtp_cfg = build_smtp_config(env)

    if args.cmd == "site-setup":
        if not ghost_client:
            raise RuntimeError("GHOST_ADMIN_API_KEY is required in .env")
        res = run_site_setup(ghost_client, env)
        print(json.dumps(res, indent=2))
        return 0

    if args.cmd == "ghost-sync":
        if not ghost_client:
            raise RuntimeError("GHOST_ADMIN_API_KEY is required in .env")
        post_dir = args.post_dir if args.post_dir.is_absolute() else (BLOG_ROOT / args.post_dir)
        updated = sync_post_to_ghost(post_dir, ghost_client)
        print(f"Updated Ghost post: {updated['slug']} (id={updated['id']})")
        return 0

    if args.cmd == "promote":
        post_dir = args.post_dir if args.post_dir.is_absolute() else (BLOG_ROOT / args.post_dir)
        res = promote_post(post_dir, BLOG_ROOT, ghost_client, smtp_cfg, dry_run=args.dry_run, env=env)
        print(res["summary_text_preview"])
        return 0

    if args.cmd == "cron-run":
        if not ghost_client:
            raise RuntimeError("GHOST_ADMIN_API_KEY is required in .env")
        promoted = run_cron_promotions(BLOG_ROOT, ghost_client, smtp_cfg, dry_run=args.dry_run, env=env)
        print(f"cron-run completed: {len(promoted)} post(s) promoted.")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
