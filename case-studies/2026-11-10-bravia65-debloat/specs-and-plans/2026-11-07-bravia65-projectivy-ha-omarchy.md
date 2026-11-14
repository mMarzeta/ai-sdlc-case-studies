# Bravia 65 Projectivy + HA Heating Overlay + Omarchy OLED Screensaver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install Projectivy Launcher on the Sony Bravia 65 (`192.0.2.10:5555`) and build/deploy the `com.tvs.haomarchy` companion APK providing a top-60% Home Assistant Heating Dashboard (`http://192.0.2.10:8123/heating-dashboard/heating`) overlay on the launcher screen plus an Omarchy-inspired pure `#000000` OLED `DreamService` screensaver.

**Architecture:** We use the official **Projectivy Launcher** (`com.spocky.projengmenu`) for app launching and HDMI input management, paired with a lightweight custom Android companion app (`com.tvs.haomarchy`) compiled directly with `aapt2`, `javac`, `d8`, and `apksigner`. The companion app provides: (1) `HeatingActivity` for full-screen interactive HA login/control (sharing WebView cookies & `localStorage`), (2) `HeatingOverlayService` rendering `http://192.0.2.10:8123/heating-dashboard/heating` in a non-focusable top-58% `TYPE_APPLICATION_OVERLAY` window visible only when the home launcher is in the foreground, and (3) `OmarchyDreamService` rendering a pure `#000000` OLED-safe terminal/ASCII animation when idle.

**Tech Stack:** Android SDK Build-Tools 34 (`aapt2`, `d8`, `zipalign`, `apksigner`), OpenJDK (`javac`), Android API 34 (`android.jar`), ADB (`192.0.2.10:5555`), Projectivy Launcher 4.73.

**Spec:** `docs/superpowers/specs/2026-11-07-bravia65-projectivy-ha-omarchy-design.md`

## Global Constraints

- Target TV ADB serial: `192.0.2.10:5555` (`SONY XR-65A80L`, Android 12 / API 31).
- Exact Home Assistant URL: `http://192.0.2.10:8123/heating-dashboard/heating`
- Companion package name: `com.tvs.haomarchy`
- OLED burn-in safety: All backgrounds in the companion overlay and `OmarchyDreamService` must use pure `#000000` black, and all text/glyphs in `OmarchyDreamService` must continuously move so no static pixel remains lit.
- Overlay visibility rule: `HeatingOverlayService` must only be `View.VISIBLE` when the foreground package is `com.spocky.projengmenu` (or `com.google.android.apps.tv.launcherx`) AND `OmarchyDreamService.isDreamingNow` is `false`. It must immediately switch to `View.GONE` when any other app (e.g., `com.pl.tmobile.magentatv`, `org.smarttube.stable`, `org.jellyfin.androidtv`, `com.tvs.haomarchy` interactive activity) or the screensaver is active.
- Overlay focus rule: The overlay `WindowManager.LayoutParams` must include `FLAG_NOT_FOCUSABLE | FLAG_NOT_TOUCH_MODAL` so the Sony TV remote D-pad always controls Projectivy Launcher underneath.

## Review Focus

- Foreground app detection on Android 12 TV when `ActivityManager.getRunningTasks` is restricted: `HeatingOverlayService` must check `UsageStatsManager.queryEvents` / `queryUsageStats` (with `GET_USAGE_STATS` granted via `appops`) and fall back to `ActivityManager.getRunningAppProcesses` so foreground transitions reliably hide the overlay when launching video apps.
- WebView authentication persistence: Home Assistant stores tokens in `localStorage` (`hassTokens`) and cookies; both `HeatingActivity` and `HeatingOverlayService` must enable `domStorageEnabled(true)` and `CookieManager` flushing in the same process so logging in once inside `HeatingActivity` authenticates the overlay automatically.
- Cleartext HTTP traffic on Android 9+: `AndroidManifest.xml` must set `android:usesCleartextTraffic="true"` on `<application>` so `http://192.0.2.10:8123/heating-dashboard/heating` loads without `ERR_CLEARTEXT_NOT_PERMITTED`.
- Overlay hiding during screensaver (`DreamService`): `OmarchyDreamService` must set a static volatile boolean `isDreamingNow = true` in `onDreamingStarted()` and `false` in `onDreamingStopped()` so `HeatingOverlayService` immediately hides the top-60% WebView while the OLED screensaver runs.
- Safe launcher transition: Never disable `com.google.android.apps.tv.launcherx` before verifying `com.spocky.projengmenu` is installed and resolves `android.intent.category.HOME`.

---

### Task 1: Android SDK Build Toolchain & Official Projectivy Launcher Installation

**Files:**
- Create: `.gitignore`
- Create: `scripts/setup_sdk_and_projectivy.sh`

**Interfaces:**
- Consumes: Homebrew (`/opt/homebrew/bin/brew`), ADB (`/opt/homebrew/bin/adb`)
- Produces:
  - `.android-sdk/build-tools/aapt2`, `.android-sdk/build-tools/d8`, `.android-sdk/build-tools/zipalign`, `.android-sdk/build-tools/apksigner`
  - `.android-sdk/platforms/android-34/android.jar`
  - `downloads/ProjectivyLauncher-4.73.apk` installed on `192.0.2.10:5555` (`com.spocky.projengmenu`)

- [ ] **Step 1: Create `.gitignore` to exclude SDK binaries, downloaded APKs, and build outputs**

Create `.gitignore` containing:
```gitignore
.android-sdk/
.superpowers/
downloads/
ha-omarchy-companion/build/
backups/bravia65_XR-65A80L/user_apks/
```

- [ ] **Step 2: Write `scripts/setup_sdk_and_projectivy.sh` to install OpenJDK, fetch Android build-tools + `android.jar`, and download/install Projectivy Launcher 4.73**

`scripts/setup_sdk_and_projectivy.sh` must:
1. Ensure `/opt/homebrew/opt/openjdk/bin/javac` exists (run `/opt/homebrew/bin/brew install openjdk` if missing).
2. Download and extract `https://dl.google.com/android/repository/build-tools_r34-macosx.zip` into `.android-sdk/build-tools` and `https://dl.google.com/android/repository/platform-34-ext7_r02.zip` into `.android-sdk/platforms/android-34` if `.android-sdk/platforms/android-34/android.jar` does not exist.
3. Download `https://github.com/spocky/miproja1/releases/download/4.73/ProjectivyLauncher-4.73-c98-xda-release.apk` to `downloads/ProjectivyLauncher-4.73.apk` and install it onto `192.0.2.10:5555` via `/opt/homebrew/bin/adb -s 192.0.2.10:5555 install -r downloads/ProjectivyLauncher-4.73.apk`.

- [ ] **Step 3: Run `scripts/setup_sdk_and_projectivy.sh` and verify toolchain + Projectivy installation**

Run: `bash scripts/setup_sdk_and_projectivy.sh && /opt/homebrew/bin/adb -s 192.0.2.10:5555 shell pm path com.spocky.projengmenu`
Expected: `package:/data/app/.../com.spocky.projengmenu.../base.apk` and `.android-sdk/platforms/android-34/android.jar` exists.

- [ ] **Step 4: Commit**

```bash
git add .gitignore scripts/setup_sdk_and_projectivy.sh
git commit -m "chore: add SDK toolchain setup and install Projectivy Launcher"
```

---

### Task 2: Build `com.tvs.haomarchy` Companion APK (HA Heating Overlay + Interactive Login + Omarchy OLED Screensaver)

**Files:**
- Create: `ha-omarchy-companion/AndroidManifest.xml`
- Create: `ha-omarchy-companion/res/values/strings.xml`
- Create: `ha-omarchy-companion/src/com/tvs/haomarchy/OmarchyDreamService.java`
- Create: `ha-omarchy-companion/src/com/tvs/haomarchy/HeatingOverlayService.java`
- Create: `ha-omarchy-companion/src/com/tvs/haomarchy/HeatingActivity.java`
- Create: `ha-omarchy-companion/src/com/tvs/haomarchy/BootReceiver.java`
- Create: `ha-omarchy-companion/build.sh`

**Interfaces:**
- Consumes: `.android-sdk/build-tools/*` and `.android-sdk/platforms/android-34/android.jar` from Task 1.
- Produces: `ha-omarchy-companion/build/ha-omarchy.apk` containing package `com.tvs.haomarchy` with components:
  - `com.tvs.haomarchy/.HeatingActivity`
  - `com.tvs.haomarchy/.HeatingOverlayService`
  - `com.tvs.haomarchy/.OmarchyDreamService`
  - `com.tvs.haomarchy/.BootReceiver`

- [ ] **Step 1: Create `ha-omarchy-companion/AndroidManifest.xml` and `res/values/strings.xml`**

`AndroidManifest.xml` must declare package `com.tvs.haomarchy`, `minSdkVersion="28"`, `targetSdkVersion="33"`, permissions `INTERNET`, `ACCESS_NETWORK_STATE`, `SYSTEM_ALERT_WINDOW`, `PACKAGE_USAGE_STATS`, `RECEIVE_BOOT_COMPLETED`, `FOREGROUND_SERVICE`, and `<application android:label="HA Heating &amp; Omarchy" android:usesCleartextTraffic="true" android:hardwareAccelerated="true">` with:
- `<activity android:name=".HeatingActivity" android:exported="true" android:theme="@android:style/Theme.NoTitleBar.Fullscreen">` with `MAIN` + `LAUNCHER` and `LEANBACK_LAUNCHER` intent-filters.
- `<service android:name=".HeatingOverlayService" android:exported="true" />`
- `<service android:name=".OmarchyDreamService" android:exported="true" android:label="Omarchy OLED" android:permission="android.permission.BIND_DREAM_SERVICE">` with `android.service.dreams.DreamService` intent-filter.
- `<receiver android:name=".BootReceiver" android:exported="true">` listening for `BOOT_COMPLETED` and `QUICKBOOT_POWERON`.

- [ ] **Step 2: Implement `OmarchyDreamService.java`**

Implement `com.tvs.haomarchy.OmarchyDreamService extends android.service.dreams.DreamService`:
- Expose `public static volatile boolean isDreamingNow = false;` updated in `onDreamingStarted()` / `onDreamingStopped()`.
- In `onAttachedToWindow()`, set `setInteractive(false)` and `setFullscreen(true)` and set content view to a custom `View` that renders on a `#000000` background:
  - 48 columns of cascading Omarchy terminal glyphs (ASCII/katakana/hex characters) in Omarchy/TokyoNight palette (`#7dcfff` cyan, `#9ece6a` green, `#bb9af7` magenta, `#e0af68` amber) with dark trails so average pixel luminance is < 3%.
  - A drifting terminal HUD box (`[ omarchy // bravia-65 // oled-guard ]` + current `HH:mm:ss` time) moving along a slow Lissajous path (`sin`/`cos` of elapsed time) so zero pixels are ever static.
  - Updates at ~30 FPS via `postInvalidateDelayed(33)` while attached.

- [ ] **Step 3: Implement `HeatingOverlayService.java`**

Implement `com.tvs.haomarchy.HeatingOverlayService extends android.app.Service`:
- Constants: `public static final String HA_URL = "http://192.0.2.10:8123/heating-dashboard/heating";` and `public static final String ACTION_RELOAD = "com.tvs.haomarchy.RELOAD";`.
- Creates a `WindowManager` overlay (`WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY`, `FLAG_NOT_FOCUSABLE | FLAG_NOT_TOUCH_MODAL | FLAG_LAYOUT_IN_SCREEN`, `PixelFormat.TRANSLUCENT`, `Gravity.TOP | Gravity.START`, width = `MATCH_PARENT`, height = `(int)(screenHeight * 0.58f)`).
- Inside the overlay container (`#000000` background, bottom 1px border `#227dcfff`), hosts a `WebView` with `javaScriptEnabled=true`, `domStorageEnabled=true`, `databaseEnabled=true`, `setBackgroundColor(Color.BLACK)`, `setInitialScale(100)`, and `CookieManager` enabled (`setAcceptCookie(true)`, `setAcceptThirdPartyCookies(webView, true)`), loading `HA_URL`.
- Runs a `Handler` loop every `500ms` checking `shouldShowOverlay()`:
  - Returns `false` immediately if `OmarchyDreamService.isDreamingNow` is `true` or `!PowerManager.isInteractive()`.
  - Queries `UsageStatsManager.queryEvents(now - 60000, now)` for the most recent `UsageEvents.Event.ACTIVITY_RESUMED` (or `MOVE_TO_FOREGROUND`) package name (caching the last known foreground package).
  - Returns `true` **only** when the active foreground package is `com.spocky.projengmenu` or `com.google.android.apps.tv.launcherx`.
  - Sets the overlay root view visibility to `View.VISIBLE` or `View.GONE` accordingly.
- When `onStartCommand` receives `ACTION_RELOAD`, calls `webView.reload()`.

- [ ] **Step 4: Implement `HeatingActivity.java` and `BootReceiver.java`**

- `HeatingActivity`:
  - Starts `HeatingOverlayService` on launch, hides the overlay while `HeatingActivity` is in the foreground, and opens `HeatingOverlayService.HA_URL` in a full-screen interactive `WebView` (`javaScriptEnabled=true`, `domStorageEnabled=true`, `CookieManager` enabled).
  - Overrides `onPause()` to call `CookieManager.getInstance().flush()` and send `ACTION_RELOAD` to `HeatingOverlayService` so any login session or thermostat change immediately updates the top-60% home overlay.
- `BootReceiver`:
  - Starts `HeatingOverlayService` on `BOOT_COMPLETED`.

- [ ] **Step 5: Write `ha-omarchy-companion/build.sh` and compile `build/ha-omarchy.apk`**

Write `ha-omarchy-companion/build.sh` to compile resources with `aapt2`, compile Java sources with `/opt/homebrew/opt/openjdk/bin/javac --release 11`, convert to DEX with `d8`, align with `zipalign`, generate a debug keystore if absent, and sign with `apksigner`.
Run: `bash ha-omarchy-companion/build.sh`
Expected: `ha-omarchy-companion/build/ha-omarchy.apk` created and verified with `apksigner verify`.

- [ ] **Step 6: Commit**

```bash
git add ha-omarchy-companion
git commit -m "feat: build com.tvs.haomarchy companion APK for HA overlay and Omarchy OLED screensaver"
```

---

### Task 3: Deploy to Bravia 65, Configure Permissions, Activate Projectivy Launcher & Omarchy Screensaver

**Files:**
- Create: `scripts/deploy_bravia65.sh`
- Modify: `backups/bravia65_XR-65A80L/restore.sh`

**Interfaces:**
- Consumes: `ha-omarchy-companion/build/ha-omarchy.apk` (from Task 2) and `com.spocky.projengmenu` on `192.0.2.10:5555` (from Task 1).
- Produces: Active Projectivy Launcher home screen + running `HeatingOverlayService` + configured `OmarchyDreamService` on `192.0.2.10:5555`.

- [ ] **Step 1: Write `scripts/deploy_bravia65.sh` to install `ha-omarchy.apk`, grant permissions, set Omarchy screensaver, and switch default launcher to Projectivy**

`scripts/deploy_bravia65.sh` must:
1. Connect to `192.0.2.10:5555` and install `ha-omarchy-companion/build/ha-omarchy.apk` (`adb install -r`).
2. Grant overlay and usage-stats permissions to both `com.tvs.haomarchy` and `com.spocky.projengmenu`:
   - `adb shell appops set com.tvs.haomarchy SYSTEM_ALERT_WINDOW allow`
   - `adb shell appops set com.tvs.haomarchy GET_USAGE_STATS allow`
   - `adb shell pm grant com.tvs.haomarchy android.permission.PACKAGE_USAGE_STATS`
   - `adb shell appops set com.spocky.projengmenu SYSTEM_ALERT_WINDOW allow`
   - Enable Projectivy's Accessibility Service (`com.spocky.projengmenu/com.spocky.projengmenu.services.ProjectivyAccessibilityService`).
3. Configure `OmarchyDreamService` as the system Android TV screensaver:
   - `adb shell settings put secure screensaver_components com.tvs.haomarchy/.OmarchyDreamService`
   - `adb shell settings put secure screensaver_enabled 1`
   - `adb shell settings put secure screensaver_activate_on_sleep 1`
4. Verify `com.spocky.projengmenu` is installed, disable the stock ad-heavy Google TV launcher (`adb shell pm disable-user --user 0 com.google.android.apps.tv.launcherx`), start `com.tvs.haomarchy/.HeatingOverlayService`, and send `KEYCODE_HOME` (`adb shell input keyevent 3`).

- [ ] **Step 2: Update `backups/bravia65_XR-65A80L/restore.sh` to also restore stock launcher and screensaver if `--stock-launcher` is passed**

Add `--stock-launcher` option to `backups/bravia65_XR-65A80L/restore.sh` that runs `pm enable --user 0 com.google.android.apps.tv.launcherx` and `settings put secure screensaver_components com.google.android.apps.tv.dreamx/.service.Backdrop`.

- [ ] **Step 3: Run `scripts/deploy_bravia65.sh` and verify services on `192.0.2.10:5555`**

Run: `bash scripts/deploy_bravia65.sh`
Verify with ADB:
- `adb -s 192.0.2.10:5555 shell settings get secure screensaver_components` outputs `com.tvs.haomarchy/.OmarchyDreamService`
- `adb -s 192.0.2.10:5555 shell dumpsys activity services com.tvs.haomarchy` shows `HeatingOverlayService` running
- `adb -s 192.0.2.10:5555 shell cmd dreams start-dreaming` briefly tests the Omarchy OLED screensaver and `input keyevent 3` returns to Projectivy Launcher + HA Heating overlay.

- [ ] **Step 4: Commit**

```bash
git add scripts/deploy_bravia65.sh backups/bravia65_XR-65A80L/restore.sh
git commit -m "feat: deploy Projectivy Launcher, HA Heating overlay, and Omarchy OLED screensaver to Bravia 65"
```
