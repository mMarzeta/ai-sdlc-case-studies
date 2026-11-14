# Design Spec: Authorship Manifesto ("An Amplifier of Intent, Not a Source of Ideas") & Autonomous Blog Engine Case Study

- **Date:** 2026-11-14
- **Author:** Maciej Marzęta
- **Target System:** `blog.marzeta.pl` (`~/projects/blog`) & `github.com/mMarzeta/ai-sdlc-case-studies`
- **Status:** Approved

---

## 1. Intent & Why

Every article and codebase featured on `blog.marzeta.pl` is produced through a deterministic, spec-driven AI Software Development Life Cycle (AI-SDLC). While autonomous coding and writing agents generate the prose and implementation code, **100% of the problem discovery, creative direction, system architecture, security boundaries, and verification gates originate from Maciej Marzęta's mind**.

To preempt any superficial critique dismissal (*"this was written by AI"*) and turn radical transparency into a core executive positioning asset for CTO / VP Engineering / Principal Engineer audiences, we need both:
1. **A permanent, site-wide disclosure & philosophical anchor** visible on every article's `AI-SDLC Blueprint`, the `/about/` executive profile, and the GitHub portfolio `README.md`.
2. **Two distinct, complementary articles:**
   - **Post #1 (Out-of-order Manifesto, published immediately on `2026-11-14` & featured):** *"Yes, AI Wrote This Blog. No, It’s Not Slop: An Amplifier of Intent (Not a Source of Ideas)"* — articulating why writing polished sentences is no longer proof of work (building on Sean Goedecke's [Writing Is No Longer Proof of Work](https://www.seangoedecke.com/writing-is-no-longer-proof-of-work/)), the **"50 Engineers 24/7 Before 2022" thought experiment**, and the mental model of AI as **50 hyper-literal contractors with encyclopedic memory and zero agency** acting as **an amplifier of human intent (not a source of ideas)**.
   - **Post #2 (Scheduled Tuesday Case Study for `2026-12-01T08:00:00.000Z`):** *"Zero-Touch Technical Publishing: Engineering an Autonomous AI-SDLC Blog & Outreach Engine"* — a deep-dive engineering case study into `blogctl` itself (`tools/`, `tests/`, Ghost 6 Admin API HTML vs. Lexical injection, deterministic regex secret/IP scrubbing for GitHub export, and idempotent Tuesday cron promotion via Mailgun SMTP).

---

## 2. Goals, Non-Goals & Anti-Goals

### Goals
- **Immediate Live Manifesto URL:** Publish Post #1 (`writing-is-no-longer-proof-of-work-amplifier-of-intent`) immediately on Ghost (`status: published`, `featured: true`) so all global links in existing posts, `/about/`, and GitHub `README.md` resolve to a live article today.
- **Global Blueprint & Portfolio Disclosure:** Update `render_blueprint_html()` in `tools/ghost_client.py`, `ABOUT_PAGE_HTML` in `tools/blogctl.py`, and `update_portfolio_readme()` in `tools/github_showcase.py` to include the **Authorship & Proof-of-Work Disclosure** with the punchline *"An Amplifier of Intent (Not a Source of Ideas)"* and links to both the live Manifesto and Sean Goedecke's essay.
- **Full Post Creation in `blogctl ghost-sync`:** Extend `GhostAdminClient` and `sync_post_to_ghost()` so `blogctl ghost-sync` can create new posts in Ghost directly from local `post.md` + `campaign.yaml` (supporting `draft`, `scheduled` with `published_at`, and `published` statuses, plus `featured` and `custom_excerpt`), updating `ghost_post_id` in `campaign.yaml`.
- **Scheduled Meta Case Study (`2026-12-01`):** Author and schedule Post #2 (`posts/2026-12-01-ai-sdlc-blog-engine/`) for Tuesday, December 1, 2026 (`08:00 UTC`), exporting `blogctl`'s own source code (`tools/`, `tests/`, `config/scrubber_rules.yaml`, `PLAYBOOK.md`) and specs/plans to `github.com/mMarzeta/ai-sdlc-case-studies`.

### Non-Goals
- Modifying the Tuesday `08:05 UTC` cron schedule or sending automated newsletter pitches for the out-of-order Manifesto post (newsletter pitches are reserved for technical deep-dive case studies or triggered intentionally).
- Replacing Ghost's theme templates on disk (all injections remain cleanly managed via the Ghost Admin API).

### Anti-Goals
- **Never sound apologetic or defensive about using AI.** The tone must be authoritative, architectural, and unapologetic.
- **Never credit the LLM as an independent creative intelligence ("genius savant").** The framing is strictly: **50 hyper-literal contractors with encyclopedic memory and zero agency — an amplifier of human intent, not a source of ideas.**

---

## 3. Approaches Considered

| Approach | Description | Trade-Offs | Decision |
|---|---|---|---|
| **A. Global Footer & `/about/` Only** | Add a short disclosure to `AI-SDLC Blueprint`, `/about/`, and GitHub README without a dedicated post. | Visible everywhere, but too cramped to develop the "50 engineers before 2022" thought experiment or detail `blogctl`'s architecture. | Rejected |
| **B. Single Combined Post (Manifesto + `blogctl` Tutorial)** | Combine the philosophical manifesto and the technical `blogctl` code walkthrough into one post queued for `2026-12-01`. | Leaves global footer links dead until Dec 1; mixes philosophical essay with low-level JWT/regex implementation details. | Rejected |
| **C. Hybrid Split (Chosen)** | Global disclosure in every Blueprint + `/about/` + GitHub README linking to **Post #1 (Manifesto published immediately out-of-order)** + **Post #2 (Technical `blogctl` Case Study scheduled for `2026-12-01`)**. | Immediate live anchor for every post today; keeps the philosophical manifesto punchy while giving `blogctl` a full `PLAYBOOK.md` technical deep dive in the Tuesday slot. | **Selected** |

---

## 4. Technical & Editorial Specifications

### 4.1 Global Blueprint Disclosure (`tools/ghost_client.py`)
`render_blueprint_html()` will include an authorship disclosure block inside `<section id="ai-sdlc-blueprint">`:
- Explicitly states that prose and implementation code are generated by AI agents acting as **an amplifier of intent, not a source of ideas**.
- References Sean Goedecke's [Writing Is No Longer Proof of Work](https://www.seangoedecke.com/writing-is-no-longer-proof-of-work/) and links to `https://blog.marzeta.pl/writing-is-no-longer-proof-of-work-amplifier-of-intent/`.

### 4.2 Markdown-to-Ghost Creation Pipeline (`tools/ghost_client.py` & `tools/blogctl.py`)
- `GhostAdminClient.create_post_html(title, slug, html, status="draft", tags=None, custom_excerpt=None, featured=False, published_at=None)` sends `POST /ghost/api/admin/posts/?source=html`.
- `extract_markdown_body(md_text: str) -> str` strips the `# Ghost Blog Post:` metadata header (everything up to and including `## Post Body` or the first `---` separator) so only the article body is rendered to HTML via `markdown.markdown(..., extensions=["fenced_code", "tables", "sane_lists"])`.
- `sync_post_to_ghost(post_dir, ghost_client)`:
  - If the post does not exist in Ghost yet, renders `post.md` to HTML, appends `blueprint_html`, creates the post in Ghost with the desired `status` (`published`, `scheduled`, or `draft`), `published_at` (from `scheduled_for` when `status == "scheduled"`), `featured`, `custom_excerpt`, and `tags`, and writes the returned `id` back to `campaign.yaml["ghost_post_id"]`.
  - If the post already exists in Ghost, updates its HTML with the latest `blueprint_html` (and if `overwrite_body=True` or body is empty, refreshes the full HTML from `post.md`).

### 4.3 Post #1: Out-of-Order Manifesto (`posts/2026-11-14-writing-is-not-proof-of-work/`)
- **Slug:** `writing-is-no-longer-proof-of-work-amplifier-of-intent`
- **Title:** `Yes, AI Wrote This Blog. No, It’s Not Slop: An Amplifier of Intent (Not a Source of Ideas)`
- **Status:** `published`, `featured: true`
- **Core Sections:**
  1. **The Radical Transparency Rule:** Every sentence and every line of code on `blog.marzeta.pl` went through AI agents—and why pretending otherwise is productivity theater.
  2. **The Pre-2022 Thought Experiment (50 Engineers Working 24/7):** Imagine someone handed you 50 hyper-literal senior contractors before 2022 who have memorized every manual on Earth, never sleep, and execute whatever you ask—with **zero agency, zero product taste, and zero architectural survival instinct**. Why 95% of people would either freeze or produce an unmaintainable disaster within 48 hours.
  3. **An Amplifier of Intent, Not a Source of Ideas:** Why AI is not a "magic author"—it multiplies whatever is inside the operator's head. Feed it lazy prompts and it amplifies chaos into AI slop. Feed it real-world debugging insights, strict system boundaries, and bite-sized TDD plans derived from the depths of your own mind, and it amplifies one architect into a 50-person engineering org.
  4. **Why Writing Is No Longer Proof of Work (Sean Goedecke):** Expanding on [Sean Goedecke's essay](https://www.seangoedecke.com/writing-is-no-longer-proof-of-work/). When polished prose is free, time spent wordsmithing paragraphs is a vanity metric. True proof of work is **effectiveness, running systems, and verifiable engineering artifacts** (`specs/`, `plans/`, `tests/`, production code).
  5. **How I Hold the System on the Rails (And What’s Coming Next):** Concrete numbers from live case studies on this blog + forward link to the upcoming technical case study on `blogctl`.

### 4.4 Post #2: Technical Case Study on `blogctl` (`posts/2026-12-01-ai-sdlc-blog-engine/`)
- **Slug:** `zero-touch-ai-sdlc-blog-publishing-outreach-engine`
- **Title:** `Zero-Touch Technical Publishing: Engineering an Autonomous AI-SDLC Blog & Outreach Engine (1,450 LOC, 25 Tests)`
- **Status:** `scheduled` (`scheduled_for: '2026-12-01T08:00:00.000Z'`, `approved: true`)
- **Structure (`PLAYBOOK.md` compliant):**
  1. **The Hook:** Why manual portfolio curation, LinkedIn personal-branding theater, and copy-pasting code into blog posts fail for hands-on architects.
  2. **System Architecture & Trade-Offs:** Self-contained `posts/<YYYY-MM-DD-slug>/` packages, hybrid symlink/copy ingestion (`blogctl ingest`), Ghost 6 Admin API (`HS256` JWT + `X-Forwarded-Proto: https`), deterministic GitHub export, and Tuesday `08:05 UTC` cron promotion.
  3. **The War Stories (Contact with Production Reality):**
     - **Ghost 6 Lexical Overwrite vs. `?source=html`:** Why updating `html` without `?source=html` silently discards changes because Ghost 6 re-renders from `lexical`, plus the `re.sub` backslash-escape corruption bug (`\1`, `\d+`) when injecting technical Blueprint summaries.
     - **Deterministic Secret & IP Scrubbing (`ScrubberSecurityError`):** Normalizing `~/projects` paths and RFC 1918 LAN IPs (`192.168.x.x` -> `192.0.2.10`) while hard-blocking accidental credential leaks before `git push`.
     - **Idempotent Outreach & Verbatim Executive Summaries:** Preventing duplicate newsletter pitches via `state.json` and delivering a complete verbatim audit trail + 1-click HN/Reddit/Lobste.rs launch kit via Mailgun SMTP.
  4. **The AI-SDLC Blueprint:** Full metrics and proof-of-work link to `case-studies/2026-12-01-ai-sdlc-blog-engine`.
