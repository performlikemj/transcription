# setup.py  –  tested with py2app 0.28.8 & modulegraph2 2.2.1
import pathlib, sys, site, pathlib
import importlib.resources as pkgres
import subprocess
sys.setrecursionlimit(50_000)         # <-- happens before py2app loads
from subprocess import check_call

from setuptools import setup

APP_NAME = "YardTalk"
APP      = ["main.py"]
ICON     = "icon.icns"
MODEL_DIR = "parakeet-tdt-0.6b-v2"  # Include the entire directory
MODEL_FILE = f"{MODEL_DIR}/parakeet-tdt-0.6b-v2.nemo"

def _patch_torio_docstring_issue():
    """
    Patch the torio module to handle None docstrings that cause AttributeError
    during py2app bundling. This fixes the 'NoneType' object has no attribute 'format' error.
    """
    try:
        # Import the problematic module
        import torio.io._streaming_media_decoder
        
        # Create a safe version of the decorator that handles None docstrings
        def safe_format_audio_args(**kwargs):
            def decorator(obj):
                # Only format docstring if it exists and is not None
                if hasattr(obj, '__doc__') and obj.__doc__ is not None:
                    try:
                        obj.__doc__ = obj.__doc__.format(**kwargs)
                    except (AttributeError, KeyError, ValueError, TypeError):
                        # If formatting fails for any reason, leave docstring unchanged
                        pass
                return obj
            return decorator
        
        # Replace the problematic function
        torio.io._streaming_media_decoder._format_audio_args = safe_format_audio_args
        print("✓ Successfully patched torio._format_audio_args to handle None docstrings")
            
    except ImportError as e:
        print(f"⚠️  Could not import torio for patching: {e}")
    except Exception as e:
        print(f"⚠️  Failed to patch torio: {e}")

def _patch_py2app_duplicate_dist_info():
    """
    Patch py2app to ignore duplicate dist-info directory creation when multiple
    paths resolve to the same metadata basename (e.g., packaging-*.dist-info).
    """
    try:
        import py2app.build_app as build_app

        original_mkdir = build_app.os.mkdir

        def safe_mkdir(path, mode=0o777):
            try:
                original_mkdir(path, mode)
            except FileExistsError:
                return

        build_app.os.mkdir = safe_mkdir
        print("✓ Patched py2app to ignore duplicate dist-info directories")
    except Exception as e:
        print(f"⚠️  Could not patch py2app dist-info handling: {e}")

# Apply the patch early, before py2app processes modules
if "py2app" in sys.argv:
    _patch_torio_docstring_issue()
    _patch_py2app_duplicate_dist_info()

PY2APP_OPTS = dict(
    iconfile      = ICON,
    optimize      = 1,
    argv_emulation= False,            # Apple-Silicon console fix
    # explicitly include only what you really need
    packages = [
        # --- core app ---
        "rumps","numpy","sounddevice","soundfile","_soundfile_data",
        "pynput","matplotlib",
        # --- NeMo ASR essentials ---
        "nemo","torch","torchaudio","torio","lightning","lhotse","braceexpand",
        "editdistance","librosa","pyloudnorm","pydub","resampy",
        "sentencepiece","sacremoses","inflect","num2words",
        "transformers","datasets","accelerate","webdataset",
        # --- data science (required by NeMo) ---
        "sklearn","scipy","pandas",
        # --- config and utilities ---
        "charset_normalizer","cytoolz","einops",
        "hydra","hydra._internal","omegaconf",
        "numba","llvmlite",
        # IPython needed by NeMo vad_utils
        "IPython",
    ],
    includes = [
        "jaraco.text",
        "jaraco.context",
        "jaraco.functools",
        "autocommand",
        "backports.tarfile",
        # sklearn submodules needed by NeMo
        "sklearn.metrics",
        "sklearn.metrics._ranking",
        "sklearn.utils",
        "sklearn.utils._param_validation",
    ],
    excludes = [
        # dev tools (IPython needed by NeMo vad_utils, jedi not needed)
        "jedi",
        "tkinter",
        # test suites (large, not needed)
        "numpy.tests","matplotlib.tests",
        "pandas.tests","scipy.tests","sklearn.tests",
        "torch.testing","numba.tests",
    ],
    resources   = [MODEL_FILE, "icon.png", "menubar_icon.png", "ui_config.py"],  # Include the model file and icons
    frameworks  = ["/opt/homebrew/lib/libsndfile.dylib"],
    site_packages = False,
    plist = {
        "CFBundleName":               APP_NAME,
        "CFBundleDisplayName":        APP_NAME,
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion":            "0.1.0",
        "LSMinimumSystemVersion":     "13.0",
        "LSUIElement":                False,  # Dock app (shows in Dock)
        "NSMainNibFile":              "",    # No nib - rumps creates UI programmatically
        "NSMicrophoneUsageDescription":
            "YardTalk needs microphone access to capture your speech for transcription.",
        "NSAccessibilityUsageDescription":
            "YardTalk needs accessibility access for global hotkeys and to type transcribed text into other applications.",
    },
)

TORCH_LIB = pathlib.Path(site.getsitepackages()[0]) / "torch" / "lib"

TORCH_DYLIBS = [
    TORCH_LIB / "libtorch_cpu.dylib",        # main symbols
    TORCH_LIB / "libtorch.dylib",            # symlink sometimes lost by py2app
    TORCH_LIB / "libtorch_python.dylib",     # Python <-> C++ bridge
    TORCH_LIB / "libc10.dylib",              # common backend
]

PY2APP_OPTS["frameworks"].extend(map(str, TORCH_DYLIBS))

PY2APP_OPTS["packages"].append("_sounddevice_data")

portaudio_lib = (
    pkgres.files("_sounddevice_data")
    / "portaudio-binaries"
    / "libportaudio.dylib"
)
PY2APP_OPTS["frameworks"].append(str(portaudio_lib))

def _fix_torio_rpaths(plat_app):
    """
    Fix rpath issues for torio .so files that can't find libtorch.dylib.
    """
    torio_lib_dir = (
        pathlib.Path(plat_app)
        / "Contents/Resources/lib/python3.11/torio/lib"
    )

    if not torio_lib_dir.exists():
        print(f"⚠️  torio/lib directory not found at {torio_lib_dir}")
        return

    # Fix all .so files in torio/lib
    for so_file in torio_lib_dir.glob("*.so"):
        print(f"Fixing rpath for {so_file.name}...")
        try:
            # Add rpath to torch/lib
            check_call([
                "install_name_tool",
                "-add_rpath",
                "@loader_path/../../torch/lib",
                str(so_file),
            ])
            # Change @rpath/libtorch.dylib to use loader_path
            check_call([
                "install_name_tool",
                "-change",
                "@rpath/libtorch.dylib",
                "@loader_path/../../torch/lib/libtorch_cpu.dylib",
                str(so_file),
            ])
            # Change @rpath/libtorch_python.dylib
            check_call([
                "install_name_tool",
                "-change",
                "@rpath/libtorch_python.dylib",
                "@loader_path/../../torch/lib/libtorch_python.dylib",
                str(so_file),
            ])
            # Re-sign
            check_call(["codesign", "--force", "-s", "-", "--timestamp=none", str(so_file)])
            print(f"✓ Fixed {so_file.name}")
        except subprocess.CalledProcessError as e:
            print(f"⚠️  Failed to fix {so_file.name}: {e}")


def _fix_torchaudio(plat_app):
    # First, fix the model directory structure
    import shutil

    # Ensure the model is in the correct location
    app_resources = pathlib.Path(plat_app) / "Contents/Resources"
    model_dest_dir = app_resources / MODEL_DIR
    model_dest_file = model_dest_dir / "parakeet-tdt-0.6b-v2.nemo"

    # Create the model directory if it doesn't exist
    model_dest_dir.mkdir(exist_ok=True)

    # Copy the model file if it's not already there or in the wrong place
    source_model = pathlib.Path(MODEL_FILE)
    if source_model.exists() and not model_dest_file.exists():
        print(f"Copying model from {source_model} to {model_dest_file}")
        shutil.copy2(str(source_model), str(model_dest_file))
        print(f"✓ Model copied to correct location")
    elif model_dest_file.exists():
        print(f"✓ Model already exists at {model_dest_file}")
    else:
        print(f"⚠️  Warning: Could not find source model at {source_model}")

    # Fix torio rpaths first (before torchaudio since torchaudio may depend on it)
    _fix_torio_rpaths(plat_app)

    # Continue with torchaudio fixes
    so = (
        pathlib.Path(plat_app)
        / "Contents/Resources/lib/python3.11/torchaudio/lib/libtorchaudio.so"
    )
    # 1) Patch the bad rpath reference
    check_call(
        [
            "install_name_tool",
            "-change",
            "@rpath/libtorch.dylib",
            "@loader_path/../../torch/lib/libtorch_cpu.dylib",
            str(so),
        ]
    )
    # 1‑b) Add torch/lib to this binary's runtime search paths (idempotent)
    check_call(
        [
            "install_name_tool",
            "-add_rpath",
            "@loader_path/../../torch/lib",
            str(so),
        ]
    )
    # 2) Re‑sign the modified torchaudio binary
    check_call(["codesign", "--force", "-s", "-", "--timestamp=none", str(so)])

    # ---------- patch PyTorch's C++ extension that depends on libtorchaudio ----------
    ext_so = (
        pathlib.Path(plat_app)
        / "Contents/Resources/lib/python3.11/torchaudio/lib/_torchaudio.so"
    )
    # rewrite dependency to use loader_path (avoids @rpath lookup)
    check_call(
        [
            "install_name_tool",
            "-change",
            "@rpath/libtorchaudio.so",
            "@loader_path/libtorchaudio.so",
            str(ext_so),
        ]
    )
    # --- libtorch_python.dylib ------------------
    check_call([
        "install_name_tool",
        "-change",
        "@rpath/libtorch_python.dylib",
        "@loader_path/../../torch/lib/libtorch_python.dylib",
        str(ext_so),
    ])
    check_call([
        "install_name_tool",
        "-add_rpath",
        "@loader_path/../../torch/lib",
        str(ext_so),
    ])
    # ensure the same rpath as above for consistency
    check_call(
        [
            "install_name_tool",
            "-add_rpath",
            "@loader_path",
            str(ext_so),
        ]
    )
    # re‑sign the patched extension
    check_call(["codesign", "--force", "-s", "-", "--timestamp=none", str(ext_so)])
    
    # ---------- Fix liblzma.5.dylib issue ----------
    frameworks_dir = pathlib.Path(plat_app) / "Contents/Frameworks"
    liblzma_path = frameworks_dir / "liblzma.5.dylib"
    
    if liblzma_path.exists():
        print(f"Found liblzma.5.dylib, replacing with fresh copy from Homebrew...")
        # Replace with a fresh copy from Homebrew
        homebrew_liblzma = pathlib.Path("/opt/homebrew/lib/liblzma.5.dylib")
        if homebrew_liblzma.exists():
            import shutil
            shutil.copy2(str(homebrew_liblzma), str(liblzma_path))
            print(f"✓ Replaced liblzma.5.dylib with fresh copy")
            subprocess.run(["xattr", "-cr", str(liblzma_path)], check=False)
            subprocess.run(["codesign", "--remove-signature", str(liblzma_path)], check=False)
            check_call(["codesign", "--force", "-s", "-", "--timestamp=none", str(liblzma_path)])
        else:
            print(f"⚠️  Could not find Homebrew liblzma.5.dylib at {homebrew_liblzma}")
    
    # --- codesign every dylib under Contents/Frameworks ---
    if frameworks_dir.exists():
        for dylib in frameworks_dir.glob("*.dylib"):
            # Clear any Finder metadata or quarantine flags
            subprocess.run(["xattr", "-cr", str(dylib)], check=False)

            # Remove any existing signature
            subprocess.run(["codesign", "--remove-signature", str(dylib)], check=False)

            # Sign the library
            try:
                check_call(
                    ["codesign", "--force", "-s", "-", "--timestamp=none", str(dylib)]
                )
                print(f"✓ Successfully signed {dylib.name}")
            except subprocess.CalledProcessError as e:
                print(f"⚠️  Could not sign {dylib.name}: {e}")
    
    # remove Finder metadata that can break codesign
    subprocess.run(["xattr", "-cr", str(plat_app)], check=False)
    
    # Re-sign the top-level bundle
    try:
        check_call(
            [
                "codesign",
                "--force",
                "-s",
                "-",
                "--timestamp=none",
                str(plat_app),
            ]
        )
        print("✓ Successfully signed the app bundle")
    except Exception as e:
        print("⚠️  Warning: shallow codesign of bundle failed – continuing:", e)


def _copy_pkg_resources_deps(plat_app):
    """
    Copy namespace packages required by pkg_resources that py2app misses
    (jaraco.* + backports.tarfile + autocommand).
    """
    import shutil

    app_site = pathlib.Path(plat_app) / "Contents/Resources/lib/python3.11"
    venv_site = pathlib.Path(site.getsitepackages()[0])
    for pkg_name in ("jaraco", "backports", "autocommand"):
        src = venv_site / pkg_name
        dest = app_site / pkg_name
        if not src.exists():
            print(f"⚠️  Warning: missing {pkg_name} in venv at {src}")
            continue
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        print(f"✓ Copied {pkg_name} to app bundle")

 # --- patch py2app *after* it finishes building the .app bundle ---
if "py2app" in sys.argv:
    from py2app.build_app import py2app as _py2app

    _orig_run = _py2app.run

    def run(self):
        _orig_run(self)  # let py2app build everything first
        built_app = pathlib.Path("dist") / f"{APP_NAME}.app"
        _copy_pkg_resources_deps(built_app)
        _fix_torchaudio(built_app)

    _py2app.run = run

setup(
    app          = APP,
    name         = APP_NAME,
    options      = {"py2app": PY2APP_OPTS},
    setup_requires = [
        "py2app>=0.28.8",
        "modulegraph2>=2.2.1",        # recursion-bug fixes 
    ],
)
