"""
Native macOS Help window for YardTalk.
Displays detailed usage instructions and keyboard shortcuts.
"""

import objc
from AppKit import (
    NSWindow, NSView, NSTextField, NSButton, NSTextView, NSScrollView,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable, NSWindowStyleMaskResizable,
    NSBackingStoreBuffered, NSApp, NSColor, NSFont, NSScreen,
    NSBezelStyleRounded, NSWindowCollectionBehaviorMoveToActiveSpace,
    NSLineBorder, NSAttributedString, NSMutableAttributedString,
    NSFontAttributeName, NSForegroundColorAttributeName,
    NSParagraphStyleAttributeName, NSMutableParagraphStyle,
)
from Foundation import NSRect, NSPoint, NSSize, NSObject, NSMakeRange

# Window dimensions
WINDOW_WIDTH = 600
WINDOW_HEIGHT = 550

HELP_CONTENT = """
YardTalk - Local Voice Dictation for macOS

YardTalk is a privacy-focused dictation app that transcribes your speech entirely on your Mac using AI. No internet connection required, no data sent to the cloud.


GETTING STARTED

1. Grant Permissions
   When you first launch YardTalk, macOS will ask for:
   • Microphone access - Required to capture your voice
   • Accessibility access - Required for global hotkeys and text insertion

   Go to System Settings > Privacy & Security to enable these.

2. Wait for Model Loading
   The first launch takes a moment while the AI model loads. You'll see
   "ASR Initializing..." in the menu. Once ready, it shows "Start Dictation".


BASIC USAGE

Starting Dictation:
   Press Cmd+Shift+D (or your custom hotkey) to start recording.
   A waveform overlay appears showing audio input.

Stopping Dictation:
   • Press the hotkey again, OR
   • Wait 2 seconds of silence (auto-stop)

Review Window:
   After recording, a review window appears with your transcription.
   • Edit the text if needed
   • Press Enter or click "Insert" to type the text
   • Press Escape or click "Discard" to cancel
   • Use Shift+Enter to add line breaks while editing


KEYBOARD SHORTCUTS

Cmd+Shift+D     Start/stop dictation (customizable)
Cmd+,           Open Settings
Enter           Insert text (in review window)
Escape          Discard text (in review window)
Shift+Enter     New line (in review window)


MENU BAR

Click the YardTalk icon in the menu bar to access:
   • Start/Stop Dictation
   • Recent Transcriptions - View and copy past transcriptions
   • Settings - Change your hotkey
   • Quit


RECENT TRANSCRIPTIONS

Your transcriptions are saved for the current session.
   • Click any entry to copy it to the clipboard
   • Entries show relative time ("2m ago", "1h ago")
   • "edited" label means you modified the text before inserting
   • "discarded" label means you cancelled the transcription


TIPS FOR BEST RESULTS

• Speak clearly at a normal pace
• Minimize background noise
• The AI works best with complete sentences
• Pause briefly between sentences for natural breaks
• Review and edit transcriptions before inserting


TROUBLESHOOTING

"ASR Model Failed"
   The AI model couldn't load. Try restarting the app.

No audio detected
   Check System Settings > Privacy & Security > Microphone
   and ensure YardTalk has permission.

Hotkey not working
   Check System Settings > Privacy & Security > Accessibility
   and ensure YardTalk has permission.

Text not inserting
   The target app may not accept simulated keyboard input.
   Try using the Copy button and paste manually.


PRIVACY

YardTalk processes all speech locally on your Mac.
   • No audio is sent to any server
   • No transcriptions are uploaded
   • History is session-only (cleared when you quit)


ABOUT

YardTalk uses NVIDIA's Parakeet ASR model for speech recognition.
Built with Python, PyTorch, and native macOS technologies.

Version 1.0
"""


class HelpWindowDelegate(NSObject):
    """Delegate for window close events."""

    def initWithCallback_(self, on_close):
        self = objc.super(HelpWindowDelegate, self).init()
        if self is None:
            return None
        self._on_close = on_close
        return self

    def windowWillClose_(self, notification):
        if self._on_close:
            self._on_close()


class HelpWindow:
    """Manages the help window."""

    _instance = None  # Singleton instance

    @classmethod
    def show_help(cls):
        """Show the help window (creates if needed)."""
        if cls._instance is None:
            cls._instance = HelpWindow()
        cls._instance.show()

    def __init__(self):
        self._window = None
        self._is_visible = False
        self._delegate = None
        self._setup_window()

    def _setup_window(self):
        """Create and configure the help window."""
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

        style_mask = (
            NSWindowStyleMaskTitled |
            NSWindowStyleMaskClosable |
            NSWindowStyleMaskResizable
        )
        self._window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            style_mask,
            NSBackingStoreBuffered,
            False
        )

        self._window.setTitle_("YardTalk Help")
        self._window.setCollectionBehavior_(NSWindowCollectionBehaviorMoveToActiveSpace)
        self._window.setMinSize_(NSSize(400, 300))

        # Set up delegate
        self._delegate = HelpWindowDelegate.alloc().initWithCallback_(self._on_window_close)
        self._window.setDelegate_(self._delegate)

        self._create_content()

    def _create_content(self):
        """Create the help content."""
        content_view = self._window.contentView()
        content_frame = content_view.frame()

        padding = 20
        scroll_frame = NSRect(
            NSPoint(padding, padding),
            NSSize(content_frame.size.width - 2 * padding,
                   content_frame.size.height - 2 * padding)
        )

        scroll_view = NSScrollView.alloc().initWithFrame_(scroll_frame)
        scroll_view.setBorderType_(NSLineBorder)
        scroll_view.setHasVerticalScroller_(True)
        scroll_view.setHasHorizontalScroller_(False)
        scroll_view.setAutohidesScrollers_(True)
        scroll_view.setAutoresizingMask_(18)  # Flexible width and height

        # Create text view
        text_frame = NSRect(
            NSPoint(0, 0),
            NSSize(scroll_frame.size.width - 20, scroll_frame.size.height)
        )
        text_view = NSTextView.alloc().initWithFrame_(text_frame)
        text_view.setEditable_(False)
        text_view.setSelectable_(True)
        text_view.setRichText_(False)
        text_view.setFont_(NSFont.systemFontOfSize_(13))
        text_view.setTextColor_(NSColor.labelColor())
        text_view.setBackgroundColor_(NSColor.textBackgroundColor())

        # Set line spacing
        para_style = NSMutableParagraphStyle.alloc().init()
        para_style.setLineSpacing_(3)
        text_view.setDefaultParagraphStyle_(para_style)

        text_view.textContainer().setLineFragmentPadding_(10)
        text_view.setMinSize_(NSSize(0, scroll_frame.size.height))
        text_view.setMaxSize_(NSSize(10000, 10000))
        text_view.setVerticallyResizable_(True)
        text_view.setHorizontallyResizable_(False)
        text_view.textContainer().setWidthTracksTextView_(True)

        # Set the help content
        text_view.setString_(HELP_CONTENT.strip())

        scroll_view.setDocumentView_(text_view)
        content_view.addSubview_(scroll_view)

    def _on_window_close(self):
        """Called when window is closed."""
        self._is_visible = False

    def show(self):
        """Show the help window."""
        self._is_visible = True
        self._window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def hide(self):
        """Hide the help window."""
        if not self._is_visible:
            return
        self._is_visible = False
        self._window.orderOut_(None)
