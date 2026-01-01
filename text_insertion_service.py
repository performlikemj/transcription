from pynput.keyboard import Controller as KeyboardController
import time
import logging
import os

# Set up logging for text insertion service
log_file = os.path.expanduser("~/dictation_app.log")
logger = logging.getLogger('TextInsertionService')

def log_print(*args, **kwargs):
    """Custom print function that logs to file"""
    message = ' '.join(str(arg) for arg in args)
    logger.info(message)
    # Also print to console for backward compatibility
    import builtins
    builtins.print(*args, **kwargs)

# Replace print with our logging version for this module
print = log_print

class TextInsertionService:
    def __init__(self):
        self.keyboard = KeyboardController()
        self.pre_type_delay = 0.2  # Delay before starting to type (seconds)
        self.char_delay = 0.01   # Delay between each character (seconds)

    def insert_text(self, text_to_insert):
        if not text_to_insert:
            print("TextInsertionService: No text to insert.")
            return False # Explicitly return False

        print(f"TextInsertionService: Preparing to insert text: '{text_to_insert}'")
        
        time.sleep(self.pre_type_delay)

        try:
            print(f"TextInsertionService: Typing character by character: '{text_to_insert}'")
            for char in text_to_insert:
                self.keyboard.press(char)
                self.keyboard.release(char)
                time.sleep(self.char_delay) # Small delay after each character
            print("TextInsertionService: Text typed successfully.")
            return True
        except Exception as e:
            print(f"TextInsertionService: Error during keyboard typing: {e}")
            return False

if __name__ == '__main__':
    print("Testing TextInsertionService...")
    service = TextInsertionService()
    # service.pre_type_delay = 0.5 # Example: Increase pre-type delay if needed
    # service.char_delay = 0.05  # Example: Increase char delay if needed for very sensitive apps
    
    test_text = "Hello from TextInsertionService! This is a test. 123."
    
    print("Please focus a text editor or input field within the next 5 seconds.")
    print("The test text will be typed there.")
    time.sleep(5)
    
    print(f"Attempting to insert: '{test_text}'")
    if service.insert_text(test_text):
        print("Test insertion successful (check your focused text field).")
    else:
        print("Test insertion failed.")
    
    print("TextInsertionService test finished.") 