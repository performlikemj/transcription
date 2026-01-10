"""
Settings manager for YardTalk using macOS NSUserDefaults.
Handles persistent storage of user preferences.
"""

from Foundation import NSUserDefaults


class SettingsManager:
    """Manages persistent settings using macOS UserDefaults."""

    # Default values
    DEFAULT_HOTKEY = "<cmd>+<shift>+d"

    # UserDefaults keys
    KEY_HOTKEY = "hotkey"

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

    def reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        self._defaults.removeObjectForKey_(self.KEY_HOTKEY)
        self._defaults.synchronize()
