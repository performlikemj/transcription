from pathlib import Path


def test_setup_includes_ui_config_resource():
    text = Path("setup.py").read_text()
    assert "ui_config.py" in text, "ui_config.py should be included in setup.py resources"
