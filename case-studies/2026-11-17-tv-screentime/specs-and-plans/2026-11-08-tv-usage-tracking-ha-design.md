# Home Assistant TV Usage & App Tracking Specification (Bravia 65 & Bravia 55)

**Date:** 2026-11-08  
**Targets:**
- **Bravia 65 (Maciej):** `SONY XR-65A80L` (`192.0.2.10:5555`)
- **Bravia 55 (Żona):** `SONY XR-55A80L` (`192.0.2.10:5555`)
- **Home Assistant Host:** `raspberrypi` (`192.0.2.10`, `~/projects/homeassistant/config`)

---

## 1. Intent & Why

Track how long each Sony Bravia OLED TV is open every day—including time spent on the launcher or screensaver—and break down daily usage by foreground application (`SmartTube`, `YouTube`, `Twitch`, `MagentaTV`, `Prime Video`, `Jellyfin`, `Videostar`, `HDMI / TV`, `Launcher / Wygaszacz`). Present this in a dedicated Home Assistant sidebar dashboard (**Telewizory**) and send a notification (both iPhone push and on-screen TV notification) whenever either TV reaches 4 hours of daily screen-on time.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- Poll both `192.0.2.10:5555` (Bravia 65 – Maciej) and `192.0.2.10:5555` (Bravia 55 – Żona) every 30 seconds via ADB from inside the Home Assistant container using the existing authorized ADB key pair.
- Accurately classify TV open state (`Awake` or `Dreaming` = `on`; `Asleep`/`Dozing`/unreachable = `off`) and active foreground app.
- Accumulate daily total open hours and per-app hours per TV using native Home Assistant `history_stats` sensors resetting at `today_at("00:00")`.
- Trigger an alert when either TV reaches 4 hours of daily open time (configurable via `input_number.prog_czas_tv_dziennie`, default `4.0` h), sending:
  1. An iPhone push notification (`notify.mobile_app_iphone`).
  2. An on-screen notification directly on that TV via ADB (`cmd notification post`).
- Provide a dedicated YAML Lovelace dashboard (`tv-dashboard` -> `tv_dashboard.yaml`, sidebar title `Telewizory`) matching the style of `heating_dashboard.yaml` and `office_dashboard.yaml`.

### Non-Goals
- Installing any custom APK or launcher on Bravia 55 (`XR-55A80L`).
- Tracking media title metadata inside DRM apps.

### Anti-Goals (Must Never Happen)
- **Never** disable or touch `com.google.android.tungsten.setupwraith` or `com.google.android.apps.tv.launcherx` on either TV.
- **Never** trigger repeated ADB authorization prompts on the TVs; reuse the already-authorized `/Users/maciejmarzeta/.android/adbkey` key pair.
- **Never** break existing Home Assistant sensors, heating automations, or dashboards in `~/projects/homeassistant/config/`.

---

## 3. Approaches Considered

1. **Approach A (Selected): Native Home Assistant ADB Polling (`adb_shell`) + `history_stats` + Template Sensors**
   - Uses Python `adb_shell` (already installed inside the `homeassistant` Docker image) with `/config/.storage/androidtv_adbkey` via `command_line` sensors and `history_stats`.
   - Zero external systemd daemons, 100% declarative in `configuration.yaml` and `automations.yaml`, and accurately detects side-loaded apps (`SmartTube`, `Projectivy`) and `DreamService` screensavers.
2. **Approach B: Sony Bravia PSK REST API (`braviatv`)**
   - Rejected: requires interactive PSK setup on TVs and cannot reliably distinguish side-loaded Android TV apps or screensaver states.
3. **Approach C: External Host Daemon Pushing to HA REST API**
   - Rejected: requires managing a separate systemd service and long-lived HA tokens outside the Home Assistant configuration directory.

---

## 4. Architecture & Data Model

### 4.1 ADB Helper Script (`/config/scripts/tv_adb_monitor.py`)
Executed inside the `homeassistant` container:
- **Status Mode (`python3 /config/scripts/tv_adb_monitor.py status <ip>`)**:
  - Connects to `<ip>:5555` using `/config/.storage/androidtv_adbkey` with a 4-second timeout.
  - Queries `dumpsys power`, `dumpsys dreams`, and `dumpsys window displays`.
  - Determines:
    - `is_on`: `true` if `mWakefulness=Awake` or `mWakefulness=Dreaming` (or `mIsDreaming=true`); `false` if `Asleep`, `Dozing`, or unreachable.
    - `app`:
      - When `is_on` is `false` → `"Wyłączony"`
      - When `mWakefulness=Dreaming` or `mIsDreaming=true` → `"Launcher / Wygaszacz"`
      - Otherwise maps foreground package from `mCurrentFocus` / `mFocusedApp`:
        - `org.smarttube.stable` → `"SmartTube"`
        - `com.google.android.youtube.tv` → `"YouTube"`
        - `tv.twitch.android.app` → `"Twitch"`
        - `com.pl.tmobile.magentatv` → `"MagentaTV"`
        - `com.amazon.amazonvideo.livingroom` → `"Prime Video"`
        - `org.jellyfin.androidtv` → `"Jellyfin"`
        - `pl.videostar` → `"Videostar"`
        - `com.sony.dtv.tvinput.external`, `com.sony.dtv.tvinput.tuner`, `com.sony.dtv.braviasyncmenu` → `"HDMI / TV"`
        - `com.spocky.projengmenu`, `com.google.android.apps.tv.launcherx`, `com.google.android.apps.tv.dreamx`, `com.tvs.haomarchy`, `com.android.tv.settings` → `"Launcher / Wygaszacz"`
        - Any other active package → `"Inne"`
  - Prints JSON: `{"is_on": bool, "wakefulness": str, "package": str, "app": str}`.
- **Notify Mode (`python3 /config/scripts/tv_adb_monitor.py notify <ip> "<title>" "<message>"`)**:
  - Connects to `<ip>:5555` and posts an on-screen Android TV system notification via `cmd notification post -S bigtext -t "<title>" "tv_limit_4h" "<message>"`.

### 4.2 Home Assistant Entities (`configuration.yaml`)
- **Primary Command-Line Sensors (`scan_interval: 30`)**:
  - `sensor.bravia_65_aktywna_aplikacja` (state: `app`, attributes: `is_on`, `wakefulness`, `package`)
  - `sensor.bravia_55_aktywna_aplikacja` (state: `app`, attributes: `is_on`, `wakefulness`, `package`)
- **Template Binary Sensors**:
  - `binary_sensor.bravia_65_wlaczony` (`device_class: power`, `on` when `state_attr('sensor.bravia_65_aktywna_aplikacja', 'is_on') == true`)
  - `binary_sensor.bravia_55_wlaczony` (`device_class: power`, `on` when `state_attr('sensor.bravia_55_aktywna_aplikacja', 'is_on') == true`)
  - `binary_sensor.bravia_65_limit_czasu` (`device_class: problem`, `on` when `sensor.bravia_65_czas_dzis >= input_number.prog_czas_tv_dziennie`)
  - `binary_sensor.bravia_55_limit_czasu` (`device_class: problem`, `on` when `sensor.bravia_55_czas_dzis >= input_number.prog_czas_tv_dziennie`)
- **Daily `history_stats` Sensors (`start: "{{ today_at('00:00') }}"`, `end: "{{ now() }}"`, `type: time`)**:
  - Total TV Open Time:
    - `sensor.bravia_65_czas_dzis` (tracks `binary_sensor.bravia_65_wlaczony` == `on`)
    - `sensor.bravia_55_czas_dzis` (tracks `binary_sensor.bravia_55_wlaczony` == `on`)
  - Per-App Breakdown for **Bravia 65 (Maciej)**:
    - `sensor.bravia_65_czas_smarttube`, `sensor.bravia_65_czas_youtube`, `sensor.bravia_65_czas_twitch`, `sensor.bravia_65_czas_magentatv`, `sensor.bravia_65_czas_prime_video`, `sensor.bravia_65_czas_jellyfin`, `sensor.bravia_65_czas_hdmi_tv`, `sensor.bravia_65_czas_launcher`
  - Per-App Breakdown for **Bravia 55 (Żona)**:
    - `sensor.bravia_55_czas_smarttube`, `sensor.bravia_55_czas_youtube`, `sensor.bravia_55_czas_magentatv`, `sensor.bravia_55_czas_prime_video`, `sensor.bravia_55_czas_jellyfin`, `sensor.bravia_55_czas_videostar`, `sensor.bravia_55_czas_hdmi_tv`, `sensor.bravia_55_czas_launcher`

### 4.3 4-Hour Notification Automations (`automations.yaml`)
- Trigger when `binary_sensor.bravia_65_limit_czasu` or `binary_sensor.bravia_55_limit_czasu` transitions to `on` (at most once per calendar day per TV).
- Action sends:
  1. Push notification via `notify.mobile_app_iphone` with deep link `url: /tv-dashboard/telewizory`.
  2. On-screen TV notification via `shell_command.tv_notify_bravia_65` / `shell_command.tv_notify_bravia_55`.

### 4.4 Lovelace Dashboard (`tv_dashboard.yaml`)
- Registered as `tv-dashboard` (`title: Telewizory`, `icon: mdi:television-shimmer`).
- Displays:
  - Live status cards for **Bravia 65 (Maciej)** and **Bravia 55 (Żona)** (power, active app, total hours today, 4h limit badge).
  - Per-app daily time breakdown entities cards for each TV.
  - 24h activity timeline (`history-graph`) and configurable daily limit (`input_number.prog_czas_tv_dziennie`).
