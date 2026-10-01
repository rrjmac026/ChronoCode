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
    # .NET / Visual Studio build output
    "bin",
    "obj",
    ".vs",
    "TestResults",
    # other common generated/cache folders
    ".next",
    ".nuxt",
    ".gradle",
    ".dart_tool",
    ".pytest_cache",
    ".mypy_cache",
    "coverage",
}
IGNORED_FILES = {".DS_Store", "Thumbs.db"}
TEMP_SUFFIXES = {".tmp", ".swp", ".part", ".lock"}

# Auto-generated / binary files that are never hand-written code.
# Matched against the END of the file name (case-insensitive), so multi-part
# endings like ".sourcelink.json" work too.
IGNORED_SUFFIXES = (
    # .NET build artifacts
    ".pdb", ".dll", ".exe", ".cache", ".nupkg", ".suo", ".user",
    ".sourcelink.json", ".assemblyinfo.cs", ".assemblyinfoinputs.cache",
    ".g.cs", ".g.i.cs", ".designer.cs.bak",
    # misc compiled / generated
    ".obj", ".o", ".class", ".pyc", ".pyo", ".so", ".log",
)

DELETE_GRACE_SECONDS = 1.0
STABLE_MAX_POLLS = 20
STABLE_POLL_SECONDS = 0.25
MAX_HASH_BYTES = 50 * 1024 * 1024