from pynput import keyboard

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
        if self.hotkey_active:
            print("Hotkey deactivated")
            self.on_deactivate()
            self.hotkey_active = False
        else:
            print("Hotkey activated")
            self.on_activate()
            self.hotkey_active = True

    def start_listening(self):
        print(f"Starting hotkey listener for {self.hotkey_str}...")
        # pynput's GlobalHotKeys expects a dictionary where keys are hotkey strings
        # and values are callback functions.
        hotkey_definition = {
            self.hotkey_str: self.on_press
        }
        self.listener = keyboard.GlobalHotKeys(hotkey_definition)
        self.listener.start() # This starts a new thread
        print("Hotkey listener started.")

    def stop_listening(self):
        if self.listener:
            print("Stopping hotkey listener...")
            self.listener.stop()
            self.listener.join() # Wait for the listener thread to finish
            self.listener = None
            print("Hotkey listener stopped.")

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
    manager = HotkeyManager('<alt>+<space>', handle_activation, handle_deactivation)
    manager.start_listening()

    try:
        # Keep the main thread alive to allow the listener thread to run
        # In a real application, the main event loop (e.g., rumps) would do this.
        while True:
            pass
    except KeyboardInterrupt:
        manager.stop_listening()
        print("Exiting example.") 