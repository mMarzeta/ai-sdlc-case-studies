# Home Assistant TV Usage & App Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track daily TV open hours and per-app usage for Bravia 65 (Maciej, `192.0.2.10`) and Bravia 55 (Żona, `192.0.2.10`) in Home Assistant, display them on a new `Telewizory` dashboard, and notify both iPhone and TV screen after 4 hours of daily usage.

**Architecture:** A Python script (`/config/scripts/tv_adb_monitor.py`) inside the Home Assistant container uses `adb_shell` and the existing authorized ADB key pair (`/config/.storage/androidtv_adbkey`) to poll both TVs every 30s and send on-screen notifications. Home Assistant `command_line`, `template`, and `history_stats` sensors compute daily total and per-app hours, while `automations.yaml` and `tv_dashboard.yaml` handle the 4-hour alerts and UI.

**Tech Stack:** Home Assistant Core (Docker on `raspberrypi`), Python 3 (`adb_shell`), Android ADB (`dumpsys` / `cmd notification`), Lovelace YAML.

**Spec:** `docs/superpowers/specs/2026-11-08-tv-usage-tracking-ha-design.md`

## Global Constraints

- Never disable or modify `com.google.android.tungsten.setupwraith` or `com.google.android.apps.tv.launcherx` on either TV.
- Do not install any APK or launcher on Bravia 55 (`192.0.2.10`).
- Reuse `/Users/maciejmarzeta/.android/adbkey` and `/Users/maciejmarzeta/.android/adbkey.pub` so neither TV prompts for ADB authorization.
- Create a backup of `~/projects/homeassistant/config/configuration.yaml` and `automations.yaml` before modifying them.

## Review Focus

- Unreachable/powered-off TV timeout handling: `tv_adb_monitor.py status <ip>` must return valid JSON (`{"is_on": false, "wakefulness": "Offline", "package": "", "app": "Wyłączony"}`) within 5 seconds when a TV is unplugged or unreachable, never crashing the HA sensor.
- Screensaver/Dream state counting: `mWakefulness=Dreaming` or `mIsDreaming=true` must return `"is_on": true` and `"app": "Launcher / Wygaszacz"` so screensaver/launcher time counts toward daily TV open hours.
- Transient lockscreen/notification shade focus: when `mCurrentFocus` is `null` or `NotificationShade` while `mWakefulness=Awake`, fall back to `mFocusedApp` so the active streaming app is still detected.
- Duplicate 4h notifications: the 4-hour automation for each TV must check `last_triggered` date so it fires at most once per calendar day per TV.
- Home Assistant YAML config validation: run `docker exec homeassistant python3 -m homeassistant --script check_config --config /config` before restarting/reloading HA.

---

### Task 1: ADB Key Deployment & `tv_adb_monitor.py` Script

**Files:**
- Create (local repo copy): `scripts/tv_adb_monitor.py`
- Create (on `raspberrypi`): `~/projects/homeassistant/config/.storage/androidtv_adbkey` (and `.pub`)
- Create (on `raspberrypi`): `~/projects/homeassistant/config/scripts/tv_adb_monitor.py`
- Test: `tests/test_tv_adb_monitor.py`

**Interfaces:**
- Produces CLI:
  - `python3 /config/scripts/tv_adb_monitor.py status <ip>` → stdout JSON `{"is_on": bool, "wakefulness": str, "package": str, "app": str}`
  - `python3 /config/scripts/tv_adb_monitor.py notify <ip> <title> <message>` → posts Android TV notification via `cmd notification post -S bigtext -t <title> tv_limit_4h <message>`

- [ ] **Step 1: Write unit tests for `parse_dumpsys(output: str) -> dict` in `tests/test_tv_adb_monitor.py`**
  Test cases:
  1. `mWakefulness=Awake` + `mFocusedApp=ActivityRecord{... u0 org.smarttube.stable/...}` → `{"is_on": True, "wakefulness": "Awake", "package": "org.smarttube.stable", "app": "SmartTube"}`
  2. `mWakefulness=Asleep` + `mFocusedApp=...launcherx...` → `{"is_on": False, "wakefulness": "Asleep", "package": "", "app": "Wyłączony"}`
  3. `mWakefulness=Dreaming` + `mIsDreaming=true` → `{"is_on": True, "wakefulness": "Dreaming", "package": "dream", "app": "Launcher / Wygaszacz"}`
  4. `mWakefulness=Awake` + `mCurrentFocus=null` + `mFocusedApp=ActivityRecord{... u0 tv.twitch.android.app/...}` → `{"is_on": True, "wakefulness": "Awake", "package": "tv.twitch.android.app", "app": "Twitch"}`

- [ ] **Step 2: Implement `scripts/tv_adb_monitor.py` and run local unit tests**
  Run: `python3 -m unittest discover -s tests -p "test_tv_adb_monitor.py" -v`
  Expected: `OK` (all tests pass).

- [ ] **Step 3: Copy ADB keys and `tv_adb_monitor.py` to `raspberrypi` and verify live inside `homeassistant` container**
  Copy `~/.android/adbkey` and `~/.android/adbkey.pub` to `raspberrypi:~/projects/homeassistant/config/.storage/androidtv_adbkey` (`.pub`), and `scripts/tv_adb_monitor.py` to `raspberrypi:~/projects/homeassistant/config/scripts/tv_adb_monitor.py`.
  Run:
  - `ssh raspberrypi 'docker exec homeassistant python3 /config/scripts/tv_adb_monitor.py status 192.0.2.10'`
  - `ssh raspberrypi 'docker exec homeassistant python3 /config/scripts/tv_adb_monitor.py status 192.0.2.10'`
  Expected: Valid JSON returned from both TVs without timeout or auth prompts.

---

### Task 2: Home Assistant Sensors, `history_stats`, Automations & `tv_dashboard.yaml`

**Files:**
- Create (local repo backup/reference): `ha-config/tv_dashboard.yaml`
- Modify (on `raspberrypi`): `~/projects/homeassistant/config/configuration.yaml`
- Modify (on `raspberrypi`): `~/projects/homeassistant/config/automations.yaml`
- Create (on `raspberrypi`): `~/projects/homeassistant/config/tv_dashboard.yaml`

**Interfaces:**
- Consumes: `/config/scripts/tv_adb_monitor.py`
- Produces HA Entities:
  - `sensor.bravia_65_aktywna_aplikacja`, `sensor.bravia_55_aktywna_aplikacja`
  - `binary_sensor.bravia_65_wlaczony`, `binary_sensor.bravia_55_wlaczony`
  - `binary_sensor.bravia_65_limit_czasu`, `binary_sensor.bravia_55_limit_czasu`
  - `input_number.prog_czas_tv_dziennie` (default `4.0` h)
  - `sensor.bravia_65_czas_dzis`, `sensor.bravia_55_czas_dzis`
  - Per-app `history_stats` sensors for both TVs (`smarttube`, `youtube`, `twitch`, `magentatv`, `prime_video`, `jellyfin`, `videostar`, `hdmi_tv`, `launcher`)
  - `shell_command.tv_notify_bravia_65`, `shell_command.tv_notify_bravia_55`
  - Dashboard `/tv-dashboard/telewizory`

- [ ] **Step 1: Backup existing Home Assistant config on `raspberrypi`**
  Run: `ssh raspberrypi 'cp ~/projects/homeassistant/config/configuration.yaml ~/projects/homeassistant/config/configuration.yaml.bak_tvs && cp ~/projects/homeassistant/config/automations.yaml ~/projects/homeassistant/config/automations.yaml.bak_tvs'`

- [ ] **Step 2: Add `command_line`, `shell_command`, `history_stats`, `template` sensors, `input_number.prog_czas_tv_dziennie`, and `tv-dashboard` to `configuration.yaml`**

- [ ] **Step 3: Add 4-hour notification automations for Bravia 65 (Maciej) and Bravia 55 (Żona) to `automations.yaml`**

- [ ] **Step 4: Create `tv_dashboard.yaml` and deploy to `~/projects/homeassistant/config/tv_dashboard.yaml`**

- [ ] **Step 5: Validate HA configuration, restart/reload Home Assistant, and verify all new entities are live**
  Run:
  - `ssh raspberrypi 'docker exec homeassistant python3 -m homeassistant --script check_config --config /config'`
  - Restart `homeassistant` container and verify states of `sensor.bravia_65_aktywna_aplikacja`, `sensor.bravia_55_aktywna_aplikacja`, `sensor.bravia_65_czas_dzis`, and `sensor.bravia_55_czas_dzis`.
  - Commit all files in `/Users/maciejmarzeta/Documents/tvs`.
