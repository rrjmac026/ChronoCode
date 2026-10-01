import os
import subprocess
from pathlib import Path

# Stops a console window from flashing on Windows for every git command.
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def run_git(repository: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(repository),
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=_NO_WINDOW,
    )


def git_available() -> bool:
    try:
        subprocess.run(
            ["git", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            creationflags=_NO_WINDOW,
        )
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def ensure_repo(repository: Path) -> None:
    repository.mkdir(parents=True, exist_ok=True)
    git_dir = repository / ".git"
    if git_dir.exists():
        return
    run_git(repository, "init")
    run_git(repository, "config", "user.name", "Codebase Change Collector")
    run_git(repository, "config", "user.email", "collector@localhost")


def commit_file(repository: Path, relative: Path, label: str) -> bool:
    run_git(repository, "add", "--", relative.as_posix())
    return commit_staged(repository, f"{label}: {relative.as_posix()}")


def commit_staged(repository: Path, message: str) -> bool:
    result = run_git(repository, "diff", "--cached", "--quiet", check=False)
    if result.returncode == 0:
        return False
    if result.returncode != 1:
        raise RuntimeError(result.stderr.strip() or "Git could not compare staged changes.")
    run_git(repository, "commit", "-m", message)
    return True


def commit_removal(repository: Path, relative: Path, label: str) -> bool:
    run_git(repository, "rm", "-r", "--cached", "--ignore-unmatch", "-q", "--", relative.as_posix(), check=False)
    return commit_staged(repository, f"{label}: {relative.as_posix()}")