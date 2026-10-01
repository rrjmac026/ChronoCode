import json
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from config import APP_NAME, CONFIG_PATH, DEFAULT_STORAGE, IGNORED_DIRS
from engine import CollectorEngine, EngineError


class CollectorApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("850x570")
        self.root.minsize(720, 480)

        self.storage_var = tk.StringVar(value=str(DEFAULT_STORAGE))
        self.engine = CollectorEngine(self._get_storage_path, self._emit_event)
        self.project_list = None
        self.start_button = None
        self.stop_button = None
        self.log_box = None

        self._build_ui()
        self._load_settings()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _get_storage_path(self) -> str:
        return self.storage_var.get()

    def _emit_event(self, event):
        self.log(f"[{event.kind}] {event.message}")

    def _load_settings(self):
        try:
            if not CONFIG_PATH.exists():
                return
            with CONFIG_PATH.open("r", encoding="utf-8") as handle:
                settings = json.load(handle)
            saved_storage = settings.get("storage_folder")
            if saved_storage:
                self.storage_var.set(saved_storage)
            for raw_path in settings.get("project_folders", []):
                project = Path(raw_path).expanduser().resolve()
                if project.is_dir():
                    try:
                        self.engine.add_project(project)
                        self.project_list.insert("end", str(project))
                    except EngineError:
                        pass
            if self.engine.states:
                self.log("Restored saved project list. Click Start monitoring to watch these folders.")
        except (OSError, ValueError, TypeError) as exc:
            self.log(f"Could not restore saved settings: {exc}")

    def _save_settings(self):
        try:
            settings = {
                "storage_folder": self.storage_var.get().strip(),
                "project_folders": [str(path) for path in self.engine.states.keys()],
            }
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            temp_path = CONFIG_PATH.with_suffix(".tmp")
            with temp_path.open("w", encoding="utf-8") as handle:
                json.dump(settings, handle, indent=2)
            temp_path.replace(CONFIG_PATH)
        except OSError as exc:
            self.log(f"Could not save settings: {exc}")

    def _build_ui(self):
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Codebase Change Collector", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(
            outer,
            text="Existing files are recorded as a baseline. Only files added or modified after monitoring starts are copied.",
        ).pack(anchor="w", pady=(3, 12))

        storage_frame = ttk.LabelFrame(outer, text="Central storage folder", padding=8)
        storage_frame.pack(fill="x", pady=(0, 10))
        ttk.Entry(storage_frame, textvariable=self.storage_var).pack(side="left", fill="x", expand=True)
        ttk.Button(storage_frame, text="Browse...", command=self.choose_storage).pack(side="left", padx=(8, 0))

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="Add project folder", command=self.add_project).pack(side="left")
        ttk.Button(controls, text="Remove selected", command=self.remove_selected).pack(side="left", padx=8)
        self.start_button = ttk.Button(controls, text="Start monitoring", command=self.start_monitoring)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(controls, text="Stop monitoring", command=self.stop_monitoring, state="disabled")
        self.stop_button.pack(side="left", padx=8)

        project_frame = ttk.LabelFrame(outer, text="Projects", padding=6)
        project_frame.pack(fill="x", pady=(0, 10))
        self.project_list = tk.Listbox(project_frame, height=5, selectmode=tk.EXTENDED)
        self.project_list.pack(fill="x", expand=True)

        log_frame = ttk.LabelFrame(outer, text="Activity log", padding=6)
        log_frame.pack(fill="both", expand=True)
        self.log_box = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        self.log_box.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(log_frame, command=self.log_box.yview)
        scroll.pack(side="right", fill="y")
        self.log_box.configure(yscrollcommand=scroll.set)

    def log(self, message):
        stamp = time.strftime("%H:%M:%S")

        def append():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", f"[{stamp}] {message}\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

        self.root.after(0, append)

    def choose_storage(self):
        folder = filedialog.askdirectory(title="Choose central storage folder")
        if folder:
            self.storage_var.set(folder)
            self._save_settings()

    def add_project(self):
        folder = filedialog.askdirectory(title="Choose a codebase/project folder")
        if not folder:
            return
        path = Path(folder).resolve()
        if not path.is_dir():
            messagebox.showerror(APP_NAME, "Please choose a valid folder.")
            return
        try:
            self.engine.add_project(path)
        except EngineError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return

        if path not in [Path(self.project_list.get(i)).resolve() for i in range(self.project_list.size())]:
            self.project_list.insert("end", str(path))
        self.log(f"Project added; existing files ignored: {path}")
        self._save_settings()
        if self.engine.running:
            self.engine.start()

    def remove_selected(self):
        selected = list(self.project_list.curselection())
        if not selected:
            return
        for index in reversed(selected):
            path = Path(self.project_list.get(index)).resolve()
            self.engine.remove_project(path)
            self.project_list.delete(index)
        self.log("Project removed.")
        self._save_settings()

    def start_monitoring(self):
        try:
            self.engine.start()
        except EngineError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.log(f"Monitoring started. Storage: {Path(self.storage_var.get()).expanduser().resolve()}")

    def stop_monitoring(self):
        self.engine.stop()
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self._save_settings()

    def close(self):
        self.engine.stop()
        self._save_settings()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except tk.TclError:
        pass
    CollectorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
