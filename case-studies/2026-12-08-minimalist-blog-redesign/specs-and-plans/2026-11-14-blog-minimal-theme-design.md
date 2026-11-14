# Design Spec: Minimalist Engineering Theme (`mitchellh` / `lucumr` Style) & Meta-Case Study Package

- **Date:** 2026-11-14
- **Target Host:** Raspberry Pi 5 (`raspberrypi`, `~/projects/content/themes/dawn_star` & `~/projects/blog/posts/2026-12-01-blog-ai-sdlc-redesign`)

## 1. Intent & Why

When designing the visual layer for `blog.marzeta.pl`, the initial AI-generated mockup used heavy dashboard cards, neon pill badges, and multi-column bento grids—which immediately looked like generic "AI slop" rather than a credible principal/CTO publication. By contrast, the most respected technical leaders in the industry (Mitchell Hashimoto, Armin Ronacher, Simon Willison, Andrej Karpathy) use calm, single-column, typography-first layouts where the engineering content and proof-of-work speak for themselves.

This spec covers:
1. Transforming the active Ghost theme (`dawn_star`) into the approved **Variant 1 (Mitchell Hashimoto / Armin Ronacher `lucumr` style)**.
2. Packaging this entire session (specs, plans, requirements, rejected vs. approved design mockup screenshots, and a concise post draft) as a self-contained blog post package in `~/projects/blog/posts/2026-12-01-blog-ai-sdlc-redesign/`.

## 2. Requirements & Visual Design Decisions

1. **Palette & Single-Column Measure (`assets/built/minimal.css`):**
   - Light mode: warm paper `#fbfaf7`, primary text `#1c1917`, muted text `#57534e`, monospace metadata `#78716c`, hairline borders `#e7e5e4`.
   - Dark mode (`.theme-dark` or `prefers-color-scheme: dark` when Auto): warm charcoal `#141413`, primary text `#f5f5f4`, muted text `#a8a29e`, borders `#292524`.
   - Maximum content container width: `680px` centered across header, homepage feed, and article body.
2. **Header & Plain-Text Intro (`default.hbs` & `partials/cover.hbs`):**
   - Top bar: `Maciej Marzęta` (left, bold `18px`) and clean text navigation links on the right (`Home`, `AI-SDLC`, `Architecture`, `Python`, `GitHub Case Studies`, `About`).
   - Homepage intro (`partials/cover.hbs`): 2-sentence plain-text introduction explaining the focus on deterministic Spec-Driven AI SDLC, high-performance Python, and production architecture, with inline underlined links to the [GitHub Case Studies repository](https://github.com/mMarzeta/ai-sdlc-case-studies) and [About / Advisory](/about/). No noisy button bars.
3. **Chronological Year-Grouped Post List (`index.hbs` & `partials/loop.hbs`):**
   - Posts are grouped under uppercase monospace year dividers (`2026`, `2025`, `2024`).
   - Each post row (`partials/loop.hbs`) is a 2-column grid (`78px 1fr`):
     - Left column: monospace date (`MMM DD`, e.g., `Nov 10`).
     - Right column: bold post title (`16px`) + 1-sentence subtitle beneath (`custom_excerpt` or 22-word excerpt).
4. **Restrained `#ai-sdlc-blueprint` Note Inside Articles:**
   - Styled as an understated engineering specification callout (`background: #f5f3ef` in light mode / `#1c1917` in dark mode, `border-left: 3px solid #1c1917` / `#e7e5e4`, monospace uppercase heading).
5. **Blog Post Material Package (`posts/2026-12-01-blog-ai-sdlc-redesign/`):**
   - `sources/`: Both specs, both implementation plans, and `agy_session_summary.md`.
   - `assets/`: PNG screenshots of:
     - `01-rejected-ai-slop-dashboard-draft.png` (rejected first draft)
     - `02-minimalist-variants-comparison.png` (approved Variant 1 comparison)
     - `03-live-blog-minimal-theme.png` (final deployed `blog.marzeta.pl`)
   - `post.md` & `campaign.yaml`: Concise meta-case study draft ready for review.
