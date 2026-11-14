# Bravia 65 (XR-65A80L): Projectivy Launcher + HA Heating Dashboard + Omarchy OLED Screensaver Design

## 1. Intent & Why
Turn the Sony Bravia 65 (`XR-65A80L`, `192.0.2.10`) into a clean, ad-free OLED media and smart-home hub without building a custom launcher from scratch:
- Use **Projectivy Launcher** (`com.spocky.projengmenu`) as the main TV launcher so app management, HDMI inputs, and remote navigation work out of the box.
- Display the live **Home Assistant Heating Dashboard** (`http://192.0.2.10:8123/heating-dashboard/heating`) on the main view (top ~60% of the screen) while keeping the bottom ~40% for the favorite apps row (**MagentaTV**, **SmartTube**, **Jellyfin**, **Twitch**, **WP Pilot**, etc.).
- Protect the 65" OLED panel and give it an **Omarchy-inspired aesthetic** with a pure `#000000` black terminal/ASCII animated Android TV screensaver (`DreamService`).

## 2. Goals, Non-Goals & Anti-Goals
- **Goals:**
  - Install and set **Projectivy Launcher** as the active home launcher on `192.0.2.10:5555` (replacing Google TV's ad-heavy `com.google.android.apps.tv.launcherx`).
  - Render `http://192.0.2.10:8123/heating-dashboard/heating` directly in the top ~60% of the Projectivy home screen via a lightweight overlay/wallpaper companion, while allowing one-click interactive access to log into HA once (saving cookies/tokens persistently) or adjust heating controls.
  - Provide a native Android TV `DreamService` screensaver with Omarchy-style pure `#000000` OLED-black terminal/ASCII animations (`tte`/Matrix/glyphs effect) so zero static pixels remain lit when idle.
- **Non-Goals:**
  - Writing or maintaining a custom app launcher from scratch.
  - Modifying Grafana (`192.0.2.10:3000`) — only Home Assistant (`http://192.0.2.10:8123/heating-dashboard/heating`) is needed.
- **Anti-Goals:**
  - Any bright/static backgrounds that risk OLED burn-in.
  - Any overlay that blocks video playback inside **MagentaTV**, **SmartTube**, or **Jellyfin**.

## 3. Constraints & Technical Reality Check
- **Stock `TvOverlay` limitation:** The off-the-shelf `TvOverlay` app (`com.tabdeveloper.tvoverlay`) only displays MQTT/REST toast notifications and sensor pills pushed from Home Assistant; it **cannot** render a live Lovelace web URL like `http://192.0.2.10:8123/heating-dashboard/heating`.
- **How we solve this cleanly (Builder Call):**
  - We install the official **Projectivy Launcher** APK for the launcher itself.
  - Alongside it, we install a tiny, single-purpose companion APK (`com.tvs.haomarchy`) that does two things that off-the-shelf apps cannot do alone:
    1. **Home-Only Heating Dashboard Panel (Top 60% Overlay / Live Wallpaper):** Renders `http://192.0.2.10:8123/heating-dashboard/heating` in a hardware-accelerated Android `WebView` with `domStorageEnabled=true` and persistent cookies. When used as a Live Wallpaper (or Home-screen overlay), it occupies the top 60% of Projectivy Launcher on a `#000000` background and never covers video apps. Clicking the app's tile in Projectivy opens the dashboard full-screen so you can log into Home Assistant once with the remote/keyboard or interact with heating controls.
    2. **Omarchy OLED `DreamService` Screensaver:** Registers as the system screensaver (`Settings.Secure.screensaver_components`) and draws a pure `#000000` OLED-black canvas with Omarchy-style terminal text / matrix / glyph animations at 60fps when the TV goes idle.

## 4. Approaches Considered
1. **Approach A — Projectivy Launcher + Live Wallpaper / Overlay Companion APK (`com.tvs.haomarchy`):**
   - *Pros:* Uses official Projectivy Launcher for all launcher duties; renders the exact `http://192.0.2.10:8123/heating-dashboard/heating` Lovelace page in the top 60% of the screen; bundles the Omarchy OLED `DreamService` screensaver in the same lightweight APK.
   - *Cons:* Requires compiling a tiny (~50 KB) companion APK on the Mac and pushing via ADB.
2. **Approach B — Stock Projectivy Launcher + Stock `TvOverlay` Only:**
   - *Pros:* 100% third-party APKs.
   - *Cons:* Stock `TvOverlay` cannot render `http://192.0.2.10:8123/heating-dashboard/heating` (only small text/icon notifications configured via HA automations).
3. **Approach C — Custom Launcher from Scratch:**
   - *Rejected:* User explicitly wants an established launcher like Projectivy rather than building a launcher from scratch.

**Selected Approach:** **Projectivy Launcher** (official release APK) + lightweight **HA Heating & Omarchy OLED Companion** (`com.tvs.haomarchy`) so that `http://192.0.2.10:8123/heating-dashboard/heating` is rendered live on the main screen AND the Omarchy OLED screensaver works natively.
