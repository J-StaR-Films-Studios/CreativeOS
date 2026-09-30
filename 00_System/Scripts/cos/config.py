"""Configuration loading and management."""

import os
import json
import sys
import stat
import logging
from typing import Dict, Any, Union

from .console import console

# Type aliases
JSONDict = Dict[str, Any]
FileFingerprint = Dict[str, Union[float, int]]
SyncState = Dict[str, Any]

# File permissions
CONFIG_PERMISSIONS = stat.S_IRUSR | stat.S_IWUSR  # 0o600 - owner read/write only
DIR_PERMISSIONS = stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH | stat.S_IXOTH  # 0o750

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Two levels up because we're in Scripts/cos now
CONFIG_PATH = os.path.join(SCRIPT_DIR, "..", "..", "Config", "config.json")

# --- LAZY CONFIG LOADING ---
# Config is loaded on first access, not on import, so the onboarding wizard
# can create config.json before these values are needed.
_CONFIG: Dict[str, Any] = {}
_config_loaded = False


def _load_config() -> Dict[str, Any]:
    """Load configuration from config.json lazily.
    
    Returns the config dict. Exits with error if config.json 
    is missing and cannot be found (post-onboarding).
    """
    global _CONFIG, _config_loaded
    if _config_loaded:
        return _CONFIG
    
    if not os.path.exists(CONFIG_PATH):
        console.print("❌ [error]CRITICAL ERROR: Config file not found. Run 'cos setup' to create it.[/error]")
        sys.exit(1)
    
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        _CONFIG = json.load(f)
    
    _config_loaded = True
    return _CONFIG


def _get(key: str, default: Any = None) -> Any:
    """Get a config value, loading config lazily if needed."""
    config = _load_config()
    return config.get(key, default)


def reload_config() -> None:
    """Force reload of configuration from disk.
    
    Call this after onboarding or setup writes a new config.json,
    so that subsequent imports get fresh values.
    """
    global _config_loaded
    _config_loaded = False
    _load_config()


class _LazyConfigAttr:
    """Descriptor that defers config value access until first use."""
    def __init__(self, key: str, default: Any = None):
        self.key = key
        self.default = default

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        return _get(self.key, self.default)


class _ConfigNamespace:
    """Namespace whose attributes are lazily loaded from config.json."""
    ROOT_PATH = _LazyConfigAttr("root_path")
    PROJECTS_PATH = _LazyConfigAttr("projects_path")
    EXPORTS_PATH = _LazyConfigAttr("exports_path")
    TEMPLATES_PATH = _LazyConfigAttr("templates_path")
    VAULT_PATH = _LazyConfigAttr("vault_path")
    DOWNLOADS_PATH = _LazyConfigAttr(
        "downloads_path", os.path.join(os.path.expanduser("~"), "Downloads")
    )
    SHUTTLE_PATH = _LazyConfigAttr("shuttle_path", "A:\\CreativeOS_Shuttle")
    ARCHIVE_PATH = _LazyConfigAttr(
        "archive_path", "D:\\OneDrive - Developer\\Archive"
    )


_ns = _ConfigNamespace()

# Module-level names kept for backward compatibility — they are now
# properties that resolve lazily on first access via __getattr__.
def __getattr__(name: str) -> Any:
    """Module-level lazy attribute access for config values."""
    _LAZY_ATTRS = {
        "ROOT_PATH", "PROJECTS_PATH", "EXPORTS_PATH", "TEMPLATES_PATH",
        "VAULT_PATH", "DOWNLOADS_PATH", "SHUTTLE_PATH", "ARCHIVE_PATH",
    }
    if name in _LAZY_ATTRS:
        return getattr(_ns, name)
    if name == "CONFIG":
        return _load_config()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# --- SYNC OPTIMIZATION CONSTANTS ---
# Directories to skip during traversal for massive speedup
EXCLUDED_DIRS = {
    'node_modules', '.git', '__pycache__', '.venv', 'venv', 'env',
    '.idea', '.vscode', 'dist', 'build', '.next', '.nuxt', 'coverage',
    '.pytest_cache', '.mypy_cache', 'egg-info', 'EGG-INFO', 'target',
    'vendor', 'Pods', '.gradle', 'DerivedData', '.cache'
}

# Sync state database path for incremental syncs
SYNC_STATE_PATH = os.path.join(SCRIPT_DIR, "..", "..", "Config", "sync_state.json")
PROJECT_INDEX_PATH = os.path.join(SCRIPT_DIR, "..", "..", "Config", "project_index.json")
# Cached, read-only inventory used by `cos storage`; normal commands never scan disks.
STORAGE_INDEX_PATH = os.path.join(SCRIPT_DIR, "..", "..", "Config", "storage_index.json")
WINDOWS_CLEANUP_INDEX_PATH = os.path.join(SCRIPT_DIR, "..", "..", "Config", "windows_cleanup_index.json")

# --- LOGGING SETUP ---
LOG_PATH = os.path.join(SCRIPT_DIR, "..", "..", "Config", "creativeos.log")

# Create logger
logger = logging.getLogger('creativeos')
logger.setLevel(logging.DEBUG)

# Create file handler
file_handler = logging.FileHandler(LOG_PATH, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

# Create formatter
formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(formatter)

# Add handler to logger
logger.addHandler(file_handler)
