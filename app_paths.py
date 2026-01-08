from pathlib import Path
import sys


def _bundle_root(executable=None):
    executable_path = Path(executable or sys.executable).resolve()
    return executable_path.parents[1]


def resolve_resource_path(name, frozen=None, executable=None, source_dir=None):
    is_frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    if is_frozen:
        return _bundle_root(executable) / "Resources" / name

    base_dir = Path(source_dir) if source_dir is not None else Path(__file__).resolve().parent
    return base_dir / name
