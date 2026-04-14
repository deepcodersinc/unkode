#!/usr/bin/env python3
"""Pre-flight check for /unkode. Determines whether to run init, sync, or skip."""

import os
import subprocess
import yaml

if not os.path.exists("unkode.yaml"):
    print("INIT")
else:
    with open("unkode.yaml", encoding="utf-8") as f:
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

    # Exclude unkode's own files
    all_changes.discard("unkode.yaml")
    all_changes.discard("arch_map.md")

    if not all_changes:
        print("UP_TO_DATE")
    else:
        print(f"SYNC {len(all_changes)}")
