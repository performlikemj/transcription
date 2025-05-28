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
MODEL    = pathlib.Path("parakeet-tdt-0.6b-v2/parakeet-tdt-0.6b-v2.nemo")

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

# Apply the patch early, before py2app processes modules
if "py2app" in sys.argv:
    _patch_torio_docstring_issue()

PY2APP_OPTS = dict(
    iconfile      = ICON,
    optimize      = 1,
    argv_emulation= False,            # Apple-Silicon console fix
    # explicitly include only what you really need
    packages = [
        # --- core ---
        "rumps","numpy","sounddevice","soundfile","_soundfile_data",
        "pynput","matplotlib",
        # --- NeMo ASR essentials ---
        "nemo","torch","torchaudio","lightning","lhotse","braceexpand",
        "editdistance","librosa","pyloudnorm","pydub","resampy",
        "sentencepiece","sacremoses","inflect","num2words",
        "transformers","datasets","accelerate",
        # utility libs already present
        "charset_normalizer","cytoolz","einops",
        "hydra",
        "hydra._internal",
    ],
    excludes = [
        # heavy science libs you don't need in production
        "sympy","numba","llvmlite","IPython","jedi","sklearn",
        "tkinter","numpy.tests","matplotlib.tests",
        "pandas.tests","scipy.tests",
    ],
    resources   = [str(MODEL)],
    frameworks  = ["/opt/homebrew/lib/libsndfile.dylib"],
    site_packages = True,
    plist = {
        "CFBundleName":               APP_NAME,
        "CFBundleDisplayName":        APP_NAME,
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion":            "0.1.0",
        "LSMinimumSystemVersion":     "13.0",
        "NSMicrophoneUsageDescription":
            "Speech to text for YardTalk",
    },
)

TORCH_LIB = pathlib.Path(site.getsitepackages()[0]) / "torch" / "lib"

TORCH_DYLIBS = [
    TORCH_LIB / "libtorch_cpu.dylib",        # main symbols
    TORCH_LIB / "libtorch.dylib",            # symlink sometimes lost by py2app
    TORCH_LIB / "libtorch_python.dylib",     # Python <-> C++ bridge
    TORCH_LIB / "libc10.dylib",              # common backend
]

TORCH_DYLIBS.append(TORCH_LIB / "libtorch_python.dylib")

PY2APP_OPTS["frameworks"].extend(map(str, TORCH_DYLIBS))

PY2APP_OPTS["packages"].append("_sounddevice_data")

portaudio_lib = (
    pkgres.files("_sounddevice_data")
    / "portaudio-binaries"
    / "libportaudio.dylib"
)
PY2APP_OPTS["frameworks"].append(str(portaudio_lib))

def _fix_torchaudio(plat_app):
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

 # --- patch py2app *after* it finishes building the .app bundle ---
if "py2app" in sys.argv:
    from py2app.build_app import py2app as _py2app

    _orig_run = _py2app.run

    def run(self):
        _orig_run(self)  # let py2app build everything first
        built_app = pathlib.Path("dist") / f"{APP_NAME}.app"
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