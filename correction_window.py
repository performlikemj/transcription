"""
Correction window for reviewing/editing transcriptions before insertion.
Enhanced UI for long-form dictation with better editing experience.
Uses PyObjC/AppKit for native macOS integration.
"""

import objc
import time
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
)
from Foundation import NSRect, NSPoint, NSSize, NSObject, NSMakeRange, NSNotificationCenter

# Window dimensions - larger for long-form editing
WINDOW_WIDTH = 650
WINDOW_HEIGHT = 420
MIN_WINDOW_WIDTH = 450
MIN_WINDOW_HEIGHT = 300

# Layout constants
PADDING = 20
TOOLBAR_HEIGHT = 44
STATUS_BAR_HEIGHT = 28
BUTTON_HEIGHT = 32
BUTTON_WIDTH = 100


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
        self._on_send_callback = on_send
        self._on_cancel_callback = on_cancel
        self._original_text = ""
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
        text_top = toolbar_y - 8
        text_height = text_top - text_bottom

        # === Toolbar at top ===
        self._create_toolbar(content_view, PADDING, toolbar_y, width - 2 * PADDING)

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
        """Create the toolbar with instruction and action buttons."""
        toolbar_view = NSView.alloc().initWithFrame_(
            NSRect(NSPoint(x, y), NSSize(width, TOOLBAR_HEIGHT))
        )

        # Instruction label on the left
        instruction_frame = NSRect(NSPoint(0, 12), NSSize(width - 200, 20))
        self._instruction_label = NSTextField.alloc().initWithFrame_(instruction_frame)
        self._instruction_label.setStringValue_("Edit your transcription. Press Enter to insert, Escape to cancel.")
        self._instruction_label.setBezeled_(False)
        self._instruction_label.setDrawsBackground_(False)
        self._instruction_label.setEditable_(False)
        self._instruction_label.setSelectable_(False)
        self._instruction_label.setTextColor_(NSColor.secondaryLabelColor())
        self._instruction_label.setFont_(NSFont.systemFontOfSize_(12))
        toolbar_view.addSubview_(self._instruction_label)

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
        self._layout_views()

        # Restore text content
        if hasattr(self, '_current_text'):
            self._text_view.setString_(self._current_text)
            self._text_view.set_callbacks(self._do_send, self._do_cancel, self._update_status)

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

        self.hide()

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

    def show(self, text: str):
        """
        Show the correction window with the given text.

        Args:
            text: The transcribed text to display for editing.
        """
        print(f"CORRECTION: show() called with text: '{text[:50]}...'")

        # Capture the currently focused app BEFORE showing our window
        workspace = NSWorkspace.sharedWorkspace()
        self._previous_app = workspace.frontmostApplication()
        if self._previous_app:
            print(f"CORRECTION: Stored previous app: {self._previous_app.localizedName()}")

        self._original_text = text
        self._current_text = text

        # Ensure layout is fresh
        self._layout_views()

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

    @property
    def is_visible(self):
        """Return whether the window is currently visible."""
        return self._is_visible
