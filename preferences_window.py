"""
Native macOS preferences window with hotkey recording.
Uses PyObjC/AppKit for native integration.
"""

import objc
from AppKit import (
    NSWindow, NSView, NSTextField, NSButton,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSBackingStoreBuffered, NSApp, NSColor, NSFont,
    NSTextFieldCell, NSBezelStyleRounded, NSScreen,
    NSEventModifierFlagCommand, NSEventModifierFlagShift,
    NSEventModifierFlagOption, NSEventModifierFlagControl,
    NSCenterTextAlignment, NSWindowCollectionBehaviorMoveToActiveSpace
)
from Foundation import NSRect, NSPoint, NSSize, NSObject

# Window dimensions
WINDOW_WIDTH = 400
WINDOW_HEIGHT = 220

# Special key code mappings (macOS keyCode -> pynput format)
SPECIAL_KEY_MAP = {
    49: "<space>",
    36: "<enter>",
    51: "<backspace>",
    53: "<esc>",
    48: "<tab>",
    122: "<f1>",
    120: "<f2>",
    99: "<f3>",
    118: "<f4>",
    96: "<f5>",
    97: "<f6>",
    98: "<f7>",
    100: "<f8>",
    101: "<f9>",
    109: "<f10>",
    103: "<f11>",
    111: "<f12>",
}

# Reserved hotkeys that shouldn't be used
RESERVED_HOTKEYS = {
    "<cmd>+q", "<cmd>+w", "<cmd>+tab", "<cmd>+<space>",
    "<cmd>+h", "<cmd>+m", "<cmd>+<shift>+3", "<cmd>+<shift>+4",
    "<cmd>+<shift>+5"
}


def hotkey_to_display(hotkey_str: str) -> str:
    """Convert pynput format '<cmd>+<shift>+d' to display format 'Cmd+Shift+D'."""
    if not hotkey_str:
        return ""
    result = hotkey_str
    replacements = [
        ("<cmd>", "Cmd"),
        ("<shift>", "Shift"),
        ("<alt>", "Option"),
        ("<ctrl>", "Ctrl"),
        ("<space>", "Space"),
        ("<enter>", "Enter"),
        ("<backspace>", "Backspace"),
        ("<tab>", "Tab"),
        ("<esc>", "Esc"),
    ]
    for pynput_fmt, display_fmt in replacements:
        result = result.replace(pynput_fmt, display_fmt)
    # Capitalize single-letter keys
    parts = result.split("+")
    parts = [p if len(p) > 1 else p.upper() for p in parts]
    return "+".join(parts)


class HotkeyRecorderView(NSView):
    """Custom NSView that captures key events when focused."""

    def initWithFrame_(self, frame):
        self = objc.super(HotkeyRecorderView, self).initWithFrame_(frame)
        if self is None:
            return None

        self._hotkey_str = ""
        self._display_str = "Click and press keys..."
        self._is_recording = False
        self._on_change_callback = None
        self._current_modifiers = 0

        # Visual styling
        self._background_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.95, 0.95, 0.95, 1.0
        )
        self._recording_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.9, 0.95, 1.0, 1.0
        )
        self._border_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.7, 0.7, 0.7, 1.0
        )
        self._recording_border_color = NSColor.colorWithCalibratedRed_green_blue_alpha_(
            0.2, 0.5, 0.9, 1.0
        )

        return self

    def setOnChangeCallback_(self, callback):
        """Set callback to be called when hotkey changes."""
        self._on_change_callback = callback

    def setHotkey_(self, hotkey_str):
        """Set the current hotkey and update display."""
        self._hotkey_str = hotkey_str
        self._display_str = hotkey_to_display(hotkey_str) if hotkey_str else "Click and press keys..."
        self.setNeedsDisplay_(True)

    def getHotkey(self):
        """Get the current hotkey string in pynput format."""
        return self._hotkey_str

    def acceptsFirstResponder(self):
        return True

    def becomeFirstResponder(self):
        self._is_recording = True
        self._display_str = "Press hotkey..."
        self._current_modifiers = 0
        self.setNeedsDisplay_(True)
        return True

    def resignFirstResponder(self):
        self._is_recording = False
        if not self._hotkey_str:
            self._display_str = "Click and press keys..."
        else:
            self._display_str = hotkey_to_display(self._hotkey_str)
        self.setNeedsDisplay_(True)
        return True

    def mouseDown_(self, event):
        """Make the view first responder when clicked."""
        self.window().makeFirstResponder_(self)

    def flagsChanged_(self, event):
        """Track modifier key changes."""
        if not self._is_recording:
            return
        self._current_modifiers = event.modifierFlags()
        # Update display to show current modifiers
        self._update_display_from_modifiers()
        self.setNeedsDisplay_(True)

    def _update_display_from_modifiers(self):
        """Update display string to show currently pressed modifiers."""
        parts = []
        if self._current_modifiers & NSEventModifierFlagControl:
            parts.append("Ctrl")
        if self._current_modifiers & NSEventModifierFlagOption:
            parts.append("Option")
        if self._current_modifiers & NSEventModifierFlagShift:
            parts.append("Shift")
        if self._current_modifiers & NSEventModifierFlagCommand:
            parts.append("Cmd")
        if parts:
            self._display_str = "+".join(parts) + "+..."
        else:
            self._display_str = "Press hotkey..."

    def keyDown_(self, event):
        """Capture key press and convert to pynput format."""
        if not self._is_recording:
            return

        modifiers = event.modifierFlags()
        key_code = event.keyCode()
        chars = event.charactersIgnoringModifiers()

        # Build the hotkey string
        parts = []

        # Add modifiers in consistent order
        if modifiers & NSEventModifierFlagControl:
            parts.append("<ctrl>")
        if modifiers & NSEventModifierFlagOption:
            parts.append("<alt>")
        if modifiers & NSEventModifierFlagShift:
            parts.append("<shift>")
        if modifiers & NSEventModifierFlagCommand:
            parts.append("<cmd>")

        # Require at least one modifier
        if not parts:
            self._display_str = "Need at least one modifier (Cmd, Ctrl, etc.)"
            self.setNeedsDisplay_(True)
            return

        # Add the base key
        if key_code in SPECIAL_KEY_MAP:
            parts.append(SPECIAL_KEY_MAP[key_code])
        elif chars and len(chars) > 0:
            char = chars[0].lower()
            # Only accept alphanumeric keys
            if char.isalnum():
                parts.append(char)
            else:
                return  # Ignore non-alphanumeric keys

        # Need at least modifier + key
        if len(parts) < 2:
            return

        # Build the hotkey string
        new_hotkey = "+".join(parts)

        # Check for reserved hotkeys
        if new_hotkey.lower() in RESERVED_HOTKEYS:
            self._display_str = f"Reserved: {hotkey_to_display(new_hotkey)}"
            self.setNeedsDisplay_(True)
            return

        # Success - update the hotkey
        self._hotkey_str = new_hotkey
        self._display_str = hotkey_to_display(new_hotkey)
        self._is_recording = False
        self.setNeedsDisplay_(True)

        # Resign first responder
        self.window().makeFirstResponder_(None)

        # Notify callback
        if self._on_change_callback:
            self._on_change_callback(new_hotkey)

    def drawRect_(self, rect):
        from AppKit import NSBezierPath, NSFontAttributeName, NSForegroundColorAttributeName
        from Foundation import NSString

        # Draw background - use white for better visibility
        if self._is_recording:
            # Light blue when recording
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.9, 0.95, 1.0, 1.0).setFill()
        else:
            # White background normally
            NSColor.whiteColor().setFill()

        bg_path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            rect, 8, 8
        )
        bg_path.fill()

        # Draw border - more visible
        if self._is_recording:
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.2, 0.5, 0.9, 1.0).setStroke()
            bg_path.setLineWidth_(2.5)
        else:
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.6, 0.6, 0.6, 1.0).setStroke()
            bg_path.setLineWidth_(1.5)
        bg_path.stroke()

        # Draw text - larger and centered
        text_color = NSColor.blackColor() if not self._is_recording else NSColor.colorWithCalibratedRed_green_blue_alpha_(0.1, 0.3, 0.7, 1.0)
        text_font = NSFont.systemFontOfSize_(15)

        # Calculate text position (centered)
        text_attrs = {
            NSFontAttributeName: text_font,
            NSForegroundColorAttributeName: text_color,
        }
        ns_string = NSString.stringWithString_(self._display_str)
        text_size = ns_string.sizeWithAttributes_(text_attrs)
        text_x = (rect.size.width - text_size.width) / 2
        text_y = (rect.size.height - text_size.height) / 2

        ns_string.drawAtPoint_withAttributes_(
            NSPoint(text_x, text_y),
            text_attrs
        )


class PreferencesWindowDelegate(NSObject):
    """Delegate to handle window close events and button actions."""

    def initWithCallbacks_(self, callbacks):
        self = objc.super(PreferencesWindowDelegate, self).init()
        if self is None:
            return None
        self._on_close = callbacks.get('on_close')
        self._on_save = callbacks.get('on_save')
        self._on_reset = callbacks.get('on_reset')
        return self

    def windowWillClose_(self, notification):
        if self._on_close:
            self._on_close()

    def saveClicked_(self, sender):
        print("PREFERENCES: Save button clicked (via delegate)")
        if self._on_save:
            self._on_save()

    def resetClicked_(self, sender):
        print("PREFERENCES: Reset button clicked (via delegate)")
        if self._on_reset:
            self._on_reset()


class PreferencesWindow:
    """Manages the preferences window lifecycle."""

    def __init__(self, current_hotkey: str, on_hotkey_changed, on_reset):
        self._window = None
        self._hotkey_recorder = None
        self._current_label = None
        self._on_hotkey_changed = on_hotkey_changed
        self._on_reset_callback = on_reset
        self._current_hotkey = current_hotkey
        self._is_visible = False
        self._delegate = None
        self._setup_window()
        print(f"PREFERENCES: Window initialized with hotkey '{current_hotkey}'")

    def _setup_window(self):
        """Create and configure the preferences window."""
        # Calculate position (centered on screen)
        screen = NSScreen.mainScreen()
        if screen:
            screen_frame = screen.frame()
            x = (screen_frame.size.width - WINDOW_WIDTH) / 2
            y = (screen_frame.size.height - WINDOW_HEIGHT) / 2
        else:
            x, y = 100, 100

        frame = NSRect(
            NSPoint(x, y),
            NSSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        )

        # Create window with title bar and close button
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
            NSBackingStoreBuffered,
            False
        )

        self._window.setTitle_("YardTalk Preferences")
        self._window.setCollectionBehavior_(NSWindowCollectionBehaviorMoveToActiveSpace)

        # Set up delegate for close events and button actions
        callbacks = {
            'on_close': self._on_window_close,
            'on_save': self._do_save,
            'on_reset': self._do_reset,
        }
        self._delegate = PreferencesWindowDelegate.alloc().initWithCallbacks_(callbacks)
        self._window.setDelegate_(self._delegate)

        # Create content view
        content_frame = NSRect(NSPoint(0, 0), NSSize(WINDOW_WIDTH, WINDOW_HEIGHT))
        content_view = NSView.alloc().initWithFrame_(content_frame)
        content_view.setWantsLayer_(True)

        # Layout from top to bottom (remember: macOS Y=0 is at bottom)
        # Content area is about 190px (220 - 30 for title bar)

        # Add "Dictation Hotkey:" label at top
        label_frame = NSRect(NSPoint(20, 160), NSSize(200, 20))
        label = NSTextField.alloc().initWithFrame_(label_frame)
        label.setStringValue_("Dictation Hotkey:")
        label.setBezeled_(False)
        label.setDrawsBackground_(False)
        label.setEditable_(False)
        label.setSelectable_(False)
        label.setFont_(NSFont.boldSystemFontOfSize_(13))
        content_view.addSubview_(label)

        # Add hotkey recorder view - make it taller and more prominent
        recorder_frame = NSRect(NSPoint(20, 110), NSSize(WINDOW_WIDTH - 40, 44))
        self._hotkey_recorder = HotkeyRecorderView.alloc().initWithFrame_(recorder_frame)
        self._hotkey_recorder.setHotkey_(self._current_hotkey)
        self._hotkey_recorder.setOnChangeCallback_(self._on_recorder_change)
        content_view.addSubview_(self._hotkey_recorder)

        # Add instruction label below recorder
        instruction_frame = NSRect(NSPoint(20, 85), NSSize(WINDOW_WIDTH - 40, 20))
        instruction_label = NSTextField.alloc().initWithFrame_(instruction_frame)
        instruction_label.setStringValue_("Click above, then press your desired hotkey combination")
        instruction_label.setBezeled_(False)
        instruction_label.setDrawsBackground_(False)
        instruction_label.setEditable_(False)
        instruction_label.setSelectable_(False)
        instruction_label.setTextColor_(NSColor.grayColor())
        instruction_label.setFont_(NSFont.systemFontOfSize_(11))
        content_view.addSubview_(instruction_label)

        # Add current hotkey label
        current_frame = NSRect(NSPoint(20, 55), NSSize(WINDOW_WIDTH - 40, 20))
        self._current_label = NSTextField.alloc().initWithFrame_(current_frame)
        self._current_label.setStringValue_(f"Current: {hotkey_to_display(self._current_hotkey)}")
        self._current_label.setBezeled_(False)
        self._current_label.setDrawsBackground_(False)
        self._current_label.setEditable_(False)
        self._current_label.setSelectable_(False)
        self._current_label.setTextColor_(NSColor.grayColor())
        content_view.addSubview_(self._current_label)

        # Add Reset button - make it wider
        reset_frame = NSRect(NSPoint(20, 15), NSSize(140, 32))
        reset_button = NSButton.alloc().initWithFrame_(reset_frame)
        reset_button.setTitle_("Reset to Default")
        reset_button.setBezelStyle_(NSBezelStyleRounded)
        reset_button.setTarget_(self._delegate)
        reset_button.setAction_(objc.selector(self._delegate.resetClicked_, signature=b'v@:@'))
        content_view.addSubview_(reset_button)

        # Add Save button
        save_frame = NSRect(NSPoint(WINDOW_WIDTH - 100, 15), NSSize(80, 32))
        save_button = NSButton.alloc().initWithFrame_(save_frame)
        save_button.setTitle_("Save")
        save_button.setBezelStyle_(NSBezelStyleRounded)
        save_button.setTarget_(self._delegate)
        save_button.setAction_(objc.selector(self._delegate.saveClicked_, signature=b'v@:@'))
        content_view.addSubview_(save_button)

        self._window.setContentView_(content_view)

    def _on_recorder_change(self, new_hotkey):
        """Called when user records a new hotkey."""
        print(f"PREFERENCES: Recorder changed to '{new_hotkey}'")
        # Update the "Current" label preview
        if self._current_label:
            self._current_label.setStringValue_(f"New: {hotkey_to_display(new_hotkey)}")

    def _do_reset(self):
        """Handle Reset button click."""
        print("PREFERENCES: _do_reset called")
        from settings_manager import SettingsManager
        default_hotkey = SettingsManager.DEFAULT_HOTKEY
        self._hotkey_recorder.setHotkey_(default_hotkey)
        self._current_label.setStringValue_(f"Reset to: {hotkey_to_display(default_hotkey)}")
        if self._on_reset_callback:
            self._on_reset_callback()

    def _do_save(self):
        """Handle Save button click."""
        print("PREFERENCES: _do_save called")
        new_hotkey = self._hotkey_recorder.getHotkey()
        print(f"PREFERENCES: New hotkey from recorder: '{new_hotkey}'")
        print(f"PREFERENCES: Callback exists: {self._on_hotkey_changed is not None}")
        if new_hotkey and self._on_hotkey_changed:
            print(f"PREFERENCES: Calling _on_hotkey_changed with '{new_hotkey}'")
            self._on_hotkey_changed(new_hotkey)
            self._current_hotkey = new_hotkey
            self._current_label.setStringValue_(f"Current: {hotkey_to_display(new_hotkey)}")
        else:
            print(f"PREFERENCES: Not saving - new_hotkey={new_hotkey}, callback={self._on_hotkey_changed}")
        self.hide()

    def _on_window_close(self):
        """Called when window is closed."""
        self._is_visible = False

    def show(self):
        """Show the preferences window."""
        print(f"PREFERENCES: show() called, _is_visible={self._is_visible}")

        # Update the recorder with current hotkey
        self._hotkey_recorder.setHotkey_(self._current_hotkey)
        self._current_label.setStringValue_(f"Current: {hotkey_to_display(self._current_hotkey)}")

        # Always bring window to front
        self._is_visible = True
        self._window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)
        print("PREFERENCES: Window should now be visible")

    def hide(self):
        """Hide the preferences window."""
        if not self._is_visible:
            return
        self._is_visible = False
        self._window.orderOut_(None)

    def set_current_hotkey(self, hotkey_str: str):
        """Update the current hotkey display."""
        self._current_hotkey = hotkey_str
        if self._hotkey_recorder:
            self._hotkey_recorder.setHotkey_(hotkey_str)
        if self._current_label:
            self._current_label.setStringValue_(f"Current: {hotkey_to_display(hotkey_str)}")
