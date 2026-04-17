"""File system paths and directory resolution."""
import sys
import os
import re
import platform
from pathlib import Path


def _bundle_dir() -> str:
    """Return the directory containing bundled app resources."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(os.path.join(__file__, "..", "..")))


def _app_dir() -> str:
    """Return the directory containing the running script or built executable."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(os.path.join(__file__, "..", "..")))


def _read_app_version() -> str:
    """Read the app version from the shared VERSION file."""
    candidates = [
        Path(_bundle_dir()) / "VERSION",
        Path(_app_dir()) / "VERSION",
        Path(__file__).resolve().parent.parent.parent.parent / "VERSION",
    ]
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text
    return "dev"


# ── Platform-dependent directories ───────────────────────────────────────────

if platform.system() == "Linux":
    APPDATA_SAVE_DIR = os.path.join(
        str(Path.home()), ".steam", "steam", "steamapps",
        "compatdata", "686060", "pfx", "drive_c", "users", "steamuser", "AppData", "Roaming",
        "Glaiel Games", "Mewgenics",
    )
    APPDATA_CONFIG_DIR = os.path.join(
        str(Path.home()), "MewgenicsBreedingManager",
    )
else:
    APPDATA_SAVE_DIR = os.path.join(
        os.environ.get("APPDATA", ""),
        "Glaiel Games", "Mewgenics",
    )
    APPDATA_CONFIG_DIR = os.path.join(
        os.environ.get("APPDATA", str(Path.home())),
        "MewgenicsBreedingManager",
    )
os.makedirs(APPDATA_CONFIG_DIR, exist_ok=True)
APP_CONFIG_PATH = os.path.join(APPDATA_CONFIG_DIR, "settings.json")
LOCALES_DIR = os.path.join(_bundle_dir(), "locales")
APP_VERSION = _read_app_version()


def _steam_library_paths() -> list[str]:
    candidates = [
        os.path.join(
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            "Steam",
            "steamapps",
            "libraryfolders.vdf",
        ),
        os.path.join(
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            "Steam",
            "steamapps",
            "libraryfolders.vdf",
        ),
        os.path.join(
            str(Path.home()),
            ".steam",
            "steam",
            "steamapps",
            "libraryfolders.vdf",
        ),
    ]
    libraries: list[str] = []
    for vdf_path in candidates:
        if not os.path.exists(vdf_path):
            continue
        try:
            with open(vdf_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            for match in re.finditer(r'"path"\s+"([^"]+)"', content):
                path = match.group(1).replace("\\\\", "\\")
                if path not in libraries:
                    libraries.append(path)
        except Exception:
            continue
    return libraries


# ── Sidecar file paths ───────────────────────────────────────────────────────

def _blacklist_path(save_path: str) -> str:
    """Return path for blacklist file associated with save."""
    return save_path + ".blacklist"


def _must_breed_path(save_path: str) -> str:
    """Return path for must-breed file associated with save."""
    return save_path + ".mustbreed"


def _pinned_path(save_path: str) -> str:
    """Return path for pinned-cats file associated with save."""
    return save_path + ".pinned"


def _tags_path(save_path: str) -> str:
    """Return JSON path for cat tag assignments associated with save."""
    return save_path + ".tags.json"


def _gender_overrides_path(save_path: str) -> str:
    """Return CSV path for manual gender overrides associated with save."""
    return save_path + ".gender_overrides.csv"


def _calibration_path(save_path: str) -> str:
    """Return JSON path for manual calibration data associated with save."""
    return save_path + ".calibration.json"


def _scoring_path(save_path: str) -> str:
    """Return JSON path for shared scoring state (ratings + profiles)."""
    return save_path + ".scoring.json"


def _planner_state_path(save_path: str) -> str:
    return save_path + ".planner_state.json"


def _not_adventured_path(save_path: str) -> str:
    """Return path for not-adventured override file associated with save."""
    return save_path + ".not_adventured"


def _breeding_cache_path(save_path: str) -> str:
    return save_path + ".breeding_cache.json"
