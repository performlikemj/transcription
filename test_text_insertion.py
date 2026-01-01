#!/usr/bin/env python3

import time
from text_insertion_service import TextInsertionService

print("Text insertion test starting in 3 seconds...")
print("Please place your cursor in a text editor or text field!")

time.sleep(3)

text_service = TextInsertionService()
test_text = "Hello from YardTalk dictation test!"

print(f"Attempting to type: '{test_text}'")
result = text_service.insert_text(test_text)

if result:
    print("✅ Text insertion successful!")
else:
    print("❌ Text insertion failed!") 