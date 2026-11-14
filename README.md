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

## Published Case Studies

| Date | Case Study Article | Artifacts & Code | Governance (Specs / Plans) | Footprint | Verification Gate |
|---|---|---|---|---|---|
| **2026-11-24** | [Spec-Driven AI SDLC in Practice: Shipping a VPN-Isolated Media Pipeline (2,120 LOC, 136 Tests) in One Evening](https://blog.marzeta.pl/spec-driven-ai-sdlc-vpn-torrent-drop-media-pipeline/) | [`case-studies/2026-11-24-torrent-drop`](./case-studies/2026-11-24-torrent-drop/) | `3` specs / `2` plans | `2,120 LOC Python backend + 926 LOC UI` | `136 automated pytest tests (~3,200 LOC test suite)` |
| **2026-11-17** | [iOS-Style "Screen Time" for Sony Bravia Google TVs: ADB Polling, Per-App History Stats, and Dual Limit Alerts in Home Assistant](https://blog.marzeta.pl/ios-screen-time-sony-bravia-home-assistant-adb/) | [`case-studies/2026-11-17-tv-screentime`](./case-studies/2026-11-17-tv-screentime/) | `1` specs / `1` plans | `Python ADB foreground-app monitor + Home Assistant history_stats & dual-alert automations` | `Automated unit test suite (test_tv_adb_monitor.py) + live ADB state-transition verification` |
| **2026-11-10** | [Reclaiming Two Bravia OLEDs: Debloating ACR Spyware, the Setupwraith Brick War Story, and Real-World Living-Room UX](https://blog.marzeta.pl/reclaiming-sony-bravia-oleds-debloat-ux/) | [`case-studies/2026-11-10-bravia65-debloat`](./case-studies/2026-11-10-bravia65-debloat/) | `2` specs / `2` plans | `42 Android system packages audited & stripped across 2 OLED TVs via ADB` | `Zero-telemetry DNS verification via Pi-hole + multi-TV rollout plan` |
| **2026-11-03** | [From 32-Bit Hacks to 64-Bit Native: Auditing & Hardening a 20-Container Raspberry Pi 5 Homelab](https://blog.marzeta.pl/from-32-bit-hacks-to-64-bit-native-raspberry-pi-5-homelab/) | [`case-studies/2026-11-03-homelab-64bit`](./case-studies/2026-11-03-homelab-64bit/) | `2` specs / `1` plans | `20-service Docker Compose stack + automated backup & healthcheck orchestration` | `20/20 native aarch64 containers verified healthy with zero seccomp/32-bit workarounds` |
| **2026-10-27** | [Surviving a Week of 9.8 RCEs on a Raspberry Pi: How I Built a Zero-Noise CVE Watchdog with Gemini 4 Argon & AGY](https://blog.marzeta.pl/surviving-a-week-of-critical-rces-on-a-raspberry-pi/) | [`case-studies/2026-10-27-cve-watchdog`](./case-studies/2026-10-27-cve-watchdog/) | `2` specs / `2` plans | `520 LOC Bash/Python automation + multi-stage Dockerfile patches` | `74 Critical CVEs -> 0 across 20 containers (Trivy + BATS test suite)` |
