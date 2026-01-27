"""
Native macOS progress window for first-launch model download.
Uses PyObjC/AppKit for native integration.
"""

import objc
from AppKit import (
    NSWindow, NSView, NSTextField, NSButton, NSProgressIndicator,
    NSWindowStyleMaskTitled, NSBackingStoreBuffered, NSApp,
    NSColor, NSFont, NSScreen, NSBezelStyleRounded,
    NSWindowCollectionBehaviorMoveToActiveSpace,
    NSProgressIndicatorStyleBar, NSAlert, NSAlertStyleWarning,
    NSCenterTextAlignment,
)
from Foundation import NSRect, NSPoint, NSSize, NSObject

WINDOW_WIDTH = 420
WINDOW_HEIGHT = 220


def _format_bytes(b):
    """Format byte count as human-readable string."""
    if b < 1024:
        return f"{b} B"
    elif b < 1024 * 1024:
        return f"{b / 1024:.0f} KB"
    elif b < 1024 * 1024 * 1024:
        return f"{b / (1024 * 1024):.1f} MB"
    else:
        return f"{b / (1024 * 1024 * 1024):.2f} GB"


def _format_eta(seconds):
    """Format seconds remaining as human-readable string."""
    if seconds <= 0:
        return ""
    if seconds < 60:
        return f"{int(seconds)}s remaining"
    elif seconds < 3600:
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}m {s}s remaining"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h {m}m remaining"


class DownloadWindowDelegate(NSObject):
    """Delegate to handle window events and button actions."""

    def initWithCallbacks_(self, callbacks):
        self = objc.super(DownloadWindowDelegate, self).init()
        if self is None:
            return None
        self._on_cancel = callbacks.get("on_cancel")
        self._on_retry = callbacks.get("on_retry")
        return self

    def windowShouldClose_(self, sender):
        # Treat close button same as Cancel
        if self._on_cancel:
            self._on_cancel()
        return False  # We handle closing ourselves

    def cancelClicked_(self, sender):
        if self._on_cancel:
            self._on_cancel()

    def retryClicked_(self, sender):
        if self._on_retry:
            self._on_retry()

    def quitClicked_(self, sender):
        NSApp.terminate_(None)


class DownloadProgressWindow:
    """Native macOS window showing model download progress."""

    def __init__(self, on_cancel=None, on_retry=None):
        self._on_cancel = on_cancel
        self._on_retry = on_retry
        self._window = None
        self._progress_bar = None
        self._status_label = None
        self._percent_label = None
        self._bytes_label = None
        self._speed_label = None
        self._cancel_button = None
        self._retry_button = None
        self._quit_button = None
        self._delegate = None
        self._setup_window()

    def _setup_window(self):
        """Create and configure the download progress window."""
        screen = NSScreen.mainScreen()
        if screen:
            sf = screen.frame()
            x = (sf.size.width - WINDOW_WIDTH) / 2
            y = (sf.size.height - WINDOW_HEIGHT) / 2
        else:
            x, y = 200, 300

        frame = NSRect(NSPoint(x, y), NSSize(WINDOW_WIDTH, WINDOW_HEIGHT))

        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSWindowStyleMaskTitled,
            NSBackingStoreBuffered,
            False,
        )
        self._window.setTitle_("YardTalk — Downloading Model")
        self._window.setCollectionBehavior_(NSWindowCollectionBehaviorMoveToActiveSpace)

        callbacks = {
            "on_cancel": self._handle_cancel,
            "on_retry": self._handle_retry,
        }
        self._delegate = DownloadWindowDelegate.alloc().initWithCallbacks_(callbacks)
        self._window.setDelegate_(self._delegate)

        content = NSView.alloc().initWithFrame_(
            NSRect(NSPoint(0, 0), NSSize(WINDOW_WIDTH, WINDOW_HEIGHT))
        )

        # --- Status label ---
        y_pos = 175
        self._status_label = self._make_label(
            content, "Downloading speech recognition model...",
            NSRect(NSPoint(20, y_pos), NSSize(WINDOW_WIDTH - 40, 22)),
            bold=True, size=13,
        )

        # --- Progress bar ---
        y_pos -= 35
        self._progress_bar = NSProgressIndicator.alloc().initWithFrame_(
            NSRect(NSPoint(20, y_pos), NSSize(WINDOW_WIDTH - 40, 20))
        )
        self._progress_bar.setStyle_(NSProgressIndicatorStyleBar)
        self._progress_bar.setMinValue_(0)
        self._progress_bar.setMaxValue_(100)
        self._progress_bar.setDoubleValue_(0)
        self._progress_bar.setIndeterminate_(False)
        content.addSubview_(self._progress_bar)

        # --- Percent label ---
        y_pos -= 25
        self._percent_label = self._make_label(
            content, "0%",
            NSRect(NSPoint(20, y_pos), NSSize(WINDOW_WIDTH - 40, 18)),
            size=12, alignment=NSCenterTextAlignment,
        )

        # --- Bytes label ---
        y_pos -= 20
        self._bytes_label = self._make_label(
            content, "",
            NSRect(NSPoint(20, y_pos), NSSize(WINDOW_WIDTH - 40, 18)),
            size=11, color=NSColor.secondaryLabelColor(),
            alignment=NSCenterTextAlignment,
        )

        # --- Speed / ETA label ---
        y_pos -= 18
        self._speed_label = self._make_label(
            content, "",
            NSRect(NSPoint(20, y_pos), NSSize(WINDOW_WIDTH - 40, 18)),
            size=11, color=NSColor.secondaryLabelColor(),
            alignment=NSCenterTextAlignment,
        )

        # --- Buttons ---
        btn_y = 15

        # Cancel button (always visible)
        self._cancel_button = NSButton.alloc().initWithFrame_(
            NSRect(NSPoint(WINDOW_WIDTH / 2 - 50, btn_y), NSSize(100, 32))
        )
        self._cancel_button.setTitle_("Cancel")
        self._cancel_button.setBezelStyle_(NSBezelStyleRounded)
        self._cancel_button.setTarget_(self._delegate)
        self._cancel_button.setAction_(
            objc.selector(self._delegate.cancelClicked_, signature=b"v@:@")
        )
        content.addSubview_(self._cancel_button)

        # Retry button (hidden by default, shown on error)
        self._retry_button = NSButton.alloc().initWithFrame_(
            NSRect(NSPoint(WINDOW_WIDTH / 2 - 110, btn_y), NSSize(100, 32))
        )
        self._retry_button.setTitle_("Retry")
        self._retry_button.setBezelStyle_(NSBezelStyleRounded)
        self._retry_button.setTarget_(self._delegate)
        self._retry_button.setAction_(
            objc.selector(self._delegate.retryClicked_, signature=b"v@:@")
        )
        self._retry_button.setHidden_(True)
        content.addSubview_(self._retry_button)

        # Quit button (hidden by default, shown on error)
        self._quit_button = NSButton.alloc().initWithFrame_(
            NSRect(NSPoint(WINDOW_WIDTH / 2 + 10, btn_y), NSSize(100, 32))
        )
        self._quit_button.setTitle_("Quit")
        self._quit_button.setBezelStyle_(NSBezelStyleRounded)
        self._quit_button.setTarget_(self._delegate)
        self._quit_button.setAction_(
            objc.selector(self._delegate.quitClicked_, signature=b"v@:@")
        )
        self._quit_button.setHidden_(True)
        content.addSubview_(self._quit_button)

        self._window.setContentView_(content)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_label(parent, text, frame, bold=False, size=12, color=None,
                    alignment=None):
        label = NSTextField.alloc().initWithFrame_(frame)
        label.setStringValue_(text)
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        if bold:
            label.setFont_(NSFont.boldSystemFontOfSize_(size))
        else:
            label.setFont_(NSFont.systemFontOfSize_(size))
        if color:
            label.setTextColor_(color)
        if alignment is not None:
            label.setAlignment_(alignment)
        parent.addSubview_(label)
        return label

    # ------------------------------------------------------------------
    # public API (call on main thread)
    # ------------------------------------------------------------------

    def show(self):
        self._window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def close(self):
        self._window.orderOut_(None)

    def update_progress(self, downloaded, total, speed_bps):
        """Update all progress indicators."""
        if total > 0:
            pct = downloaded / total * 100
            self._progress_bar.setDoubleValue_(pct)
            self._percent_label.setStringValue_(f"{pct:.1f}%")
            self._bytes_label.setStringValue_(
                f"{_format_bytes(downloaded)} / {_format_bytes(total)}"
            )
            remaining = total - downloaded
            if speed_bps > 0:
                eta_sec = remaining / speed_bps
                speed_str = f"{_format_bytes(int(speed_bps))}/s"
                eta_str = _format_eta(eta_sec)
                self._speed_label.setStringValue_(
                    f"{speed_str}  —  {eta_str}" if eta_str else speed_str
                )
            else:
                self._speed_label.setStringValue_("")
        else:
            # Unknown total — indeterminate
            self._progress_bar.setIndeterminate_(True)
            self._progress_bar.startAnimation_(None)
            self._bytes_label.setStringValue_(f"{_format_bytes(downloaded)}")

    def show_error(self, message):
        """Switch the window to error state."""
        self._status_label.setStringValue_("Download failed")
        self._status_label.setTextColor_(NSColor.systemRedColor())
        self._percent_label.setStringValue_(message)
        self._percent_label.setTextColor_(NSColor.secondaryLabelColor())
        self._bytes_label.setStringValue_("")
        self._speed_label.setStringValue_("")
        self._progress_bar.setDoubleValue_(0)

        # Show Retry + Quit, hide Cancel
        self._cancel_button.setHidden_(True)
        self._retry_button.setHidden_(False)
        self._quit_button.setHidden_(False)

    def reset_for_retry(self):
        """Reset the window to downloading state for a retry."""
        self._status_label.setStringValue_(
            "Downloading speech recognition model..."
        )
        self._status_label.setTextColor_(NSColor.labelColor())
        self._percent_label.setStringValue_("0%")
        self._percent_label.setTextColor_(NSColor.labelColor())
        self._bytes_label.setStringValue_("")
        self._speed_label.setStringValue_("")
        self._progress_bar.setIndeterminate_(False)
        self._progress_bar.setDoubleValue_(0)

        # Show Cancel, hide Retry + Quit
        self._cancel_button.setHidden_(False)
        self._retry_button.setHidden_(True)
        self._quit_button.setHidden_(True)

    # ------------------------------------------------------------------
    # internal handlers
    # ------------------------------------------------------------------

    def _handle_cancel(self):
        """Show confirmation alert, then invoke on_cancel callback."""
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Cancel download?")
        alert.setInformativeText_(
            "YardTalk needs the speech model to work. "
            "The app will quit, but your partial download will be saved "
            "so it can resume next time."
        )
        alert.setAlertStyle_(NSAlertStyleWarning)
        alert.addButtonWithTitle_("Cancel Download")
        alert.addButtonWithTitle_("Continue")
        result = alert.runModal()
        if result == 1000:  # First button ("Cancel Download")
            if self._on_cancel:
                self._on_cancel()

    def _handle_retry(self):
        self.reset_for_retry()
        if self._on_retry:
            self._on_retry()
