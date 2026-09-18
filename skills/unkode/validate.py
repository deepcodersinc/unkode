#!/usr/bin/env python3
"""Validate the architecture map against the codebase.

Run this before writing the map (during init) to catch invented modules,
unresolved dependencies, and duplicate names while they are still cheap to fix.

Exit codes:
  0  clean
  1  warnings only
  2  errors found
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

import paths

# Directories that are never part of the architecture.
SKIP_DIRS = {
    ".git", ".svn", ".hg", "node_modules", "dist", "build", "out",
    "target", "vendor", "__pycache__", ".venv", "venv", ".tox",
    ".next", ".nuxt", ".cache", "coverage", ".idea", ".vscode",
    paths.UNKODE_DIR,
}

# Test directories are excluded from modules by rule 9, so they never count
# against coverage.
TEST_DIR_NAMES = {
    "test", "tests", "__tests__", "spec", "specs", "e2e",
    "fixtures", "testdata", "__mocks__",
}

DISPLAY_LIMIT = 10


def load_config():
    cfg_path = Path(__file__).parent / "config.yaml"
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def tracked_files():
    """Files tracked by git, or a filesystem walk when git is unavailable."""
    try:
        out = subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True, check=True,
        ).stdout
        files = [line for line in out.splitlines() if line.strip()]
        if files:
            return files
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    files = []
    for root, dirs, names in os.walk("."):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in names:
            files.append(Path(root, name).relative_to(".").as_posix())
    return files


def dirs_holding_files(files):
    """Directories that directly contain at least one file."""
    dirs = set()
    for f in files:
        parts = Path(f).as_posix().split("/")
        if len(parts) < 2:
            continue
        if any(p in SKIP_DIRS for p in parts[:-1]):
            continue
        dirs.add("/".join(parts[:-1]))
    return dirs


def under(child, parent):
    """True when `child` is `parent` or sits beneath it."""
    parent = parent.rstrip("/")
    return child == parent or child.startswith(parent + "/")


def find_cycles(edges):
    """Return dependency cycles as lists of names, using DFS colouring."""
    cycles = []
    state = {}
    stack = []

    def walk(node):
        state[node] = "open"
        stack.append(node)
        for nxt in edges.get(node, []):
            if state.get(nxt) == "open":
                cycles.append(stack[stack.index(nxt):] + [nxt])
            elif nxt not in state:
                walk(nxt)
        stack.pop()
        state[node] = "done"

    for node in edges:
        if node not in state:
            walk(node)
    return cycles


def validate(yaml_path, config):
    errors = []
    warnings = []

    try:
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return [f"{yaml_path} not found"], []
    except yaml.YAMLError as e:
        return [f"{yaml_path} is not valid YAML: {e}"], []

    architecture = data.get("architecture")
    if not architecture:
        return ["no architecture section found"], []

    modules = [m for m in architecture if isinstance(m, dict) and m.get("name")]
    unnamed = len(architecture) - len(modules)
    if unnamed:
        errors.append(f"{unnamed} architecture entries have no name")

    internals = [m for m in modules if m.get("type") != "external"]
    all_names = {m["name"] for m in modules}

    # Duplicate module names break every name-based reference downstream.
    seen = set()
    for m in modules:
        if m["name"] in seen:
            errors.append(f"duplicate module name '{m['name']}'")
        seen.add(m["name"])

    # Paths must point at real directories - this is the hallucination check.
    for m in internals:
        path = (m.get("path") or "").strip()
        if not path:
            warnings.append(f"{m['name']} -> no path set")
            continue
        target = Path(path)
        if not target.exists():
            errors.append(f"{m['name']} -> path '{path}' does not exist")
        elif not target.is_dir():
            warnings.append(f"{m['name']} -> path '{path}' is a file, expected a directory")

    # depends_on must reference exact names from other entries (rule 3).
    for m in modules:
        for dep in m.get("depends_on", []) or []:
            if dep not in all_names:
                errors.append(f"{m['name']} -> depends_on '{dep}' does not resolve")

    # Component names must be unique within their module: the Mermaid converter
    # resolves component dependencies by bare name.
    component_owners = {}
    for m in internals:
        local = set()
        for comp in m.get("components", []) or []:
            if not isinstance(comp, dict) or not comp.get("name"):
                errors.append(f"{m['name']} -> component with no name")
                continue
            cname = comp["name"]
            if cname in local:
                errors.append(f"{m['name']} -> duplicate component '{cname}'")
            local.add(cname)
            component_owners.setdefault(cname, []).append(m["name"])

    for cname, owners in component_owners.items():
        if len(owners) > 1:
            errors.append(
                f"component '{cname}' appears in {len(owners)} modules "
                f"({', '.join(owners)}) - dependencies on it are ambiguous"
            )

    # Deployment references must resolve too.
    deployment = data.get("deployment") or []
    resource_names = {r["name"] for r in deployment if isinstance(r, dict) and r.get("name")}
    for res in deployment:
        if not isinstance(res, dict) or not res.get("name"):
            continue
        for hosted in res.get("hosts", []) or []:
            if hosted not in all_names:
                errors.append(f"{res['name']} -> hosts '{hosted}' does not resolve")
        for dep in res.get("depends_on", []) or []:
            if dep not in resource_names:
                errors.append(f"{res['name']} -> depends_on '{dep}' is not a deployment resource")

    # Circular module dependencies (SKILL.md Init Process, step 6).
    edges = {m["name"]: [d for d in (m.get("depends_on") or []) if d in all_names] for m in modules}
    for cycle in find_cycles(edges):
        warnings.append("circular dependency: " + " -> ".join(cycle))

    # Coverage: every source directory should belong to exactly one module (rule 7).
    exclude_paths = [p for p in (config.get("exclude_paths") or []) if p]
    module_paths = [(m.get("path") or "").strip().rstrip("/") for m in internals]
    module_paths = [p for p in module_paths if p]

    candidates = dirs_holding_files(tracked_files())
    unclaimed = []
    for d in sorted(candidates):
        if any(part in TEST_DIR_NAMES for part in d.split("/")):
            continue
        if any(under(d, e) for e in exclude_paths):
            continue
        if any(under(d, p) for p in module_paths):
            continue
        if any(under(d, already) for already in unclaimed):
            continue
        unclaimed.append(d)

    claimed_count = len(candidates) - len(
        [d for d in candidates if not any(under(d, p) for p in module_paths)]
    )
    if unclaimed:
        shown = ", ".join(unclaimed[:DISPLAY_LIMIT])
        more = f" (+{len(unclaimed) - DISPLAY_LIMIT} more)" if len(unclaimed) > DISPLAY_LIMIT else ""
        noun = "directory" if len(unclaimed) == 1 else "directories"
        warnings.append(
            f"{len(unclaimed)} source {noun} claimed by no module: {shown}{more}"
        )

    summary = {
        "modules": len(internals),
        "externals": len(modules) - len(internals),
        "claimed": claimed_count,
        "total_dirs": len(candidates),
    }
    return errors, warnings, summary


def main():
    parser = argparse.ArgumentParser(description="Validate the architecture map against the codebase")
    parser.add_argument("input", nargs="?", help=f"Path to the architecture map (default: {paths.ARCH})")
    args = parser.parse_args()

    source = paths.find_arch(args.input)
    if not source:
        print(f"  ERROR   no architecture map found at {paths.ARCH}")
        sys.exit(2)

    result = validate(source, load_config())
    if len(result) == 2:
        errors, warnings = result
        summary = None
    else:
        errors, warnings, summary = result

    for e in errors:
        print(f"  ERROR   {e}")
    for w in warnings:
        print(f"  WARN    {w}")

    if summary:
        print(
            f"\n  {summary['modules']} modules, {summary['externals']} externals | "
            f"{summary['claimed']} of {summary['total_dirs']} source directories claimed"
        )

    if errors:
        print(f"\n  {len(errors)} error(s), {len(warnings)} warning(s) - map is not valid")
        sys.exit(2)
    if warnings:
        print(f"\n  {len(warnings)} warning(s)")
        sys.exit(1)
    print("\n  Valid.")
    sys.exit(0)


if __name__ == "__main__":
    main()
