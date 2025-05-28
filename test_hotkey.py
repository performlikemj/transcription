#!/usr/bin/env python3

import sys
sys.path.insert(0, '.')
from hotkey_manager import HotkeyManager
import time

def test_callback():
    print('HOTKEY TEST: Callback triggered!')

print('Testing hotkey manager...')
hm = HotkeyManager('<ctrl>+<alt>+<space>', test_callback, test_callback)
hm.start_listening()
print('Hotkey listener started. Press Ctrl+Alt+Space to test.')
print('Waiting 10 seconds for hotkey test...')

try:
    time.sleep(10)
except KeyboardInterrupt:
    print('Test interrupted.')

hm.stop_listening()
print('Test complete.') 