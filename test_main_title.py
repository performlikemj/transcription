from pathlib import Path


def test_main_sets_status_title_explicitly():
    text = Path("main.py").read_text()
    assert "self.title = STATUS_TITLE" in text
