# Case Study: iOS-Style "Screen Time" for Sony Bravia Google TVs: ADB Polling, Per-App History Stats, and Dual Limit Alerts in Home Assistant

- **Published Article:** [https://blog.marzeta.pl/ios-screen-time-sony-bravia-home-assistant-adb/](https://blog.marzeta.pl/ios-screen-time-sony-bravia-home-assistant-adb/)
- **Author:** Maciej Marzęta ([blog.marzeta.pl](https://blog.marzeta.pl/about/))
- **AI-SDLC Stack:** Gemini 4 Argon (High)

## Executive Summary

Spec-driven implementation of iOS-style per-app Screen Time tracking and daily limit alerts for Sony Bravia Google TVs using Python, ADB polling, and Home Assistant.

## AI-SDLC Delivery Metrics

| Metric | Value |
|---|---|
| **Production Footprint** | `Python ADB foreground-app monitor + Home Assistant history_stats & dual-alert automations` |
| **Automated Verification / Tests** | `Automated unit test suite (test_tv_adb_monitor.py) + live ADB state-transition verification` |
| **Design Specs Authored Before Code** | `1` |
| **TDD Implementation Plans** | `1` |

## AI-SDLC Artifacts (`specs-and-plans/`)

- [`2026-11-08-tv-usage-tracking-ha-design.md`](./specs-and-plans/2026-11-08-tv-usage-tracking-ha-design.md)
- [`2026-11-08-tv-usage-tracking-ha.md`](./specs-and-plans/2026-11-08-tv-usage-tracking-ha.md)
