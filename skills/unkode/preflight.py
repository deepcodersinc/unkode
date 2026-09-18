#!/usr/bin/env python3
"""Pre-flight check for /unkode. Reports whether the map exists and what changed since.

Prints one of:
  INIT        no architecture map anywhere
  UP_TO_DATE  map exists, no code changes since it was built
  SYNC <n>    map exists, n files changed since it was built
"""

import subprocess
import yaml

import paths

source = paths.find_arch()

if source is None:
    print("INIT")
else:
    with open(source, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    last_sync = data.get("_meta", {}).get("last_sync_commit", "")

    # Check for committed changes since last sync
    committed = ""
    if last_sync:
        committed = subprocess.run(
            ["git", "diff", "--name-only", f"{last_sync}..HEAD"],
            capture_output=True, text=True,
        ).stdout.strip()

    # Check for uncommitted changes (staged + unstaged)
    uncommitted = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip()

    staged = subprocess.run(
        ["git", "diff", "--name-only", "--cached"],
        capture_output=True, text=True,
    ).stdout.strip()

    all_changes = set()
    if committed:
        all_changes.update(committed.splitlines())
    if uncommitted:
        all_changes.update(uncommitted.splitlines())
    if staged:
        all_changes.update(staged.splitlines())

    # Unkode's own files are not code changes.
    all_changes -= paths.OWN_FILES

    if not all_changes:
        print("UP_TO_DATE")
    else:
        print(f"SYNC {len(all_changes)}")
