"""
Correction window for reviewing/editing transcriptions before insertion.
Enhanced UI for long-form dictation with better editing experience.
Uses PyObjC/AppKit for native macOS integration.
"""

import objc
import time
import logging
from typing import Union

# Use the same logging as main.py
logger = logging.getLogger('CorrectionWindow')

def log_print(*args):
    """Log to the shared log file"""
    message = ' '.join(str(arg) for arg in args)
    logger.info(message)

# Use log_print for all prints in this module
print = log_print
from AppKit import (
    NSWindow, NSView, NSTextField, NSButton, NSTextView, NSScrollView,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable, NSWindowStyleMaskResizable,
    NSWindowStyleMaskMiniaturizable,
    NSBackingStoreBuffered, NSApp, NSColor, NSFont, NSScreen,
    NSBezelStyleRounded, NSFloatingWindowLevel, NSEvent,
    NSWindowCollectionBehaviorMoveToActiveSpace,
    NSLineBorder, NSWorkspace, NSPasteboard, NSPasteboardTypeString,
    NSFontAttributeName, NSForegroundColorAttributeName,
    NSMutableParagraphStyle, NSParagraphStyleAttributeName,
    NSLeftTextAlignment, NSTextAlignmentLeft,
    NSSegmentedControl, NSSegmentStyleTexturedSquare,
    NSSegmentSwitchTrackingSelectOne,
)
from Foundation import NSRect, NSPoint, NSSize, NSObject, NSMakeRange, NSNotificationCenter

from transcription_result import TranscriptionResult

# Window dimensions - larger for long-form editing
WINDOW_WIDTH = 650
WINDOW_HEIGHT = 420
MIN_WINDOW_WIDTH = 450
MIN_WINDOW_HEIGHT = 300

# Layout constants
PADDING = 20
TOOLBAR_HEIGHT = 56
MODE_BAR_HEIGHT = 32
STATUS_BAR_HEIGHT = 28
BUTTON_HEIGHT = 32
BUTTON_WIDTH = 100

# View modes
MODE_EDIT = 0
MODE_TIMESTAMPS = 1


class CorrectionTextView(NSTextView):
    """Custom NSTextView that handles Enter and Escape keys."""

    def initWithFrame_(self, frame):
        self = objc.super(CorrectionTextView, self).initWithFrame_(frame)
        if self is None:
            return None

        self._on_send = None
        self._on_cancel = None
        self._on_text_change = None

        # Configure for plain text editing with improved typography
        self.setRichText_(False)
        self.setFont_(NSFont.monospacedSystemFontOfSize_weight_(14, 0.0))
        self.setTextColor_(NSColor.labelColor())

        # Better text container settings
        self.textContainer().setLineFragmentPadding_(8)

        # Set line spacing via paragraph style
        para_style = NSMutableParagraphStyle.alloc().init()
        para_style.setLineSpacing_(4)
        para_style.setAlignment_(NSTextAlignmentLeft)
        self.setDefaultParagraphStyle_(para_style)

        return self

    @objc.python_method
    def set_callbacks(self, on_send, on_cancel, on_text_change=None):
        """Set callbacks for send (Enter) and cancel (Escape)."""
        self._on_send = on_send
        self._on_cancel = on_cancel
        self._on_text_change = on_text_change

    def didChangeText(self):
        """Called when text content changes."""
        objc.super(CorrectionTextView, self).didChangeText()
        if self._on_text_change:
            self._on_text_change()

    def keyDown_(self, event):
        """Handle Enter and Escape key events."""
        key_code = event.keyCode()
        modifiers = event.modifierFlags()

        # Escape key (keyCode 53) - cancel
        if key_code == 53:
            if self._on_cancel:
                self._on_cancel()
            return

        # Return/Enter key (keyCode 36)
        # Cmd+Enter or plain Enter sends, Shift+Enter inserts newline
        if key_code == 36:
            shift_pressed = modifiers & (1 << 17)  # NSEventModifierFlagShift
            cmd_pressed = modifiers & (1 << 20)  # NSEventModifierFlagCommand

            if cmd_pressed or not shift_pressed:
                if self._on_send:
                    self._on_send()
                return

        # Pass other keys to parent
        objc.super(CorrectionTextView, self).keyDown_(event)


class CorrectionWindowDelegate(NSObject):
    """Delegate for window events and button actions."""

    def initWithCallbacks_(self, callbacks):
        self = objc.super(CorrectionWindowDelegate, self).init()
        if self is None:
            return None
        self._on_send = callbacks.get('on_send')
        self._on_cancel = callbacks.get('on_cancel')
        self._on_close = callbacks.get('on_close')
        self._on_copy = callbacks.get('on_copy')
        self._on_clear = callbacks.get('on_clear')
        self._on_resize = callbacks.get('on_resize')
        self._on_mode_change = callbacks.get('on_mode_change')
        return self

    def windowWillClose_(self, notification):
        if self._on_close:
            self._on_close()

    def windowDidResize_(self, notification):
        if self._on_resize:
            self._on_resize()

    def sendClicked_(self, sender):
        if self._on_send:
            self._on_send()

    def cancelClicked_(self, sender):
        if self._on_cancel:
            self._on_cancel()

    def copyClicked_(self, sender):
        if self._on_copy:
            self._on_copy()

    def clearClicked_(self, sender):
        if self._on_clear:
            self._on_clear()

    def modeChanged_(self, sender):
        if self._on_mode_change:
            self._on_mode_change(sender.selectedSegment())


class CorrectionWindow:
    """Manages the correction window for reviewing transcriptions."""

    def __init__(self, on_send, on_cancel):
        """
        Initialize the correction window.

        Args:
            on_send: Callback(original_text, corrected_text) when user confirms.
            on_cancel: Callback() when user cancels.
        """
        self._window = None
        self._text_view = None
        self._scroll_view = None
        self._delegate = None
        self._status_label = None
        self._instruction_label = None
        self._target_app_label = None
        self._duration_label = None
        self._mode_toggle = None
        self._timestamp_scroll_view = None
        self._timestamp_text_view = None
        self._on_send_callback = on_send
        self._on_cancel_callback = on_cancel
        self._original_text = ""
        self._transcription_result = None  # Full TranscriptionResult with timestamps
        self._current_mode = MODE_EDIT
        self._is_visible = False
        self._previous_app = None  # Store the app that had focus before showing window
        self._setup_window()
        print("CORRECTION: Window initialized")

    def _setup_window(self):
        """Create and configure the correction window."""
        # Position at center of screen initially (will be repositioned on show)
        screen = NSScreen.mainScreen()
        if screen:
            screen_frame = screen.frame()
            x = (screen_frame.size.width - WINDOW_WIDTH) / 2
            y = (screen_frame.size.height - WINDOW_HEIGHT) / 2
        else:
            x, y = 200, 200

        frame = NSRect(
            NSPoint(x, y),
            NSSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        )

        # Create titled, closable, resizable window
        style_mask = (
            NSWindowStyleMaskTitled |
            NSWindowStyleMaskClosable |
            NSWindowStyleMaskResizable |
            NSWindowStyleMaskMiniaturizable
        )
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            style_mask,
            NSBackingStoreBuffered,
            False
        )

        self._window.setTitle_("Review Transcription")
        self._window.setLevel_(NSFloatingWindowLevel)
        self._window.setCollectionBehavior_(NSWindowCollectionBehaviorMoveToActiveSpace)
        self._window.setMinSize_(NSSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT))

        # Set up delegate
        callbacks = {
            'on_send': self._do_send,
            'on_cancel': self._do_cancel,
            'on_close': self._on_window_close,
            'on_copy': self._do_copy,
            'on_clear': self._do_clear,
            'on_resize': self._update_layout,
            'on_mode_change': self._on_mode_change,
        }
        self._delegate = CorrectionWindowDelegate.alloc().initWithCallbacks_(callbacks)
        self._window.setDelegate_(self._delegate)

        self._create_content()

    def _create_content(self):
        """Create the window content views."""
        content_frame = self._window.contentView().frame()
        content_view = NSView.alloc().initWithFrame_(content_frame)
        content_view.setWantsLayer_(True)

        # We'll set a subtle background
        content_view.layer().setBackgroundColor_(
            NSColor.windowBackgroundColor().CGColor()
        )

        self._window.setContentView_(content_view)
        self._layout_views()

    def _layout_views(self):
        """Layout all subviews based on current window size."""
        content_view = self._window.contentView()
        content_frame = content_view.frame()
        width = content_frame.size.width
        height = content_frame.size.height

        # Clear existing subviews
        for subview in list(content_view.subviews()):
            subview.removeFromSuperview()

        # Calculate layout (bottom to top in macOS coordinates)
        button_y = PADDING
        status_y = button_y + BUTTON_HEIGHT + 12
        text_bottom = status_y + STATUS_BAR_HEIGHT + 8
        toolbar_y = height - TOOLBAR_HEIGHT - 8
        mode_bar_y = toolbar_y - MODE_BAR_HEIGHT - 4
        text_top = mode_bar_y - 8
        text_height = text_top - text_bottom

        # === Toolbar at top ===
        self._create_toolbar(content_view, PADDING, toolbar_y, width - 2 * PADDING)

        # === Mode bar (Edit/Timestamps toggle) ===
        self._create_mode_bar(content_view, PADDING, mode_bar_y, width - 2 * PADDING)

        # === Text area (main editing area) ===
        scroll_frame = NSRect(
            NSPoint(PADDING, text_bottom),
            NSSize(width - 2 * PADDING, text_height)
        )
        self._scroll_view = NSScrollView.alloc().initWithFrame_(scroll_frame)
        self._scroll_view.setBorderType_(NSLineBorder)
        self._scroll_view.setHasVerticalScroller_(True)
        self._scroll_view.setHasHorizontalScroller_(False)
        self._scroll_view.setAutohidesScrollers_(True)

        # Round the corners of the scroll view
        self._scroll_view.setWantsLayer_(True)
        self._scroll_view.layer().setCornerRadius_(8)
        self._scroll_view.layer().setMasksToBounds_(True)

        # Create text view inside scroll view
        text_frame = NSRect(
            NSPoint(0, 0),
            NSSize(scroll_frame.size.width - 20, scroll_frame.size.height)
        )
        self._text_view = CorrectionTextView.alloc().initWithFrame_(text_frame)
        self._text_view.set_callbacks(self._do_send, self._do_cancel, self._update_status)
        self._text_view.setMinSize_(NSSize(0, scroll_frame.size.height))
        self._text_view.setMaxSize_(NSSize(10000, 10000))
        self._text_view.setVerticallyResizable_(True)
        self._text_view.setHorizontallyResizable_(False)
        self._text_view.textContainer().setWidthTracksTextView_(True)

        self._scroll_view.setDocumentView_(self._text_view)
        content_view.addSubview_(self._scroll_view)

        # === Timestamp view (read-only, same frame as text area) ===
        self._timestamp_scroll_view = NSScrollView.alloc().initWithFrame_(scroll_frame)
        self._timestamp_scroll_view.setBorderType_(NSLineBorder)
        self._timestamp_scroll_view.setHasVerticalScroller_(True)
        self._timestamp_scroll_view.setHasHorizontalScroller_(False)
        self._timestamp_scroll_view.setAutohidesScrollers_(True)
        self._timestamp_scroll_view.setWantsLayer_(True)
        self._timestamp_scroll_view.layer().setCornerRadius_(8)
        self._timestamp_scroll_view.layer().setMasksToBounds_(True)
        self._timestamp_scroll_view.setHidden_(True)  # Hidden by default

        # Create read-only text view for timestamps
        self._timestamp_text_view = NSTextView.alloc().initWithFrame_(text_frame)
        self._timestamp_text_view.setEditable_(False)
        self._timestamp_text_view.setSelectable_(True)
        self._timestamp_text_view.setFont_(NSFont.monospacedSystemFontOfSize_weight_(13, 0.0))
        self._timestamp_text_view.setTextColor_(NSColor.labelColor())
        self._timestamp_text_view.setMinSize_(NSSize(0, scroll_frame.size.height))
        self._timestamp_text_view.setMaxSize_(NSSize(10000, 10000))
        self._timestamp_text_view.setVerticallyResizable_(True)
        self._timestamp_text_view.setHorizontallyResizable_(False)
        self._timestamp_text_view.textContainer().setWidthTracksTextView_(True)
        self._timestamp_text_view.textContainer().setLineFragmentPadding_(8)

        # Set line spacing
        para_style = NSMutableParagraphStyle.alloc().init()
        para_style.setLineSpacing_(6)
        para_style.setAlignment_(NSTextAlignmentLeft)
        self._timestamp_text_view.setDefaultParagraphStyle_(para_style)

        self._timestamp_scroll_view.setDocumentView_(self._timestamp_text_view)
        content_view.addSubview_(self._timestamp_scroll_view)

        # === Status bar ===
        status_frame = NSRect(NSPoint(PADDING, status_y), NSSize(width - 2 * PADDING, STATUS_BAR_HEIGHT))
        self._status_label = NSTextField.alloc().initWithFrame_(status_frame)
        self._status_label.setStringValue_("0 characters | 0 words")
        self._status_label.setBezeled_(False)
        self._status_label.setDrawsBackground_(False)
        self._status_label.setEditable_(False)
        self._status_label.setSelectable_(False)
        self._status_label.setTextColor_(NSColor.secondaryLabelColor())
        self._status_label.setFont_(NSFont.monospacedSystemFontOfSize_weight_(11, 0.0))
        content_view.addSubview_(self._status_label)

        # === Bottom buttons ===
        self._create_bottom_buttons(content_view, PADDING, button_y, width)

    def _create_toolbar(self, parent_view, x, y, width):
        """Create the toolbar with duration, instruction and action buttons."""
        toolbar_view = NSView.alloc().initWithFrame_(
            NSRect(NSPoint(x, y), NSSize(width, TOOLBAR_HEIGHT))
        )

        # Duration label on the far left (pill-style)
        duration_frame = NSRect(NSPoint(0, 22), NSSize(90, 24))
        self._duration_label = NSTextField.alloc().initWithFrame_(duration_frame)
        self._duration_label.setStringValue_("Duration: --")
        self._duration_label.setBezeled_(False)
        self._duration_label.setDrawsBackground_(True)
        self._duration_label.setBackgroundColor_(NSColor.tertiarySystemFillColor())
        self._duration_label.setEditable_(False)
        self._duration_label.setSelectable_(False)
        self._duration_label.setTextColor_(NSColor.secondaryLabelColor())
        self._duration_label.setFont_(NSFont.monospacedSystemFontOfSize_weight_(11, 0.3))
        self._duration_label.setAlignment_(NSTextAlignmentLeft)
        self._duration_label.setWantsLayer_(True)
        self._duration_label.layer().setCornerRadius_(4)
        toolbar_view.addSubview_(self._duration_label)

        # Instruction label (after duration)
        instruction_frame = NSRect(NSPoint(100, 24), NSSize(width - 310, 20))
        self._instruction_label = NSTextField.alloc().initWithFrame_(instruction_frame)
        self._instruction_label.setStringValue_("Edit your transcription. Press Enter to insert, Escape to cancel.")
        self._instruction_label.setBezeled_(False)
        self._instruction_label.setDrawsBackground_(False)
        self._instruction_label.setEditable_(False)
        self._instruction_label.setSelectable_(False)
        self._instruction_label.setTextColor_(NSColor.secondaryLabelColor())
        self._instruction_label.setFont_(NSFont.systemFontOfSize_(12))
        toolbar_view.addSubview_(self._instruction_label)

        # Target app indicator (below instruction)
        target_app_frame = NSRect(NSPoint(100, 6), NSSize(width - 310, 16))
        self._target_app_label = NSTextField.alloc().initWithFrame_(target_app_frame)
        self._target_app_label.setStringValue_("")
        self._target_app_label.setBezeled_(False)
        self._target_app_label.setDrawsBackground_(False)
        self._target_app_label.setEditable_(False)
        self._target_app_label.setSelectable_(False)
        # Use secondaryLabelColor for better visibility (tertiaryLabelColor was too subtle)
        self._target_app_label.setTextColor_(NSColor.secondaryLabelColor())
        self._target_app_label.setFont_(NSFont.systemFontOfSize_(11))
        toolbar_view.addSubview_(self._target_app_label)
        print(f"CORRECTION: Created _target_app_label with frame: {target_app_frame}")

        # Copy button on the right
        copy_frame = NSRect(NSPoint(width - 160, 6), NSSize(70, 28))
        copy_button = NSButton.alloc().initWithFrame_(copy_frame)
        copy_button.setTitle_("Copy")
        copy_button.setBezelStyle_(NSBezelStyleRounded)
        copy_button.setTarget_(self._delegate)
        copy_button.setAction_(objc.selector(self._delegate.copyClicked_, signature=b'v@:@'))
        toolbar_view.addSubview_(copy_button)

        # Clear button
        clear_frame = NSRect(NSPoint(width - 80, 6), NSSize(70, 28))
        clear_button = NSButton.alloc().initWithFrame_(clear_frame)
        clear_button.setTitle_("Clear")
        clear_button.setBezelStyle_(NSBezelStyleRounded)
        clear_button.setTarget_(self._delegate)
        clear_button.setAction_(objc.selector(self._delegate.clearClicked_, signature=b'v@:@'))
        toolbar_view.addSubview_(clear_button)

        parent_view.addSubview_(toolbar_view)

    def _create_mode_bar(self, parent_view, x, y, width):
        """Create the mode bar with Edit/Timestamps toggle."""
        mode_bar_view = NSView.alloc().initWithFrame_(
            NSRect(NSPoint(x, y), NSSize(width, MODE_BAR_HEIGHT))
        )

        # Segmented control for Edit/Timestamps modes
        toggle_frame = NSRect(NSPoint(0, 4), NSSize(180, 24))
        self._mode_toggle = NSSegmentedControl.alloc().initWithFrame_(toggle_frame)
        self._mode_toggle.setSegmentCount_(2)
        self._mode_toggle.setLabel_forSegment_("Edit Mode", 0)
        self._mode_toggle.setLabel_forSegment_("Timestamps", 1)
        self._mode_toggle.setWidth_forSegment_(85, 0)
        self._mode_toggle.setWidth_forSegment_(85, 1)
        self._mode_toggle.setSelectedSegment_(self._current_mode)
        self._mode_toggle.setTarget_(self._delegate)
        self._mode_toggle.setAction_(objc.selector(self._delegate.modeChanged_, signature=b'v@:@'))
        mode_bar_view.addSubview_(self._mode_toggle)

        parent_view.addSubview_(mode_bar_view)

    def _on_mode_change(self, new_mode: int):
        """Handle mode toggle between Edit and Timestamps views."""
        if new_mode == self._current_mode:
            return

        self._current_mode = new_mode
        print(f"CORRECTION: Mode changed to {'Timestamps' if new_mode == MODE_TIMESTAMPS else 'Edit'}")

        if new_mode == MODE_EDIT:
            # Show edit view, hide timestamp view
            self._scroll_view.setHidden_(False)
            self._timestamp_scroll_view.setHidden_(True)
            # Update instruction
            if self._instruction_label:
                self._instruction_label.setStringValue_("Edit your transcription. Press Enter to insert, Escape to cancel.")
        else:
            # Show timestamp view, hide edit view
            self._scroll_view.setHidden_(True)
            self._timestamp_scroll_view.setHidden_(False)
            # Update timestamp view content
            self._update_timestamp_view()
            # Update instruction
            if self._instruction_label:
                self._instruction_label.setStringValue_("Read-only timestamp view. Switch to Edit Mode to modify.")

    def _update_timestamp_view(self):
        """Update the timestamp view with segment timestamps."""
        if not self._timestamp_text_view:
            return

        if not self._transcription_result or not self._transcription_result.has_timestamps:
            # No timestamps available
            self._timestamp_text_view.setString_("No timestamp data available for this transcription.")
            return

        # Check if text was edited (timestamps may not align)
        current_text = self._text_view.string() if self._text_view else ""
        was_edited = current_text != self._original_text

        # Build formatted timestamp text
        lines = []
        if was_edited:
            lines.append("Note: Text was edited. Timestamps show original segments.\n")

        for segment in self._transcription_result.segment_timestamps:
            time_range = segment.formatted_range()
            lines.append(f"{time_range}  {segment.text}")

        timestamp_text = "\n".join(lines)
        self._timestamp_text_view.setString_(timestamp_text)

    def _create_bottom_buttons(self, parent_view, x, y, width):
        """Create the bottom action buttons."""
        # Cancel button (left)
        cancel_frame = NSRect(NSPoint(x, y), NSSize(BUTTON_WIDTH, BUTTON_HEIGHT))
        cancel_button = NSButton.alloc().initWithFrame_(cancel_frame)
        cancel_button.setTitle_("Discard")
        cancel_button.setBezelStyle_(NSBezelStyleRounded)
        cancel_button.setTarget_(self._delegate)
        cancel_button.setAction_(objc.selector(self._delegate.cancelClicked_, signature=b'v@:@'))
        cancel_button.setKeyEquivalent_("\x1b")  # Escape key
        parent_view.addSubview_(cancel_button)

        # Keyboard hint
        hint_frame = NSRect(NSPoint(x + BUTTON_WIDTH + 10, y + 8), NSSize(200, 16))
        hint_label = NSTextField.alloc().initWithFrame_(hint_frame)
        hint_label.setStringValue_("Shift+Enter for new line")
        hint_label.setBezeled_(False)
        hint_label.setDrawsBackground_(False)
        hint_label.setEditable_(False)
        hint_label.setSelectable_(False)
        hint_label.setTextColor_(NSColor.tertiaryLabelColor())
        hint_label.setFont_(NSFont.systemFontOfSize_(10))
        parent_view.addSubview_(hint_label)

        # Insert button (right) - primary action
        insert_frame = NSRect(NSPoint(width - PADDING - BUTTON_WIDTH, y), NSSize(BUTTON_WIDTH, BUTTON_HEIGHT))
        insert_button = NSButton.alloc().initWithFrame_(insert_frame)
        insert_button.setTitle_("Insert")
        insert_button.setBezelStyle_(NSBezelStyleRounded)
        insert_button.setTarget_(self._delegate)
        insert_button.setAction_(objc.selector(self._delegate.sendClicked_, signature=b'v@:@'))
        insert_button.setKeyEquivalent_("\r")  # Enter key
        parent_view.addSubview_(insert_button)

    def _update_layout(self):
        """Update layout when window is resized."""
        # Save current mode and text before rebuilding
        saved_mode = self._current_mode
        saved_text = getattr(self, '_current_text', '')

        self._layout_views()

        # Restore text content
        if saved_text:
            self._text_view.setString_(saved_text)
            self._text_view.set_callbacks(self._do_send, self._do_cancel, self._update_status)

        # Restore mode state
        if self._mode_toggle:
            self._mode_toggle.setSelectedSegment_(saved_mode)
            # Re-apply mode visibility
            if saved_mode == MODE_TIMESTAMPS:
                self._scroll_view.setHidden_(True)
                self._timestamp_scroll_view.setHidden_(False)
                self._update_timestamp_view()
            else:
                self._scroll_view.setHidden_(False)
                self._timestamp_scroll_view.setHidden_(True)

        # Update duration label
        if self._duration_label and self._transcription_result:
            duration_str = self._transcription_result.formatted_duration()
            self._duration_label.setStringValue_(f" Duration: {duration_str}")

        # Update timestamps availability
        if self._mode_toggle and self._transcription_result:
            has_timestamps = self._transcription_result.has_timestamps
            self._mode_toggle.setEnabled_forSegment_(has_timestamps, MODE_TIMESTAMPS)
            if not has_timestamps:
                self._mode_toggle.setLabel_forSegment_("Timestamps (N/A)", MODE_TIMESTAMPS)
            else:
                self._mode_toggle.setLabel_forSegment_("Timestamps", MODE_TIMESTAMPS)

    def _update_status(self):
        """Update the character/word count status."""
        if not self._text_view or not self._status_label:
            return

        text = self._text_view.string()
        self._current_text = text  # Store for layout updates

        char_count = len(text)
        word_count = len(text.split()) if text.strip() else 0

        # Format with proper pluralization
        char_word = "character" if char_count == 1 else "characters"
        word_word = "word" if word_count == 1 else "words"

        status_text = f"{char_count:,} {char_word} | {word_count:,} {word_word}"

        # Add edit indicator if text was modified
        if text != self._original_text:
            status_text += " (edited)"

        self._status_label.setStringValue_(status_text)

    def _position_near_cursor(self):
        """Position the window near the mouse cursor."""
        mouse_loc = NSEvent.mouseLocation()
        screen = NSScreen.mainScreen()

        if screen:
            screen_frame = screen.frame()

            # Position above and to the right of cursor
            x = mouse_loc.x - WINDOW_WIDTH / 2
            y = mouse_loc.y + 50

            # Clamp to screen bounds
            x = max(20, min(x, screen_frame.size.width - WINDOW_WIDTH - 20))
            y = max(100, min(y, screen_frame.size.height - WINDOW_HEIGHT - 50))

            self._window.setFrameOrigin_(NSPoint(x, y))

    def _do_send(self):
        """Handle send action."""
        corrected_text = self._text_view.string()
        print(f"CORRECTION: Insert clicked. Original: '{self._original_text[:30]}...', Corrected: '{corrected_text[:30]}...'")

        # Hide window immediately
        self._is_visible = False
        self._window.orderOut_(None)

        # Schedule callback for next event loop iteration (allows window to disappear first)
        from PyObjCTools import AppHelper
        AppHelper.callAfter(self._execute_send_callback, corrected_text)

    def _execute_send_callback(self, corrected_text):
        """Execute send callback after window is hidden."""
        if self._on_send_callback:
            self._on_send_callback(self._original_text, corrected_text)

    def _do_cancel(self):
        """Handle cancel action."""
        print("CORRECTION: Discard clicked")
        self.hide()

        if self._on_cancel_callback:
            self._on_cancel_callback()

    def _do_copy(self):
        """Copy current text to clipboard."""
        text = self._text_view.string()
        if text:
            pb = NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.setString_forType_(text, NSPasteboardTypeString)

            # Update instruction to confirm copy
            if self._instruction_label:
                self._instruction_label.setStringValue_("Copied to clipboard!")
                # Reset after 2 seconds (would need a timer, for now just leave it)
        print(f"CORRECTION: Copied {len(text)} characters to clipboard")

    def _do_clear(self):
        """Clear all text."""
        self._text_view.setString_("")
        self._update_status()
        print("CORRECTION: Text cleared")

    def _on_window_close(self):
        """Called when window is closed via X button."""
        self._is_visible = False
        # Treat close as cancel
        if self._on_cancel_callback:
            self._on_cancel_callback()

    def show(self, transcription: Union[TranscriptionResult, str]):
        """
        Show the correction window with the given transcription.

        Args:
            transcription: Either a TranscriptionResult object or plain text string.
        """
        # Handle both TranscriptionResult and plain string
        if isinstance(transcription, TranscriptionResult):
            self._transcription_result = transcription
            # Use formatted text with paragraph breaks between segments
            text = transcription.formatted_with_breaks()
            print(f"CORRECTION: show() called with TranscriptionResult: '{text[:50]}...'")
            print(f"CORRECTION: Duration: {transcription.formatted_duration()}, has_timestamps: {transcription.has_timestamps}")
            if transcription.has_timestamps:
                print(f"CORRECTION: Text formatted with {len(transcription.segment_timestamps)} paragraph breaks")
        else:
            # Plain string - wrap in TranscriptionResult for consistency
            text = str(transcription)
            self._transcription_result = TranscriptionResult.from_text_only(text)
            print(f"CORRECTION: show() called with plain text: '{text[:50]}...'")

        # Capture the currently focused app BEFORE showing our window
        workspace = NSWorkspace.sharedWorkspace()
        self._previous_app = workspace.frontmostApplication()
        if self._previous_app:
            print(f"CORRECTION: Stored previous app: {self._previous_app.localizedName()}")

        self._original_text = text
        self._current_text = text
        self._current_mode = MODE_EDIT  # Reset to edit mode

        # Ensure layout is fresh (this recreates all UI elements)
        self._layout_views()

        # Update duration label
        if self._duration_label and self._transcription_result:
            duration_str = self._transcription_result.formatted_duration()
            self._duration_label.setStringValue_(f" Duration: {duration_str}")
            print(f"CORRECTION: Set duration label to: 'Duration: {duration_str}'")

        # Update mode toggle state and enable/disable timestamps mode
        if self._mode_toggle:
            self._mode_toggle.setSelectedSegment_(MODE_EDIT)
            # Disable timestamps segment if no timestamp data
            has_timestamps = self._transcription_result and self._transcription_result.has_timestamps
            self._mode_toggle.setEnabled_forSegment_(has_timestamps, MODE_TIMESTAMPS)
            if not has_timestamps:
                # Visual feedback that timestamps aren't available
                self._mode_toggle.setLabel_forSegment_("Timestamps (N/A)", MODE_TIMESTAMPS)
            else:
                self._mode_toggle.setLabel_forSegment_("Timestamps", MODE_TIMESTAMPS)

        # Update target app label AFTER _layout_views() since it recreates the label
        print(f"CORRECTION: _target_app_label exists: {self._target_app_label is not None}")
        print(f"CORRECTION: _previous_app exists: {self._previous_app is not None}")
        if self._target_app_label:
            if self._previous_app:
                app_name = self._previous_app.localizedName()
                label_text = f"Insert into: {app_name}"
                self._target_app_label.setStringValue_(label_text)
                print(f"CORRECTION: Set target app label to: '{label_text}'")
                print(f"CORRECTION: Label frame: {self._target_app_label.frame()}")
                print(f"CORRECTION: Label superview: {self._target_app_label.superview()}")
            else:
                self._target_app_label.setStringValue_("Insert into: (unknown)")
                print("CORRECTION: Set target app label to: 'Insert into: (unknown)'")

        # Set the text in the text view
        self._text_view.setString_(text)
        self._text_view.set_callbacks(self._do_send, self._do_cancel, self._update_status)

        # Select all text for easy replacement
        text_length = len(text)
        self._text_view.setSelectedRange_(NSMakeRange(0, text_length))

        # Update status
        self._update_status()

        # Reset instruction
        if self._instruction_label:
            self._instruction_label.setStringValue_("Edit your transcription. Press Enter to insert, Escape to cancel.")

        # Position near cursor
        self._position_near_cursor()

        # Show window and bring to front - must activate to receive keyboard input
        self._is_visible = True
        self._window.makeKeyAndOrderFront_(None)

        # Activate our app to receive keyboard events (we restore focus later)
        NSApp.activateIgnoringOtherApps_(True)

        # Focus the text view within our window
        self._window.makeFirstResponder_(self._text_view)

        print("CORRECTION: Window should now be visible")

    def hide(self):
        """Hide the correction window."""
        if not self._is_visible:
            return
        self._is_visible = False
        self._window.orderOut_(None)
        print("CORRECTION: Window hidden")

    def restore_previous_app_focus(self):
        """Restore focus to the app that was active before correction window."""
        if self._previous_app:
            print(f"CORRECTION: Restoring focus to: {self._previous_app.localizedName()}")
            self._previous_app.activateWithOptions_(0)
            time.sleep(0.1)  # Small delay for focus to settle
            self._previous_app = None

    def copy_to_clipboard(self, text: str) -> bool:
        """
        Copy text to clipboard silently (no UI feedback).

        Args:
            text: Text to copy

        Returns:
            True if copy succeeded, False otherwise
        """
        if not text:
            return False
        try:
            pb = NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.setString_forType_(text, NSPasteboardTypeString)
            print(f"CORRECTION: Silently copied {len(text)} characters to clipboard")
            return True
        except Exception as e:
            print(f"CORRECTION: Failed to copy to clipboard: {e}")
            return False

    def get_target_app_name(self) -> str:
        """Return the name of the target app, or empty string if unknown."""
        if self._previous_app:
            return self._previous_app.localizedName()
        return ""

    def get_target_app_bundle_id(self) -> str:
        """Return the bundle identifier of the target app, or empty string if unknown."""
        if self._previous_app:
            return self._previous_app.bundleIdentifier() or ""
        return ""

    def is_target_likely_text_accepting(self) -> bool:
        """
        Heuristic check: is the target app likely to accept text input?

        Returns False for apps known to not have text fields (Desktop, Finder windows, etc.)
        Returns True for apps that typically have text input.

        This is a heuristic - we can't know for certain if the cursor is in a text field.
        """
        if not self._previous_app:
            print("CORRECTION: No previous app - assuming NOT text-accepting")
            return False

        bundle_id = self._previous_app.bundleIdentifier() or ""
        app_name = self._previous_app.localizedName() or ""

        # Apps that typically don't accept arbitrary text input
        non_text_apps = {
            # System apps
            "com.apple.finder",  # Finder (Desktop, file browser)
            "com.apple.dock.extra",  # Dock
            "com.apple.loginwindow",  # Login screen
            "com.apple.SecurityAgent",  # Password dialogs
            "com.apple.systempreferences",  # System Preferences
            "com.apple.systempreferences.extensions",
            # Desktop window server
            "com.apple.WindowServer",
        }

        # Check bundle ID
        if bundle_id in non_text_apps:
            print(f"CORRECTION: Target app '{app_name}' ({bundle_id}) is in non-text-apps list")
            return False

        # Special check for Finder - even if not in desktop, text input is rare
        if bundle_id == "com.apple.finder":
            print(f"CORRECTION: Target is Finder - likely NOT text-accepting")
            return False

        # If bundle ID is empty or unknown, be cautious
        if not bundle_id:
            print(f"CORRECTION: Target app '{app_name}' has no bundle ID - assuming NOT text-accepting")
            return False

        print(f"CORRECTION: Target app '{app_name}' ({bundle_id}) is likely text-accepting")
        return True

    @property
    def is_visible(self):
        """Return whether the window is currently visible."""
        return self._is_visible
