import importlib
import os
import sys
import types
import logging


def _install_stub_modules():
    def clicked(_title):
        def decorator(fn):
            return fn
        return decorator

    rumps = types.ModuleType("rumps")
    rumps.App = object
    rumps.Timer = object
    rumps.notification = lambda *args, **kwargs: None
    rumps.alert = lambda *args, **kwargs: None
    rumps.clicked = clicked
    sys.modules["rumps"] = rumps

    hotkey_manager = types.ModuleType("hotkey_manager")
    hotkey_manager.HotkeyManager = object
    sys.modules["hotkey_manager"] = hotkey_manager

    audio_manager = types.ModuleType("audio_manager")
    audio_manager.AudioManager = object
    sys.modules["audio_manager"] = audio_manager

    asr_service = types.ModuleType("asr_service")
    asr_service.ASRService = object
    sys.modules["asr_service"] = asr_service

    text_insertion_service = types.ModuleType("text_insertion_service")
    text_insertion_service.TextInsertionService = object
    sys.modules["text_insertion_service"] = text_insertion_service

    waveform_visualizer = types.ModuleType("waveform_visualizer")
    waveform_visualizer.WaveformVisualizer = object
    sys.modules["waveform_visualizer"] = waveform_visualizer

    sounddevice = types.ModuleType("sounddevice")
    sounddevice.query_devices = lambda: []
    sys.modules["sounddevice"] = sounddevice

    apphelper = types.SimpleNamespace(callAfter=lambda *args, **kwargs: None)
    pyobjc_tools = types.ModuleType("PyObjCTools")
    pyobjc_tools.AppHelper = apphelper
    sys.modules["PyObjCTools"] = pyobjc_tools


def test_logging_setup_falls_back_on_permission_error(monkeypatch, tmp_path):
    logging.getLogger().handlers.clear()
    for module_name in (
        "main",
        "rumps",
        "hotkey_manager",
        "audio_manager",
        "asr_service",
        "text_insertion_service",
        "waveform_visualizer",
        "sounddevice",
        "PyObjCTools",
    ):
        sys.modules.pop(module_name, None)

    _install_stub_modules()
    os.environ["HOME"] = str(tmp_path)

    def _raise_permission(*_args, **_kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(logging, "FileHandler", _raise_permission)

    importlib.import_module("main")
