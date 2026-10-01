# ChronoCode

A small Windows-friendly Python desktop app that monitors one or more project folders and copies files created or modified **after monitoring starts** into a central storage folder, with a Git history of every captured change.

## Features

- Choose multiple project/codebase folders.
- Existing files are scanned as a baseline and are not copied.
- Newly added and modified files are copied into a central storage directory.
- Projects with the same folder name get separate storage folders.
- Files are stored **flat** in the project's storage folder. If two files share a name, the first one stays flat and later ones from a different folder keep their relative folders (see Storage layout).
- A basic activity log shows what was collected.
- Creates a separate local Git repository per project and commits each successfully captured content change.
- Git history can be inspected with standard Git tools; unchanged content does not create a duplicate commit.
- Remembers selected project folders and storage path between launches.
- If a captured file is reverted to its original content (for example with `git checkout`/discard changes), its copy is removed from storage and the removal is committed.
- If a file or folder is deleted or renamed in the project, its stored copy is removed too (the Git history keeps the earlier versions).
- Common generated/dependency folders are ignored by default.
- Git commands run silently, with no console windows flashing on Windows.

## Requirements

- Python 3.10 or newer recommended
- Windows, macOS, or Linux with Tkinter available
- Git available on PATH

## Run on Windows

1. Extract the ZIP.
2. Open the extracted folder.
3. Double-click `run.bat`, or run these commands in Command Prompt:

```bat
py -m pip install -r requirements.txt
py main.py
```

## How to use

1. Click **Add project folder** and select a codebase, for example `F:\Projects\RemoteNexuz`.
2. Add other projects if desired.
3. Choose the **Central storage folder**. The default is `C:\Users\<you>\CodebaseChangeStorage`.
4. Click **Start monitoring**.
5. Create or edit files in your project. Once the file stops changing briefly, a copy is placed in central storage.
6. Click **Stop monitoring** when finished.
7. Close and reopen the app later: your project list and storage path are restored. Click **Start monitoring** to resume.

## Storage layout

Each project gets its own folder, named after the project folder plus a short identifier derived from the full project path, so same-named projects never collide. Each project folder is also a local Git repository.

Inside it, files are stored flat:

- The **first** file with a given name is stored directly in the project's storage folder.
- A **later file with the same name from a different source folder** keeps its relative folders, so it doesn't overwrite the first one.

```text
CodebaseChangeStorage/
  RemoteNexuz_a1b2c3d/
    .git/
    .collector_map.json
    UserController.php        <- first User*.php stays flat
    web.php
    User.php                  <- first "User.php" (from app/Models/)
    tests/
      User.php                <- same name, different source folder
```

`.collector_map.json` records which source file owns which stored file, so the layout stays consistent after restarts. It is not tracked by Git. When a stored file is removed (delete, rename, or revert), its flat name becomes free again.

The original project files are not moved or deleted.

## Important notes

- Git is required on your system and must be available on PATH (test with `git --version`). The app uses local repository settings for commit identity and does not push to GitHub or any remote server.
- Each captured change is committed to the project's storage repository. Git keeps prior committed versions even though the working copy at that path is updated. Commit messages show the stored path (for example `Modified: UserController.php`).
- Only files successfully captured while monitoring is running are committed. A very fast edit-and-revert can be missed, and changes while the app is closed are not captured.
- The initial project baseline is not copied into storage or committed. History begins with the first captured change to each file, so earlier/original contents are not recoverable unless a version was captured.
- Monitoring only runs while the app is open and monitoring is started. On the next launch, saved projects are restored and a fresh baseline is taken, so files changed while the app was closed are treated as existing and are not retroactively collected.
- Changes made while monitoring is stopped are not guaranteed to be collected, for the same reason.
- Project-list settings are stored locally in `~/.codebase_change_collector.json` (your Windows user home folder). This file stores folder paths, not the contents of your code files.
- Revert detection compares against the content the file had when monitoring started (files over 50 MB are not hashed, so they are not auto-removed on revert). Because each Start takes a fresh baseline, a file captured in an earlier session and reverted later is treated as a normal modification.
- Large files may take longer to settle before being copied.
- `.git`, `node_modules`, `vendor`, virtual environments, build folders, and common editor/generated directories are skipped by default. Edit `IGNORED_DIRS` in `config.py` to change this.
- Files stored in an older nested layout are not moved automatically. Delete the old storage folder for a clean start.
- Keep the central storage folder outside the projects being monitored.
- If an editor saves a file by replacing it with a temporary file, the app attempts to capture the resulting file.
- This program does not send files over the internet; collection is local to your machine.