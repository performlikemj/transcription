from pynput import keyboard
import traceback
import subprocess
import sys
import logging
import os

# Set up logging for hotkey manager
log_file = os.path.expanduser("~/dictation_app.log")
logger = logging.getLogger('HotkeyManager')

def log_print(*args, **kwargs):
    """Custom print function that logs to file"""
    message = ' '.join(str(arg) for arg in args)
    logger.info(message)
    # Also print to console for backward compatibility
    import builtins
    builtins.print(*args, **kwargs)

# Replace print with our logging version for this module
print = log_print

# Check if running as bundled app
_is_bundled = getattr(sys, "frozen", False)

# macOS key code mappings for native event monitoring
# https://developer.apple.com/documentation/appkit/1535851-function-key_unicodes
MACOS_KEY_CODES = {
    # Letters
    0: 'a', 1: 's', 2: 'd', 3: 'f', 4: 'h', 5: 'g', 6: 'z', 7: 'x',
    8: 'c', 9: 'v', 11: 'b', 12: 'q', 13: 'w', 14: 'e', 15: 'r',
    16: 'y', 17: 't', 18: '1', 19: '2', 20: '3', 21: '4', 22: '6',
    23: '5', 24: '=', 25: '9', 26: '7', 27: '-', 28: '8', 29: '0',
    30: ']', 31: 'o', 32: 'u', 33: '[', 34: 'i', 35: 'p', 37: 'l',
    38: 'j', 39: "'", 40: 'k', 41: ';', 42: '\\', 43: ',', 44: '/',
    45: 'n', 46: 'm', 47: '.', 49: 'space', 50: '`',
    # Function keys
    122: 'f1', 120: 'f2', 99: 'f3', 118: 'f4', 96: 'f5', 97: 'f6',
    98: 'f7', 100: 'f8', 101: 'f9', 109: 'f10', 103: 'f11', 111: 'f12',
    # Special keys
    36: 'return', 48: 'tab', 51: 'backspace', 53: 'escape',
    123: 'left', 124: 'right', 125: 'down', 126: 'up',
}

# Modifier flag masks for NSEvent
NSEventModifierFlagCapsLock = 1 << 16
NSEventModifierFlagShift = 1 << 17
NSEventModifierFlagControl = 1 << 18
NSEventModifierFlagOption = 1 << 19
NSEventModifierFlagCommand = 1 << 20

class HotkeyManager:
    def __init__(self, hotkey_str, on_activate, on_deactivate):
        self.hotkey_str = hotkey_str
        self.on_activate = on_activate
        self.on_deactivate = on_deactivate # Placeholder for future use
        self.listener = None
        self.hotkey_active = False
        self._hotkey = None

        # Native event monitor (for bundled apps)
        self._native_monitor = None
        self._use_native = _is_bundled and sys.platform == "darwin"

        # Track modifier keys for combination detection
        self.cmd_pressed = False
        self.ctrl_pressed = False
        self.alt_pressed = False
        self.shift_pressed = False

        # Parse hotkey for native monitoring
        self._target_key = None
        self._target_modifiers = set()

        # Check accessibility permissions on macOS
        self._check_accessibility_permissions()
        self._configure_hotkey()
        self._parse_hotkey_for_native()

    def _normalize_hotkey_key(self, key):
        """Normalize keys so HotKey matching works across pynput variants."""
        if self._hotkey is None:
            return key
        if key == keyboard.Key.space:
            if hasattr(self._hotkey, "_keys"):
                hotkey_keys = self._hotkey._keys
                space_match = None
                for hotkey_key in hotkey_keys:
                    if isinstance(hotkey_key, keyboard.KeyCode):
                        if getattr(hotkey_key, "char", None) == " ":
                            space_match = hotkey_key
                            break
                        if getattr(hotkey_key, "vk", None) == 49:
                            space_match = hotkey_key
                            break
                hotkey_has_key = any(hotkey_key == key for hotkey_key in hotkey_keys)
                if space_match is not None and not hotkey_has_key:
                    return space_match
        return key

    def _configure_hotkey(self):
        """Parse the hotkey string into a pynput HotKey object for generic matching."""
        try:
            hotkey_parts = keyboard.HotKey.parse(self.hotkey_str)
            self._hotkey = keyboard.HotKey(hotkey_parts, self.on_press)
            print(f"HOTKEY_MANAGER: Parsed hotkey '{self.hotkey_str}' into HotKey bindings.")
        except Exception as e:
            self._hotkey = None
            print(f"HOTKEY_MANAGER: Failed to parse hotkey '{self.hotkey_str}': {e}")

    def _parse_hotkey_for_native(self):
        """Parse hotkey string for native macOS event monitoring."""
        # Parse hotkey like '<ctrl>+<shift>+d' into components
        parts = self.hotkey_str.lower().replace('>', '').split('+')
        self._target_modifiers = set()
        self._target_key = None

        for part in parts:
            part = part.strip().strip('<')
            if part in ('cmd', 'command'):
                self._target_modifiers.add('cmd')
            elif part in ('ctrl', 'control'):
                self._target_modifiers.add('ctrl')
            elif part in ('alt', 'option'):
                self._target_modifiers.add('alt')
            elif part in ('shift',):
                self._target_modifiers.add('shift')
            elif len(part) == 1:
                # Single character key
                self._target_key = part
            elif part == 'space':
                self._target_key = 'space'
            elif part.startswith('f') and part[1:].isdigit():
                # Function key like f9
                self._target_key = part

        print(f"HOTKEY_MANAGER: Native hotkey parsed - key='{self._target_key}', modifiers={self._target_modifiers}")

    def _check_accessibility_permissions(self):
        """Check if the app has accessibility permissions on macOS using native API."""
        if sys.platform != "darwin":
            return True

        try:
            from ApplicationServices import AXIsProcessTrusted
            is_trusted = AXIsProcessTrusted()
            if is_trusted:
                print("HOTKEY_MANAGER: Accessibility permissions granted.")
                return True
            else:
                print("HOTKEY_MANAGER: WARNING - Accessibility permissions NOT granted.")
                print("HOTKEY_MANAGER: Please grant in System Settings > Privacy & Security > Accessibility")
                return False
        except ImportError:
            # Fallback if ApplicationServices not available
            print("HOTKEY_MANAGER: Could not check accessibility permissions (API unavailable)")
            return True
        except Exception as e:
            print(f"HOTKEY_MANAGER: Error checking accessibility permissions: {e}")
            return False

    def on_press(self):
        # This function will be registered with GlobalHotKeys
        # and called when the hotkey combination is pressed.
        # We will toggle the active state here.
        try:
            print(f"HOTKEY_MANAGER: Hotkey {self.hotkey_str} pressed! Current state: {self.hotkey_active}")
            if self.hotkey_active:
                print("Hotkey deactivated")
                self.on_deactivate()
                self.hotkey_active = False
            else:
                print("Hotkey activated")
                self.on_activate()
                self.hotkey_active = True
        except Exception as e:
            print(f"HOTKEY_MANAGER: Error in on_press: {e}")
            traceback.print_exc()

    def _handle_native_event(self, event):
        """Handle native macOS keyboard events from NSEvent monitor."""
        try:
            from Quartz import (
                NSEventTypeKeyDown,
                NSEventTypeKeyUp,
                NSEventTypeFlagsChanged,
            )

            event_type = event.type()
            key_code = event.keyCode()
            flags = event.modifierFlags()

            # Check current modifier state from event flags
            cmd_down = bool(flags & NSEventModifierFlagCommand)
            ctrl_down = bool(flags & NSEventModifierFlagControl)
            alt_down = bool(flags & NSEventModifierFlagOption)
            shift_down = bool(flags & NSEventModifierFlagShift)

            if event_type == NSEventTypeKeyDown:
                # Get the key name from keycode
                key_name = MACOS_KEY_CODES.get(key_code)

                if key_name and key_name == self._target_key:
                    # Check if modifiers match
                    current_mods = set()
                    if cmd_down:
                        current_mods.add('cmd')
                    if ctrl_down:
                        current_mods.add('ctrl')
                    if alt_down:
                        current_mods.add('alt')
                    if shift_down:
                        current_mods.add('shift')

                    if current_mods == self._target_modifiers:
                        print(f"HOTKEY_MANAGER: Native hotkey matched! key={key_name}, mods={current_mods}")
                        self.on_press()

        except Exception as e:
            print(f"HOTKEY_MANAGER: Error in native event handler: {e}")
            traceback.print_exc()

    def start_listening(self):
        import sys as _sys
        try:
            print(f"Starting hotkey listener for {self.hotkey_str}...")
            _sys.stdout.flush()

            # Validate hotkey format for macOS
            if sys.platform == "darwin" and "<fn>" in self.hotkey_str:
                print("HOTKEY_MANAGER: WARNING - Function key (fn) combinations may not work reliably on macOS")
                print("HOTKEY_MANAGER: Consider using <cmd>, <alt>, <ctrl>, or <shift> instead")

            # Use native NSEvent monitoring for bundled apps on macOS
            if self._use_native:
                print("HOTKEY_MANAGER: Using native NSEvent monitoring (bundled app mode)")
                _sys.stdout.flush()
                try:
                    from Quartz import (
                        NSEvent,
                        NSEventMaskKeyDown,
                        NSEventMaskFlagsChanged,
                    )

                    # Monitor key down and modifier changes
                    mask = NSEventMaskKeyDown | NSEventMaskFlagsChanged

                    self._native_monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
                        mask,
                        self._handle_native_event
                    )

                    if self._native_monitor:
                        print("HOTKEY_MANAGER: Native event monitor installed successfully")
                    else:
                        print("HOTKEY_MANAGER: WARNING - Native monitor returned None (check accessibility permissions)")
                    _sys.stdout.flush()
                    return
                except ImportError as ie:
                    print(f"HOTKEY_MANAGER: Quartz import failed, falling back to pynput: {ie}")
                    self._use_native = False
                except Exception as native_error:
                    print(f"HOTKEY_MANAGER: Native monitoring failed, falling back to pynput: {native_error}")
                    traceback.print_exc()
                    self._use_native = False

            # Fall back to pynput listener (for development/unbundled mode)
            print("HOTKEY_DEBUG: Starting pynput key listener...")
            _sys.stdout.flush()
            try:
                print("HOTKEY_DEBUG: Creating Listener object...")
                _sys.stdout.flush()
                self.listener = keyboard.Listener(
                    on_press=self._on_key_press_with_hotkey_detection,
                    on_release=self._on_key_release_with_hotkey_detection
                )
                print("HOTKEY_DEBUG: Listener created, calling start()...")
                _sys.stdout.flush()
                self.listener.start()
                print("HOTKEY_DEBUG: pynput key listener started successfully")
                _sys.stdout.flush()
            except Exception as debug_error:
                print(f"HOTKEY_DEBUG: Failed to start pynput listener: {debug_error}")
                _sys.stdout.flush()

        except Exception as e:
            print(f"HOTKEY_MANAGER: Error starting listener: {e}")
            print("HOTKEY_MANAGER: This might be due to:")
            print("  1. Missing accessibility permissions")
            print("  2. Invalid hotkey format")
            print("  3. Conflicting system hotkeys")
            traceback.print_exc()

    def stop_listening(self):
        try:
            # Stop native monitor if active
            if self._native_monitor:
                print("Stopping native event monitor...")
                try:
                    from Quartz import NSEvent
                    NSEvent.removeMonitor_(self._native_monitor)
                    self._native_monitor = None
                    print("Native event monitor stopped.")
                except Exception as e:
                    print(f"HOTKEY_MANAGER: Error stopping native monitor: {e}")

            # Stop pynput listener if active
            if self.listener:
                print("Stopping pynput hotkey listener...")
                self.listener.stop()
                # Don't join - let it stop asynchronously to avoid blocking issues
                # self.listener.join()
                self.listener = None
                print("Hotkey listener stopped.")

            if not self._native_monitor and not self.listener:
                print("HOTKEY_MANAGER: All listeners stopped")
        except Exception as e:
            print(f"HOTKEY_MANAGER: Error stopping listener: {e}")
            traceback.print_exc()

    def update_hotkey(self, new_hotkey_str: str) -> bool:
        """
        Update the hotkey at runtime.

        Updates the hotkey binding without restarting the listener.
        The listener passes events to self._hotkey, so we just need to
        update that object.
        """
        try:
            print(f"HOTKEY_MANAGER: Updating hotkey from '{self.hotkey_str}' to '{new_hotkey_str}'")

            # Update the hotkey string
            self.hotkey_str = new_hotkey_str
            self.hotkey_active = False  # Reset toggle state

            # Reconfigure the HotKey object (for pynput fallback)
            self._configure_hotkey()

            # Re-parse for native monitoring (in case we're using that)
            self._parse_hotkey_for_native()

            print(f"HOTKEY_MANAGER: Hotkey updated successfully to '{new_hotkey_str}'")
            return True
        except Exception as e:
            print(f"HOTKEY_MANAGER: Failed to update hotkey: {e}")
            traceback.print_exc()
            return False

    def _on_key_press_with_hotkey_detection(self, key):
        """Combined debug and hotkey detection"""
        try:
            print(f"HOTKEY_DEBUG: Key pressed: {key}")
            if hasattr(key, 'vk') and key.vk:
                print(f"HOTKEY_DEBUG: Virtual key code: {key.vk}")
            
            # Track modifier keys
            if key == keyboard.Key.cmd:
                self.cmd_pressed = True
                print("HOTKEY_DEBUG: Command key pressed")
            elif key == keyboard.Key.ctrl:
                self.ctrl_pressed = True
                print("HOTKEY_DEBUG: Control key pressed") 
            elif key == keyboard.Key.alt:
                self.alt_pressed = True
                print("HOTKEY_DEBUG: Alt key pressed")
            elif key == keyboard.Key.shift:
                self.shift_pressed = True
                print("HOTKEY_DEBUG: Shift key pressed")
            
            if self._hotkey is not None:
                normalized_key = self._normalize_hotkey_key(key)
                self._hotkey.press(normalized_key)
                
        except Exception as e:
            print(f"HOTKEY_DEBUG: Error in key press detection: {e}")

    def _on_key_release_with_hotkey_detection(self, key):
        """Combined debug and hotkey release detection"""
        try:
            print(f"HOTKEY_DEBUG: Key released: {key}")
            
            # Track modifier key releases
            if key == keyboard.Key.cmd:
                self.cmd_pressed = False
                print("HOTKEY_DEBUG: Command key released")
            elif key == keyboard.Key.ctrl:
                self.ctrl_pressed = False
                print("HOTKEY_DEBUG: Control key released")
            elif key == keyboard.Key.alt:
                self.alt_pressed = False
                print("HOTKEY_DEBUG: Alt key released")
            elif key == keyboard.Key.shift:
                self.shift_pressed = False
                print("HOTKEY_DEBUG: Shift key released")
                
            if self._hotkey is not None:
                normalized_key = self._normalize_hotkey_key(key)
                self._hotkey.release(normalized_key)

        except Exception as e:
            print(f"HOTKEY_DEBUG: Error in key release detection: {e}")

if __name__ == '__main__':
    # Example Usage (for testing hotkey_manager.py directly)
    def handle_activation():
        print("Activation callback triggered!")

    def handle_deactivation():
        print("Deactivation callback triggered!")

    # Define the hotkey, e.g., <cmd>+<shift>+h or <alt>+<space>
    # For Option+Space, use '<alt>+<space>'
    # For Command+Shift+D, use '<cmd>+<shift>+d'
    # Note: On macOS, 'alt' is the Option key.
    
    # Test with a more reliable hotkey combination for macOS
    test_hotkey = '<cmd>+<shift>+d'  # Command+Shift+D
    print(f"Testing with hotkey: {test_hotkey}")
    print("Press the hotkey to test, or Ctrl+C to exit")
    
    manager = HotkeyManager(test_hotkey, handle_activation, handle_deactivation)
    manager.start_listening()

    try:
        # Keep the main thread alive to allow the listener thread to run
        # In a real application, the main event loop (e.g., rumps) would do this.
        while True:
            pass
    except KeyboardInterrupt:
        manager.stop_listening()
        print("Exiting example.") 
