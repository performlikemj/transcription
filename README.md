# Transcription App (YardTalk)

This project is a small macOS menu bar application built with [rumps](https://github.com/jaredks/rumps) that records audio, transcribes it using NVIDIA NeMo's Parakeet-TDT model and types the text into the active window.

The repository already contains a `setup.py` for building a standalone `.app` bundle using **py2app**. The NeMo model itself is too large to keep in source control, so you need to download it before packaging.

## Getting Started

1. **Create a virtual environment** and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. **Download the Parakeet model**:

```bash
python scripts/download_parakeet_model.py
```

This will create a `parakeet-tdt-0.6b-v2` directory containing `parakeet-tdt-0.6b-v2.nemo`. The directory is already listed in `.gitignore` and will be bundled automatically by py2app.

3. **Build the macOS app**:

```bash
python setup.py py2app
```

The resulting application will be in the `dist` folder.

## Notes

- The project has been tested with `py2app 0.28.8` and `modulegraph2 2.2.1`.
- Ensure that you have the developer tools installed on macOS (Xcode command line tools) as py2app relies on them.

