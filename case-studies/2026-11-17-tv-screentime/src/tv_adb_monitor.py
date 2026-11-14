#!/usr/bin/env python3
"""
tv_adb_monitor.py - Monitor Sony Bravia TV state and send notifications via adb_shell.

Subcommands:
  status <ip>                   - Query TV power and foreground app status as JSON.
  notify <ip> <title> <message> - Post an on-screen notification to the TV.
"""

import json
import os
import re
import shlex
import sys
from typing import Dict, Any, Optional

PACKAGE_APP_MAP: Dict[str, str] = {
    "org.smarttube.stable": "SmartTube",
    "com.google.android.youtube.tv": "YouTube",
    "tv.twitch.android.app": "Twitch",
    "com.pl.tmobile.magentatv": "MagentaTV",
    "com.amazon.amazonvideo.livingroom": "Prime Video",
    "org.jellyfin.androidtv": "Jellyfin",
    "pl.videostar": "Videostar",
    "com.sony.dtv.tvinput.external": "HDMI / TV",
    "com.sony.dtv.tvinput.tuner": "HDMI / TV",
    "com.sony.dtv.braviasyncmenu": "HDMI / TV",
    "com.spocky.projengmenu": "Launcher / Wygaszacz",
    "com.google.android.apps.tv.launcherx": "Launcher / Wygaszacz",
    "com.google.android.apps.tv.dreamx": "Launcher / Wygaszacz",
    "com.tvs.haomarchy": "Launcher / Wygaszacz",
    "com.android.tv.settings": "Launcher / Wygaszacz",
    "com.google.android.tungsten.setupwraith": "Launcher / Wygaszacz",
    "com.google.android.backdrop": "Launcher / Wygaszacz",
}

DEFAULT_OFFLINE_RESULT: Dict[str, Any] = {
    "is_on": False,
    "wakefulness": "Offline",
    "package": "",
    "app": "Wyłączony",
}

DUMPSYS_COMMAND = (
    'dumpsys power | grep -E "mWakefulness="; '
    'dumpsys dreams | grep -E "mIsDreaming=|mCurrentDream="; '
    'dumpsys window displays | grep -E "mCurrentFocus=|mFocusedApp="'
)


def parse_dumpsys(output: str) -> Dict[str, Any]:
    """Parse adb dumpsys output to determine power state and active app."""
    # 1. Wakefulness
    wake_match = re.search(r"mWakefulness=([A-Za-z]+)", output)
    wakefulness = wake_match.group(1) if wake_match else "Offline"

    # 2. Dreams / Screensaver
    dream_match = re.search(r"mIsDreaming=(true|false)", output, re.IGNORECASE)
    is_dreaming = dream_match.group(1).lower() == "true" if dream_match else False

    if is_dreaming or wakefulness.lower() == "dreaming":
        return {
            "is_on": True,
            "wakefulness": "Dreaming",
            "package": "dream",
            "app": "Launcher / Wygaszacz",
        }

    # 3. Off / Asleep / Dozing / Offline
    if wakefulness.lower() != "awake":
        return {
            "is_on": False,
            "wakefulness": wakefulness,
            "package": "",
            "app": "Wyłączony",
        }

    # 4. Awake -> extract package
    focus_match = re.search(r"mCurrentFocus=Window\{[^\s]+\s+u\d+\s+([a-zA-Z0-9._]+)/", output)
    focused_app_match = re.search(r"mFocusedApp=ActivityRecord\{[^\s]+\s+u\d+\s+([a-zA-Z0-9._]+)/", output)

    focus_pkg = focus_match.group(1) if focus_match else None
    app_pkg = focused_app_match.group(1) if focused_app_match else None

    # Fall back if mCurrentFocus is null or system UI overlay
    if focus_pkg and focus_pkg != "com.android.systemui":
        package = focus_pkg
    elif app_pkg:
        package = app_pkg
    elif focus_pkg:
        package = focus_pkg
    else:
        package = ""

    # Map package to human-readable app name
    if package == "dream":
        app = "Launcher / Wygaszacz"
    elif package in PACKAGE_APP_MAP:
        app = PACKAGE_APP_MAP[package]
    elif package.startswith("com.sony.dtv.tvinput."):
        app = "HDMI / TV"
    elif package:
        app = "Inne"
    else:
        app = "Launcher / Wygaszacz"

    return {
        "is_on": True,
        "wakefulness": wakefulness,
        "package": package,
        "app": app,
    }


def _get_adb_signer():
    """Find and load the ADB private key."""
    from adb_shell.auth.sign_pythonrsa import PythonRSASigner

    candidate_paths = [
        "/config/.storage/androidtv_adbkey",
        os.path.expanduser("~/.android/adbkey"),
        "/root/.android/adbkey",
    ]
    for key_path in candidate_paths:
        if os.path.exists(key_path):
            try:
                return PythonRSASigner.FromRSAKeyPath(key_path)
            except Exception:
                continue
    return None


def get_tv_status(ip: str, timeout_s: float = 4.0) -> Dict[str, Any]:
    """Query TV status via adb_shell over TCP."""
    from adb_shell.adb_device import AdbDeviceTcp

    signer = _get_adb_signer()
    if not signer:
        return DEFAULT_OFFLINE_RESULT

    device = None
    try:
        device = AdbDeviceTcp(ip, 5555, default_transport_timeout_s=timeout_s)
        device.connect(rsa_keys=[signer], auth_timeout_s=timeout_s)
        output = device.shell(DUMPSYS_COMMAND, transport_timeout_s=timeout_s, read_timeout_s=timeout_s)
        return parse_dumpsys(output or "")
    except Exception:
        return DEFAULT_OFFLINE_RESULT
    finally:
        if device:
            try:
                device.close()
            except Exception:
                pass


def send_tv_notification(ip: str, title: str, message: str, timeout_s: float = 4.0) -> bool:
    """Send an on-screen notification to the TV via adb_shell."""
    from adb_shell.adb_device import AdbDeviceTcp

    signer = _get_adb_signer()
    if not signer:
        return False

    device = None
    try:
        device = AdbDeviceTcp(ip, 5555, default_transport_timeout_s=timeout_s)
        device.connect(rsa_keys=[signer], auth_timeout_s=timeout_s)
        cmd = f"cmd notification post -S bigtext -t {shlex.quote(title)} tv_limit_4h {shlex.quote(message)}"
        device.shell(cmd, transport_timeout_s=timeout_s, read_timeout_s=timeout_s)
        return True
    except Exception:
        return False
    finally:
        if device:
            try:
                device.close()
            except Exception:
                pass


def main():
    if len(sys.argv) < 2:
        print("Usage: tv_adb_monitor.py status <ip> | notify <ip> <title> <message>", file=sys.stderr)
        sys.exit(1)

    subcommand = sys.argv[1].lower()

    if subcommand == "status":
        if len(sys.argv) < 3:
            print(json.dumps(DEFAULT_OFFLINE_RESULT, ensure_ascii=False))
            sys.exit(0)
        ip = sys.argv[2]
        result = get_tv_status(ip)
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)

    elif subcommand == "notify":
        if len(sys.argv) < 5:
            print("Usage: tv_adb_monitor.py notify <ip> <title> <message>", file=sys.stderr)
            sys.exit(1)
        ip = sys.argv[2]
        title = sys.argv[3]
        message = sys.argv[4]
        success = send_tv_notification(ip, title, message)
        if success:
            print("Notification sent successfully")
            sys.exit(0)
        else:
            print("Failed to send notification", file=sys.stderr)
            sys.exit(1)

    else:
        print(f"Unknown subcommand: {subcommand}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
