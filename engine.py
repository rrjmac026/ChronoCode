"""Monitoring engine: baselines, change capture, revert/delete handling.

This module contains no GUI code. The UI hands it a ``get_storage`` callable and an
``emit`` callback (called from worker threads) and reads state via ``snapshot()``.

Storage layout: the first file with a given name is stored flat in the project's
storage folder. A later file with the same name from a different source folder keeps
its relative folders. The source->stored mapping is saved in ``.collector_map.json``
inside the storage repo (untracked by Git).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from watchdog.observers import Observer

import gitstore
from config import (
    DELETE_GRACE_SECONDS,
    IGNORED_DIRS,
    STABLE_MAX_POLLS,
    STABLE_POLL_SECONDS,
)
from utils import (
    file_hash,
    file_signature,
    project_storage_name,
    should_ignore,
    should_ignore_dir,
)
from watcher import ChangeHandler

GIT_ERRORS = (subprocess.CalledProcessError, OSError, RuntimeError)
MAP_FILE = ".collector_map.json"


class EngineError(Exception):
    """A problem the user should be told about (shown in a dialog)."""


@dataclass
class Event:
    kind: str  # info | added | modified | reverted | deleted | error
    message: str
    project: Optional[Path] = None
    stamp: str = field(default_factory=lambda: time.strftime("%H:%M:%S"))


@dataclass
class ProjectState:
    root: Path
    known: dict = field(default_factory=dict)  # Path -> (size, mtime) signature
    hashes: dict = field(default_factory=dict)  # Path -> content hash at baseline
    observer: Optional[Observer] = None
    stats: Counter = field(default_factory=Counter)


def _git_detail(exc: Exception) -> str:
    return (getattr(exc, "stderr", None) or str(exc)).strip()


class CollectorEngine:
    def __init__(self, get_storage: Callable[[], str], emit: Callable[[Event], None]):
        self._get_storage = get_storage
        self._emit = emit
        self.states: dict = {}  # resolved project Path -> ProjectState
        self.running = False
        self._lock = threading.RLock()
        self._pending: set = set()
        self._pending_lock = threading.Lock()
        self._git_lock = threading.Lock()  # serialize copy/delete + git commands + map access
        self._maps: dict = {}  # repository Path -> {source_posix: stored_posix}

    # ------------------------------------------------------------------ helpers
    def log(self, kind: str, message: str, project: Optional[Path] = None) -> None:
        self._emit(Event(kind, message, project))

    def storage_root(self) -> Path:
        return Path(self._get_storage()).expanduser().resolve()

    def _validate_storage(self, only: Optional[Path] = None) -> Path:
        raw = self._get_storage().strip()
        if not raw:
            raise EngineError("Choose a central storage folder.")
        storage = Path(raw).expanduser().resolve()
        for root in [only] if only else list(self.states):
            if storage == root or root in storage.parents:
                raise EngineError(f"The storage folder can't be inside a monitored project:\n{root}")
            if storage in root.parents:
                raise EngineError(f"A project can't be inside the storage folder:\n{root}")
        return storage

    def snapshot(self) -> list:
        """Per-project info for the UI."""
        with self._lock:
            return [
                {"path": root, "tracked": len(state.known), "stats": Counter(state.stats)}
                for root, state in self.states.items()
            ]

    # ------------------------------------------------------- source->stored map
    # Callers must hold self._git_lock.
    def _load_map(self, repository: Path) -> dict:
        mapping = self._maps.get(repository)
        if mapping is not None:
            return mapping
        mapping = {}
        map_path = repository / MAP_FILE
        try:
            if map_path.is_file():
                with map_path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)
                if isinstance(data, dict):
                    mapping = {str(k): str(v) for k, v in data.items()}
        except (OSError, ValueError):
            mapping = {}
        self._maps[repository] = mapping
        return mapping

    def _save_map(self, repository: Path) -> None:
        mapping = self._maps.get(repository)
        if mapping is None:
            return
        try:
            repository.mkdir(parents=True, exist_ok=True)
            map_path = repository / MAP_FILE
            temp_path = map_path.with_suffix(".tmp")
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(mapping, handle, indent=2)
            temp_path.replace(map_path)
        except OSError:
            pass

    def _resolve_stored(self, repository: Path, relative: Path) -> Path:
        """Return where this source file is stored, assigning a spot if it has none.

        First file with a given name -> flat. Later same-named file from another
        folder -> keeps its relative folders.
        """
        mapping = self._load_map(repository)
        key = relative.as_posix()
        if key in mapping:
            return Path(mapping[key])
        flat = relative.name
        if flat in set(mapping.values()) or (repository / flat).exists():
            stored = key
        else:
            stored = flat
        mapping[key] = stored
        return Path(stored)

    # ----------------------------------------------------------------- projects
    def _scan(self, root: Path) -> ProjectState:
        """Record every existing file (signature + content hash) as the baseline."""
        state = ProjectState(root=root)
        for current, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            for name in names:
                file_path = Path(current) / name
                if should_ignore(file_path, root):
                    continue
                signature = file_signature(file_path)
                if signature is None:
                    continue
                resolved = file_path.resolve()
                state.known[resolved] = signature
                digest = file_hash(resolved)
                if digest is not None:
                    state.hashes[resolved] = digest
        return state

    def add_project(self, folder) -> Path:
        root = Path(folder).expanduser().resolve()
        if not root.is_dir():
            raise EngineError("Please choose a valid folder.")
        with self._lock:
            if root in self.states:
                raise EngineError("That project folder is already added.")
        if self._get_storage().strip():
            self._validate_storage(only=root)
        state = self._scan(root)
        with self._lock:
            self.states[root] = state
            if self.running:
                self._attach(state)
        self.log("info", f"Project added ({len(state.known)} existing files set as baseline): {root}", root)
        return root

    def remove_project(self, root: Path) -> None:
        with self._lock:
            state = self.states.pop(root, None)
        if state is None:
            return
        self._detach(state)
        self.log("info", f"Project removed: {root}", root)

    # --------------------------------------------------------------- start/stop
    def _attach(self, state: ProjectState) -> None:
        if state.observer:
            return
        observer = Observer()
        observer.schedule(ChangeHandler(self, state.root), str(state.root), recursive=True)
        observer.start()
        state.observer = observer
        self.log("info", f"Watching: {state.root}", state.root)

    @staticmethod
    def _detach(state: ProjectState) -> None:
        if state.observer:
            state.observer.stop()
            state.observer.join(timeout=2)
            state.observer = None

    def start(self) -> None:
        if self.running:
            return
        if not self.states:
            raise EngineError("Add at least one project folder first.")
        if not gitstore.git_available():
            raise EngineError(
                "Git was not found on PATH.\n\nInstall Git for Windows (https://git-scm.com) "
                "and restart this app. Test with:  git --version"
            )
        storage = self._validate_storage()
        try:
            storage.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise EngineError(f"Cannot create storage folder:\n{exc}")

        # Fresh baseline right before watching: existing files are never copied.
        for root in list(self.states):
            fresh = self._scan(root)
            fresh.stats = self.states[root].stats
            with self._lock:
                self.states[root] = fresh
        with self._lock:
            self.running = True
            for state in self.states.values():
                self._attach(state)
        self.log("info", f"Monitoring started. Storage: {storage}")

    def stop(self) -> None:
        with self._lock:
            self.running = False
            states = list(self.states.values())
        for state in states:
            self._detach(state)
        self.log("info", "Monitoring stopped.")

    # ------------------------------------------------------------------ capture
    def queue_capture(self, project: Path, file_path: Path) -> None:
        project = project.resolve()
        try:
            file_path = file_path.resolve()
        except OSError:
            return
        if should_ignore(file_path, project):
            return
        key = (project, file_path)
        with self._pending_lock:
            if key in self._pending:
                return
            self._pending.add(key)
        threading.Thread(
            target=self._capture_when_stable, args=(project, file_path, key), daemon=True
        ).start()

    def _capture_when_stable(self, project: Path, file_path: Path, key) -> None:
        try:
            state = self.states.get(project)
            if state is None:
                return

            # Editors write in chunks or swap temp files: wait until size/mtime settles.
            previous = None
            stable_checks = 0
            for _ in range(STABLE_MAX_POLLS):
                time.sleep(STABLE_POLL_SECONDS)
                current = file_signature(file_path)
                if current is None:
                    continue
                if current == previous:
                    stable_checks += 1
                    if stable_checks >= 2:
                        break
                else:
                    previous = current
                    stable_checks = 0

            signature = file_signature(file_path)
            if signature is None:
                return
            previous_signature = state.known.get(file_path)
            if previous_signature == signature:
                return
            try:
                relative = file_path.relative_to(project)
            except ValueError:
                return
            shown = f"{project.name}: {relative.as_posix()}"

            # Reverted: content equals the baseline, so it is no longer a change and
            # its stored copy must go.
            baseline_hash = state.hashes.get(file_path)
            if baseline_hash is not None and file_hash(file_path) == baseline_hash:
                state.known[file_path] = signature
                if self._remove_from_storage(project, relative, "Reverted"):
                    state.stats["reverted"] += 1
                    self.log("reverted", f"Reverted to original, removed from storage - {shown}", project)
                return

            repository = self.storage_root() / project_storage_name(project)
            label = "Added" if previous_signature is None else "Modified"
            with self._git_lock:
                stored = self._resolve_stored(repository, relative)
                destination = repository / stored
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(file_path, destination)
                self._save_map(repository)
                try:
                    gitstore.ensure_repo(repository)
                    committed = gitstore.commit_file(repository, stored, label)
                except GIT_ERRORS as exc:
                    state.known[file_path] = signature
                    self.log("error", f"Copied, but Git snapshot failed - {shown}: {_git_detail(exc)}", project)
                    return

            state.known[file_path] = signature
            if committed:
                state.stats[label.lower()] += 1
                self.log(label.lower(), f"{label} - {shown}", project)
            else:
                self.log("info", f"Saved but content unchanged, no new snapshot - {shown}", project)
        except (OSError, PermissionError) as exc:
            self.log("error", f"Could not collect {file_path}: {exc}", project)
        finally:
            with self._pending_lock:
                self._pending.discard(key)

    # ------------------------------------------------------------------ removal
    def queue_removal(self, project: Path, file_path: Path, label: str, is_dir: bool = False) -> None:
        project = project.resolve()
        try:
            file_path = file_path.resolve()
            relative = file_path.relative_to(project)
        except (OSError, ValueError):
            return
        if any(part in IGNORED_DIRS for part in relative.parts[:-1]):
            return
        if is_dir:
            if should_ignore_dir(file_path, project):
                return
        elif should_ignore(file_path, project):
            return
        threading.Thread(
            target=self._remove_when_gone,
            args=(project, file_path, relative, label, is_dir),
            daemon=True,
        ).start()

    def _remove_when_gone(self, project: Path, file_path: Path, relative: Path, label: str, is_dir: bool) -> None:
        try:
            time.sleep(DELETE_GRACE_SECONDS)
            if file_path.exists():
                return  # delete + re-create "save"; the capture path handles it
            state = self.states.get(project)
            if state is None:
                return
            if is_dir:
                for path in [p for p in state.known if file_path in p.parents]:
                    if path not in state.hashes:
                        state.known.pop(path, None)
            elif file_path not in state.hashes:
                state.known.pop(file_path, None)
            if self._remove_from_storage(project, relative, label, is_dir):
                state.stats["deleted"] += 1
                self.log("deleted", f"{label}, removed from storage - {project.name}: {relative.as_posix()}", project)
        except (OSError, PermissionError) as exc:
            self.log("error", f"Could not remove stored copy of {file_path}: {exc}", project)

    def _remove_from_storage(self, project: Path, relative: Path, label: str, is_dir: bool = False) -> bool:
        """Delete collected copies and record the removal in the project's Git history."""
        repository = self.storage_root() / project_storage_name(project)
        removed_any = False
        with self._git_lock:
            mapping = self._load_map(repository)
            key = relative.as_posix()
            if is_dir:
                prefix = key + "/"
                sources = [s for s in mapping if s.startswith(prefix)]
            else:
                sources = [key] if key in mapping else []

            for source in sources:
                stored = Path(mapping[source])
                target = repository / stored
                if target.is_file():
                    try:
                        target.unlink()
                    except OSError as exc:
                        self.log("error", f"Could not delete stored copy {stored.as_posix()}: {exc}", project)
                        continue
                    removed_any = True
                    # Tidy up folders left empty (never removes the repository root or .git).
                    parent = target.parent
                    while parent != repository and parent.is_dir() and not any(parent.iterdir()):
                        parent.rmdir()
                        parent = parent.parent
                    if (repository / ".git").exists():
                        try:
                            gitstore.commit_removal(repository, stored, label)
                        except GIT_ERRORS as exc:
                            self.log("error", f"Removed copy, but Git snapshot failed - {stored.as_posix()}: {_git_detail(exc)}", project)
                mapping.pop(source, None)  # frees the flat name for reuse

            if sources:
                self._save_map(repository)
        return removed_any