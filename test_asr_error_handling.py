import importlib
import os
import sys
import types


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


class _DummyTimer:
    def __init__(self, user_payload):
        self.user_payload = user_payload
        self.log_id = "test_timer"
        self.stopped = False

    def stop(self):
        self.stopped = True


def _import_main():
    if "main" not in sys.modules:
        _install_stub_modules()
        os.environ["HOME"] = os.getcwd()
        importlib.import_module("main")
    return sys.modules["main"]


def test_blank_transcription_with_error_schedules_timer():
    main = _import_main()
    calls = []
    main.AppHelper.callAfter = lambda fn, payload: calls.append((fn, payload))

    dummy_app = types.SimpleNamespace(
        _model_loaded_handled=False,
        asr_model_status="loaded",
        is_transcribing=False,
        hotkey_manager=types.SimpleNamespace(hotkey_active=False),
        update_menu_state=lambda: None,
        _create_timer_on_main=lambda payload: None,
    )

    main.DictationApp._handle_asr_service_result(dummy_app, "", Exception("boom"))

    assert calls, "Expected AppHelper.callAfter to be called for transcription errors"
    _, payload = calls[0]
    assert payload["type"] == main.ASR_CALLBACK_TYPE_TRANSCRIPTION
    assert payload["data"]["error"] is not None


def test_blank_transcription_with_error_triggers_alert():
    main = _import_main()
    alerts = []
    main.rumps.alert = lambda *args, **kwargs: alerts.append((args, kwargs))

    timer = _DummyTimer(
        {
            "type": main.ASR_CALLBACK_TYPE_TRANSCRIPTION,
            "data": {"text": "", "error": Exception("boom")},
        }
    )

    dummy_app = types.SimpleNamespace(
        asr_model_status="loaded",
        hotkey_string="<cmd>+d",
        _last_transcribed_text=None,
        text_insertion_service=types.SimpleNamespace(insert_text=lambda text: True),
        hotkey_manager=types.SimpleNamespace(hotkey_active=False),
        audio_manager=types.SimpleNamespace(
            _is_recording=False,
            stop_recording=lambda *args, **kwargs: None,
        ),
        waveform_visualizer=types.SimpleNamespace(stop=lambda: None),
        dictation_active=True,
        is_transcribing=True,
        active_timers=[timer],
        update_menu_state=lambda: None,
    )

    main.DictationApp._process_asr_result_on_main_thread(dummy_app, timer)

    assert alerts, "Expected a transcription error alert even when text is blank"
