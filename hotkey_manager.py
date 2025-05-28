from pynput import keyboard
import traceback

class HotkeyManager:
    def __init__(self, hotkey_str, on_activate, on_deactivate):
        self.hotkey_str = hotkey_str
        self.on_activate = on_activate
        self.on_deactivate = on_deactivate # Placeholder for future use
        self.listener = None
        self.hotkey_active = False

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
        try:
            print(f"Starting hotkey listener for {self.hotkey_str}...")
            # pynput's GlobalHotKeys expects a dictionary where keys are hotkey strings
            # and values are callback functions.
            hotkey_definition = {
                self.hotkey_str: self.on_press
            }
            self.listener = keyboard.GlobalHotKeys(hotkey_definition)
            self.listener.start() # This starts a new thread
            print("Hotkey listener started.")
            
            # Check if the listener is actually running
            if hasattr(self.listener, '_thread') and self.listener._thread:
                print(f"HOTKEY_MANAGER: Listener thread is alive: {self.listener._thread.is_alive()}")
            else:
                print("HOTKEY_MANAGER: Warning - No listener thread found")
                
        except Exception as e:
            print(f"HOTKEY_MANAGER: Error starting listener: {e}")
            traceback.print_exc()

    def stop_listening(self):
        try:
            if self.listener:
                print("Stopping hotkey listener...")
                self.listener.stop()
                self.listener.join() # Wait for the listener thread to finish
                self.listener = None
                print("Hotkey listener stopped.")
            else:
                print("HOTKEY_MANAGER: No listener to stop")
        except Exception as e:
            print(f"HOTKEY_MANAGER: Error stopping listener: {e}")
            traceback.print_exc()

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
    manager = HotkeyManager('<fn>+<ctrl>+<space>', handle_activation, handle_deactivation)
    manager.start_listening()

    try:
        # Keep the main thread alive to allow the listener thread to run
        # In a real application, the main event loop (e.g., rumps) would do this.
        while True:
            pass
    except KeyboardInterrupt:
        manager.stop_listening()
        print("Exiting example.") 