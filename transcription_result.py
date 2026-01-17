"""
Data structures for carrying transcription results with timestamps.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class WordTimestamp:
    """A single word with its start and end timestamps."""
    word: str
    start: float  # seconds
    end: float    # seconds

    def __str__(self) -> str:
        return f"[{self.start:.2f}-{self.end:.2f}] {self.word}"


@dataclass
class SegmentTimestamp:
    """A segment (sentence/phrase) with its start and end timestamps."""
    text: str
    start: float  # seconds
    end: float    # seconds

    def __str__(self) -> str:
        return f"[{self.start:.2f}-{self.end:.2f}] {self.text}"

    @staticmethod
    def format_time(seconds: float) -> str:
        """Format seconds as M:SS or H:MM:SS."""
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"

    def formatted_range(self) -> str:
        """Return a formatted time range like '[0:05 - 0:12]'."""
        return f"[{self.format_time(self.start)} - {self.format_time(self.end)}]"


@dataclass
class TranscriptionResult:
    """
    Complete transcription result with text and optional timestamps.

    Attributes:
        text: The full transcribed text
        duration_seconds: Total audio duration in seconds
        word_timestamps: List of word-level timestamps (optional)
        segment_timestamps: List of segment-level timestamps (optional)
    """
    text: str
    duration_seconds: float = 0.0
    word_timestamps: List[WordTimestamp] = field(default_factory=list)
    segment_timestamps: List[SegmentTimestamp] = field(default_factory=list)

    @classmethod
    def from_text_only(cls, text: str, duration_seconds: float = 0.0) -> "TranscriptionResult":
        """Create a result with just text (no timestamps)."""
        return cls(text=text, duration_seconds=duration_seconds)

    @classmethod
    def from_nemo_hypothesis(cls, hypothesis, audio_duration: float = 0.0) -> "TranscriptionResult":
        """
        Create a TranscriptionResult from a NeMo hypothesis object.

        NeMo's timestamp output format (when timestamps=True):
        - hypothesis.text: The full transcribed text
        - hypothesis.timestamp: Dict with keys 'word', 'segment', 'char', 'timestep'
          Each contains a list of dicts with 'word'/'segment', 'start', 'end' keys

        For segment timestamps, we use NeMo's segment timestamps if available,
        otherwise group words by natural pauses or sentence boundaries.
        """
        # Handle string input (backwards compatibility)
        if isinstance(hypothesis, str):
            return cls.from_text_only(hypothesis, audio_duration)

        # Extract text
        text = ""
        if hasattr(hypothesis, 'text'):
            text = hypothesis.text
        elif isinstance(hypothesis, str):
            text = hypothesis

        # Extract timestamps from hypothesis.timestamp dict
        word_timestamps = []
        segment_timestamps = []

        if hasattr(hypothesis, 'timestamp') and hypothesis.timestamp:
            ts_dict = hypothesis.timestamp

            # Extract word-level timestamps
            if 'word' in ts_dict and ts_dict['word']:
                for ts in ts_dict['word']:
                    if isinstance(ts, dict):
                        word_timestamps.append(WordTimestamp(
                            word=ts.get('word', ''),
                            start=ts.get('start', 0.0),
                            end=ts.get('end', 0.0)
                        ))

            # Extract segment-level timestamps (NeMo provides these directly)
            if 'segment' in ts_dict and ts_dict['segment']:
                for ts in ts_dict['segment']:
                    if isinstance(ts, dict):
                        segment_timestamps.append(SegmentTimestamp(
                            text=ts.get('segment', ''),
                            start=ts.get('start', 0.0),
                            end=ts.get('end', 0.0)
                        ))

        # If no segments from NeMo, generate from words
        if not segment_timestamps and word_timestamps:
            segment_timestamps = cls._create_segments_from_words(word_timestamps, text)

        return cls(
            text=text,
            duration_seconds=audio_duration,
            word_timestamps=word_timestamps,
            segment_timestamps=segment_timestamps
        )

    @staticmethod
    def _create_segments_from_words(
        word_timestamps: List[WordTimestamp],
        full_text: str
    ) -> List[SegmentTimestamp]:
        """
        Group words into segments based on punctuation and pauses.

        Strategy:
        1. Split on sentence-ending punctuation (. ? !)
        2. If no punctuation, group by pauses > 0.5s between words
        3. If still no segments, use the full text as one segment
        """
        if not word_timestamps:
            # No word timestamps - create one segment from full text
            if full_text.strip():
                return [SegmentTimestamp(text=full_text.strip(), start=0.0, end=0.0)]
            return []

        segments = []
        current_words = []
        current_start = word_timestamps[0].start

        # Sentence-ending punctuation
        sentence_enders = {'.', '?', '!'}
        # Pause threshold for grouping (seconds)
        pause_threshold = 0.5

        for i, word_ts in enumerate(word_timestamps):
            current_words.append(word_ts.word)

            # Check for sentence end
            is_sentence_end = any(word_ts.word.rstrip().endswith(p) for p in sentence_enders)

            # Check for pause before next word
            has_long_pause = False
            if i < len(word_timestamps) - 1:
                next_word = word_timestamps[i + 1]
                gap = next_word.start - word_ts.end
                has_long_pause = gap > pause_threshold

            # Create segment if sentence ends or long pause
            if is_sentence_end or has_long_pause or i == len(word_timestamps) - 1:
                segment_text = ' '.join(current_words)
                segments.append(SegmentTimestamp(
                    text=segment_text,
                    start=current_start,
                    end=word_ts.end
                ))
                current_words = []
                if i < len(word_timestamps) - 1:
                    current_start = word_timestamps[i + 1].start

        return segments

    @property
    def has_timestamps(self) -> bool:
        """Check if this result has timestamp data."""
        return bool(self.word_timestamps) or bool(self.segment_timestamps)

    @property
    def word_count(self) -> int:
        """Count words in the transcription."""
        return len(self.text.split()) if self.text.strip() else 0

    @property
    def char_count(self) -> int:
        """Count characters in the transcription."""
        return len(self.text)

    def formatted_with_breaks(self) -> str:
        """
        Return the transcription text with line breaks between segments.

        Uses segment boundaries to create natural paragraph breaks for
        better readability. If no segments are available, returns the
        original text unchanged.
        """
        if not self.segment_timestamps:
            return self.text

        # Join segments with double newline for paragraph separation
        paragraphs = [seg.text.strip() for seg in self.segment_timestamps if seg.text.strip()]
        return "\n\n".join(paragraphs)

    def formatted_duration(self) -> str:
        """Return duration formatted as M:SS or H:MM:SS."""
        return SegmentTimestamp.format_time(self.duration_seconds)

    def __str__(self) -> str:
        return self.text

    def __bool__(self) -> bool:
        """A result is truthy if it has non-empty text."""
        return bool(self.text.strip())
