from pathlib import Path

from app_paths import resolve_resource_path


def test_resolve_resource_path_for_source():
    source_dir = Path("/tmp/yardtalk-test")
    result = resolve_resource_path("menubar_icon.png", frozen=False, source_dir=source_dir)
    assert result == source_dir / "menubar_icon.png"


def test_resolve_resource_path_for_bundle():
    executable = "/Applications/YardTalk.app/Contents/MacOS/YardTalk"
    result = resolve_resource_path("menubar_icon.png", frozen=True, executable=executable)
    assert result == Path("/Applications/YardTalk.app/Contents/Resources/menubar_icon.png")
