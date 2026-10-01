from pathlib import Path

APP_NAME = "Codebase Change Collector"
DEFAULT_STORAGE = Path.home() / "CodebaseChangeStorage"
CONFIG_PATH = Path.home() / ".codebase_change_collector.json"

# Common generated/dependency folders are skipped to avoid collecting huge amounts
# of unrelated files. Edit this set if you want to monitor these directories too.
IGNORED_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "vendor",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
}
IGNORED_FILES = {".DS_Store", "Thumbs.db"}
TEMP_SUFFIXES = {".tmp", ".swp", ".part", ".lock"}

DELETE_GRACE_SECONDS = 1.0
STABLE_MAX_POLLS = 20
STABLE_POLL_SECONDS = 0.25
MAX_HASH_BYTES = 50 * 1024 * 1024
