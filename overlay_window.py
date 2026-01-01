"""
Native macOS floating overlay window with bar-style waveform visualization.
Uses PyObjC/AppKit for thread-safe integration with rumps.
"""

import objc
from AppKit import (
    NSWindow, NSView, NSColor, NSBezierPath,
    NSWindowStyleMaskBorderless, NSBackingStoreBuffered,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSFloatingWindowLevel, NSScreen
)
from Foundation import NSRect, NSPoint, NSSize, NSTimer, NSRunLoop, NSDefaultRunLoopMode
import numpy as np
from collections import deque
import threading

# Constants
WINDOW_WIDTH = 400
WINDOW_HEIGHT = 70
BUFFER_SAMPLES = 8000  # 0.5 seconds at 16kHz
REFRESH_INTERVAL = 1.0 / 30  # 30 FPS
NUM_BARS = 60  # Number of vertical bars


class WaveformView(NSView):
    """Custom NSView for drawing bar-style waveform"""

    def initWithFrame_(self, frame):
        self = objc.super(WaveformView, self).initWithFrame_(frame)
        if self is None:
            return None

        self._samples = np.zeros(BUFFER_SAMPLES, dtype=np.float32)
        self._sample_buffer = deque(maxlen=BUFFER_SAMPLES)
        self._lock = threading.Lock()
        self._timer = None
        self._is_active = False
        self._bar_heights = np.zeros(NUM_BARS, dtype=np.float32)
        return self

    def isOpaque(self):
        return False

    def startUpdating(self):
        """Start the refresh timer"""
        if self._is_active:
            return

        self._is_active = True
        self._sample_buffer.clear()
        self._samples = np.zeros(BUFFER_SAMPLES, dtype=np.float32)
        self._bar_heights = np.zeros(NUM_BARS, dtype=np.float32)

        # Create timer and add to run loop
        self._timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            REFRESH_INTERVAL,
            self,
            objc.selector(self.refresh_, signature=b'v@:@'),
            None,
            True
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(self._timer, NSDefaultRunLoopMode)

    def stopUpdating(self):
        """Stop the refresh timer"""
        if not self._is_active:
            return

        self._is_active = False

        if self._timer:
            self._timer.invalidate()
            self._timer = None

        self._sample_buffer.clear()

    def addChunk_(self, chunk_float):
        """Add audio samples to buffer (thread-safe)"""
        if not self._is_active:
            return

        with self._lock:
            self._sample_buffer.extend(chunk_float)

    def refresh_(self, timer):
        """Timer callback to update display"""
        if not self._is_active:
            return

        try:
            with self._lock:
                buffer_len = len(self._sample_buffer)
                if buffer_len > 0:
                    samples = np.array(list(self._sample_buffer), dtype=np.float32)
                    self._samples = samples.copy()

                    # Calculate bar heights from samples
                    samples_per_bar = max(1, len(samples) // NUM_BARS)
                    new_heights = np.zeros(NUM_BARS, dtype=np.float32)

                    for i in range(NUM_BARS):
                        start = i * samples_per_bar
                        end = min(start + samples_per_bar, len(samples))
                        if start < len(samples):
                            # Use RMS for smoother visualization
                            chunk = samples[start:end]
                            new_heights[i] = np.sqrt(np.mean(chunk ** 2)) * 3.0  # Amplify

                    # Smooth transition (lerp toward new values)
                    self._bar_heights = self._bar_heights * 0.3 + new_heights * 0.7

            # Trigger redraw
            self.setNeedsDisplay_(True)
        except Exception as e:
            print(f"WAVEFORM_VIEW: Error in refresh: {e}")

    def drawRect_(self, rect):
        # Draw dark background with rounded corners
        bg_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.12, 0.12, 0.12, 0.92
        )
        bg_color.setFill()

        bg_path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            rect, 14, 14
        )
        bg_path.fill()

        # Draw waveform bars
        with self._lock:
            heights = self._bar_heights.copy()

        padding = 20  # Horizontal padding
        bar_area_width = rect.size.width - (padding * 2)
        bar_width = bar_area_width / NUM_BARS
        gap = 2  # Gap between bars
        actual_bar_width = max(1, bar_width - gap)
        center_y = rect.size.height / 2
        max_bar_height = (rect.size.height / 2) * 0.8  # 80% of half height

        # Bar color - light gray/white
        bar_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.75, 0.75, 0.75, 0.9
        )
        bar_color.setFill()

        for i, height in enumerate(heights):
            x = padding + i * bar_width + gap / 2

            # Clamp height
            bar_h = min(height, 1.0) * max_bar_height

            # Minimum bar height for visual feedback (dotted line effect when quiet)
            min_height = 1.5
            bar_h = max(min_height, bar_h)

            # Draw mirrored bar (up and down from center)
            bar_rect = NSRect(
                NSPoint(x, center_y - bar_h),
                NSSize(actual_bar_width, bar_h * 2)
            )

            # Rounded bars
            bar_path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                bar_rect, actual_bar_width / 2, actual_bar_width / 2
            )
            bar_path.fill()


class OverlayWindow:
    """Manages the floating overlay window for waveform display"""

    def __init__(self):
        self._window = None
        self._waveform_view = None
        self._is_visible = False
        self._setup_window()

    def _setup_window(self):
        """Create and configure the overlay window"""
        # Calculate position (bottom center of main screen)
        screen = NSScreen.mainScreen()
        if screen is None:
            x, y = 100, 100
        else:
            screen_frame = screen.frame()
            x = (screen_frame.size.width - WINDOW_WIDTH) / 2
            y = 80  # 80px from bottom

        frame = NSRect(
            NSPoint(x, y),
            NSSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        )

        # Create borderless, transparent window
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered,
            False
        )

        # Configure window properties
        self._window.setLevel_(NSFloatingWindowLevel)
        self._window.setOpaque_(False)
        self._window.setBackgroundColor_(NSColor.clearColor())
        self._window.setIgnoresMouseEvents_(True)  # Click-through
        self._window.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces |
            NSWindowCollectionBehaviorStationary
        )
        self._window.setHasShadow_(True)

        # Create and add waveform view
        view_frame = NSRect(NSPoint(0, 0), NSSize(WINDOW_WIDTH, WINDOW_HEIGHT))
        self._waveform_view = WaveformView.alloc().initWithFrame_(view_frame)
        self._window.setContentView_(self._waveform_view)

    def show(self):
        """Show window and start refresh timer (call on main thread)"""
        if self._is_visible:
            return

        self._is_visible = True
        self._window.orderFront_(None)

        if self._waveform_view:
            self._waveform_view.startUpdating()

    def hide(self):
        """Hide window and stop timer (call on main thread)"""
        if not self._is_visible:
            return

        self._is_visible = False

        if self._waveform_view:
            self._waveform_view.stopUpdating()

        self._window.orderOut_(None)

    def add_chunk(self, chunk_int16):
        """Add audio chunk (thread-safe, can be called from any thread)"""
        if not self._is_visible or not self._waveform_view:
            return

        try:
            # Normalize int16 to float32 [-1, 1]
            chunk_array = np.array(chunk_int16, dtype=np.float32).flatten()
            chunk_float = chunk_array / 32768.0
            self._waveform_view.addChunk_(chunk_float)
        except Exception as e:
            print(f"OVERLAY_WINDOW: Error adding chunk: {e}")
