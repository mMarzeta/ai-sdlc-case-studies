# Minimalist Engineering Theme & Meta-Post Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deploy the Variant 1 (`mitchellh` / `lucumr`) minimalist theme to `blog.marzeta.pl` and assemble the complete post package (`posts/2026-12-01-blog-ai-sdlc-redesign/`) with specs, plans, session summary, design draft screenshots, and article draft.

**Architecture:** Customize Handlebars templates (`default.hbs`, `partials/cover.hbs`, `partials/loop.hbs`) and inject a dedicated `assets/built/minimal.css` stylesheet in `~/projects/content/themes/dawn_star/`, verified via `pytest` against the local Ghost HTTP server. Capture PNG screenshots of the design drafts and live site and ingest all artifacts into `posts/2026-12-01-blog-ai-sdlc-redesign/`.

**Tech Stack:** Ghost 6 Handlebars (`.hbs`), CSS3, Python 3 + `pytest`, headless Chromium / Playwright screenshot capture.

**Spec:** `~/projects/docs/superpowers/specs/2026-11-14-blog-minimal-theme-design.md`

---

### Task 1: Minimalist Theme Templates & Stylesheet (`dawn_star`)

**Files:**
- Create: `~/projects/content/themes/dawn_star/assets/built/minimal.css`
- Modify: `~/projects/content/themes/dawn_star/default.hbs`
- Modify: `~/projects/content/themes/dawn_star/partials/cover.hbs`
- Modify: `~/projects/content/themes/dawn_star/partials/loop.hbs`
- Test: `~/projects/blog/tests/test_theme_rendering.py`

- [ ] **Step 1: Write failing test `tests/test_theme_rendering.py` checking live Ghost HTML for `.minimal-intro`, `.minimal-post-row`, `.minimal-post-excerpt`, and `minimal.css`**
- [ ] **Step 2: Run pytest to verify RED failure**
- [ ] **Step 3: Implement `minimal.css`, `default.hbs`, `cover.hbs`, and `loop.hbs`, and restart `ghost` container**
- [ ] **Step 4: Run pytest to verify GREEN**

---

### Task 2: Design Draft Screenshots & Post Material Package (`posts/2026-12-01-blog-ai-sdlc-redesign/`)

**Files:**
- Create: `~/projects/blog/posts/2026-12-01-blog-ai-sdlc-redesign/assets/01-rejected-ai-slop-dashboard-draft.png`
- Create: `~/projects/blog/posts/2026-12-01-blog-ai-sdlc-redesign/assets/02-minimalist-variants-comparison.png`
- Create: `~/projects/blog/posts/2026-12-01-blog-ai-sdlc-redesign/assets/03-live-blog-minimal-theme.png`
- Create: `~/projects/blog/posts/2026-12-01-blog-ai-sdlc-redesign/sources/agy_session_summary.md`
- Create: `~/projects/blog/posts/2026-12-01-blog-ai-sdlc-redesign/post.md`
- Create: `~/projects/blog/posts/2026-12-01-blog-ai-sdlc-redesign/campaign.yaml`
- Create: `~/projects/blog/posts/2026-12-01-blog-ai-sdlc-redesign/state.json`

- [ ] **Step 1: Capture PNG screenshots of the rejected draft, the 3-variant comparison, and the live site**
- [ ] **Step 2: Write `agy_session_summary.md`, `post.md`, `campaign.yaml`, `state.json`, and ingest specs/plans via `blogctl.py ingest`**
- [ ] **Step 3: Verify package completeness and run full `pytest` suite**
