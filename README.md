# YardTalk

A macOS dictation app powered by NVIDIA's Parakeet ASR model. Speak naturally and have your words transcribed and typed directly into any application.

## Features

- **Local ASR Processing**: Uses NVIDIA Parakeet TDT 0.6B model - no cloud required, your audio stays on your device
- **Global Hotkey**: Press `Cmd+Shift+D` to start recording from anywhere
- **Auto-Send on Silence**: Automatically transcribes and types when you stop speaking (2 seconds of silence)
- **Visual Feedback**: Floating waveform overlay shows audio levels while recording
- **Universal Text Insertion**: Types transcribed text directly into the active application
- **Apple Silicon Optimized**: Runs on MPS (Metal Performance Shaders) for fast inference

## Requirements

- macOS 13.0 (Ventura) or later
- Apple Silicon Mac (M1/M2/M3) recommended for best performance
- ~2GB disk space for the ASR model
- Microphone access permission
- Accessibility permission (for global hotkeys and text insertion)

## Installation

### Pre-built App (Recommended)

1. Download `YardTalk.app` from the [Releases](https://github.com/performlikemj/transcription/releases) page
2. Move it to `/Applications/`
3. Launch YardTalk
4. Grant permissions when prompted (see [Permissions](#permissions) below)

### From Source

1. Clone the repository:
   ```bash
   git clone https://github.com/performlikemj/transcription.git
   cd transcription
   ```

2. Create and activate a virtual environment (Python 3.11 recommended):
   ```bash
   python3.11 -m venv .yardtalk
   source .yardtalk/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Download the Parakeet model:
   ```bash
   # Download from NVIDIA NGC or HuggingFace
   # Place in: parakeet-tdt-0.6b-v2/parakeet-tdt-0.6b-v2.nemo
   ```

5. Run the app:
   ```bash
   python main.py
   ```

### Building the App Bundle

To create a standalone macOS app:

```bash
source .yardtalk/bin/activate
python setup.py py2app
```

The built app will be in `dist/YardTalk.app`. Copy it to `/Applications/` to install:

```bash
cp -R dist/YardTalk.app /Applications/
```

## Usage

1. **Launch YardTalk** - The app appears in your Dock
2. **Grant permissions** when prompted (Microphone and Accessibility)
3. **Position your cursor** where you want text to appear
4. **Press `Cmd+Shift+D`** to start recording (waveform overlay appears)
5. **Speak naturally** - say what you want to type
6. **Stop speaking** - after 2 seconds of silence, the audio is automatically transcribed
7. **Text appears** at your cursor position

You can also press `Cmd+Shift+D` again to manually stop recording before the silence timeout.

## Permissions

YardTalk requires two permissions to function:

### Microphone Access
- **Why**: To capture your voice for transcription
- **Grant in**: System Settings > Privacy & Security > Microphone > Enable YardTalk

### Accessibility Access
- **Why**: To detect global hotkeys and type text into other applications
- **Grant in**: System Settings > Privacy & Security > Accessibility > Add YardTalk
- **Important**: After adding, toggle it OFF and ON, then restart the app

If hotkeys aren't working after granting permissions, try:
1. Remove YardTalk from Accessibility
2. Quit the app completely
3. Re-add YardTalk to Accessibility
4. Restart your Mac (sometimes required on newer macOS versions)

## Configuration

You can adjust silence detection settings in `main.py`:

```python
self.silence_threshold = 500  # RMS level for silence detection (0-32767)
self.silence_duration = 2.0   # Seconds of silence before auto-send
```

## Architecture

- `main.py` - Main application and menu bar integration via rumps
- `audio_manager.py` - Audio capture using sounddevice
- `asr_service.py` - ASR processing with NVIDIA NeMo/Parakeet
- `text_insertion_service.py` - Text typing via PyAutoGUI
- `overlay_window.py` - Native macOS floating waveform display
- `hotkey_manager.py` - Global hotkey handling via pynput
- `ui_config.py` - UI configuration (title, icon settings)

## Troubleshooting

### Hotkeys not working
- Ensure YardTalk is added to Accessibility permissions
- Try removing and re-adding the app to Accessibility
- Restart your Mac after changing permissions

### No audio detected
- Check that YardTalk has Microphone permission
- Verify your microphone is working in other apps
- Check System Settings > Sound > Input

### App not appearing in menu bar (macOS 14+)
- On newer macOS versions, the app appears in the Dock instead of the menu bar
- This is a known compatibility issue with rumps on macOS 14+

### Transcription is slow
- Apple Silicon Macs use MPS acceleration for fast inference
- Intel Macs will use CPU, which is significantly slower
- First transcription may be slower as the model warms up

## Known Issues

- Menu bar icon may not appear on macOS 14 (Sonoma) and later - app shows in Dock instead
- FFmpeg warnings in logs can be ignored (not required for core functionality)

## License

MIT License

## Acknowledgments

- [NVIDIA NeMo](https://github.com/NVIDIA/NeMo) for the Parakeet ASR model
- [rumps](https://github.com/jaredks/rumps) for macOS menu bar integration
- [PyObjC](https://pyobjc.readthedocs.io/) for native macOS window support
- [pynput](https://github.com/moses-palmer/pynput) for global hotkey detection
