# setup.py  –  tested with py2app 0.28.8 & modulegraph2 2.2.1
import pathlib, sys, site
sys.setrecursionlimit(50_000)         # <-- happens before py2app loads

from setuptools import setup

APP_NAME = "YardTalk"
APP      = ["main.py"]
ICON     = "icon.icns"
MODEL    = pathlib.Path("parakeet-tdt-0.6b-v2/parakeet-tdt-0.6b-v2.nemo")

PY2APP_OPTS = dict(
    iconfile      = ICON,
    optimize      = 1,
    argv_emulation= False,            # Apple-Silicon console fix
    # explicitly include only what you really need
    packages      = [
        # core
        "rumps", "numpy", "sounddevice", "soundfile", "_soundfile_data",
        "pynput", "sympy", "IPython", "jedi", "PIL", "matplotlib",
        "numba", "llvmlite", "hydra",
        # heavy hitters that cause deep AST-trees → skip analysis
    ],
    # heavy hitters that cause deep AST-trees → skip analysis
    excludes      = [
        "sympy", "numba", "llvmlite", "IPython", "jedi",
        "sklearn", "tkinter", "hydra_plugins",
        "numpy.tests", "sympy.tests", "numba.tests",
        "matplotlib.tests", "pandas.tests",
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

setup(
    app          = APP,
    name         = APP_NAME,
    options      = {"py2app": PY2APP_OPTS},
    setup_requires = [
        "setuptools<71",              # avoids errno 17 race  [oai_citation:9‡Apple Developer](https://developer.apple.com/forums/thread/732314?utm_source=chatgpt.com)
        "py2app>=0.28.8",
        "modulegraph2>=2.2.1",        # recursion-bug fixes 
    ],
)