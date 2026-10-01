import hashlib
from pathlib import Path

from config import IGNORED_DIRS, IGNORED_FILES, MAX_HASH_BYTES, TEMP_SUFFIXES


def should_ignore(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    if any(part in IGNORED_DIRS for part in relative.parts[:-1]):
        return True
    if path.name in IGNORED_FILES or path.suffix.lower() in TEMP_SUFFIXES:
        return True
    return False


def should_ignore_dir(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    return any(part in IGNORED_DIRS for part in relative.parts)


def file_signature(path: Path):
    """Return a stable signature for baseline comparisons."""
    try:
        stat = path.stat()
        if not path.is_file():
            return None
        return (stat.st_size, stat.st_mtime_ns)
    except (OSError, PermissionError):
        return None


def file_hash(path: Path):
    """Content hash used to tell whether a file is back to its original content."""
    try:
        if path.stat().st_size > MAX_HASH_BYTES:
            return None
        digest = hashlib.sha1()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except (OSError, PermissionError):
        return None


def project_storage_name(project: Path) -> str:
    """Avoid collisions when two selected projects share the same folder name."""
    digest = hashlib.sha1(str(project.resolve()).encode("utf-8")).hexdigest()[:7]
    return f"{project.name}_{digest}"
