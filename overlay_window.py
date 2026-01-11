"""
Native macOS floating overlay window with bar-style waveform visualization.
Uses PyObjC/AppKit for thread-safe integration with rumps.
"""

import objc
from AppKit import (
    NSWindow, NSView, NSColor, NSBezierPath, NSFont,
    NSWindowStyleMaskBorderless, NSBackingStoreBuffered,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary,
    NSFloatingWindowLevel, NSScreen,
    NSFontAttributeName, NSForegroundColorAttributeName,
    NSParagraphStyleAttributeName, NSMutableParagraphStyle,
    NSCenterTextAlignment
)
from Foundation import NSRect, NSPoint, NSSize, NSTimer, NSRunLoop, NSDefaultRunLoopMode, NSString
import numpy as np
from collections import deque
import threading

# Constants
WINDOW_WIDTH = 400
WAVEFORM_HEIGHT = 70
PREVIEW_TEXT_HEIGHT = 35
WINDOW_HEIGHT = WAVEFORM_HEIGHT + PREVIEW_TEXT_HEIGHT  # Total height when live preview is shown
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
        print(f"WAVEFORM_VIEW: startUpdating called, _is_active={self._is_active}")
        if self._is_active:
            print("WAVEFORM_VIEW: Already active, returning")
            return

        self._is_active = True
        self._sample_buffer.clear()
        self._samples = np.zeros(BUFFER_SAMPLES, dtype=np.float32)
        self._bar_heights = np.zeros(NUM_BARS, dtype=np.float32)

        # Create timer and add to MAIN run loop (not currentRunLoop which may differ)
        print("WAVEFORM_VIEW: Creating timer...")
        self._timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            REFRESH_INTERVAL,
            self,
            objc.selector(self.refresh_, signature=b'v@:@'),
            None,
            True
        )
        # Use mainRunLoop to ensure timer fires on the main thread
        NSRunLoop.mainRunLoop().addTimer_forMode_(self._timer, NSDefaultRunLoopMode)
        print("WAVEFORM_VIEW: Timer added to MAIN run loop")

    def stopUpdating(self):
        """Stop the refresh timer"""
        if not self._is_active:
            return

        self._is_active = False

        if self._timer:
            self._timer.invalidate()
            self._timer = None

        self._sample_buffer.clear()

    _chunk_count = 0

    def addChunk_(self, chunk_float):
        """Add audio samples to buffer (thread-safe)"""
        if not self._is_active:
            return

        self._chunk_count = getattr(self, '_chunk_count', 0) + 1
        if self._chunk_count % 50 == 1:  # Log every 50 chunks
            print(f"WAVEFORM_VIEW: addChunk_ #{self._chunk_count}, len={len(chunk_float)}")

        with self._lock:
            self._sample_buffer.extend(chunk_float)

    _refresh_count = 0

    def refresh_(self, timer):
        """Timer callback to update display"""
        self._refresh_count = getattr(self, '_refresh_count', 0) + 1
        if self._refresh_count % 30 == 1:  # Log every ~1 second at 30fps
            print(f"WAVEFORM_VIEW: refresh_ #{self._refresh_count}, active={self._is_active}")

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
                            new_heights[i] = np.sqrt(np.mean(chunk ** 2)) * 15.0  # Amplify (increased from 3.0)

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
            min_height = 0.5  # Reduced from 1.5 to allow audio levels to show through
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


class LiveTextView(NSView):
    """Custom NSView for displaying live transcription preview text."""

    def initWithFrame_(self, frame):
        self = objc.super(LiveTextView, self).initWithFrame_(frame)
        if self is None:
            return None

        self._text = ""
        self._lock = threading.Lock()
        return self

    def isOpaque(self):
        return False

    def setText_(self, text):
        """Set the preview text (thread-safe)."""
        with self._lock:
            self._text = text
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        """Draw the text with a semi-transparent background."""
        with self._lock:
            text = self._text

        # Draw semi-transparent background
        bg_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.12, 0.12, 0.12, 0.92
        )
        bg_color.setFill()

        bg_path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            rect, 10, 10
        )
        bg_path.fill()

        if not text:
            return

        # Draw text centered
        text_font = NSFont.systemFontOfSize_(13)
        text_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.85, 0.85, 0.85, 1.0
        )

        # Set up paragraph style for centering
        para_style = NSMutableParagraphStyle.alloc().init()
        para_style.setAlignment_(NSCenterTextAlignment)

        text_attrs = {
            NSFontAttributeName: text_font,
            NSForegroundColorAttributeName: text_color,
            NSParagraphStyleAttributeName: para_style,
        }

        ns_string = NSString.stringWithString_(text)
        text_size = ns_string.sizeWithAttributes_(text_attrs)

        # Center vertically, use padding horizontally
        text_y = (rect.size.height - text_size.height) / 2
        text_rect = NSRect(
            NSPoint(10, text_y),
            NSSize(rect.size.width - 20, text_size.height)
        )

        ns_string.drawInRect_withAttributes_(text_rect, text_attrs)


class OverlayWindow:
    """Manages the floating overlay window for waveform display"""

    def __init__(self):
        self._window = None
        self._waveform_view = None
        self._live_text_view = None
        self._container_view = None
        self._is_visible = False
        self._live_preview_enabled = False
        self._setup_window()

    def _setup_window(self):
        """Create and configure the overlay window"""
        # Start with just waveform height (live preview adds more when enabled)
        # Position will be set with center() after window creation
        frame = NSRect(
            NSPoint(0, 0),
            NSSize(WINDOW_WIDTH, WAVEFORM_HEIGHT)
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

        # Create container view
        container_frame = NSRect(NSPoint(0, 0), NSSize(WINDOW_WIDTH, WINDOW_HEIGHT))
        self._container_view = NSView.alloc().initWithFrame_(container_frame)
        self._container_view.setWantsLayer_(True)

        # Create waveform view at top of container
        waveform_frame = NSRect(
            NSPoint(0, PREVIEW_TEXT_HEIGHT),
            NSSize(WINDOW_WIDTH, WAVEFORM_HEIGHT)
        )
        self._waveform_view = WaveformView.alloc().initWithFrame_(waveform_frame)
        self._container_view.addSubview_(self._waveform_view)

        # Create live text view at bottom (hidden by default)
        text_frame = NSRect(
            NSPoint(0, 0),
            NSSize(WINDOW_WIDTH, PREVIEW_TEXT_HEIGHT)
        )
        self._live_text_view = LiveTextView.alloc().initWithFrame_(text_frame)
        self._live_text_view.setHidden_(True)
        self._container_view.addSubview_(self._live_text_view)

        self._window.setContentView_(self._container_view)

        # Manually center the window (center() is broken on macOS 26)
        screen = NSScreen.mainScreen()
        if screen:
            vf = screen.visibleFrame()
            # Calculate center position within visible frame
            x = vf.origin.x + (vf.size.width - WINDOW_WIDTH) / 2
            y = vf.origin.y + (vf.size.height - WAVEFORM_HEIGHT) / 2

            print(f"OVERLAY DEBUG: Visible frame: origin=({vf.origin.x}, {vf.origin.y}), size=({vf.size.width}, {vf.size.height})")
            print(f"OVERLAY DEBUG: Calculated center: ({x}, {y})")

            # Set the window position
            self._window.setFrameOrigin_(NSPoint(x, y))

            frame = self._window.frame()
            print(f"OVERLAY DEBUG: Window frame after setFrameOrigin: origin=({frame.origin.x}, {frame.origin.y})")

    def show(self):
        """Show window and start refresh timer (call on main thread)"""
        # Debug: check window position at show time
        frame = self._window.frame()
        print(f"OVERLAY: show() called, was_visible={self._is_visible}, window_pos=({frame.origin.x}, {frame.origin.y})")
        if self._is_visible:
            print("OVERLAY: Already visible, returning early")
            return

        self._is_visible = True
        self._window.orderFront_(None)
        print(f"OVERLAY: Window ordered front, _is_visible={self._is_visible}")

        if self._waveform_view:
            print("OVERLAY: Starting waveform view updating...")
            self._waveform_view.startUpdating()
            print(f"OVERLAY: Waveform view startUpdating done, _is_active={self._waveform_view._is_active}")
        else:
            print("OVERLAY: WARNING - No waveform view to start!")

    def hide(self):
        """Hide window and stop timer (call on main thread)"""
        print(f"OVERLAY: hide() called, was_visible={self._is_visible}")
        if not self._is_visible:
            print("OVERLAY: Already hidden, returning early")
            return

        self._is_visible = False
        print(f"OVERLAY: Set _is_visible=False")

        if self._waveform_view:
            print("OVERLAY: Stopping waveform view updating...")
            self._waveform_view.stopUpdating()

        self._window.orderOut_(None)
        print("OVERLAY: Window ordered out")

    _add_chunk_log_count = 0

    def add_chunk(self, chunk_int16):
        """Add audio chunk (thread-safe, can be called from any thread)"""
        self._add_chunk_log_count = getattr(self, '_add_chunk_log_count', 0) + 1
        if self._add_chunk_log_count % 100 == 1:
            print(f"OVERLAY: add_chunk #{self._add_chunk_log_count}, visible={self._is_visible}, view={self._waveform_view is not None}")

        if not self._is_visible or not self._waveform_view:
            if self._add_chunk_log_count % 100 == 1:
                print(f"OVERLAY: Skipping chunk - visible={self._is_visible}")
            return

        try:
            # Normalize int16 to float32 [-1, 1]
            chunk_array = np.array(chunk_int16, dtype=np.float32).flatten()
            chunk_float = chunk_array / 32768.0
            self._waveform_view.addChunk_(chunk_float)
        except Exception as e:
            print(f"OVERLAY_WINDOW: Error adding chunk: {e}")

    def set_live_preview_enabled(self, enabled: bool):
        """Enable or disable live preview mode (call on main thread)."""
        if self._live_preview_enabled == enabled:
            return

        print(f"OVERLAY: set_live_preview_enabled({enabled})")
        self._live_preview_enabled = enabled

        if self._live_text_view:
            self._live_text_view.setHidden_(not enabled)
            # Clear text when disabling
            if not enabled:
                self._live_text_view.setText_("")

        # Resize window to show/hide text area
        current_frame = self._window.frame()
        if enabled:
            new_height = WINDOW_HEIGHT
            # Move waveform up to make room for text
            waveform_frame = NSRect(
                NSPoint(0, PREVIEW_TEXT_HEIGHT),
                NSSize(WINDOW_WIDTH, WAVEFORM_HEIGHT)
            )
        else:
            new_height = WAVEFORM_HEIGHT
            # Move waveform to bottom when no text
            waveform_frame = NSRect(
                NSPoint(0, 0),
                NSSize(WINDOW_WIDTH, WAVEFORM_HEIGHT)
            )

        if self._waveform_view:
            self._waveform_view.setFrame_(waveform_frame)

        new_frame = NSRect(
            current_frame.origin,
            NSSize(WINDOW_WIDTH, new_height)
        )
        self._window.setFrame_display_(new_frame, True)

    def set_preview_text(self, text: str):
        """Set the live preview text (can be called from any thread)."""
        if self._live_text_view and self._live_preview_enabled:
            # Truncate long text
            if len(text) > 100:
                text = text[:97] + "..."
            self._live_text_view.setText_(text)

    @property
    def live_preview_enabled(self):
        """Return whether live preview is currently enabled."""
        return self._live_preview_enabled
