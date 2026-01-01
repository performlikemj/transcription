# YardTalk

A macOS dictation app powered by NVIDIA's Parakeet ASR model. Speak naturally and have your words transcribed and typed directly into any application.

## Features

- **Local ASR Processing**: Uses NVIDIA Parakeet TDT 0.6B model - no cloud required, your audio stays on your device
- **Global Hotkey**: Press `Cmd+Shift+D` to start/stop recording from anywhere
- **Menu Bar App**: Unobtrusive menu bar presence with easy toggle
- **Visual Feedback**: Floating waveform overlay shows audio levels while recording
- **Universal Text Insertion**: Types transcribed text directly into the active application

## Requirements

- macOS 12.0 or later (Apple Silicon recommended)
- Microphone access permission
- Accessibility permission (for text insertion)

## Installation

### From Source

1. Clone the repository:
   ```bash
   git clone https://github.com/performlikemj/transcription.git
   cd transcription
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .yardtalk
   source .yardtalk/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Download the Parakeet model:
   ```bash
   python scripts/download_parakeet_model.py
   ```

5. Run the app:
   ```bash
   python main.py
   ```

### Building the App Bundle

To create a standalone macOS app:

```bash
python setup.py py2app
```

The built app will be in `dist/YardTalk.app`. Copy it to `/Applications/` to install.

## Usage

1. Launch YardTalk - it appears in your menu bar as "Dictation App"
2. Grant microphone and accessibility permissions when prompted
3. Position your cursor where you want text to appear
4. Press `Cmd+Shift+D` to start recording (waveform overlay appears)
5. Speak naturally
6. Press `Cmd+Shift+D` again to stop and transcribe
7. Your spoken words are typed at the cursor position

## Permissions

YardTalk requires:

- **Microphone**: To capture your voice for transcription
- **Accessibility**: To type text into other applications

Grant these in System Settings > Privacy & Security.

## Architecture

- `main.py` - Main application, menu bar integration via rumps
- `audio_manager.py` - Audio capture using sounddevice
- `asr_service.py` - ASR processing with NVIDIA NeMo/Parakeet
- `text_insertion_service.py` - Text typing via PyAutoGUI
- `overlay_window.py` - Native macOS floating waveform display
- `hotkey_manager.py` - Global hotkey handling via pynput

## License

MIT License

## Acknowledgments

- [NVIDIA NeMo](https://github.com/NVIDIA/NeMo) for the Parakeet ASR model
- [rumps](https://github.com/jaredks/rumps) for macOS menu bar integration
- [PyObjC](https://pyobjc.readthedocs.io/) for native macOS window support
