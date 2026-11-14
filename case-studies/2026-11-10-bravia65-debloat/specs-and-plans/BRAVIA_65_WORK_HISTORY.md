# Work History: Reclaiming a Sony Bravia 65" OLED (`XR-65A80L`) — Debloating ACR Spyware, Building a Native Home Assistant Dashboard Overlay, and an Omarchy-Inspired OLED Screensaver

**Date:** November 7, 2026
**Target Device:** Sony Bravia 65" 4K OLED (`SONY XR-65A80L`, Android TV 12 / API 31, `192.0.2.10:5555`)
**Homelab Integration:** Raspberry Pi 5 (`192.0.2.10`) running Home Assistant (`:8123`) & Ghost (`blog.marzeta.pl`)

---

## 1. Motivation: Owning the Biggest Screen in the House

After moving my personal cloud, media (Jellyfin, Navidrome, Immich), and home automation (Home Assistant, Prometheus, Grafana, Pi-hole) onto a self-hosted 64-bit Raspberry Pi 5, the glaring holdout in the living room was the TV itself: a **65-inch Sony Bravia XR-65A80L OLED**.

Out of the box, modern Google TV / Sony Bravia firmware treats a flagship OLED panel like a billboard and telemetry node:
- The stock home screen is 80% ads and algorithmic "recommendations" for streaming services I don't even use.
- Under the hood, background daemons continuously fingerprint video frames (Automatic Content Recognition / ACR), phone home usage patterns, and keep hotel/retail demo runtimes (including an entire embedded Node.js runtime!) sitting on the system partition.
- Meanwhile, the data I *actually* care about when I walk into the room—my **Home Assistant Heating & Air Quality Dashboard** (`CO₂`, `PM2.5`, room temperatures, radiator states, and action alerts)—was locked away in a browser tab instead of living right on the TV.

The goal of this session was threefold:
1. **Audit & Strip All Spyware, ACR Frame-Grabbers, Telemetry, Retail Demo/Hotel Bloat, and Unused Streaming Apps**—with a complete, one-command rollback snapshot before touching a single package.
2. **Replace the Ad-Heavy Home Screen with Projectivy Launcher + a Custom Home Assistant Heating Overlay** occupying the top `41%` (`442px` of `1080p`) of the screen, leaving clean, D-pad-accessible rows for HDMI inputs and essential apps (SmartTube, Jellyfin, Magenta TV, Twitch) underneath.
3. **Build an Omarchy-Inspired Pure `#000000` OLED Screensaver (`DreamService`)** that renders drifting, low-luminance terminal/ASCII glyphs in TokyoNight / Catppuccin tones while keeping 98%+ of the OLED panel completely powered off (`#000000`) so zero static pixels can ever burn in.

---

## 2. Phase 1: Privacy & Microphone / Camera / Frame-Grabber Audit

Before removing anything, we audited every package on the `XR-65A80L` holding `RECORD_AUDIO`, `CAMERA`, or screen-capture capabilities via `adb shell dumpsys package` and `appops`:

### Video Frame Grabbing & Automatic Content Recognition (ACR)
- **`tv.samba.ssm` & `tv.samba.ssm.ui` (Samba TV System Service):** Pre-installed Automatic Content Recognition (ACR) spyware. Reads pixels directly from the TV buffer to fingerprint whatever is playing on screen (even across HDMI inputs) to build household ad-targeting profiles.
- **`com.sony.dtv.videoframeserver`:** Sony internal daemon designed to capture video frames from the display pipeline for analysis services.

### Camera & Presence Sensing
- **`com.sony.dtv.sensingcamera.settings`, `com.sony.dtv.sensingcamera.fwupdate`, `com.sony.dtv.gestureapp`, `com.sony.dtv.distancealert` (Bravia Cam suite):** Background services for camera gesture recognition, viewer distance alerts, and presence tracking.

### Microphone (`RECORD_AUDIO`)
- **`com.google.android.katniss` (Google Assistant on TV):** Holds `RECORD_AUDIO` (`allow` via Bluetooth remote mic button). Kept enabled so remote voice search in SmartTube/YouTube still works, while disabling hands-free background listening.
- **`com.sony.dtv.ime.chww` / `com.google.android.inputmethod.latin`:** On-screen keyboards for voice-to-text dictation in search bars.
- **`com.sony.dtv.bleadvertiseservice`:** Sony Bluetooth Low Energy service that handles the remote control's mic audio stream over BLE.

### Telemetry, Diagnostics & Usage Tracking
- **`com.sony.dtv.da.service` & `com.qterics.da.product`:** Qterics / Sony Device Analytics agents collecting usage telemetry.
- **`com.sonyericsson.idd.agent`:** Sony IDD analytics/crash probe.
- **`com.sony.dtv.usercontext` & `com.sony.dtv.lastaccess`:** Services tracking which apps and inputs the user opens and when.
- **`com.sony.dtv.promos`, `com.sony.dtv.sonyselect`, `com.sony.dtv.sonytab`:** Promotional banners and Sony ad tabs.

---

## 3. Phase 2: Full Backup Snapshot & Surgical Debloat (42 Packages Removed)

Following a strict backup-first rule, we dumped the complete package state (`pm list packages -f`, enabled/disabled lists, system properties) and pulled all split APKs (`base.apk` + `split_config.*.apk`) of user-installed streaming apps to `/Users/maciejmarzeta/Documents/tvs/backups/bravia65_XR-65A80L/` alongside an automated `restore.sh` script.

We then removed **42 packages** for User 0 (`pm uninstall --user 0`):
- **5 User-Installed Streaming Apps:** Disney+ (`com.disney.disneyplus`), Max (`com.wbd.stream`), Canal+ (`com.canal.android.canal`), TVP VOD (`com.tvp.vodtv.tv`), Crunchyroll (`com.crunchyroll.crunchyroid`) — freeing ~450 MB of `/data` storage.
- **5 Pre-Installed Streaming Stubs/Apps:** Netflix (`com.netflix.ninja`) + Netflix Partner NCM (`com.netflix.partner.ncm`), Apple TV (`com.apple.atve.sony.appletv`), Sony Pictures Core (`com.sonypicturescore`), YouTube Music (`com.google.android.youtube.tvmusic`).
- **14 Spying, ACR, Telemetry & Promo Packages:** `tv.samba.ssm`, `tv.samba.ssm.ui`, `com.sony.dtv.videoframeserver`, `com.sony.dtv.da.service`, `com.qterics.da.product`, `com.sonyericsson.idd.agent`, `com.sony.dtv.sonybugreportsys`, `com.sony.dtv.sonyloglevelsettingsys`, `com.google.android.feedback`, `com.sony.dtv.usercontext`, `com.sony.dtv.lastaccess`, `com.sony.dtv.promos`, `com.sony.dtv.sonyselect`, `com.sony.dtv.sonytab`.
- **14 Retail Demo & Hotel / B2B Mode Packages:** `com.sony.dtv.demosupport`, `com.sony.dtv.demosystemsupport`, `com.sony.dtv.multiscreendemo`, `com.sony.dtv.b2b.hotelmode`, `com.sony.dtv.b2b.rs232csupport`, `com.sony.dtv.b2b.prosettings`, `com.sony.dtv.b2b.adminpassword`, `com.sony.dtv.b2b.deviceadminsettings`, `com.sony.dtv.b2b.importexport`, and 5 embedded B2B Node.js / WebApp DRM runtimes (`com.sony.dtv.b2b.noderuntime.*`).
- **4 Bravia Cam Packages:** `com.sony.dtv.gestureapp`, `com.sony.dtv.distancealert`, `com.sony.dtv.sensingcamera.settings`, `com.sony.dtv.sensingcamera.fwupdate`.

---

## 4. The "SetupWraith" War Story: How Disabling One Google TV Package Killed Ethernet DNS

On generic Android TV boxes, people routinely replace the stock Google TV home screen by running:
```bash
adb shell pm disable-user --user 0 com.google.android.apps.tv.launcherx
adb shell pm disable-user --user 0 com.google.android.tungsten.setupwraith
```
When one of our subagents ran that pair of commands on the **Sony Bravia XR-65A80L**, the TV immediately lost all internet and DNS resolution—even over a hardwired Ethernet cable (`192.0.2.10`). YouTube, Twitch, and even local LAN pings dropped within 6 seconds.

### Why It Happened
On Sony Bravia Google TV firmware, `com.google.android.tungsten.setupwraith` isn't just a first-boot wizard—it owns the network provisioning state check. If `setupwraith` is disabled, Sony's connectivity service marks the network interface as unprovisioned and drops DNS/routing.

### The Fix
1. Re-enabled both `com.google.android.tungsten.setupwraith` and `com.google.android.apps.tv.launcherx` (`pm enable --user 0 ...`), which immediately restored Ethernet, DNS, and LAN connectivity.
2. Instead of disabling `launcherx` at the package manager level, we enabled **Projectivy Launcher's Accessibility Service** (`com.spocky.projengmenu/.services.ProjectivyAccessibilityService`) and toggled **"Nadpisz bieżący launcher" (Override current launcher)** inside Projectivy Settings. That intercepts the Home button cleanly while keeping Sony's underlying network stack 100% happy.
3. Hardened `scripts/deploy_bravia65.sh` so every deployment explicitly asserts that `setupwraith` and `launcherx` remain enabled.

---

## 5. Phase 3: Building the Custom `com.tvs.haomarchy` Companion APK From Scratch

Because Android TV launchers don't natively embed authenticated Home Assistant dashboards or terminal OLED screensavers, we built a lightweight (**20 KB!**) dependency-free Android APK (`com.tvs.haomarchy`) compiled directly with `javac`, `aapt2`, `d8`, `zipalign`, and `apksigner` (targeting API 34, minSdk 28):

### Component A: `HeatingOverlayService.java` (Top 41% Home Assistant Dashboard)
- Runs as a persistent foreground service (`TYPE_APPLICATION_OVERLAY`) anchored to the top `41%` (`442px` of `1080p`) of the screen.
- **Why 41% (`442px`)?** At 58%, the overlay covered Projectivy's top rows. At `41%` (`442px`), it stops right above Projectivy's **Wejścia** (`HDMI 1–4`) and **Aplikacje TV** icons, with a subtle 1px `#337dcfff` cyan separator line.
- **Never Steals D-Pad Focus (`FLAG_NOT_FOCUSABLE`):** A classic pitfall with WebView overlays on Android TV is that the WebView traps the remote control's D-pad focus so you can't click your app icons. By setting `WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE | FLAG_NOT_TOUCH_MODAL`, the remote control always drives Projectivy Launcher underneath.
- **Auto-Hides When You Launch Any App:** Polls `UsageStatsManager` every `500ms`. The moment you open SmartTube, Jellyfin, Twitch, or an HDMI input, or when the screensaver starts, the overlay switches to `View.GONE`. When you press Home to return to Projectivy, it reappears instantly.
- **Zero-Touch Auto-Login, Dark Mode & Shadow-DOM Kiosk Styling:**
  - Injects a pre-authorized Home Assistant long-lived refresh token into `localStorage.setItem('hassTokens', ...)` along with `selectedTheme: {"dark": true}` and `dockedSidebar: "always_hidden"`.
  - Traverses Home Assistant's nested Web Components shadow DOM (`home-assistant` -> `home-assistant-main` -> `ha-panel-lovelace` -> `hui-root`) and injects a `<style id="__tvKioskStyle">` tag that hides the top toolbar (`ha-top-app-bar-fixed`, `.header`) and applies `zoom: 0.64` on `#view`.
  - Result: All 3 Lovelace columns (**Gabinet – powietrze** gauges, **⚠️ Gabinet – do zrobienia** air quality alerts, and **Gabinet – CO₂ / Temperatury**) fit side-by-side inside the top `442px` strip on a pure `#000000` OLED background.

### Component B: `HeatingActivity.java` (Full-Screen Interactive Mode)
- Need to scroll further down the Heating Dashboard? Clicking the **HA Heating & Omarchy** app tile in Projectivy's app row opens `HeatingActivity` full-screen (`100%` height), pauses the top overlay, and maps the TV remote's **D-pad Up/Down** keys to smooth `webView.scrollBy(0, ±180)` scrolling. Pressing **Back** returns to Projectivy Launcher.

### Component C: `OmarchyDreamService.java` (Omarchy-Inspired OLED Screensaver)
- Registered as the system `DreamService` (`settings put secure screensaver_components com.tvs.haomarchy/.OmarchyDreamService`).
- Draws a pure `#000000` background (so 98%+ of the OLED pixels are physically turned off) with a slow, drifting `24fps` monospace ASCII / terminal glyph rain (`01{}[]/>_#*+~:=`), a subtly drifting status badge (`[ OMARCHY // BRAVIA-65 // OLED-SAFE ]` + live `HH:mm` clock) that recalculates random coordinates every 45 seconds, and capped alpha (`<= 175/255`) in muted TokyoNight/Catppuccin colors (`#7dcfff`, `#9ece6a`, `#bb9af7`, `#565f89`).
- Zero static pixels ever remain in one place, completely eliminating OLED burn-in risk.

---

## 6. Iteration & Real-World UX Lesson: Ditching the Persistent Top Overlay for a Pure Launcher

After getting the top `41%` Home Assistant overlay working (auto-logged in, dark mode, shadow-DOM toolbar stripped, `zoom: 0.64`), looking at it on a 65-inch OLED in the living room taught a classic product lesson: **just because you *can* pin a live telemetry dashboard to 40% of your TV home screen doesn't mean you actually want it staring at you every time you switch inputs.**

A TV launcher is at its best when it gets out of the way immediately. Even a well-proportioned top overlay adds visual clutter above the HDMI inputs and app icons. So we made a decisive cut:
- Stripped `HeatingOverlayService` and `BootReceiver` out of `AndroidManifest.xml` and revoked `SYSTEM_ALERT_WINDOW`.
- Kept **Projectivy Launcher** 100% clean and full-screen as the primary launcher on the 65" OLED, paired with the **Omarchy OLED `DreamService` screensaver** for burn-in protection and the standalone **HA Heating & Omarchy** app tile (`HeatingActivity`) in the *Aplikacje TV* row whenever a full-screen check of the heating dashboard is actually wanted.

---

## 7. Scaling Across the House: Surgical Debloat on the Second OLED — Sony Bravia 55" (`XR-55A80L`)

With the exact 42-package debloat manifest battle-tested on the 65-inch `XR-65A80L` (`192.0.2.10`), we turned to the second TV on the LAN: the **55-inch Sony Bravia `XR-55A80L`** (`192.0.2.10:5555`).

For the 55-inch Bravia, the goal was even simpler and more surgical:
- **Keep the stock launcher (`com.google.android.apps.tv.launcherx` + `setupwraith`)** untouched—no custom launcher, no Home Assistant app, zero UI changes to learn.
- **Execute the exact same backup-first snapshot and 42-package privacy/bloatware purge** using cost-optimized `flash` subagents:
  1. Dumped all package lists, system properties, and pulled **~308 MB** of split APKs (`Disney+`, `Max`, `Canal+`, `TVP VOD`, `Crunchyroll`) + generated an automated `restore.sh` in `backups/bravia55_XR-55A80L/`.
  2. Uninstalled all **42 packages** (`42/42 Success`): Samba TV ACR (`tv.samba.ssm`, `tv.samba.ssm.ui`), `videoframeserver`, Qterics/Sony Device Analytics (`da.service`, `da.product`), `idd.agent`, Bravia Cam daemons, all 14 retail demo & hotel/B2B Node.js runtimes, and the 10 unused streaming apps.
  3. Verified `0/42` bloat packages remained on User 0 while stock launcher and network health (`8.8.8.8` @ `9.8 ms` RTT, `0%` packet loss) stayed rock-solid.

Two OLEDs (`65"` and `55"`), zero ACR frame-grabbers, zero telemetry daemons, over 750 MB of reclaimed `/data` space across both sets, and full rollback backups on disk.
