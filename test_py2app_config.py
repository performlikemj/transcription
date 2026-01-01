from pathlib import Path


def test_py2app_avoids_system_site_packages():
    text = Path("setup.py").read_text()
    assert "site_packages = False" in text or "site_packages=False" in text


def test_py2app_handles_duplicate_dist_info_dirs():
    text = Path("setup.py").read_text()
    assert "py2app.build_app" in text and "FileExistsError" in text


def test_py2app_includes_pkg_resources_deps():
    text = Path("setup.py").read_text()
    assert "jaraco.text" in text


def _extract_list_block(text: str, name: str) -> str:
    start = text.find(f"{name} = [")
    assert start != -1, f"missing {name} list"
    end = text.find("]", start)
    assert end != -1, f"unterminated {name} list"
    return text[start:end + 1]


def test_py2app_copies_pkg_resources_deps():
    text = Path("setup.py").read_text()
    assert "copy_pkg_resources_deps" in text or "copy_pkg_resources_dependencies" in text


def test_py2app_does_not_exclude_sympy():
    text = Path("setup.py").read_text()
    excludes_block = _extract_list_block(text, "excludes")
    assert "\"sympy\"" not in excludes_block and "'sympy'" not in excludes_block


def test_py2app_does_not_exclude_numba():
    text = Path("setup.py").read_text()
    excludes_block = _extract_list_block(text, "excludes")
    assert "\"numba\"" not in excludes_block and "'numba'" not in excludes_block
