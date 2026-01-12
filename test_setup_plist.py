from pathlib import Path


def test_setup_plist_sets_lsuielement():
    text = Path("setup.py").read_text()
    assert "LSUIElement" in text and "True" in text, "LSUIElement should be set to True in setup.py plist"
