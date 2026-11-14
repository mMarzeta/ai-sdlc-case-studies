from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
from typing import Any
import yaml


class ScrubberSecurityError(Exception):
    """Raised when sensitive credentials or tokens are detected in exported content."""


DEFAULT_RULES: dict[str, Any] = {
    "replacements": [
        {
            "pattern": r"./src/docs/superpowers/(?:specs|plans)/([A-Za-z0-9._-]+)",
            "replacement": r"./specs-and-plans/\1",
        },
        {
            "pattern": r"./src/blog/[^)\s]+/sources/([A-Za-z0-9._-]+)",
            "replacement": r"./specs-and-plans/\1",
        },
        {
            "pattern": r"file://~/projects/([A-Za-z0-9._/-]+)",
            "replacement": r"./src/\1",
        },
        {
            "pattern": r"~/projects",
            "replacement": r"~/projects",
        },
        {
            "pattern": r"~",
            "replacement": r"~",
        },
        {
            "pattern": r"\b192\.168\.\d{1,3}\.\d{1,3}\b",
            "replacement": r"192.0.2.10",
        },
    ],
    "blocked_patterns": [
        r'(?:GHOST_DB_PASSWORD|GHOST_MAILGUN_PASSWD|SMTP_PASSWORD|MYSQL_ROOT_PASSWORD|WIREGUARD_PRIVATE_KEY|GHOST_ADMIN_API_KEY)\s*=\s*(?!["\']?\$\{)(?!["\']?<)(?!smtppass\b)(?!testpass\b)[^\s"\'#]{6,}',
        r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"\bsk-[A-Za-z0-9]{20,}\b",
    ],
}

SKIP_NAMES = {
    ".env",
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "downloads",
    "data",
    "node_modules",
}

SKIP_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".bak",
}

TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".py",
    ".sh",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".html",
    ".css",
    ".js",
    ".service",
    ".ini",
    ".cfg",
}


def loaded_default_rules(config_path: Path | None = None) -> dict[str, Any]:
    if config_path is None:
        candidate = Path(__file__).resolve().parent.parent / "config" / "scrubber_rules.yaml"
        if candidate.exists():
            config_path = candidate
    if config_path and config_path.exists():
        return yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return DEFAULT_RULES


def scrub_content(text: str, rules: dict[str, Any]) -> str:
    cleaned = text
    for item in rules.get("replacements", []):
        cleaned = re.sub(item["pattern"], item["replacement"], cleaned)

    for blocked in rules.get("blocked_patterns", []):
        match = re.search(blocked, cleaned)
        if match:
            snippet = match.group(0)[:24] + "..."
            raise ScrubberSecurityError(f"Blocked secret pattern matched: {snippet}")

    return cleaned


def _should_skip(path: Path) -> bool:
    name = path.name
    if name in SKIP_NAMES or name.startswith(".env") or name.endswith(".egg-info") or ".bak" in name:
        return True
    if path.suffix.lower() in SKIP_SUFFIXES:
        return True
    return False


TEXT_FILENAMES = {
    "Dockerfile",
    "Makefile",
    "Caddyfile",
    "Procfile",
    "LICENSE",
    ".gitignore",
}


def _is_text_file(real_src: Path) -> bool:
    if real_src.suffix.lower() in TEXT_EXTENSIONS or real_src.name in TEXT_FILENAMES:
        return True
    try:
        chunk = real_src.read_bytes()[:2048]
        return b"\x00" not in chunk
    except OSError:
        return False


def _copy_and_scrub_file(src_file: Path, dst_file: Path, rules: dict[str, Any]) -> None:
    real_src = src_file.resolve()
    if not real_src.exists() or _should_skip(src_file) or _should_skip(real_src):
        return
    dst_file.parent.mkdir(parents=True, exist_ok=True)
    if _is_text_file(real_src):
        raw = real_src.read_text(encoding="utf-8", errors="replace")
        cleaned = scrub_content(raw, rules)
        dst_file.write_text(cleaned, encoding="utf-8")
    else:
        shutil.copy2(real_src, dst_file)


def _copy_and_scrub_tree(src_path: Path, dst_root: Path, rules: dict[str, Any]) -> None:
    real_src = src_path.resolve()
    if not real_src.exists() or _should_skip(src_path):
        return
    if real_src.is_file():
        _copy_and_scrub_file(real_src, dst_root / src_path.name, rules)
        return

    for item in sorted(real_src.rglob("*")):
        rel = item.relative_to(real_src)
        if any(_should_skip(Path(p)) for p in rel.parts):
            continue
        if item.is_file():
            _copy_and_scrub_file(item, dst_root / src_path.name / rel, rules)


def export_case_study(
    post_dir: Path,
    repo_dir: Path,
    rules: dict[str, Any] | None = None,
    git_push: bool = False,
) -> dict[str, Any]:
    if rules is None:
        rules = loaded_default_rules()

    campaign_path = post_dir / "campaign.yaml"
    campaign = yaml.safe_load(campaign_path.read_text(encoding="utf-8"))
    showcase_cfg = campaign.get("github_showcase", {})
    case_study_rel = showcase_cfg.get("case_study_dir", f"case-studies/{post_dir.name}")
    target_dir = repo_dir / case_study_rel

    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Export sources/ (specs, plans, architecture summaries)
    sources_dir = post_dir / "sources"
    specs_out = target_dir / "specs-and-plans"
    exported_specs: list[str] = []
    if sources_dir.exists():
        for entry in sorted(sources_dir.iterdir()):
            if _should_skip(entry) or entry.name.endswith(".jsonl"):
                continue
            real_entry = entry.resolve()
            if real_entry.is_file():
                _copy_and_scrub_file(entry, specs_out / entry.name, rules)
                exported_specs.append(entry.name)

    # 2. Export include_paths into src/
    src_out = target_dir / "src"
    for rel_inc in showcase_cfg.get("include_paths", []):
        inc_path = (post_dir / rel_inc).resolve()
        if inc_path.exists():
            _copy_and_scrub_tree(inc_path, src_out, rules)

    # 3. Render case study README.md
    slug = campaign["slug"]
    title = campaign["title"]
    status = campaign.get("status", "published")
    post_url = f"https://blog.marzeta.pl/{slug}/"
    article_line = (
        f"- **Published Article:** [{post_url}]({post_url})\n"
        if status == "published"
        else f"- **Article Status:** `{status.upper()}` on [blog.marzeta.pl](https://blog.marzeta.pl)\n"
    )
    metrics = campaign.get("sdlc_metrics", {})
    summary = showcase_cfg.get("summary", "")

    specs_list_md = "\n".join(f"- [`{name}`](./specs-and-plans/{name})" for name in exported_specs) or "- *See article for architectural breakdown*"
    case_readme = (
        f"# Case Study: {title}\n\n"
        f"{article_line}"
        f"- **Author:** Maciej Marzęta ([blog.marzeta.pl](https://blog.marzeta.pl/about/))\n"
        f"- **AI-SDLC Stack:** {', '.join(metrics.get('models_used', ['Gemini 4 Argon (High)']))}\n\n"
        f"## Executive Summary\n\n{summary}\n\n"
        "## AI-SDLC Delivery Metrics\n\n"
        "| Metric | Value |\n"
        "|---|---|\n"
        f"| **Production Footprint** | `{metrics.get('code_loc', 'N/A')}` |\n"
        f"| **Automated Verification / Tests** | `{metrics.get('test_count', 'N/A')}` |\n"
        f"| **Design Specs Authored Before Code** | `{metrics.get('specs_count', 'N/A')}` |\n"
        f"| **TDD Implementation Plans** | `{metrics.get('plans_count', 'N/A')}` |\n\n"
        "## AI-SDLC Artifacts (`specs-and-plans/`)\n\n"
        f"{specs_list_md}\n"
    )
    (target_dir / "README.md").write_text(case_readme, encoding="utf-8")

    result = {
        "folder": post_dir.name,
        "slug": slug,
        "title": title,
        "status": status,
        "post_url": post_url,
        "case_study_rel": case_study_rel,
        "github_url": f"https://github.com/mMarzeta/ai-sdlc-case-studies/tree/main/{case_study_rel}",
        "metrics": metrics,
        "summary": summary,
    }

    if git_push and (repo_dir / ".git").exists():
        _git_commit_and_push(repo_dir, f"feat(case-study): sync {post_dir.name} AI-SDLC artifacts")

    return result


def update_portfolio_readme(repo_dir: Path, case_studies: list[dict[str, Any]], git_push: bool = False) -> Path:
    rows = []
    for cs in sorted(case_studies, key=lambda x: x["folder"], reverse=True):
        m = cs.get("metrics", {})
        status = cs.get("status", "published")
        if status == "published":
            title_cell = f"[{cs['title']}]({cs['post_url']})"
        elif status == "scheduled":
            title_cell = f"**{cs['title']}** *(Scheduled: {cs['folder'][:10]})*"
        else:
            title_cell = f"**{cs['title']}** *(Upcoming Case Study)*"
        rows.append(
            f"| **{cs['folder'][:10]}** | {title_cell} | "
            f"[`{cs['case_study_rel']}`](./{cs['case_study_rel']}/) | "
            f"`{m.get('specs_count', '-')}` specs / `{m.get('plans_count', '-')}` plans | "
            f"`{m.get('code_loc', '-')}` | `{m.get('test_count', '-')}` |"
        )
    table_body = "\n".join(rows)
    readme_text = (
        "# AI-Native SDLC Case Studies & Production Architecture Portfolio\n\n"
        "**Author:** Maciej Marzęta — Technical Leader, Systems Architect & AI-Native SDLC Practitioner  \n"
        "**Publication:** [blog.marzeta.pl](https://blog.marzeta.pl) | **Executive Profile:** [blog.marzeta.pl/about](https://blog.marzeta.pl/about/) | **Contact:** `contact@marzeta.pl`\n\n"
        "---\n\n"
        "## Why This Repository Exists\n\n"
        "Most organizations struggle to adopt AI in software engineering because developers treat LLMs as ad-hoc chat autocomplete—resulting in architectural drift, unreviewed tech debt, and fragile production releases.\n\n"
        "This repository contains **verifiable, production Proof-of-Work** demonstrating a deterministic **Spec-Driven AI Software Development Life Cycle (AI-SDLC)**:\n"
        "1. **Architecture & Threat-Model Specs First (`specs/`):** Before any implementation code is written, agentic brainstorming and adversarial builder-checks lock down constraints, state machines, and trade-offs.\n"
        "2. **Bite-Sized TDD Implementation Plans (`plans/`):** Specs are decomposed into strict Red-Green-Refactor tasks with explicit interface contracts.\n"
        "3. **Subagent Execution & Automated Verification (`src/` & `tests/`):** Autonomous agents execute under strict test gates, producing hardened production services.\n\n"
        "## Authorship & Proof of Work: An Amplifier of Intent (Not a Source of Ideas)\n\n"
        "Every article on `blog.marzeta.pl` and every codebase in this repository is generated with AI agents—and none of it is \"AI slop.\" Every problem diagnosed, every architectural constraint, and every creative leap comes from my mind; the agents act as **50 hyper-literal contractors with encyclopedic memory and zero agency**—**an amplifier of intent, not a source of ideas**.\n\n"
        "As Sean Goedecke argues in [*Writing Is No Longer Proof of Work*](https://www.seangoedecke.com/writing-is-no-longer-proof-of-work/), manually wordsmithing sentences is no longer proof of engineering labor. Real proof of work is effectiveness, running systems, and verifiable outcomes. Read the full manifesto: [**Yes, AI Wrote This Blog. No, It’s Not Slop: An Amplifier of Intent (Not a Source of Ideas) →**](https://blog.marzeta.pl/writing-is-no-longer-proof-of-work-amplifier-of-intent/)\n\n"
        "## Published Case Studies\n\n"
        "| Date | Case Study Article | Artifacts & Code | Governance (Specs / Plans) | Footprint | Verification Gate |\n"
        "|---|---|---|---|---|---|\n"
        f"{table_body}\n"
    )
    readme_path = repo_dir / "README.md"
    readme_path.write_text(readme_text, encoding="utf-8")

    if git_push and (repo_dir / ".git").exists():
        _git_commit_and_push(repo_dir, "docs(portfolio): update AI-SDLC case studies index")

    return readme_path


def _git_commit_and_push(repo_dir: Path, message: str) -> str | None:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=True,
    )
    if not status.stdout.strip():
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_dir, capture_output=True, text=True, check=False)
        return head.stdout.strip() or None

    subprocess.run(["git", "add", "-A"], cwd=repo_dir, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Maciej Marzeta", "-c", "user.email=23502918+mMarzeta@users.noreply.github.com", "commit", "-m", message],
        cwd=repo_dir,
        check=True,
    )
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=repo_dir, check=True)
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo_dir, capture_output=True, text=True, check=True)
    return head.stdout.strip()
