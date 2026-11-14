# AGY Architecture & Design Session Summary: Why Every AI-Generated Blog Looks Like a SaaS Pricing Page (And Returning to `mitchellh` / `lucumr` Minimalism)

**Date:** 2026-11-14  
**Session ID:** `ff417bb8-3614-419b-b63a-0790bf8ce2cf`  
**Model:** Gemini 4 Argon (High)  
**Target Service:** `blog.marzeta.pl` (`content/themes/dawn_star` in Ghost 6)

---

## 1. Problem Statement & Initial Requirements

During the rollout of the `blogctl` AI-SDLC publishing engine on `blog.marzeta.pl`, two issues surfaced immediately on the live Ghost 6 instance:
1. **UTF-8 / Mojibake Corruption in MySQL:** Author bio and site metadata updated via raw `mysql` CLI without `--default-character-set=utf8mb4` rendered Polish diacritics and em-dashes as mojibake (`Case Studies â€” by Maciej MarzÄ™ta`).
2. **Default Theme Noise vs. Senior Engineering Signal:** The stock Ghost Dawn theme (`dawn_star`) coupled with our initial attempt to redesign it produced what every LLM defaults to when asked for a "CTO / Head of AI technical blog": dark-mode bento cards, neon glowing pills (`2,120 LOC · 136 Tests · 3 Specs`), multi-button hero banners, and squashed multi-column grids.

## 2. The Rejected First Draft ("AI Slop")

In the first iteration (`01-rejected-dashboard-slop-draft.png`), the agent generated three dark-mode dashboard concepts inside a constrained preview card frame:
- **Why it failed:**
  - It treated an engineering blog like a Series A AI SaaS landing page.
  - Multi-column flexbox headers wrapped awkwardly inside narrow containers.
  - Badge proliferation (`AI-SDLC`, `2,120 LOC · 136 Tests`) on every homepage row turned reading into scanning a telemetry dashboard.
- **Human Architect Verdict:** *"każde wygląda jak slop i źle się renderuje. Może coś bardziej na podstawie blogów które odnosza sukcesy a nie sa przekomplikowane?"* ("Every one of these looks like slop and renders poorly. How about something based on blogs that actually succeed without being over-complicated?")

## 3. Pivot: Studying Engineering Blogs That Actually Succeed

Instead of inventing ornamental UI chrome, we benchmarked the personal blogs of some of the most respected systems engineers and technical leaders on the internet:
- **Mitchell Hashimoto (`mitchellh.com`)**
- **Armin Ronacher (`lucumr.pocoo.org`)**
- **Simon Willison (`simonwillison.net`)**
- **Gergely Orosz (`blog.pragmaticengineer.com`)**

### Key Design Invariants Extracted (`02-minimalist-variants-comparison.png`)
1. **Single-Column `680px` Reading Container:** Zero multi-column grids, zero feature cards, zero thumbnails.
2. **Warm Paper Background (`#fbfaf7`) & High-Contrast Ink (`#18181b`):** Instantly distinguishes long-form engineering writing from dark-mode AI landing pages.
3. **Two-Sentence Plain-Text Identity Intro:** No bordered hero box, no CTA buttons—just two sentences stating who the author is, what the blog covers, and an inline underlined link to the [GitHub Case Studies repository](https://github.com/mMarzeta/ai-sdlc-case-studies) and [/about/](https://blog.marzeta.pl/about/).
4. **Year-Grouped Chronological Index (`2026`):** Tabular monospace dates (`MMM DD`, `82px` column) paired with bold titles and a single-sentence summary (`custom_excerpt`).

## 4. Implementation & Visual Verification Catch

We implemented the theme override across 4 files in `~/projects/content/themes/dawn_star`:
- `assets/built/minimal.css` (295 LOC)
- `default.hbs`
- `partials/cover.hbs`
- `partials/loop.hbs`

### Catching Dawn JS & CSS Collisions via Headless Browser Verification
When we captured a headless Chromium (`Brave Browser --headless`) screenshot of the live site (`03-live-blog-minimal-theme.png`) after the initial deploy, visual inspection revealed two subtle regressions that HTML string assertions (`pytest`) missed:
1. **Dawn's `main.min.js` Responsive Menu Collapse:** Because `.gh-head-inner` was constrained to `680px`, Dawn's JavaScript calculated that `.gh-head-menu` was too wide for its 3-column header grid and collapsed all navigation links into a `...` overflow button. **Fix:** Renamed the nav container to `.minimal-head-nav` with a clean 2-part flex layout (`justify-content: space-between`), bypassing Dawn's overflow script.
2. **Dawn's `.post-feed .post` Vertical Centering:** Passing Ghost's `{{post_class}}` helper onto `<article class="minimal-post-row">` applied `.post`, which inherited `align-items: center` from Dawn's `screen.css`, causing the `MMM DD` date to float mid-row instead of aligning with the first line of the post title. **Fix:** Removed `{{post_class}}` from `.minimal-post-row` and enforced `align-items: start !important;`.
