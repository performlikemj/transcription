import sys
import types

sounddevice = types.ModuleType("sounddevice")


class _PortAudioError(Exception):
    pass


sounddevice.PortAudioError = _PortAudioError
sounddevice.InputStream = object
sounddevice.query_devices = lambda *args, **kwargs: {"name": "Dummy Input"}
sys.modules["sounddevice"] = sounddevice

import audio_manager


def test_start_recording_returns_false_on_stream_error(monkeypatch):
    class _FailingStream:
        def __init__(self, *args, **kwargs):
            raise audio_manager.sd.PortAudioError("Input device unavailable")

    monkeypatch.setattr(audio_manager.sd, "InputStream", _FailingStream)
    monkeypatch.setattr(
        audio_manager.sd,
        "query_devices",
        lambda *args, **kwargs: {"name": "Dummy Input"},
    )

    manager = audio_manager.AudioManager()
    started = manager.start_recording("test_start")

    if manager._recording_thread:
        manager._recording_thread.join(timeout=0.5)

    assert started is False
    assert manager.get_last_error() is not None
    assert not manager._recording_active_event.is_set()
