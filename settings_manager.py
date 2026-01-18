"""
Settings manager for YardTalk using macOS NSUserDefaults.
Handles persistent storage of user preferences.
"""

from Foundation import NSUserDefaults


class SettingsManager:
    """Manages persistent settings using macOS UserDefaults."""

    # Default values
    DEFAULT_HOTKEY = "<cmd>+<shift>+d"
    DEFAULT_SILENCE_DURATION = 2.0  # seconds
    DEFAULT_SILENCE_AUTO_STOP_ENABLED = True
    DEFAULT_SKIP_EDIT_WINDOW = False

    # UserDefaults keys
    KEY_HOTKEY = "hotkey"
    KEY_SILENCE_DURATION = "silence_duration"
    KEY_SILENCE_AUTO_STOP_ENABLED = "silence_auto_stop_enabled"
    KEY_SKIP_EDIT_WINDOW = "skip_edit_window"

    def __init__(self):
        self._defaults = NSUserDefaults.standardUserDefaults()

    def get_hotkey(self) -> str:
        """Get the stored hotkey string, or default if not set."""
        hotkey = self._defaults.stringForKey_(self.KEY_HOTKEY)
        if hotkey is None or hotkey == "":
            return self.DEFAULT_HOTKEY
        return hotkey

    def set_hotkey(self, hotkey_str: str) -> None:
        """Persist the hotkey string to UserDefaults."""
        self._defaults.setObject_forKey_(hotkey_str, self.KEY_HOTKEY)
        self._defaults.synchronize()

    def get_silence_duration(self) -> float:
        """Get silence duration in seconds (0.5-10.0)."""
        value = self._defaults.floatForKey_(self.KEY_SILENCE_DURATION)
        if value == 0.0:  # Not set (floatForKey_ returns 0.0 for missing keys)
            return self.DEFAULT_SILENCE_DURATION
        return max(0.5, min(10.0, value))

    def set_silence_duration(self, seconds: float) -> None:
        """Set silence duration (clamped to 0.5-10.0)."""
        clamped = max(0.5, min(10.0, seconds))
        self._defaults.setFloat_forKey_(clamped, self.KEY_SILENCE_DURATION)
        self._defaults.synchronize()

    def get_silence_auto_stop_enabled(self) -> bool:
        """Get whether auto-stop on silence is enabled."""
        # NSUserDefaults returns False for missing bool keys, need explicit check
        if self._defaults.objectForKey_(self.KEY_SILENCE_AUTO_STOP_ENABLED) is None:
            return self.DEFAULT_SILENCE_AUTO_STOP_ENABLED
        return self._defaults.boolForKey_(self.KEY_SILENCE_AUTO_STOP_ENABLED)

    def set_silence_auto_stop_enabled(self, enabled: bool) -> None:
        """Set whether auto-stop on silence is enabled."""
        self._defaults.setBool_forKey_(enabled, self.KEY_SILENCE_AUTO_STOP_ENABLED)
        self._defaults.synchronize()

    def get_skip_edit_window(self) -> bool:
        """Get whether to skip the edit window after transcription."""
        # Default is False (show edit window)
        if self._defaults.objectForKey_(self.KEY_SKIP_EDIT_WINDOW) is None:
            return self.DEFAULT_SKIP_EDIT_WINDOW
        return self._defaults.boolForKey_(self.KEY_SKIP_EDIT_WINDOW)

    def set_skip_edit_window(self, skip: bool) -> None:
        """Set whether to skip the edit window after transcription."""
        self._defaults.setBool_forKey_(skip, self.KEY_SKIP_EDIT_WINDOW)
        self._defaults.synchronize()

    def reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        self._defaults.removeObjectForKey_(self.KEY_HOTKEY)
        self._defaults.removeObjectForKey_(self.KEY_SILENCE_DURATION)
        self._defaults.removeObjectForKey_(self.KEY_SILENCE_AUTO_STOP_ENABLED)
        self._defaults.removeObjectForKey_(self.KEY_SKIP_EDIT_WINDOW)
        self._defaults.synchronize()
