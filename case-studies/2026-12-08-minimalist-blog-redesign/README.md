# Case Study: Why Every AI-Generated Blog Looks Like a SaaS Pricing Page (And Why I Rebuilt Mine Like Mitchell Hashimoto’s)

- **Article Status:** `SCHEDULED` on [blog.marzeta.pl](https://blog.marzeta.pl)
- **Author:** Maciej Marzęta ([blog.marzeta.pl](https://blog.marzeta.pl/about/))
- **AI-SDLC Stack:** Gemini 4 Argon (High)

## Executive Summary

Visual redesign case study of blog.marzeta.pl: why LLM-generated UI defaults converge on dark-mode SaaS bento slop, how we pivoted to 680px warm-paper minimalism (mitchellh.com / lucumr style), including before/after design draft PNGs, Handlebars/CSS overrides, and pytest + headless browser verification.

## AI-SDLC Delivery Metrics

| Metric | Value |
|---|---|
| **Production Footprint** | `295 LOC Minimalist CSS & 4 Ghost 6 Handlebars Templates (default.hbs, cover.hbs, loop.hbs, minimal.css)` |
| **Automated Verification / Tests** | `19 automated pytest tests + 3 headless Chromium visual verification screenshots` |
| **Design Specs Authored Before Code** | `1` |
| **TDD Implementation Plans** | `1` |

## AI-SDLC Artifacts (`specs-and-plans/`)

- [`01-rejected-dashboard-slop-draft.png`](./specs-and-plans/01-rejected-dashboard-slop-draft.png)
- [`02-minimalist-variants-comparison.png`](./specs-and-plans/02-minimalist-variants-comparison.png)
- [`03-live-blog-minimal-theme.png`](./specs-and-plans/03-live-blog-minimal-theme.png)
- [`2026-11-14-agy-minimal-theme-session-summary.md`](./specs-and-plans/2026-11-14-agy-minimal-theme-session-summary.md)
- [`2026-11-14-blog-minimal-theme-design.md`](./specs-and-plans/2026-11-14-blog-minimal-theme-design.md)
- [`2026-11-14-blog-minimal-theme.md`](./specs-and-plans/2026-11-14-blog-minimal-theme.md)
