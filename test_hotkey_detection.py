import sys
import types


def _install_pynput_stub():
    """Install a minimal pynput stub so hotkey_manager can be imported in tests."""
    pynput_module = types.ModuleType("pynput")
    keyboard_module = types.ModuleType("pynput.keyboard")

    class Key:
        ctrl = object()
        alt = object()
        cmd = object()
        shift = object()
        space = object()
        f9 = object()

    class KeyCode:
        def __init__(self, char):
            self.char = char

        @classmethod
        def from_char(cls, char):
            return cls(char)

        def __eq__(self, other):
            return isinstance(other, KeyCode) and self.char == other.char

        def __hash__(self):
            return hash(self.char)

    class HotKey:
        def __init__(self, keys, on_activate):
            self._keys = set(keys)
            self._pressed = set()
            self._on_activate = on_activate

        @staticmethod
        def parse(hotkey_str):
            parts = [part.strip() for part in hotkey_str.split("+") if part.strip()]
            keys = []
            for part in parts:
                if part.startswith("<") and part.endswith(">"):
                    key_name = part[1:-1]
                    key = getattr(Key, key_name, None)
                    if key is None:
                        raise ValueError(f"Unsupported key: {part}")
                    keys.append(key)
                else:
                    keys.append(KeyCode.from_char(part))
            return keys

        def press(self, key):
            self._pressed.add(key)
            if self._keys.issubset(self._pressed):
                self._on_activate()

        def release(self, key):
            self._pressed.discard(key)

    class Listener:
        def __init__(self, on_press=None, on_release=None):
            self._on_press = on_press
            self._on_release = on_release

        def start(self):
            return self

        def stop(self):
            return None

        def join(self):
            return None

    keyboard_module.Key = Key
    keyboard_module.KeyCode = KeyCode
    keyboard_module.HotKey = HotKey
    keyboard_module.Listener = Listener

    pynput_module.keyboard = keyboard_module
    sys.modules["pynput"] = pynput_module
    sys.modules["pynput.keyboard"] = keyboard_module


try:
    import pynput  # noqa: F401
except ModuleNotFoundError:
    _install_pynput_stub()

import hotkey_manager
from hotkey_manager import HotkeyManager
from pynput import keyboard


def test_hotkey_ctrl_alt_space_triggers(monkeypatch):
    monkeypatch.setattr(hotkey_manager.sys, "platform", "linux")

    calls = []

    def on_activate():
        calls.append("on")

    def on_deactivate():
        calls.append("off")

    manager = HotkeyManager("<ctrl>+<alt>+<space>", on_activate, on_deactivate)

    manager._on_key_press_with_hotkey_detection(keyboard.Key.ctrl)
    manager._on_key_press_with_hotkey_detection(keyboard.Key.alt)
    manager._on_key_press_with_hotkey_detection(keyboard.Key.space)

    manager._on_key_release_with_hotkey_detection(keyboard.Key.space)
    manager._on_key_release_with_hotkey_detection(keyboard.Key.alt)
    manager._on_key_release_with_hotkey_detection(keyboard.Key.ctrl)

    assert calls == ["on"]
