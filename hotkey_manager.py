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

class HotkeyManager:
    def __init__(self, hotkey_str, on_activate, on_deactivate):
        self.hotkey_str = hotkey_str
        self.on_activate = on_activate
        self.on_deactivate = on_deactivate # Placeholder for future use
        self.listener = None
        self.hotkey_active = False
        self._hotkey = None
        
        # Track modifier keys for combination detection
        self.cmd_pressed = False
        self.ctrl_pressed = False
        self.alt_pressed = False
        self.shift_pressed = False
        
        # Check accessibility permissions on macOS
        self._check_accessibility_permissions()
        self._configure_hotkey()

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

    def start_listening(self):
        import sys as _sys
        try:
            print(f"Starting hotkey listener for {self.hotkey_str}...")
            _sys.stdout.flush()

            # Validate hotkey format for macOS
            if sys.platform == "darwin" and "<fn>" in self.hotkey_str:
                print("HOTKEY_MANAGER: WARNING - Function key (fn) combinations may not work reliably on macOS")
                print("HOTKEY_MANAGER: Consider using <cmd>, <alt>, <ctrl>, or <shift> instead")

            # Since GlobalHotKeys doesn't work well with F9, use direct key listener
            print("HOTKEY_DEBUG: Starting direct F9 key listener...")
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
                print("HOTKEY_DEBUG: Direct key listener started successfully")
                _sys.stdout.flush()
            except Exception as debug_error:
                print(f"HOTKEY_DEBUG: Failed to start direct listener: {debug_error}")
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
            if self.listener:
                print("Stopping hotkey listener...")
                self.listener.stop()
                # Don't join - let it stop asynchronously to avoid blocking issues
                # self.listener.join()
                self.listener = None
                print("Hotkey listener stopped.")
            else:
                print("HOTKEY_MANAGER: No listener to stop")
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

            # Reconfigure the HotKey object (listener will use the new binding)
            self._configure_hotkey()

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
