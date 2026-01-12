# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YardTalk is a macOS dictation app powered by NVIDIA's Parakeet ASR model. It captures speech via global hotkeys, transcribes locally using NeMo/PyTorch, and types the result into the active application. No cloud services required.

**Stack:** Python 3.11 + PyTorch + NeMo ASR + rumps (menu bar) + PyObjC (native macOS UI) + pynput (hotkeys)

## Common Commands

```bash
# Development
source .yardtalk/bin/activate    # Activate virtual environment
python main.py                   # Run from source

# Testing
pytest                           # Run all tests
pytest test_audio_manager.py     # Run single test file
pytest -k "test_name"            # Run specific test by name

# Build macOS app bundle
python setup.py py2app           # Creates dist/YardTalk.app
cp -R dist/YardTalk.app /Applications/  # Install
```

## Architecture

The app follows a service-oriented architecture with clear separation of concerns:

```
main.py (DictationApp)
├── HotkeyManager       - Global hotkey detection via pynput
├── AudioManager        - Microphone capture via sounddevice (threaded)
├── ASRService          - Speech recognition via NeMo (worker thread)
├── TextInsertionService - Keyboard input simulation via pynput
├── OverlayWindow       - Native macOS floating waveform (PyObjC/AppKit)
├── SettingsManager     - Persistent settings via NSUserDefaults
└── PreferencesWindow   - Settings UI
```

### Key Patterns

**Thread Safety:** The app runs on rumps' main thread but uses worker threads for audio and ASR:
- `AudioManager._recording_loop()` runs in a background thread
- `ASRService._asr_worker_loop()` handles all model operations in a dedicated thread
- Cross-thread communication uses `AppHelper.callAfter()` to dispatch to the main thread
- `rumps.Timer` is used to process ASR results on the main thread

**State Machine:** Dictation has multiple states tracked by `DictationApp`:
- `asr_model_status`: "initializing" | "loaded" | "error"
- `dictation_active`: Whether recording is active
- `is_transcribing`: Whether ASR is processing audio
- `hotkey_manager.hotkey_active`: Toggle state of the hotkey

**Audio Flow:**
1. Hotkey activates → `AudioManager.start_recording()`
2. Audio chunks → `_process_audio_chunk()` → buffered in `ASRService`
3. Silence detected (2s) or hotkey deactivates → stop recording
4. Audio submitted to ASR worker thread → transcription returned via callback
5. Text inserted via `TextInsertionService`

### py2app Build System

`setup.py` contains extensive configuration for bundling with py2app:
- Patches for torio/torchaudio rpath issues
- Dynamic library signing and copying
- Model file placement in Resources
- Torch dylib framework handling

## Testing Notes

- Some tests require GUI interaction and are excluded via `conftest.py`
- Tests run without the ASR model loaded (mock where needed)
- Use `pytest -v` for verbose output showing pass/fail per test

## macOS Permissions

The app requires two system permissions:
- **Microphone:** For audio capture
- **Accessibility:** For global hotkeys and text insertion

## Agent Protocol (MANDATORY)

**CRITICAL: Before starting ANY work, you MUST:**

1. **Read `AGENTS.md`** - Contains operating principles, ledger protocol, and task flow rules
2. **Read `CONTINUITY.md`** - Master ledger with current project state and active tasks
3. **Check for active planning ledgers** in `ledgers/` directory

**This is not optional.** These files are the single source of truth for project state.

### Key Rules from AGENTS.md

- **Ledger-first:** Update CONTINUITY.md when state changes (goals, decisions, blockers)
- **Task statuses:** `pending` → `ready` → `in-progress` → `complete`
- **Quality bar:** Tests must pass before marking work complete
- **Trivial tasks** (<15 min, single file): Log one-liner in CONTINUITY.md Trivial Log

### Ralph Autonomous Mode

When running via `./scripts/ralph/ralph.sh`:
- Pick ONLY `ready` tasks from the active planning ledger
- Complete ONE task per iteration
- Update ledger status and commit after each task
- Output `<ralph>COMPLETE</ralph>` when all tasks done
- Output `<ralph>STOP</ralph>` when blocked
