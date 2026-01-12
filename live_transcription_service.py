"""
Live transcription service for periodic preview during recording.

This provides a simulated live transcription experience by periodically
transcribing accumulated audio to show preview text while the user speaks.
"""

import threading
import time
import numpy as np
from typing import Callable, Optional


class LiveTranscriptionService:
    """
    Provides periodic preview transcriptions during recording.

    This is a simulation of live transcription - it periodically sends
    accumulated audio for transcription to provide feedback while speaking.
    True streaming isn't well-supported by Parakeet-TDT, so we use this
    periodic re-transcription approach instead.
    """

    PREVIEW_INTERVAL = 2.0  # Seconds between preview transcriptions
    MIN_AUDIO_LENGTH = 0.5  # Minimum audio seconds before previewing

    def __init__(
        self,
        asr_service,
        on_preview: Callable[[str], None],
        sample_rate: int = 16000
    ):
        """
        Initialize the live transcription service.

        Args:
            asr_service: The ASRService instance for transcription.
            on_preview: Callback(text) when preview text is available.
            sample_rate: Audio sample rate in Hz.
        """
        self._asr_service = asr_service
        self._on_preview = on_preview
        self._sample_rate = sample_rate

        self._is_active = False
        self._audio_buffer: list[np.ndarray] = []
        self._buffer_lock = threading.Lock()
        self._preview_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Track last preview to avoid duplicate callbacks
        self._last_preview_text = ""

    @property
    def is_active(self):
        """Return whether the service is currently active."""
        return self._is_active

    def start(self):
        """Start periodic preview transcription."""
        if self._is_active:
            print("LIVE_TRANSCRIPTION: Already active, ignoring start")
            return

        print("LIVE_TRANSCRIPTION: Starting preview service")
        self._is_active = True
        self._stop_event.clear()
        self._audio_buffer = []
        self._last_preview_text = ""

        self._preview_thread = threading.Thread(
            target=self._preview_loop,
            name="LiveTranscriptionPreview"
        )
        self._preview_thread.daemon = True
        self._preview_thread.start()

    def stop(self):
        """Stop preview transcription."""
        if not self._is_active:
            return

        print("LIVE_TRANSCRIPTION: Stopping preview service")
        self._is_active = False
        self._stop_event.set()

        if self._preview_thread:
            self._preview_thread.join(timeout=2.0)
            self._preview_thread = None

        # Clear buffer
        with self._buffer_lock:
            self._audio_buffer = []

    def add_audio_chunk(self, chunk: np.ndarray):
        """
        Add audio chunk to preview buffer (thread-safe).

        Args:
            chunk: Audio data as int16 numpy array.
        """
        if not self._is_active:
            return

        # Convert int16 to float32
        chunk_float = chunk.astype(np.float32) / 32768.0
        if chunk_float.ndim > 1:
            chunk_float = chunk_float.flatten()

        with self._buffer_lock:
            self._audio_buffer.append(chunk_float)

    def _preview_loop(self):
        """Background thread that periodically triggers preview transcription."""
        print("LIVE_TRANSCRIPTION: Preview loop started")

        while not self._stop_event.wait(timeout=self.PREVIEW_INTERVAL):
            if not self._is_active:
                break

            with self._buffer_lock:
                if not self._audio_buffer:
                    continue

                # Get copy of accumulated audio
                try:
                    audio = np.concatenate(self._audio_buffer)
                except ValueError:
                    # Empty buffer or invalid data
                    continue

            # Check minimum length
            duration = len(audio) / self._sample_rate
            if duration < self.MIN_AUDIO_LENGTH:
                continue

            # Request preview transcription
            self._request_preview_transcription(audio)

        print("LIVE_TRANSCRIPTION: Preview loop ended")

    def _request_preview_transcription(self, audio: np.ndarray):
        """
        Request a preview transcription.

        This uses direct model access for preview to avoid interfering
        with the main transcription queue.
        """
        try:
            # Check if model is loaded and available
            if not self._asr_service.is_model_loaded:
                return

            asr_model = getattr(self._asr_service, 'asr_model', None)
            if asr_model is None:
                return

            # Direct model call for preview (not through queue)
            import torch
            with torch.no_grad():
                results = asr_model.transcribe([audio], batch_size=1)
                if results and len(results) > 0:
                    text = results[0] if isinstance(results[0], str) else ""
                    if text and text != self._last_preview_text:
                        self._last_preview_text = text
                        # Callback to UI (needs main thread dispatch)
                        from PyObjCTools import AppHelper
                        AppHelper.callAfter(self._on_preview, text)
                        print(f"LIVE_TRANSCRIPTION: Preview updated: '{text[:50]}...'")

        except Exception as e:
            print(f"LIVE_TRANSCRIPTION: Preview error: {e}")

    def clear_buffer(self):
        """Clear the audio buffer."""
        with self._buffer_lock:
            self._audio_buffer = []
        self._last_preview_text = ""
