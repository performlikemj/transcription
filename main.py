# --- macOS dylib workaround: ensure Torch's private libs are discoverable ---
import sys, os, pathlib
if getattr(sys, "frozen", False):  # running inside YardTalk.app
    bundle_root = pathlib.Path(sys.executable).resolve().parents[1]  # .../Contents
    torch_lib_dir = (
        bundle_root
        / "Resources"
        / f"lib/python{sys.version_info.major}.{sys.version_info.minor}"
        / "torch"
        / "lib"
    )
    # Tell the dynamic loader where to look first for @rpath-dependent libs
    os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = str(torch_lib_dir)
# ---------------------------------------------------------------------------

# Set up file logging for GUI app debugging
import logging
import datetime

# Create a log file in the user's home directory for GUI launches
def _configure_logging():
    log_file = os.path.expanduser("~/Library/Logs/YardTalk/dictation_app.log")
    handlers = [logging.StreamHandler(sys.stdout)]
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        handlers.insert(0, logging.FileHandler(log_file, mode='w'))
    except Exception as file_error:
        fallback_path = "/tmp/yardtalk.log"
        try:
            handlers.insert(0, logging.FileHandler(fallback_path, mode='w'))
            log_file = fallback_path
        except Exception:
            log_file = None
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=handlers,
        )
        if log_file:
            logging.warning("Logging file handler failed; using fallback path: %s", log_file)
        else:
            logging.warning("Logging file handler failed: %s", file_error)
        return

    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers,
    )

_configure_logging()

def log_print(*args, **kwargs):
    """Custom print function that logs to both file and console"""
    message = ' '.join(str(arg) for arg in args)
    logging.info(message)

# Replace print with our logging version
print = log_print

import rumps
from app_paths import resolve_resource_path
# ui_config imports removed - using simple icon="icon.png" instead
from hotkey_manager import HotkeyManager
from audio_manager import AudioManager
from asr_service import ASRService
from text_insertion_service import TextInsertionService
from overlay_window import OverlayWindow
from settings_manager import SettingsManager
from preferences_window import PreferencesWindow, hotkey_to_display
from transcription_history import TranscriptionHistory
from correction_window import CorrectionWindow
from live_transcription_service import LiveTranscriptionService
from help_window import HelpWindow
import sounddevice as sd
from PyObjCTools import AppHelper
import time
import numpy as np

# For Dock menu support and toast notifications
import objc
from AppKit import (
    NSApplication, NSMenu, NSMenuItem, NSPasteboard, NSPasteboardTypeString,
    NSWindow, NSView, NSTextField, NSColor, NSFont, NSScreen,
    NSWindowStyleMaskBorderless, NSBackingStoreBuffered,
    NSFloatingWindowLevel, NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSTextAlignmentCenter
)
from Foundation import NSObject, NSRect, NSPoint, NSSize, NSTimer, NSRunLoop, NSDefaultRunLoopMode

# Global reference to the app instance for menu callbacks
_app_instance = None

# Simple toast notification window
_toast_window = None

def _dismiss_toast():
    """Dismiss the toast window."""
    global _toast_window
    if _toast_window:
        _toast_window.orderOut_(None)
        _toast_window = None
        print("MAIN_APP: Toast dismissed")

def show_toast(title: str, message: str, duration: float = 2.5):
    """Show a simple floating toast notification using AppKit."""
    global _toast_window

    # Cancel any existing toast
    if _toast_window:
        _toast_window.orderOut_(None)
        _toast_window = None

    # Create toast window
    screen = NSScreen.mainScreen()
    screen_frame = screen.frame() if screen else NSRect(NSPoint(0, 0), NSSize(1920, 1080))

    toast_width = 320
    toast_height = 60
    x = (screen_frame.size.width - toast_width) / 2
    y = screen_frame.size.height - 120  # Near top of screen

    frame = NSRect(NSPoint(x, y), NSSize(toast_width, toast_height))

    _toast_window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        frame,
        NSWindowStyleMaskBorderless,
        NSBackingStoreBuffered,
        False
    )
    _toast_window.setLevel_(NSFloatingWindowLevel + 1)
    _toast_window.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces)
    _toast_window.setOpaque_(False)
    _toast_window.setBackgroundColor_(NSColor.clearColor())

    # Create content view with rounded background
    content = NSView.alloc().initWithFrame_(NSRect(NSPoint(0, 0), NSSize(toast_width, toast_height)))
    content.setWantsLayer_(True)
    content.layer().setBackgroundColor_(NSColor.colorWithWhite_alpha_(0.15, 0.95).CGColor())
    content.layer().setCornerRadius_(12)

    # Title label
    title_frame = NSRect(NSPoint(15, 30), NSSize(toast_width - 30, 22))
    title_label = NSTextField.alloc().initWithFrame_(title_frame)
    title_label.setStringValue_(title)
    title_label.setBezeled_(False)
    title_label.setDrawsBackground_(False)
    title_label.setEditable_(False)
    title_label.setSelectable_(False)
    title_label.setTextColor_(NSColor.whiteColor())
    title_label.setFont_(NSFont.boldSystemFontOfSize_(14))
    title_label.setAlignment_(NSTextAlignmentCenter)
    content.addSubview_(title_label)

    # Message label
    msg_frame = NSRect(NSPoint(15, 10), NSSize(toast_width - 30, 18))
    msg_label = NSTextField.alloc().initWithFrame_(msg_frame)
    msg_label.setStringValue_(message)
    msg_label.setBezeled_(False)
    msg_label.setDrawsBackground_(False)
    msg_label.setEditable_(False)
    msg_label.setSelectable_(False)
    msg_label.setTextColor_(NSColor.colorWithWhite_alpha_(1.0, 0.8))
    msg_label.setFont_(NSFont.systemFontOfSize_(12))
    msg_label.setAlignment_(NSTextAlignmentCenter)
    content.addSubview_(msg_label)

    _toast_window.setContentView_(content)
    _toast_window.orderFrontRegardless()

    # Auto-dismiss using AppHelper.callLater
    AppHelper.callLater(duration, _dismiss_toast)
    print(f"MAIN_APP: Toast shown: '{title}' - '{message}'")


class AppMenuHandler(NSObject):
    """Handler for application menu items and Dock menu."""

    @objc.python_method
    def _get_app(self):
        global _app_instance
        return _app_instance

    def openSettings_(self, sender):
        """Handle Settings menu click."""
        app = self._get_app()
        if app:
            AppHelper.callAfter(app._open_settings_window)

    def showHelp_(self, sender):
        """Handle Help menu click."""
        HelpWindow.show_help()

    def toggleDictation_(self, sender):
        """Handle Toggle Dictation menu click."""
        app = self._get_app()
        if app:
            AppHelper.callAfter(app._toggle_dictation_from_dock)

    def copyHistoryEntry_(self, sender):
        """Copy a history entry to clipboard."""
        # The entry is stored in the menu item's represented object
        entry = sender.representedObject()
        if entry:
            pb = NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.setString_forType_(entry.display_text, NSPasteboardTypeString)
            print(f"MAIN_APP: Copied history entry to clipboard")

    def clearHistory_(self, sender):
        """Clear all history entries."""
        app = self._get_app()
        if app:
            AppHelper.callAfter(app._clear_history, None)

    def applicationDockMenu_(self, sender):
        """Provide the Dock right-click menu."""
        menu = NSMenu.alloc().init()

        # Toggle Dictation item
        app = self._get_app()
        toggle_title = "Start Dictation"
        if app and app.dictation_active:
            toggle_title = "Stop Dictation"
        elif app and app.is_transcribing:
            toggle_title = "Processing..."

        toggle_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            toggle_title, "toggleDictation:", ""
        )
        toggle_item.setTarget_(self)
        menu.addItem_(toggle_item)

        # Separator
        menu.addItem_(NSMenuItem.separatorItem())

        # Settings item
        settings_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Settings...", "openSettings:", ""
        )
        settings_item.setTarget_(self)
        menu.addItem_(settings_item)

        return menu


def setup_app_menu(handler):
    """Build a complete menu bar like Terminal has."""
    app = NSApplication.sharedApplication()

    # Create a brand new menu bar
    main_menu = NSMenu.alloc().init()

    # === 1. Application Menu (YardTalk) ===
    app_menu = NSMenu.alloc().initWithTitle_("YardTalk")
    app_menu_item = NSMenuItem.alloc().init()
    app_menu_item.setSubmenu_(app_menu)

    # About YardTalk
    about_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "About YardTalk", "orderFrontStandardAboutPanel:", ""
    )
    app_menu.addItem_(about_item)

    app_menu.addItem_(NSMenuItem.separatorItem())

    # Settings with Cmd+,
    settings_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Settings...", "openSettings:", ","
    )
    settings_item.setTarget_(handler)
    app_menu.addItem_(settings_item)

    app_menu.addItem_(NSMenuItem.separatorItem())

    # Hide YardTalk (Cmd+H)
    hide_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Hide YardTalk", "hide:", "h"
    )
    app_menu.addItem_(hide_item)

    # Hide Others (Cmd+Opt+H)
    hide_others = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Hide Others", "hideOtherApplications:", "h"
    )
    hide_others.setKeyEquivalentModifierMask_(1 << 19 | 1 << 20)  # Cmd+Opt
    app_menu.addItem_(hide_others)

    # Show All
    show_all = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Show All", "unhideAllApplications:", ""
    )
    app_menu.addItem_(show_all)

    app_menu.addItem_(NSMenuItem.separatorItem())

    # Quit YardTalk (Cmd+Q)
    quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Quit YardTalk", "terminate:", "q"
    )
    app_menu.addItem_(quit_item)

    main_menu.addItem_(app_menu_item)

    # === 2. Dictation Menu ===
    dictation_menu = NSMenu.alloc().initWithTitle_("Dictation")
    dictation_menu_item = NSMenuItem.alloc().init()
    dictation_menu_item.setSubmenu_(dictation_menu)
    dictation_menu_item.setTitle_("Dictation")

    # Toggle Dictation (no key equivalent - actual hotkey handled by pynput)
    toggle_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Start Dictation", "toggleDictation:", ""
    )
    toggle_item.setTarget_(handler)
    dictation_menu.addItem_(toggle_item)

    dictation_menu.addItem_(NSMenuItem.separatorItem())

    # Recent Transcriptions (placeholder - will be dynamic)
    recent_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Recent Transcriptions", "", ""
    )
    recent_submenu = NSMenu.alloc().initWithTitle_("Recent Transcriptions")
    placeholder = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "No transcriptions yet", "", ""
    )
    placeholder.setEnabled_(False)
    recent_submenu.addItem_(placeholder)
    recent_item.setSubmenu_(recent_submenu)
    dictation_menu.addItem_(recent_item)

    main_menu.addItem_(dictation_menu_item)

    # === 3. Window Menu ===
    window_menu = NSMenu.alloc().initWithTitle_("Window")
    window_menu_item = NSMenuItem.alloc().init()
    window_menu_item.setSubmenu_(window_menu)
    window_menu_item.setTitle_("Window")

    # Minimize (Cmd+M)
    minimize_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Minimize", "performMiniaturize:", "m"
    )
    window_menu.addItem_(minimize_item)

    # Zoom
    zoom_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "Zoom", "performZoom:", ""
    )
    window_menu.addItem_(zoom_item)

    main_menu.addItem_(window_menu_item)

    # === 4. Help Menu ===
    help_menu = NSMenu.alloc().initWithTitle_("Help")
    help_menu_item = NSMenuItem.alloc().init()
    help_menu_item.setSubmenu_(help_menu)
    help_menu_item.setTitle_("Help")

    # YardTalk Help
    help_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
        "YardTalk Help", "showHelp:", "?"
    )
    help_item.setTarget_(handler)
    help_menu.addItem_(help_item)

    main_menu.addItem_(help_menu_item)

    # Set the menu bar
    app.setMainMenu_(main_menu)

    # Store references for later updates
    handler.dictation_menu = dictation_menu
    handler.toggle_menu_item = toggle_item
    handler.recent_submenu = recent_submenu

    print("MAIN_APP: Full menu bar created (YardTalk, Dictation, Window, Help)")
    return True


def find_parakeet_model(search_dir):
    """
    Find a Parakeet TDT model in the given directory.
    Searches for directories matching 'parakeet-tdt-*' and returns the path
    to the .nemo file inside. Supports any version (v2, v3, etc).

    Returns the path to the .nemo file, or None if not found.
    """
    import glob
    search_path = pathlib.Path(search_dir)

    # Look for parakeet-tdt-* directories
    model_dirs = sorted(search_path.glob("parakeet-tdt-*"), reverse=True)

    for model_dir in model_dirs:
        if model_dir.is_dir():
            # Find .nemo file inside
            nemo_files = list(model_dir.glob("*.nemo"))
            if nemo_files:
                return str(nemo_files[0])

    # Also check for .nemo files directly in the search directory (for bundled app)
    direct_nemo = sorted(search_path.glob("parakeet-tdt-*.nemo"), reverse=True)
    if direct_nemo:
        return str(direct_nemo[0])

    return None


# Used to distinguish ASR service callbacks
ASR_CALLBACK_TYPE_MODEL_LOAD = "model_load_status"
ASR_CALLBACK_TYPE_TRANSCRIPTION = "transcription_result"

class DictationApp(rumps.App):
    def __init__(self):
        # Simple initialization that works (from commit 1fbd7e3)
        super(DictationApp, self).__init__("Dictation App", icon="icon.png")
        print(f"MAIN_APP: App initialized with icon='icon.png'")
        # Initialize transcription history (session only)
        self.transcription_history = TranscriptionHistory()

        # Build menu with history submenu
        self.menu = [
            "Toggle Dictation",
            ("Recent Transcriptions", self._build_history_menu_items()),
            None,
            "Settings",
            None,
            "Quit"
        ]

        self.dictation_active = False
        self.is_transcribing = False

        # Initialize settings manager and load saved hotkey
        self.settings_manager = SettingsManager()
        self.hotkey_string = self.settings_manager.get_hotkey()
        self.preferences_window = None  # Lazy initialization

        # Initialize correction window for reviewing transcriptions
        self.correction_window = CorrectionWindow(
            on_send=self._on_correction_send,
            on_cancel=self._on_correction_cancel
        )

        # Silence detection settings for auto-send
        self.silence_threshold = 150  # RMS level below which audio is considered silence (lowered from 500)
        self.silence_duration = 2.0   # Seconds of silence before auto-sending
        self._last_sound_time = None  # Timestamp of last non-silent audio
        self._auto_stop_pending = False  # Prevent multiple auto-stops
        self._waiting_for_correction = False  # True while correction window is open

        self.asr_model_status = "initializing" # "initializing", "loaded", "error"
        # Flag to ensure MODEL_LOADED_SUCCESSFULLY is handled only once
        self._model_loaded_handled = False
        self.active_timers = [] # Add a list to keep track of active timers
        self._last_transcribed_text = None  # Remember the last text we actually typed
        self.update_menu_state()
        self._debug_id_counter = 0 # For generating unique log IDs

        # Initialize services
        self.audio_manager = AudioManager()
        self.text_insertion_service = TextInsertionService()
        self.overlay_window = OverlayWindow()

        # Determine model path based on whether we're running from a bundle or source
        if getattr(sys, "frozen", False):
            # Running inside YardTalk.app - model is in Resources
            bundle_root = pathlib.Path(sys.executable).resolve().parents[1]  # .../Contents
            resources_dir = bundle_root / "Resources"
            model_path = find_parakeet_model(resources_dir)
        else:
            # Running from source - search current directory for parakeet-tdt-* folder
            model_path = find_parakeet_model(".")

        if not model_path:
            print("MAIN_APP: ERROR - No Parakeet model found! Please download a parakeet-tdt model.")
            model_path = None  # Will trigger error in ASRService
        else:
            print(f"MAIN_APP: Using model path: {model_path}")
        self.asr_service = ASRService(model_path=model_path, result_callback=self._handle_asr_service_result)

        # Initialize live transcription service for preview during recording
        # Note: Currently disabled by default - can be enabled in settings later
        self.live_transcription_enabled = False  # Toggle for live preview feature
        self.live_transcription_service = LiveTranscriptionService(
            asr_service=self.asr_service,
            on_preview=self._on_live_preview
        )

        # Check and request accessibility permissions before initializing hotkey manager
        self._check_and_request_accessibility()

        # Initialize hotkey manager but don't start it yet
        self.hotkey_manager = HotkeyManager(
            hotkey_str=self.hotkey_string,
            on_activate=self.request_activate_dictation,
            on_deactivate=self.request_deactivate_dictation
        )
        
        # Start hotkey manager after a short delay to ensure rumps is fully initialized
        print("MAIN_APP: Scheduling hotkey manager startup...")
        rumps.Timer(self._start_hotkey_manager, 1.0).start()

        # Set up global settings shortcut (Cmd+,)
        global _app_instance
        _app_instance = self
        self._settings_shortcut_active = False
        self._setup_settings_shortcut()

        # Set up application menu (YardTalk menu) with Settings item
        # Also set as app delegate for Dock menu support
        self._menu_handler = AppMenuHandler.alloc().init()
        NSApplication.sharedApplication().setDelegate_(self._menu_handler)
        rumps.Timer(self._setup_app_menu, 0.5).start()

        # Initial menu state is set above, will be updated by ASR callback

    def _check_and_request_accessibility(self):
        """Check accessibility permissions and prompt user if needed."""
        try:
            from ApplicationServices import AXIsProcessTrusted
            if not AXIsProcessTrusted():
                print("MAIN_APP: Accessibility permissions NOT granted - prompting user")
                # Show alert and offer to open System Settings
                response = rumps.alert(
                    title="Permissions Required",
                    message="YardTalk needs two permissions for hotkeys and text insertion:\n\n"
                            "1. Accessibility - for global hotkeys\n"
                            "2. Input Monitoring - for keyboard detection\n\n"
                            "Click 'Open Settings' to grant Accessibility first, then:\n"
                            "1. Click the + button and add YardTalk\n"
                            "2. Go to Input Monitoring and add YardTalk there too\n"
                            "3. Restart YardTalk",
                    ok="Open Settings",
                    cancel="Later"
                )
                if response == 1:  # OK clicked
                    import subprocess
                    subprocess.run([
                        "open",
                        "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
                    ])
            else:
                print("MAIN_APP: Accessibility permissions already granted")
        except ImportError:
            print("MAIN_APP: Could not check accessibility (API unavailable)")
        except Exception as e:
            print(f"MAIN_APP: Error checking accessibility: {e}")

    def _start_hotkey_manager(self, timer):
        """Start the hotkey manager after rumps is fully initialized"""
        print("MAIN_APP: Starting hotkey manager...")
        try:
            self.hotkey_manager.start_listening()
            print(f"MAIN_APP: Hotkey manager started successfully for {self.hotkey_string}")
            rumps.notification("Dictation App", "Hotkeys Active", f"Press {self.hotkey_string} to start dictation")
        except Exception as e:
            print(f"MAIN_APP: Failed to start hotkey manager: {e}")
            rumps.alert("Hotkey Error", f"Failed to start hotkey listener: {e}")
        finally:
            timer.stop()  # Make this a one-shot timer

    def _setup_app_menu(self, timer):
        """Add Settings to the application menu after rumps is initialized"""
        try:
            if setup_app_menu(self._menu_handler):
                print("MAIN_APP: Application menu configured with Settings")
                # Verify recent_submenu was set
                has_submenu = hasattr(self._menu_handler, 'recent_submenu')
                submenu_value = getattr(self._menu_handler, 'recent_submenu', None)
                print(f"HISTORY DEBUG: After setup_app_menu - has recent_submenu: {has_submenu}, value: {submenu_value}")
            else:
                print("MAIN_APP: Could not configure application menu")
        except Exception as e:
            print(f"MAIN_APP: Error setting up app menu: {e}")
            import traceback
            traceback.print_exc()
        finally:
            timer.stop()  # Make this a one-shot timer

    def _setup_settings_shortcut(self):
        """Set up Cmd+, global shortcut to open Settings."""
        from pynput import keyboard

        def on_key_press(key):
            # Track Cmd key state
            if key == keyboard.Key.cmd or key == keyboard.Key.cmd_l or key == keyboard.Key.cmd_r:
                self._cmd_pressed = True
                return

            # Check for comma key while Cmd is held
            if self._cmd_pressed:
                # Check by character
                is_comma = False
                if hasattr(key, 'char') and key.char == ',':
                    is_comma = True
                # Also check by virtual key code (43 is comma on macOS)
                elif hasattr(key, 'vk') and key.vk == 43:
                    is_comma = True

                if is_comma:
                    print("MAIN_APP: Settings shortcut (Cmd+,) detected!")
                    AppHelper.callAfter(self._open_settings_window)

        def on_key_release(key):
            if key == keyboard.Key.cmd or key == keyboard.Key.cmd_l or key == keyboard.Key.cmd_r:
                self._cmd_pressed = False

        self._cmd_pressed = False
        self._settings_listener = keyboard.Listener(
            on_press=on_key_press,
            on_release=on_key_release
        )
        self._settings_listener.start()
        print("MAIN_APP: Settings shortcut (Cmd+,) listener started")

    def _process_audio_chunk(self, chunk):
        self.asr_service.process_audio_chunk(chunk)

        # Diagnostic logging for overlay state
        if not hasattr(self, '_chunk_log_count'):
            self._chunk_log_count = 0
        self._chunk_log_count += 1

        if self.overlay_window:
            # Log overlay state periodically
            if self._chunk_log_count % 50 == 1:
                overlay_visible = getattr(self.overlay_window, '_is_visible', 'N/A')
                waveform_view = getattr(self.overlay_window, '_waveform_view', None)
                waveform_active = getattr(waveform_view, '_is_active', 'N/A') if waveform_view else 'N/A'
                print(f"MAIN_APP: Chunk #{self._chunk_log_count} - overlay_visible={overlay_visible}, waveform_active={waveform_active}")
            self.overlay_window.add_chunk(chunk)
        else:
            print("MAIN_APP: WARNING - overlay_window is None, can't add chunk")

        # Feed to live transcription service if active
        if self.live_transcription_service.is_active:
            self.live_transcription_service.add_audio_chunk(chunk)

        # Silence detection for auto-send
        if self.dictation_active and not self._auto_stop_pending:
            # Calculate RMS (root mean square) of the audio chunk
            audio_data = chunk.flatten().astype(np.float32)
            rms = np.sqrt(np.mean(audio_data ** 2))

            current_time = time.time()

            # Log RMS periodically for debugging
            if not hasattr(self, '_rms_log_count'):
                self._rms_log_count = 0
            self._rms_log_count += 1
            if self._rms_log_count % 20 == 1:  # Log every 20 chunks
                silence_elapsed = current_time - self._last_sound_time if self._last_sound_time else 0
                print(f"MAIN_APP: Audio RMS={rms:.0f} (threshold={self.silence_threshold}), silence_elapsed={silence_elapsed:.1f}s")

            if rms > self.silence_threshold:
                # Sound detected - reset the silence timer
                self._last_sound_time = current_time
            elif self._last_sound_time is not None:
                # Check if we've been silent long enough
                silence_elapsed = current_time - self._last_sound_time
                if silence_elapsed >= self.silence_duration:
                    print(f"MAIN_APP: Auto-stop triggered after {silence_elapsed:.1f}s of silence (RMS: {rms:.0f})")
                    self._auto_stop_pending = True
                    AppHelper.callAfter(self._auto_deactivate_dictation)

    def _auto_deactivate_dictation(self):
        """Automatically deactivate dictation after silence detection"""
        if self.dictation_active and not self.is_transcribing:
            print("MAIN_APP: Auto-deactivating dictation due to silence")
            self.hotkey_manager.hotkey_active = True  # Simulate hotkey state for proper deactivation
            self.request_deactivate_dictation()
        self._auto_stop_pending = False

    def _create_timer_on_main(self, payload_with_context):
        # payload_with_context is expected to be timer_payload_for_main_thread from _handle_asr_service_result
        # Let's assume it might contain a 'log_id' if we pass it from _handle_asr_service_result
        log_id_for_timer = payload_with_context.pop('log_id_for_timer', f"timer_{time.monotonic()}")

        # This method is called on the main thread via performSelectorOnMainThread_
        print(f"MAIN_APP ({log_id_for_timer}): _create_timer_on_main executing on main thread.")
        timer_instance = rumps.Timer(self._process_asr_result_on_main_thread, 0.0)
        timer_instance.user_payload = payload_with_context # This is the original timer_payload_for_main_thread
        timer_instance.log_id = log_id_for_timer # Attach log_id to timer instance
        
        if not hasattr(self, 'active_timers'):
            self.active_timers = []
        self.active_timers.append(timer_instance)
        timer_instance.start()
        print(f"MAIN_APP ({log_id_for_timer}): Timer started for _process_asr_result_on_main_thread.")

    def _handle_asr_service_result(self, result_payload, error_payload):
        # Generate a log ID for this specific ASR result handling sequence
        asr_result_log_id = f"asr_res_{time.monotonic()}"
        print(f"MAIN_APP ({asr_result_log_id}): _handle_asr_service_result ENTERED. Result: '{str(result_payload)[:50]}...', Error: {error_payload}")

        if result_payload == "MODEL_LOADED_SUCCESSFULLY" and self._model_loaded_handled:
            print(f"MAIN_APP ({asr_result_log_id}): Duplicate MODEL_LOADED_SUCCESSFULLY received, ignoring.")
            return
        
        callback_type = ASR_CALLBACK_TYPE_TRANSCRIPTION 
        data_to_pass = {'text': result_payload, 'error': error_payload}

        if result_payload == "MODEL_LOADED_SUCCESSFULLY":
            callback_type = ASR_CALLBACK_TYPE_MODEL_LOAD
            data_to_pass = {'status': "loaded", 'error': None}
            self._model_loaded_handled = True
            print(f"MAIN_APP ({asr_result_log_id}): Processed as MODEL_LOADED_SUCCESSFULLY.")
        elif error_payload and self.asr_model_status == "initializing": 
            callback_type = ASR_CALLBACK_TYPE_MODEL_LOAD
            data_to_pass = {'status': "error", 'error': error_payload}
            print(f"MAIN_APP ({asr_result_log_id}): Processed as MODEL_LOAD error during init.")
        elif callback_type == ASR_CALLBACK_TYPE_TRANSCRIPTION:
            # Fix 2: Don't even create a timer for blank results
            if error_payload is None and (
                result_payload is None
                or (isinstance(result_payload, str) and result_payload.strip() == "")
            ):
                print(f"MAIN_APP ({asr_result_log_id}): Empty or blank transcription received from ASRService. Skipping timer creation.")
                # Explicitly set is_transcribing to False here if appropriate, 
                # as _process_asr_result_on_main_thread won't be called to do it.
                if self.is_transcribing: # Only if we were actually waiting for a transcription
                    self.is_transcribing = False
                    print(f"MAIN_APP ({asr_result_log_id}): Set is_transcribing to False due to blank result.")
                    # Potentially reset hotkey_manager.hotkey_active as well, like in _process_asr_result_on_main_thread finally block
                    if self.hotkey_manager.hotkey_active:
                        print(f"MAIN_APP ({asr_result_log_id}): Resetting hotkey_manager.hotkey_active from True to False (blank result).")
                        self.hotkey_manager.hotkey_active = False
                    self.update_menu_state()
                return
        
        timer_payload_for_main_thread = {'type': callback_type, 'data': data_to_pass}
        
        # Pass the asr_result_log_id to be used by _create_timer_on_main
        payload_with_context = timer_payload_for_main_thread.copy() # Avoid modifying original dict if it's used elsewhere
        payload_with_context['log_id_for_timer'] = asr_result_log_id

        print(f"MAIN_APP ({asr_result_log_id}): Posting to _create_timer_on_main via AppHelper.callAfter.")
        AppHelper.callAfter(self._create_timer_on_main, payload_with_context)
        print(f"MAIN_APP ({asr_result_log_id}): _handle_asr_service_result EXITED.")

    def _process_asr_result_on_main_thread(self, timer_instance): # Receives the Timer instance
        log_id = hasattr(timer_instance, 'log_id') and timer_instance.log_id or "unknown_timer"
        print(f"MAIN_APP ({log_id}): _process_asr_result_on_main_thread ENTERED.")
        try:
            # This runs on the main Rumps thread
            user_payload = timer_instance.user_payload
            callback_type = user_payload['type']
            data = user_payload['data']

            if callback_type == ASR_CALLBACK_TYPE_MODEL_LOAD:
                status = data['status']
                error = data['error']
                if status == "loaded":
                    self.asr_model_status = "loaded"
                    rumps.notification("Dictation App", "Ready", f"ASR model loaded. Press {self.hotkey_string} to dictate.")
                elif status == "error":
                    self.asr_model_status = "error"
                    rumps.alert("ASR Model Error", f"Failed to load ASR model: {str(error)}. Transcription will not be available.")
            
            elif callback_type == ASR_CALLBACK_TYPE_TRANSCRIPTION:
                transcribed_text = data['text']
                error_obj = data['error'] # Renamed to avoid conflict with 'error' in MODEL_LOAD

                # Existing handling for actual transcription results
                try:
                    if error_obj:
                        rumps.alert("Transcription Failed", f"Could not transcribe audio: {str(error_obj)}")
                        return
                    # Fix 1 (part 1): Bail out early on empty text
                    # This check is now also in _handle_asr_service_result, but good to have defensively here too.
                    if transcribed_text is None or (isinstance(transcribed_text, str) and transcribed_text.strip() == ""):
                        print(f"MAIN_APP ({log_id}): Transcription result is None or blank. Bailing out early from processing.")
                        # No notification for blank text here, as it's handled by _handle_asr_service_result or if it slips through.
                        return # Return directly from here. The finally block will still execute.
                    elif transcribed_text is not None: # We already checked for blank, so this means non-blank
                        if transcribed_text == self._last_transcribed_text:
                            pass
                        else:
                            print("--- Transcribed Text ---")
                            print(transcribed_text)
                            print("------------------------")
                            # Show correction window instead of immediate insertion
                            print(f"MAIN_APP ({log_id}): Showing correction window for review...")
                            self._waiting_for_correction = True
                            self._pending_transcription_text = transcribed_text  # Store for cancel handler
                            AppHelper.callAfter(self.correction_window.show, transcribed_text)
                    # No explicit 'else' for transcribed_text == "" here as we return early if blank
                finally:
                    # This 'finally' is for the inner try related to processing transcription text and errors.
                    # The main state flags (is_transcribing, dictation_active) are reset in the outer finally block.
                    pass # Placeholder, could remove this inner finally if not strictly needed
        except Exception as e_outer:
            print(f"MAIN_APP ({log_id}): CRITICAL ERROR in _process_asr_result_on_main_thread: {e_outer}")
            import traceback
            traceback.print_exc()
        finally:
            # Fix 1 (part 2): Make this timer truly one-shot
            print(f"MAIN_APP ({log_id}): Stopping and removing timer.")
            timer_instance.stop()
            if timer_instance in self.active_timers:
                self.active_timers.remove(timer_instance)
            else:
                print(f"MAIN_APP ({log_id}): Timer was not in active_timers list for removal.")

            # This is the outer finally, ensure state flags are reset here if a transcription was processed (or attempted)
            # Only reset these if it was a transcription callback, not a model_load callback.
            # Also skip if correction window is open (state will be reset by correction callbacks)
            if callback_type == ASR_CALLBACK_TYPE_TRANSCRIPTION:
                if self._waiting_for_correction:
                    print(f"MAIN_APP ({log_id}): Outer FINALLY - Correction window open, skipping state reset.")
                else:
                    print(f"MAIN_APP ({log_id}): Outer FINALLY for ASR_CALLBACK_TYPE_TRANSCRIPTION. is_transcribing PRE: {self.is_transcribing}, dictation_active PRE: {self.dictation_active}")
                    self.is_transcribing = False
                    self.dictation_active = False

                    current_hotkey_active_state = self.hotkey_manager.hotkey_active
                    print(f"MAIN_APP ({log_id}): Hotkey_manager.hotkey_active PRE-check: {current_hotkey_active_state}")
                    if self.hotkey_manager.hotkey_active:
                        print(f"MAIN_APP ({log_id}): Resetting hotkey_manager.hotkey_active from True to False.")
                        self.hotkey_manager.hotkey_active = False

                    audio_is_recording_flag = getattr(self.audio_manager, "_is_recording", "N/A")
                    print(f"MAIN_APP ({log_id}): AudioManager._is_recording PRE-check: {audio_is_recording_flag}")
                    if audio_is_recording_flag == True:
                        print(f"MAIN_APP ({log_id}): Cleanup – mic was still flagged recording; stopping.")
                        self.audio_manager.stop_recording(f"from_process_asr_result_finally_{log_id}")
                        if self.overlay_window:
                            AppHelper.callAfter(self.overlay_window.hide)

                    print(f"MAIN_APP ({log_id}): is_transcribing POST: {self.is_transcribing}, dictation_active POST: {self.dictation_active}")
            else:
                print(f"MAIN_APP ({log_id}): Outer FINALLY for {callback_type}. Not resetting transcription-specific flags.")

            self.update_menu_state()

    def request_activate_dictation(self):
        AppHelper.callAfter(self._activate_dictation_main)

    def _activate_dictation_main(self):
        self._debug_id_counter += 1
        log_id = f"activate_{self._debug_id_counter}"
        print(f"MAIN_APP ({log_id}): _activate_dictation_main ENTERED.")
        
        # Directive B: Stop-before-restart guard
        audio_is_recording_flag = getattr(self.audio_manager, "_is_recording", "N/A")
        print(f"MAIN_APP ({log_id}): Directive B check: audio_manager._is_recording = {audio_is_recording_flag}")
        if audio_is_recording_flag == True: # Explicitly check True
            rumps.notification("Mic busy", "Still closing the previous stream…", "")
            if self.hotkey_manager.hotkey_active: 
                self.hotkey_manager.hotkey_active = False
            print(f"MAIN_APP ({log_id}): Mic busy, returning.")
            return

        print(f"MAIN_APP ({log_id}): State pre-activation: asr_model_status='{self.asr_model_status}', is_transcribing={self.is_transcribing}, dictation_active={self.dictation_active}")

        if self.asr_model_status == "initializing":
            rumps.notification("ASR Not Ready", "Model is still initializing.", "Please wait.")
            if self.hotkey_manager.hotkey_active: self.hotkey_manager.hotkey_active = False
            print(f"MAIN_APP ({log_id}): ASR initializing, returning.")
            return
        if self.asr_model_status == "error":
            rumps.alert("ASR Error", "ASR model failed to load. Cannot start dictation.")
            if self.hotkey_manager.hotkey_active: self.hotkey_manager.hotkey_active = False
            return
        if self.is_transcribing:
            print(f"MAIN_APP ({log_id}): Already transcribing, returning.")
            return

        if not self.dictation_active:
            print(f"MAIN_APP ({log_id}): Activation - Starting dictation logic...")

            # Capture the frontmost app NOW, before we show any UI
            from AppKit import NSWorkspace
            workspace = NSWorkspace.sharedWorkspace()
            self._dictation_source_app = workspace.frontmostApplication()
            if self._dictation_source_app:
                print(f"MAIN_APP ({log_id}): Captured source app: {self._dictation_source_app.localizedName()} ({self._dictation_source_app.bundleIdentifier()})")

            print(f"MAIN_APP ({log_id}): Activation - Before clearing ASR buffer.")
            self.asr_service.get_buffered_audio_and_clear() # Clear any old audio
            print(f"MAIN_APP ({log_id}): Activation - After clearing ASR buffer.")

            self.dictation_active = True
            self._last_sound_time = time.time()  # Initialize silence timer
            self._auto_stop_pending = False
            print(f"MAIN_APP ({log_id}): dictation_active SET to True.")
            if self.overlay_window:
                print(f"MAIN_APP ({log_id}): Showing overlay window...")
                self.overlay_window.show()  # Call directly - we're already on main thread
                # Enable live preview if feature is enabled
                if self.live_transcription_enabled:
                    self.overlay_window.set_live_preview_enabled(True)
            else:
                print(f"MAIN_APP ({log_id}): WARNING - overlay_window is None!")

            # Start live transcription if enabled
            if self.live_transcription_enabled:
                print(f"MAIN_APP ({log_id}): Starting live transcription service...")
                self.live_transcription_service.start()

            self.audio_manager.set_chunk_callback(self._process_audio_chunk)
            print(f"MAIN_APP ({log_id}): Calling audio_manager.start_recording().")
            if self.audio_manager.start_recording(f"from_activate_{log_id}"):
                rumps.notification("Dictation Started", "Listening...", "Press hotkey again to stop.")
            else:
                print(f"MAIN_APP ({log_id}): Activation - Failed to start audio recording.")
                error_detail = None
                if hasattr(self.audio_manager, "get_last_error"):
                    error_detail = self.audio_manager.get_last_error()
                error_message = "Failed to start audio recording."
                if error_detail:
                    error_text = str(error_detail)
                    error_message = f"{error_message}\n\n{error_text}"
                    if any(keyword in error_text.lower() for keyword in ("permission", "not permitted", "denied")):
                        error_message = (
                            f"{error_message}\n\n"
                            "Check System Settings > Privacy & Security > Microphone and allow YardTalk."
                        )
                rumps.alert("Audio Error", error_message)
                self.dictation_active = False
                if self.hotkey_manager.hotkey_active: self.hotkey_manager.hotkey_active = False
            self.update_menu_state()

    def request_deactivate_dictation(self):
        self._debug_id_counter += 1
        log_id = f"deactivate_req_{self._debug_id_counter}"
        print(f"MAIN_APP ({log_id}): request_deactivate_dictation called.")
        AppHelper.callAfter(self._deactivate_dictation_main)

    def _deactivate_dictation_main(self):
        # Note: log_id for _deactivate_dictation_main will be from the request_... call context if needed,
        # or we can generate one if it's called directly (though it shouldn't be).
        # For now, let's assume AppHelper carries context or we manage within.
        # For simplicity, use a new counter for direct calls to _deactivate_dictation_main if any.
        # However, it's always called via AppHelper.callAfter(self._deactivate_dictation_main)
        # which doesn't easily pass the log_id. Let's create one here.
        # This might lead to the counter being less sequential across activate/deactivate if they interleave rapidly.
        # A shared counter or passing log_id through AppHelper might be better if strict sequence is vital.
        # For now, a local log_id for this function's scope:
        # Let's use a timestamp for deactivate log_id to make it unique
        import time
        log_id = f"deactivate_main_{time.monotonic()}"

        print(f"MAIN_APP ({log_id}): _deactivate_dictation_main ENTERED.")
        print(f"MAIN_APP ({log_id}): State pre-deactivation: dictation_active={self.dictation_active}, is_transcribing={self.is_transcribing}")

        if not self.dictation_active:
            print(f"MAIN_APP ({log_id}): Deactivation called when dictation_active was False.")
            audio_is_recording_flag = getattr(self.audio_manager, "_is_recording", "N/A")
            print(f"MAIN_APP ({log_id}): audio_manager._is_recording = {audio_is_recording_flag}")
            if audio_is_recording_flag == True: # Explicitly check True
                print(f"MAIN_APP ({log_id}): AudioManager was unexpectedly recording. Stopping it now.")
                self.audio_manager.stop_recording(f"from_deactivate_not_active_{log_id}")
            
            if not self.is_transcribing:
                 if self.hotkey_manager.hotkey_active:
                    print(f"MAIN_APP ({log_id}): Resetting hotkey_active state (deactivation while not active/transcribing).")
                    self.hotkey_manager.hotkey_active = False
            else: # Not dictation_active, but is_transcribing
                print(f"MAIN_APP ({log_id}): Deactivation while not dictation_active, but is_transcribing. Hotkey likely to be reset by ASR callback.")

            self.update_menu_state() 
            print(f"MAIN_APP ({log_id}): _deactivate_dictation_main EXITED (dictation not active path).")
            return

        print(f"MAIN_APP ({log_id}): Deactivation - Stopping dictation logic...")
        self.dictation_active = False
        print(f"MAIN_APP ({log_id}): dictation_active SET to False.")
        print(f"MAIN_APP ({log_id}): Calling audio_manager.stop_recording().")
        self.audio_manager.stop_recording(f"from_deactivate_active_{log_id}")

        # Stop live transcription if active
        if self.live_transcription_service.is_active:
            print(f"MAIN_APP ({log_id}): Stopping live transcription service...")
            self.live_transcription_service.stop()

        if self.overlay_window:
            # Disable live preview before hiding
            if self.overlay_window.live_preview_enabled:
                AppHelper.callAfter(self.overlay_window.set_live_preview_enabled, False)
            AppHelper.callAfter(self.overlay_window.hide)
        print(f"MAIN_APP ({log_id}): Audio recording stopped call returned.")

        if self.is_transcribing:
            print(f"MAIN_APP ({log_id}): Deactivation - Transcription already in progress. Ignoring duplicate ASR submit request.")
            self.update_menu_state()
            print(f"MAIN_APP ({log_id}): _deactivate_dictation_main EXITED (already transcribing path).")
            return

        print(f"MAIN_APP ({log_id}): Getting buffered audio from ASR service.")
        audio_to_transcribe = self.asr_service.get_buffered_audio_and_clear()
        if audio_to_transcribe.size == 0:
            print(f"MAIN_APP ({log_id}): Deactivation - Audio buffer is empty. Nothing to transcribe.")
            rumps.notification("Dictation Stopped", "No audio recorded.", "")
            # If nothing to transcribe, ensure hotkey_active is False if it was True from the deactivation press
            if self.hotkey_manager.hotkey_active:
                 print(f"MAIN_APP ({log_id}): No audio, ensuring hotkey_manager.hotkey_active is False.")
                 self.hotkey_manager.hotkey_active = False
            self.update_menu_state()
            print(f"MAIN_APP ({log_id}): _deactivate_dictation_main EXITED (no audio to transcribe path).")
            return

        print(f"MAIN_APP ({log_id}): Submitting {len(audio_to_transcribe)} audio samples for transcription.")
        self.is_transcribing = True
        print(f"MAIN_APP ({log_id}): is_transcribing SET to True.")
        # Generate a log_id for this transcription request to track it into the callback
        transcription_log_id = f"asr_req_{time.monotonic()}"
        print(f"MAIN_APP ({log_id}): Submitting to ASR with transcription_log_id: {transcription_log_id}")
        # How to pass transcription_log_id to _handle_asr_service_result?
        # ASRService callback doesn't directly support passing extra context this way.
        # For now, the timer_instance in _create_timer_on_main will get its own ID.
        # We can correlate by timestamps in logs.
        # Let's try to attach it to the timer payload.
        
        # Modify _create_timer_on_main and _handle_asr_service_result to carry this ID.
        # This means the current edit is insufficient alone.
        # For now, just submit. The next step will be to modify the timer logic.
        self.asr_service.submit_transcription_request(audio_to_transcribe) 
        
        rumps.notification("Dictation Stopped", "Processing audio...", "Please wait.")
        self.update_menu_state()
        print(f"MAIN_APP ({log_id}): _deactivate_dictation_main EXITED (submitted to ASR path).")

    def update_menu_state(self):
        toggle_item = self.menu["Toggle Dictation"]

        # Keep app title stable to avoid rumps menu bar disappearing bug
        # Only change the menu item text to indicate state
        display_hotkey = hotkey_to_display(self.hotkey_string)
        menu_item_title = f"Start Dictation ({display_hotkey})"

        if self.asr_model_status == "initializing":
            menu_item_title = "ASR Initializing..."
        elif self.asr_model_status == "error":
            menu_item_title = "ASR Model Failed"
        elif self.is_transcribing:
            menu_item_title = "Processing..."
        elif self.dictation_active:
            menu_item_title = "Stop Dictation (Recording...)"

        # Update rumps menu item
        if toggle_item and toggle_item.title != menu_item_title:
            toggle_item.title = menu_item_title

        # Update native AppKit menu item (Dictation > Start/Stop Dictation)
        if hasattr(self, '_menu_handler') and hasattr(self._menu_handler, 'toggle_menu_item'):
            native_item = self._menu_handler.toggle_menu_item
            if native_item and native_item.title() != menu_item_title:
                native_item.setTitle_(menu_item_title)

    def _build_history_menu_items(self) -> list:
        """Build the Recent Transcriptions submenu items."""
        entries = self.transcription_history.get_entries()

        if not entries:
            # Return a disabled placeholder item
            placeholder = rumps.MenuItem("No transcriptions yet")
            placeholder.set_callback(None)
            return [placeholder]

        items = []
        for entry in entries:
            # Create menu item with closure to capture the entry
            def make_callback(e):
                return lambda sender: self._copy_history_entry(e)

            item = rumps.MenuItem(entry.menu_title(), callback=make_callback(entry))
            items.append(item)

        # Add separator and clear option
        items.append(None)  # Separator
        items.append(rumps.MenuItem("Clear History", callback=self._clear_history))

        return items

    def _copy_history_entry(self, entry):
        """Copy a history entry to clipboard."""
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(entry.display_text, NSPasteboardTypeString)

        preview = entry.display_text[:50]
        if len(entry.display_text) > 50:
            preview += "..."
        rumps.notification("Copied to Clipboard", "", preview)

    def _clear_history(self, _):
        """Clear all history entries."""
        self.transcription_history.clear()
        self._update_history_menu()
        rumps.notification("History Cleared", "", "")

    def _update_history_menu(self):
        """Refresh the Recent Transcriptions submenu (both rumps and native menus)."""
        print("HISTORY DEBUG: _update_history_menu() called")

        # Update rumps menu
        history_menu = self.menu.get("Recent Transcriptions")
        if history_menu is not None:
            history_menu.clear()
            new_items = self._build_history_menu_items()
            for item in new_items:
                if item is None:
                    history_menu.add(rumps.separator)
                else:
                    history_menu.add(item)
            print(f"HISTORY DEBUG: Updated rumps menu with {len(new_items)} items")

        # Update native menu bar (Dictation > Recent Transcriptions)
        print(f"HISTORY DEBUG: hasattr _menu_handler: {hasattr(self, '_menu_handler')}")
        if hasattr(self, '_menu_handler'):
            print(f"HISTORY DEBUG: hasattr recent_submenu: {hasattr(self._menu_handler, 'recent_submenu')}")

        if hasattr(self, '_menu_handler') and hasattr(self._menu_handler, 'recent_submenu'):
            native_menu = self._menu_handler.recent_submenu
            print(f"HISTORY DEBUG: native_menu object: {native_menu}")
            if native_menu:
                # Clear existing items
                native_menu.removeAllItems()

                entries = list(self.transcription_history.get_entries())
                print(f"HISTORY DEBUG: Found {len(entries)} entries to display")
                if not entries:
                    placeholder = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        "No transcriptions yet", "", ""
                    )
                    placeholder.setEnabled_(False)
                    native_menu.addItem_(placeholder)
                    print("HISTORY DEBUG: Added placeholder (no entries)")
                else:
                    for entry in entries:
                        print(f"HISTORY DEBUG: Adding menu item: '{entry.menu_title()}'")
                        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                            entry.menu_title(), "copyHistoryEntry:", ""
                        )
                        item.setTarget_(self._menu_handler)
                        item.setRepresentedObject_(entry)
                        native_menu.addItem_(item)

                    # Add separator and clear option
                    native_menu.addItem_(NSMenuItem.separatorItem())
                    clear_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        "Clear History", "clearHistory:", ""
                    )
                    clear_item.setTarget_(self._menu_handler)
                    native_menu.addItem_(clear_item)

                print(f"HISTORY DEBUG: Native menu now has {native_menu.numberOfItems()} items")
        else:
            print("HISTORY DEBUG: WARNING - _menu_handler or recent_submenu not found!")

    def _add_to_history(self, original_text: str, corrected_text: str = None, discarded: bool = False):
        """Add transcription to history and update menu."""
        status = "discarded" if discarded else "inserted"
        print(f"HISTORY DEBUG: _add_to_history called ({status}): '{original_text[:30]}...'")
        self.transcription_history.add(original_text, corrected_text, discarded=discarded)
        entry_count = len(list(self.transcription_history.get_entries()))
        print(f"HISTORY DEBUG: History now has {entry_count} entries")
        print(f"HISTORY DEBUG: Scheduling _update_history_menu via AppHelper.callAfter")
        AppHelper.callAfter(self._update_history_menu)

    def _on_correction_send(self, original_text: str, corrected_text: str):
        """Called when user confirms corrected text in the correction window."""
        print(f"MAIN_APP: Correction confirmed. Original: '{original_text[:30]}...', Corrected: '{corrected_text[:30]}...'")

        # Use the source app captured when dictation STARTED (not when correction window opened)
        source_app = getattr(self, '_dictation_source_app', None)
        if source_app:
            target_app_name = source_app.localizedName() or ""
            bundle_id = source_app.bundleIdentifier() or ""
            # Check if source app is likely to accept text
            non_text_bundles = {"com.apple.finder", "com.apple.dock.extra", "com.apple.loginwindow"}
            target_likely_text = bundle_id not in non_text_bundles and bundle_id != ""
            print(f"MAIN_APP: Source app (from dictation start): '{target_app_name}' ({bundle_id}), likely_text_accepting: {target_likely_text}")
        else:
            # Fallback to correction window's captured app
            target_app_name = self.correction_window.get_target_app_name()
            target_likely_text = self.correction_window.is_target_likely_text_accepting()
            print(f"MAIN_APP: Target app (fallback): '{target_app_name}', likely_text_accepting: {target_likely_text}")

        # SAFETY NET: Copy to clipboard BEFORE attempting insertion
        clipboard_success = self.correction_window.copy_to_clipboard(corrected_text)

        # Restore focus to the SOURCE app (where dictation started) BEFORE inserting text
        if source_app:
            print(f"MAIN_APP: Restoring focus to source app: {target_app_name}")
            source_app.activateWithOptions_(0)
            time.sleep(0.1)  # Small delay for focus to settle
        else:
            self.correction_window.restore_previous_app_focus()

        # Add to history with both original and corrected
        self._add_to_history(original_text, corrected_text)

        # Insert the corrected text (skip if target won't accept it)
        if not target_likely_text:
            # Don't even try to type - it would just cause error beeps
            print(f"MAIN_APP: Skipping keyboard insertion - target not text-accepting")
            # Show toast notification using AppKit (more reliable than rumps)
            show_toast("Text Copied", "Press Cmd+V to paste")
        else:
            try:
                insertion_result = self.text_insertion_service.insert_text(corrected_text)
                print(f"MAIN_APP: insert_text returned: {insertion_result}")

                if insertion_result:
                    msg = f"Text inserted into {target_app_name}." if target_app_name else "Text inserted."
                    rumps.notification("Transcription Complete", msg, corrected_text[:50])
                else:
                    if clipboard_success:
                        rumps.notification("Insertion Failed",
                            "Text copied to clipboard. Press Cmd+V to paste.", corrected_text[:50])
                    else:
                        rumps.notification("Insertion Failed",
                            "Could not insert or copy text.", corrected_text[:50])
            except Exception as e:
                print(f"MAIN_APP: Error during text insertion: {e}")
                if clipboard_success:
                    rumps.notification("Insertion Error",
                        "Text copied to clipboard. Press Cmd+V to paste.", corrected_text[:50])
                else:
                    rumps.notification("Insertion Error", str(e)[:50], corrected_text[:50])

        self._last_transcribed_text = corrected_text
        self._pending_transcription_text = None  # Clear pending text
        self._finish_transcription_cycle()

    def _on_correction_cancel(self):
        """Called when user cancels/discards transcription in the correction window."""
        print("MAIN_APP: Transcription discarded by user")

        # Save discarded transcription to history for recovery
        if hasattr(self, '_pending_transcription_text') and self._pending_transcription_text:
            self._add_to_history(self._pending_transcription_text, discarded=True)
            self._pending_transcription_text = None

        rumps.notification("Transcription Discarded", "Saved to history for recovery.", "")
        self._finish_transcription_cycle()

    def _on_live_preview(self, preview_text: str):
        """Called when live preview text is available."""
        print(f"MAIN_APP: Live preview: '{preview_text[:50]}...'")
        if self.overlay_window:
            self.overlay_window.set_preview_text(preview_text)

    def _finish_transcription_cycle(self):
        """Clean up state after transcription cycle (send or cancel)."""
        self._waiting_for_correction = False
        self.is_transcribing = False
        self.dictation_active = False

        if self.hotkey_manager.hotkey_active:
            self.hotkey_manager.hotkey_active = False

        # Cleanup mic if still recording
        audio_is_recording = getattr(self.audio_manager, "_is_recording", False)
        if audio_is_recording:
            self.audio_manager.stop_recording("from_finish_transcription_cycle")
            if self.overlay_window:
                AppHelper.callAfter(self.overlay_window.hide)

        self.update_menu_state()

    @rumps.clicked("Toggle Dictation")
    def toggle_dictation_manual(self, _):
        """Manual toggle for dictation - useful when hotkeys aren't working"""
        print(f"MAIN_APP: Manual toggle dictation clicked. dictation_active={self.dictation_active}, hotkey_active={self.hotkey_manager.hotkey_active}, is_transcribing={self.is_transcribing}")

        if self.asr_model_status == "initializing":
            rumps.notification("ASR Not Ready", "Model is still initializing.", "Please wait.")
            return
        elif self.asr_model_status == "error":
            rumps.alert("ASR Error", "ASR model failed to load. Cannot start dictation.")
            return

        # If transcription is in progress, ignore the toggle
        if self.is_transcribing:
            print("MAIN_APP: Manual toggle ignored - transcription in progress")
            rumps.notification("Processing", "Please wait for transcription to complete.", "")
            return

        # Sync hotkey_active state with dictation_active for menu-based toggle
        if self.dictation_active or self.hotkey_manager.hotkey_active:
            # Currently active (by either mechanism), so deactivate
            # Set hotkey_active to True so deactivate logic works correctly
            self.hotkey_manager.hotkey_active = True
            self.request_deactivate_dictation()
        else:
            # Currently inactive, so activate
            self.hotkey_manager.hotkey_active = True
            self.request_activate_dictation()

    @rumps.clicked("Settings")
    def settings(self, _):
        """Open the preferences window."""
        if self.preferences_window is None:
            self.preferences_window = PreferencesWindow(
                current_hotkey=self.hotkey_string,
                on_hotkey_changed=self._on_hotkey_changed,
                on_reset=self._on_hotkey_reset
            )
        self.preferences_window.set_current_hotkey(self.hotkey_string)
        self.preferences_window.show()

    def _open_settings_window(self):
        """Open settings window - called from Dock menu."""
        print("MAIN_APP: Opening settings from Dock menu")
        self.settings(None)

    def _toggle_dictation_from_dock(self):
        """Toggle dictation - called from Dock menu."""
        print("MAIN_APP: Toggle dictation from Dock menu")
        self.toggle_dictation_manual(None)

    def _on_hotkey_changed(self, new_hotkey: str):
        """Callback when user saves a new hotkey in preferences."""
        if new_hotkey == self.hotkey_string:
            return  # No change

        # Validate by attempting to parse with pynput
        try:
            from pynput import keyboard
            keyboard.HotKey.parse(new_hotkey)
        except Exception as e:
            rumps.alert("Invalid Hotkey", f"Could not parse hotkey: {e}")
            return

        # Store for deferred update
        self._pending_hotkey = new_hotkey
        # Stop settings listener before update to avoid conflicts
        if hasattr(self, '_settings_listener') and self._settings_listener:
            print("MAIN_APP: Stopping settings listener before hotkey update")
            self._settings_listener.stop()
            self._settings_listener = None
        # Defer the actual update to avoid threading issues with rumps
        print(f"MAIN_APP: Scheduling hotkey update to '{new_hotkey}'")
        rumps.Timer(self._do_hotkey_update, 0.1).start()

    def _do_hotkey_update(self, timer):
        """Perform the actual hotkey update (called from timer to avoid threading issues)."""
        timer.stop()
        new_hotkey = getattr(self, '_pending_hotkey', None)
        if not new_hotkey:
            return

        print(f"MAIN_APP: Updating hotkey to '{new_hotkey}'")
        try:
            if self.hotkey_manager.update_hotkey(new_hotkey):
                self.hotkey_string = new_hotkey
                self.settings_manager.set_hotkey(new_hotkey)
                self.update_menu_state()
                rumps.notification(
                    "Hotkey Updated",
                    "New hotkey active",
                    f"Press {new_hotkey} to start dictation"
                )
                print("MAIN_APP: Hotkey update complete!")
            else:
                rumps.alert("Hotkey Error", "Failed to update hotkey. Please try again.")
        except Exception as e:
            print(f"MAIN_APP: Error during hotkey update: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._pending_hotkey = None

    def _on_hotkey_reset(self):
        """Callback when user clicks Reset to Default in preferences."""
        default_hotkey = SettingsManager.DEFAULT_HOTKEY
        if default_hotkey != self.hotkey_string:
            self._on_hotkey_changed(default_hotkey)

    @rumps.clicked("Quit")
    def quit_app(self, _):
        print("MAIN_APP: Quit clicked.")
        if self.dictation_active:
            print("MAIN_APP: Quit - Dictation was active, stopping audio manager...")
            self.audio_manager.stop_recording()
            if self.overlay_window:
                self.overlay_window.hide()
        
        print("MAIN_APP: Quit - Shutting down ASR service...")
        if self.asr_service: # Check if ASR service was initialized
            self.asr_service.shutdown() # Signal worker thread to stop
        
        print("MAIN_APP: Quit - Stopping hotkey manager.")
        if self.hotkey_manager: # Check if hotkey manager was initialized
            self.hotkey_manager.stop_listening()
        
        rumps.quit_application()

if __name__ == "__main__":
    # This dummy icon creation should ideally be conditional or handled better.
    try:
        with open("icon.png", "rb") as f:
            pass # Icon exists
    except FileNotFoundError:
        try:
            import base64
            png_data = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
            with open("icon.png", "wb") as f:
                f.write(png_data)
            print("Created dummy icon.png for main.py")
        except Exception as e:
            print(f"Could not create dummy icon.png for main.py: {e}")
            
    app = DictationApp()
    app.run() 
