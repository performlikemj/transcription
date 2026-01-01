"""
Native macOS floating overlay window with waveform visualization.
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
WINDOW_HEIGHT = 80
BUFFER_SAMPLES = 8000  # 0.5 seconds at 16kHz
REFRESH_INTERVAL = 1.0 / 30  # 30 FPS


class WaveformView(NSView):
    """Custom NSView for drawing waveform using Core Graphics"""

    def initWithFrame_(self, frame):
        self = objc.super(WaveformView, self).initWithFrame_(frame)
        if self is None:
            return None

        self._samples = np.zeros(BUFFER_SAMPLES, dtype=np.float32)
        self._sample_buffer = deque(maxlen=BUFFER_SAMPLES)
        self._lock = threading.Lock()
        self._timer = None
        self._is_active = False
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

            # Trigger redraw
            self.setNeedsDisplay_(True)
        except Exception as e:
            print(f"WAVEFORM_VIEW: Error in refresh: {e}")

    def drawRect_(self, rect):
        # Draw background with transparency and rounded corners
        bg_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.1, 0.1, 0.1, 0.85
        )
        bg_color.setFill()

        # Create rounded rect path
        bg_path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            rect, 12, 12
        )
        bg_path.fill()

        # Get samples thread-safely
        with self._lock:
            samples = self._samples.copy()

        if len(samples) == 0:
            return

        # Downsample for drawing - one point per pixel
        draw_points = int(rect.size.width)
        if draw_points <= 0:
            return

        step = max(1, len(samples) // draw_points)
        display_samples = samples[::step][:draw_points]

        if len(display_samples) == 0:
            return

        # Normalize to view height
        height = rect.size.height
        mid_y = height / 2

        # Create waveform path
        path = NSBezierPath.bezierPath()
        path.setLineWidth_(1.5)

        for i, sample in enumerate(display_samples):
            x = float(i)
            # Clamp sample to [-1, 1] and scale to view height
            clamped = max(-1.0, min(1.0, sample))
            y = mid_y + (clamped * mid_y * 0.8)  # 80% of half-height

            if i == 0:
                path.moveToPoint_(NSPoint(x, y))
            else:
                path.lineToPoint_(NSPoint(x, y))

        # Draw waveform in green
        waveform_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.0, 0.8, 0.4, 1.0
        )
        waveform_color.setStroke()
        path.stroke()

        # Draw center line (subtle)
        center_path = NSBezierPath.bezierPath()
        center_path.setLineWidth_(0.5)
        center_path.moveToPoint_(NSPoint(0, mid_y))
        center_path.lineToPoint_(NSPoint(rect.size.width, mid_y))

        center_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.3, 0.3, 0.3, 0.5
        )
        center_color.setStroke()
        center_path.stroke()


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
            y = 100  # 100px from bottom

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
