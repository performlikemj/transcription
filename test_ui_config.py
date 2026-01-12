from ui_config import STATUS_TITLE, STATUS_USE_ICON


def test_status_title_is_set():
    assert STATUS_TITLE == "YT"


def test_status_use_icon_default_is_false():
    assert STATUS_USE_ICON is False
