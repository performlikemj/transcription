"""
Session-only transcription history manager for YardTalk.
Stores recent transcriptions in memory for menu access.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from collections import deque


@dataclass
class TranscriptionEntry:
    """Single transcription record."""

    timestamp: datetime
    original_text: str
    corrected_text: Optional[str]  # None if not edited
    discarded: bool = False  # True if user discarded (saved for recovery)

    @property
    def display_text(self) -> str:
        """Return the text that was actually inserted (or original if discarded)."""
        return self.corrected_text if self.corrected_text else self.original_text

    @property
    def was_corrected(self) -> bool:
        """Return True if text was edited before insertion."""
        return (
            self.corrected_text is not None
            and self.corrected_text != self.original_text
        )

    def menu_title(self, max_length: int = 40) -> str:
        """Formatted string for menu display."""
        text = self.display_text.replace("\n", " ")
        if len(text) > max_length:
            text = text[: max_length - 3] + "..."
        time_str = self.timestamp.strftime("%H:%M")

        # Indicators: * = edited, X = discarded
        if self.discarded:
            prefix = "X "
        elif self.was_corrected:
            prefix = "* "
        else:
            prefix = ""

        return f"{prefix}[{time_str}] {text}"


class TranscriptionHistory:
    """Session-only transcription history manager."""

    MAX_ENTRIES = 20

    def __init__(self):
        self._entries: deque[TranscriptionEntry] = deque(maxlen=self.MAX_ENTRIES)

    def add(
        self, original_text: str, corrected_text: Optional[str] = None, discarded: bool = False
    ) -> TranscriptionEntry:
        """Add a new transcription entry."""
        entry = TranscriptionEntry(
            timestamp=datetime.now(),
            original_text=original_text,
            corrected_text=corrected_text if corrected_text != original_text else None,
            discarded=discarded,
        )
        self._entries.appendleft(entry)  # Most recent first
        return entry

    def get_entries(self) -> list[TranscriptionEntry]:
        """Return all entries, most recent first."""
        return list(self._entries)

    def clear(self):
        """Clear all history."""
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
