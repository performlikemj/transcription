# YardTalk

A macOS dictation app powered by NVIDIA's Parakeet ASR model. Speak naturally and have your words transcribed and typed directly into any application. All processing happens locally on your Mac - no cloud services required.

## Features

- **Local ASR Processing**: Uses NVIDIA Parakeet TDT 0.6B model - no cloud required, your audio stays on your device
- **Global Hotkey**: Press `Cmd+Shift+D` to start recording from anywhere
- **Auto-Send on Silence**: Automatically transcribes and types when you stop speaking (2 seconds of silence)
- **Visual Feedback**: Floating waveform overlay shows audio levels while recording
- **Correction Window**: Review and edit transcribed text before insertion
- **Transcription History**: Access recent transcriptions from the menu
- **Universal Text Insertion**: Types transcribed text directly into the active application
- **Apple Silicon Optimized**: Runs on MPS (Metal Performance Shaders) for fast inference

## Requirements

- macOS 13.0 (Ventura) or later
- Apple Silicon Mac (M1/M2/M3) recommended for best performance
- ~2GB disk space for the ASR model
- Python 3.11 (for building from source)

## Installation

### From Source

1. **Clone the repository:**
   ```bash
   git clone https://github.com/performlikemj/transcription.git
   cd transcription
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3.11 -m venv .yardtalk
   source .yardtalk/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Download the Parakeet ASR model:**

   The app uses NVIDIA's Parakeet TDT model. Download from HuggingFace:

   ```bash
   # Download using huggingface-cli (install with: pip install huggingface_hub)
   huggingface-cli download nvidia/parakeet-tdt-0.6b-v3 \
     --local-dir parakeet-tdt-0.6b-v3 \
     --include "*.nemo"
   ```

   Or download manually from https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3/tree/main

   The app automatically detects any `parakeet-tdt-*` directory in the project root, so newer model versions work without code changes.

5. **Run the app:**
   ```bash
   python main.py
   ```

### Building the macOS App Bundle

To create a standalone `.app` that you can install in `/Applications`:

```bash
# Make sure you're in the virtual environment
source .yardtalk/bin/activate

# Build the app bundle
python setup.py py2app
```

The build process takes several minutes as it bundles Python, PyTorch, and all dependencies. The built app will be in `dist/YardTalk.app`.

**Install to Applications:**
```bash
cp -R dist/YardTalk.app /Applications/
```

## Permissions

YardTalk requires **three** system permissions to function properly:

### 1. Microphone Access
- **Why**: To capture your voice for transcription
- **Grant in**: System Settings > Privacy & Security > Microphone > Enable YardTalk

### 2. Accessibility Access
- **Why**: To type transcribed text into other applications
- **Grant in**: System Settings > Privacy & Security > Accessibility > Add YardTalk

### 3. Input Monitoring
- **Why**: To detect global hotkey presses (may be required depending on macOS version)
- **Grant in**: System Settings > Privacy & Security > Input Monitoring > Add YardTalk
- **Note**: The bundled app uses native macOS event monitoring which may work without this permission, but grant it if hotkeys don't respond

**Important**: After granting Accessibility and Input Monitoring permissions:
1. Toggle each permission OFF and then ON again
2. Quit YardTalk completely (Cmd+Q or right-click Dock icon > Quit)
3. Relaunch YardTalk

If hotkeys still don't work, try restarting your Mac (sometimes required on newer macOS versions).

## Usage

1. **Launch YardTalk** - The app appears in your Dock
2. **Grant permissions** when prompted (Microphone, Accessibility, and Input Monitoring)
3. **Position your cursor** where you want text to appear
4. **Press `Cmd+Shift+D`** to start recording (waveform overlay appears)
5. **Speak naturally** - say what you want to type
6. **Stop speaking** - after 2 seconds of silence, the audio is automatically transcribed
7. **Review and edit** the transcription in the correction window
8. **Click "Send"** (or press Enter) to insert the text

You can also:
- Press `Cmd+Shift+D` again to manually stop recording before the silence timeout
- Click "Toggle Dictation" in the Dock menu or Dictation menu
- Press `Escape` in the correction window to discard the transcription

## Configuration

### Changing the Hotkey

1. Open YardTalk
2. Press `Cmd+,` or go to YardTalk menu > Settings
3. Enter a new hotkey combination (e.g., `<cmd>+<shift>+d` or `<alt>+<space>`)
4. Click Save

### Silence Detection Settings

You can adjust silence detection in `main.py`:

```python
self.silence_threshold = 150  # RMS level for silence detection (lower = more sensitive)
self.silence_duration = 2.0   # Seconds of silence before auto-send
```

## Troubleshooting

### Hotkeys not working

This is usually a permissions issue:

1. **Check both permissions**: Ensure YardTalk is in both Accessibility AND Input Monitoring
2. **Toggle permissions**: Turn each permission OFF, then ON again
3. **Restart the app**: Quit completely (Cmd+Q) and relaunch
4. **Restart Mac**: Sometimes required after permission changes on newer macOS

### No audio detected

1. Check that YardTalk has Microphone permission
2. Verify your microphone works in other apps (Voice Memos, etc.)
3. Check System Settings > Sound > Input - ensure correct mic is selected

### Transcription is slow

- Apple Silicon Macs use MPS acceleration for fast inference (~1-2 seconds)
- Intel Macs use CPU only, which is significantly slower (~10-30 seconds)
- The first transcription after launch may be slower as the model warms up

### App crashes on launch

1. Check logs at `~/Library/Logs/YardTalk/dictation_app.log`
2. Ensure the Parakeet model file exists at the expected path
3. Try running from source (`python main.py`) to see error messages

### "ASR Initializing..." stays indefinitely

The ASR model takes 10-30 seconds to load on first launch. If it doesn't complete:
1. Check you have enough RAM (model requires ~2GB)
2. Look for errors in the log file
3. Try running from source to see detailed output

## Architecture

```
main.py (DictationApp)
├── HotkeyManager       - Global hotkey detection (native NSEvent in app, pynput in dev)
├── AudioManager        - Microphone capture via sounddevice (threaded)
├── ASRService          - Speech recognition via NeMo (worker thread)
├── TextInsertionService - Keyboard input simulation via pynput
├── OverlayWindow       - Native macOS floating waveform (PyObjC/AppKit)
├── CorrectionWindow    - Text review/editing with timestamp display
├── SettingsManager     - Persistent settings via NSUserDefaults
└── PreferencesWindow   - Settings UI for hotkey configuration
```

## Development

### Running Tests

```bash
source .yardtalk/bin/activate
pytest
```

### Project Structure

- `main.py` - Main application and rumps integration
- `audio_manager.py` - Audio capture using sounddevice
- `asr_service.py` - ASR processing with NVIDIA NeMo/Parakeet
- `transcription_result.py` - Transcription data with word/segment timestamps
- `text_insertion_service.py` - Text typing via pynput
- `overlay_window.py` - Native macOS floating waveform display
- `correction_window.py` - Text review/editing window with timestamp view
- `hotkey_manager.py` - Global hotkey handling (native NSEvent / pynput)
- `settings_manager.py` - UserDefaults-based settings persistence
- `preferences_window.py` - Settings UI
- `transcription_history.py` - Recent transcriptions management
- `setup.py` - py2app build configuration

## Known Issues

- Menu bar icon may not appear on macOS 14 (Sonoma) and later - app shows in Dock instead
- FFmpeg warnings in logs can be ignored (not required for core functionality)
- After rebuilding the app, you may need to re-grant Accessibility and Input Monitoring permissions

## License

MIT License

## Acknowledgments

- [NVIDIA NeMo](https://github.com/NVIDIA/NeMo) for the Parakeet ASR model
- [rumps](https://github.com/jaredks/rumps) for macOS menu bar integration
- [PyObjC](https://pyobjc.readthedocs.io/) for native macOS window and event support
- [pynput](https://github.com/moses-palmer/pynput) for keyboard input simulation
