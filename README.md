# AI-Native SDLC Case Studies & Production Architecture Portfolio

**Author:** Maciej Marzęta — Technical Leader, Systems Architect & AI-Native SDLC Practitioner  
**Publication:** [blog.marzeta.pl](https://blog.marzeta.pl) | **Executive Profile:** [blog.marzeta.pl/about](https://blog.marzeta.pl/about/) | **Contact:** `contact@marzeta.pl`

---

## Why This Repository Exists

Most organizations struggle to adopt AI in software engineering because developers treat LLMs as ad-hoc chat autocomplete—resulting in architectural drift, unreviewed tech debt, and fragile production releases.

This repository contains **verifiable, production Proof-of-Work** demonstrating a deterministic **Spec-Driven AI Software Development Life Cycle (AI-SDLC)**:
1. **Architecture & Threat-Model Specs First (`specs/`):** Before any implementation code is written, agentic brainstorming and adversarial builder-checks lock down constraints, state machines, and trade-offs.
2. **Bite-Sized TDD Implementation Plans (`plans/`):** Specs are decomposed into strict Red-Green-Refactor tasks with explicit interface contracts.
3. **Subagent Execution & Automated Verification (`src/` & `tests/`):** Autonomous agents execute under strict test gates, producing hardened production services.

## Authorship & Proof of Work: An Amplifier of Intent (Not a Source of Ideas)

Every article on `blog.marzeta.pl` and every codebase in this repository is generated with AI agents—and none of it is "AI slop." Every problem diagnosed, every architectural constraint, and every creative leap comes from my mind; the agents act as **50 hyper-literal contractors with encyclopedic memory and zero agency**—**an amplifier of intent, not a source of ideas**.

As Sean Goedecke argues in [*Writing Is No Longer Proof of Work*](https://www.seangoedecke.com/writing-is-no-longer-proof-of-work/), manually wordsmithing sentences is no longer proof of engineering labor. Real proof of work is effectiveness, running systems, and verifiable outcomes. Read the full manifesto: [**Yes, AI Wrote This Blog. No, It’s Not Slop: An Amplifier of Intent (Not a Source of Ideas) →**](https://blog.marzeta.pl/writing-is-no-longer-proof-of-work-amplifier-of-intent/)

## Published Case Studies

| Date | Case Study Article | Artifacts & Code | Governance (Specs / Plans) | Footprint | Verification Gate |
|---|---|---|---|---|---|
| **2026-12-08** | **Why Every AI-Generated Blog Looks Like a SaaS Pricing Page (And Why I Rebuilt Mine Like Mitchell Hashimoto’s)** *(Scheduled: 2026-12-08)* | [`case-studies/2026-12-08-minimalist-blog-redesign`](./case-studies/2026-12-08-minimalist-blog-redesign/) | `1` specs / `1` plans | `295 LOC Minimalist CSS & 4 Ghost 6 Handlebars Templates (default.hbs, cover.hbs, loop.hbs, minimal.css)` | `19 automated pytest tests + 3 headless Chromium visual verification screenshots` |
| **2026-12-01** | **Zero-Touch Technical Publishing: Engineering an Autonomous AI-SDLC Blog & Outreach Engine (1,450 LOC, 18 Tests)** *(Scheduled: 2026-12-01)* | [`case-studies/2026-12-01-ai-sdlc-blog-engine`](./case-studies/2026-12-01-ai-sdlc-blog-engine/) | `2` specs / `2` plans | `1,450 LOC Python CLI, Ghost JWT Client, Regex Scrubber & SMTP Outreach Engine` | `18 automated pytest unit & integration tests (~410 LOC test suite)` |
| **2026-11-24** | **Spec-Driven AI SDLC in Practice: Shipping a VPN-Isolated Media Pipeline (2,120 LOC, 136 Tests) in One Evening** *(Upcoming Case Study)* | [`case-studies/2026-11-24-torrent-drop`](./case-studies/2026-11-24-torrent-drop/) | `3` specs / `2` plans | `2,120 LOC Python backend + 926 LOC UI` | `136 automated pytest tests (~3,200 LOC test suite)` |
| **2026-11-17** | **iOS-Style "Screen Time" for Sony Bravia Google TVs: ADB Polling, Per-App History Stats, and Dual Limit Alerts in Home Assistant** *(Scheduled: 2026-11-17)* | [`case-studies/2026-11-17-tv-screentime`](./case-studies/2026-11-17-tv-screentime/) | `1` specs / `1` plans | `Python ADB foreground-app monitor + Home Assistant history_stats & dual-alert automations` | `Automated unit test suite (test_tv_adb_monitor.py) + live ADB state-transition verification` |
| **2026-11-10** | [Reclaiming Two Bravia OLEDs: Debloating ACR Spyware, the Setupwraith Brick War Story, and Real-World Living-Room UX](https://blog.marzeta.pl/reclaiming-sony-bravia-oleds-debloat-ux/) | [`case-studies/2026-11-10-bravia65-debloat`](./case-studies/2026-11-10-bravia65-debloat/) | `2` specs / `2` plans | `42 Android system packages audited & stripped across 2 OLED TVs via ADB` | `Zero-telemetry DNS verification via Pi-hole + multi-TV rollout plan` |
| **2026-11-03** | [From 32-Bit Hacks to 64-Bit Native: Auditing & Hardening a 20-Container Raspberry Pi 5 Homelab](https://blog.marzeta.pl/from-32-bit-hacks-to-64-bit-native-raspberry-pi-5-homelab/) | [`case-studies/2026-11-03-homelab-64bit`](./case-studies/2026-11-03-homelab-64bit/) | `2` specs / `1` plans | `20-service Docker Compose stack + automated backup & healthcheck orchestration` | `20/20 native aarch64 containers verified healthy with zero seccomp/32-bit workarounds` |
| **2026-10-27** | [Surviving a Week of 9.8 RCEs on a Raspberry Pi: How I Built a Zero-Noise CVE Watchdog with Gemini 4 Argon & AGY](https://blog.marzeta.pl/surviving-a-week-of-critical-rces-on-a-raspberry-pi/) | [`case-studies/2026-10-27-cve-watchdog`](./case-studies/2026-10-27-cve-watchdog/) | `2` specs / `2` plans | `520 LOC Bash/Python automation + multi-stage Dockerfile patches` | `74 Critical CVEs -> 0 across 20 containers (Trivy + BATS test suite)` |
