# Case Study: Spec-Driven AI SDLC in Practice: Shipping a VPN-Isolated Media Pipeline (2,120 LOC, 136 Tests) in One Evening

- **Article Status:** `DRAFT` on [blog.marzeta.pl](https://blog.marzeta.pl)
- **Author:** Maciej Marzęta ([blog.marzeta.pl](https://blog.marzeta.pl/about/))
- **AI-SDLC Stack:** Gemini 4 Argon (High)

## Executive Summary

Complete AI-SDLC case study: 3 design specs, 2 TDD implementation plans, architecture trade-off analysis, and a 2,120-LOC FastAPI/SQLite/Gluetun media pipeline with 136 pytest tests.

## AI-SDLC Delivery Metrics

| Metric | Value |
|---|---|
| **Production Footprint** | `2,120 LOC Python backend + 926 LOC UI` |
| **Automated Verification / Tests** | `136 automated pytest tests (~3,200 LOC test suite)` |
| **Design Specs Authored Before Code** | `3` |
| **TDD Implementation Plans** | `2` |

## AI-SDLC Artifacts (`specs-and-plans/`)

- [`2026-11-13-vpn-torrent-drop-design.md`](./specs-and-plans/2026-11-13-vpn-torrent-drop-design.md)
- [`2026-11-13-vpn-torrent-drop.md`](./specs-and-plans/2026-11-13-vpn-torrent-drop.md)
- [`2026-11-14-magnet-links-design.md`](./specs-and-plans/2026-11-14-magnet-links-design.md)
- [`2026-11-14-magnet-links.md`](./specs-and-plans/2026-11-14-magnet-links.md)
- [`2026-11-14-rich-html-emails-design.md`](./specs-and-plans/2026-11-14-rich-html-emails-design.md)
- [`architecture_decisions_summary.md`](./specs-and-plans/architecture_decisions_summary.md)
