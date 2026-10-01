from pathlib import Path

from watchdog.events import FileSystemEventHandler


class ChangeHandler(FileSystemEventHandler):
    def __init__(self, app, project_root: Path):
        self.app = app
        self.project_root = project_root.resolve()

    def on_created(self, event):
        if not event.is_directory:
            self.app.queue_capture(self.project_root, Path(event.src_path))

    def on_modified(self, event):
        if not event.is_directory:
            self.app.queue_capture(self.project_root, Path(event.src_path))

    def on_moved(self, event):
        if not event.is_directory:
            self.app.queue_removal(self.project_root, Path(event.src_path), "Moved away")
            self.app.queue_capture(self.project_root, Path(event.dest_path))

    def on_deleted(self, event):
        self.app.queue_removal(
            self.project_root,
            Path(event.src_path),
            "Deleted",
            is_dir=event.is_directory,
        )
