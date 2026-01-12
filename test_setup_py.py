from pathlib import Path


def test_setup_py_signs_liblzma():
    text = Path("setup.py").read_text()
    assert "skip re-signing" not in text, "liblzma should be signed to avoid load failures"
