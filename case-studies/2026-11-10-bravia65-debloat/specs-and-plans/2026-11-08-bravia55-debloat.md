# Sony Bravia 55 (`XR-55A80L` / `192.0.2.10`) Backup & Debloat Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task using `Model: "flash"` subagents for cost optimization.

**Goal:** Create a complete backup snapshot of the Sony Bravia 55 (`192.0.2.10:5555`) and uninstall the exact same 42 bloatware, ACR/spying, telemetry, retail/hotel demo, Bravia Cam, and unused streaming packages as on the Bravia 65 — **without** installing Projectivy Launcher or any Home Assistant / companion APK.

**Critical Safety Constraints:**
- **NEVER** touch or disable `com.google.android.tungsten.setupwraith` or `com.google.android.apps.tv.launcherx` (the stock Google TV launcher remains active).
- **NEVER** run commands against `192.0.2.10:5555` (Bravia 65); always pass `-s 192.0.2.10:5555`.
- **Backup First:** Dump all package lists, device properties, and pull any installed user streaming APKs + generate `restore.sh` in `/Users/maciejmarzeta/Documents/tvs/backups/bravia55_XR-55A80L/` before running any `pm uninstall --user 0` command.

---

### Task 1: Full Backup Snapshot & `restore.sh` Generation (`flash` Subagent)

**Files:**
- Create: `/Users/maciejmarzeta/Documents/tvs/backups/bravia55_XR-55A80L/all_packages_with_paths.txt`
- Create: `/Users/maciejmarzeta/Documents/tvs/backups/bravia55_XR-55A80L/enabled_packages.txt`
- Create: `/Users/maciejmarzeta/Documents/tvs/backups/bravia55_XR-55A80L/disabled_packages.txt`
- Create: `/Users/maciejmarzeta/Documents/tvs/backups/bravia55_XR-55A80L/system_packages.txt`
- Create: `/Users/maciejmarzeta/Documents/tvs/backups/bravia55_XR-55A80L/user_packages_with_paths.txt`
- Create: `/Users/maciejmarzeta/Documents/tvs/backups/bravia55_XR-55A80L/device_props.txt`
- Create: `/Users/maciejmarzeta/Documents/tvs/backups/bravia55_XR-55A80L/user_apks/` (any installed user streaming apps among `com.disney.disneyplus`, `com.wbd.stream`, `com.canal.android.canal`, `com.tvp.vodtv.tv`, `com.crunchyroll.crunchyroid`)
- Create: `/Users/maciejmarzeta/Documents/tvs/backups/bravia55_XR-55A80L/restore.sh`

- [x] **Step 1: Verify ADB authorization on `192.0.2.10:5555` and capture package lists + properties**
- [x] **Step 2: Pull split APKs for any of the 5 user streaming packages installed on `192.0.2.10:5555`**
- [x] **Step 3: Create executable `restore.sh` to re-install system packages via `cmd package install-existing` and user APKs via `adb install-multiple`**

---

### Task 2: Surgical Removal of the 42 Target Packages & Verification (`flash` Subagent)

**Target Packages (42 total):**
1. **User-Installed Streaming Apps (5):**
   - `com.disney.disneyplus`
   - `com.wbd.stream`
   - `com.canal.android.canal`
   - `com.tvp.vodtv.tv`
   - `com.crunchyroll.crunchyroid`
2. **Pre-Installed Streaming Stubs/Apps (5):**
   - `com.netflix.ninja`
   - `com.netflix.partner.ncm`
   - `com.apple.atve.sony.appletv`
   - `com.sonypicturescore`
   - `com.google.android.youtube.tvmusic`
3. **Spying, ACR Frame-Grabbers, Telemetry & Promotions (14):**
   - `tv.samba.ssm`
   - `tv.samba.ssm.ui`
   - `com.sony.dtv.videoframeserver`
   - `com.sony.dtv.da.service`
   - `com.qterics.da.product`
   - `com.sonyericsson.idd.agent`
   - `com.sony.dtv.sonybugreportsys`
   - `com.sony.dtv.sonyloglevelsettingsys`
   - `com.google.android.feedback`
   - `com.sony.dtv.usercontext`
   - `com.sony.dtv.lastaccess`
   - `com.sony.dtv.promos`
   - `com.sony.dtv.sonyselect`
   - `com.sony.dtv.sonytab`
4. **Retail Demo & Hotel / B2B Packages (14):**
   - `com.sony.dtv.demosupport`
   - `com.sony.dtv.demosystemsupport`
   - `com.sony.dtv.multiscreendemo`
   - `com.sony.dtv.b2b.hotelmode`
   - `com.sony.dtv.b2b.rs232csupport`
   - `com.sony.dtv.b2b.prosettings`
   - `com.sony.dtv.b2b.adminpassword`
   - `com.sony.dtv.b2b.deviceadminsettings`
   - `com.sony.dtv.b2b.importexport`
   - `com.sony.dtv.b2b.noderuntime.normal`
   - `com.sony.dtv.b2b.noderuntime.privilege`
   - `com.sony.dtv.b2b.noderuntimeextension.bpk`
   - `com.sony.dtv.b2b.noderuntimeextension.node_20_11_1`
   - `com.sony.dtv.b2b.webappruntimedrm`
5. **Bravia Cam Packages (4):**
   - `com.sony.dtv.gestureapp`
   - `com.sony.dtv.distancealert`
   - `com.sony.dtv.sensingcamera.settings`
   - `com.sony.dtv.sensingcamera.fwupdate`

- [x] **Step 1: Run `adb -s 192.0.2.10:5555 shell pm uninstall --user 0 <pkg>` for each of the 42 packages and log results**
- [x] **Step 2: Verify none of the 42 packages remain in `pm list packages` for user 0**
- [x] **Step 3: Verify network connectivity (`ping -c 2 8.8.8.8`) and confirm `setupwraith` and `launcherx` remain enabled**
