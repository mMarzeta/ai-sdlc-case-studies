import sys
import unittest
from pathlib import Path

# Ensure scripts directory is on sys.path
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from tv_adb_monitor import parse_dumpsys


class TestTvAdbMonitor(unittest.TestCase):
    def test_awake_smarttube(self):
        output = """
  mWakefulness=Awake
  mCurrentFocus=Window{e000943 u0 org.smarttube.stable/com.liskovsoft.smartyoutubetv2.tv.ui.playback.PlaybackActivity}
  mFocusedApp=ActivityRecord{85f79a7 u0 org.smarttube.stable/com.liskovsoft.smartyoutubetv2.tv.ui.playback.PlaybackActivity t13789}
"""
        result = parse_dumpsys(output)
        self.assertEqual(
            result,
            {
                "is_on": True,
                "wakefulness": "Awake",
                "package": "org.smarttube.stable",
                "app": "SmartTube",
            },
        )

    def test_asleep(self):
        output = """
  mWakefulness=Asleep
  mCurrentFocus=null
  mFocusedApp=ActivityRecord{c6de6dc u0 com.google.android.apps.tv.launcherx/.coreservices.bootmode.DispatchActivity t26276}
"""
        result = parse_dumpsys(output)
        self.assertEqual(
            result,
            {
                "is_on": False,
                "wakefulness": "Asleep",
                "package": "",
                "app": "Wyłączony",
            },
        )

    def test_dreaming_wakefulness(self):
        output = """
  mWakefulness=Dreaming
  mIsDreaming=true
  mCurrentDream=ComponentInfo{com.google.android.backdrop/com.google.android.backdrop.Backdrop}
"""
        result = parse_dumpsys(output)
        self.assertEqual(
            result,
            {
                "is_on": True,
                "wakefulness": "Dreaming",
                "package": "dream",
                "app": "Launcher / Wygaszacz",
            },
        )

    def test_dreaming_flag_only(self):
        output = """
  mWakefulness=Awake
  mIsDreaming=true
  mCurrentFocus=Window{12345 u0 com.google.android.backdrop/com.google.android.backdrop.Backdrop}
"""
        result = parse_dumpsys(output)
        self.assertEqual(
            result,
            {
                "is_on": True,
                "wakefulness": "Dreaming",
                "package": "dream",
                "app": "Launcher / Wygaszacz",
            },
        )

    def test_awake_focus_null_focused_app_twitch(self):
        output = """
  mWakefulness=Awake
  mCurrentFocus=null
  mFocusedApp=ActivityRecord{85f79a7 u0 tv.twitch.android.app/tv.twitch.android.app.MainActivity t13789}
"""
        result = parse_dumpsys(output)
        self.assertEqual(
            result,
            {
                "is_on": True,
                "wakefulness": "Awake",
                "package": "tv.twitch.android.app",
                "app": "Twitch",
            },
        )

    def test_awake_systemui_focus_falls_back_to_focused_app(self):
        output = """
  mWakefulness=Awake
  mCurrentFocus=Window{abc1234 u0 com.android.systemui/com.android.systemui.volume.VolumeDialogImpl}
  mFocusedApp=ActivityRecord{85f79a7 u0 com.pl.tmobile.magentatv/com.pl.tmobile.magentatv.MainActivity t123}
"""
        result = parse_dumpsys(output)
        self.assertEqual(
            result,
            {
                "is_on": True,
                "wakefulness": "Awake",
                "package": "com.pl.tmobile.magentatv",
                "app": "MagentaTV",
            },
        )


if __name__ == "__main__":
    unittest.main()
