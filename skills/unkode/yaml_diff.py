#!/usr/bin/env python3
"""Compare two unkode.yaml files and output a diff Mermaid diagram.

Usage:
    python yaml_diff.py --base base.yaml --current current.yaml
    python yaml_diff.py --base-branch main                          # extracts base from git
    python yaml_diff.py --base-branch main --current unkode.yaml
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from pathlib import Path


def load_config() -> dict:
    """Load config.yaml from the same directory as this script."""
    cfg_path = Path(__file__).parent / "config.yaml"
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def sanitize_id(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name).strip("_")


def escape_label(text: str) -> str:
    return text.replace('"', "&quot;").replace("[", "(").replace("]", ")")


INTERNAL_SHAPES = {
    "frontend": ("[/", "\\]"),
    "backend":  ("[", "]"),
    "worker":   ("[\\", "/]"),
    "library":  ("([", "])"),
    "cli":      (">", "]"),
    "other":    ("(", ")"),
}
EXTERNAL_SHAPES = {
    "database": ("[(", ")]"),
    "cache":    ("[(", ")]"),
    "storage":  ("[(", ")]"),
    "queue":    ("[/", "/]"),
    "api":      ("[[", "]]"),
    "other":    ("(", ")"),
}


def shape_node(node_id: str, label: str, kind: str | None, is_external: bool) -> str:
    shapes = EXTERNAL_SHAPES if is_external else INTERNAL_SHAPES
    default = "other" if is_external else "backend"
    o, c = shapes.get(kind or default, shapes[default])
    return f'{node_id}{o}"{label}"{c}'


def load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_yaml_from_git(branch: str, filepath: str = "unkode.yaml") -> dict:
    # Fetch latest from remote to ensure we compare against current upstream
    subprocess.run(
        ["git", "fetch", "origin", branch],
        capture_output=True, text=True,
    )
    # Prefer origin/<branch> (upstream) over local branch which may be stale
    # Unless the input is already an origin/ ref
    if branch.startswith("origin/"):
        refs = [branch]
    else:
        refs = [f"origin/{branch}", branch]
    for ref in refs:
        try:
            result = subprocess.run(
                ["git", "show", f"{ref}:{filepath}"],
                capture_output=True, text=True, check=True,
            )
            return yaml.safe_load(result.stdout) or {}
        except subprocess.CalledProcessError:
            continue
    return {}


def compute_diff(base_arch: list, curr_arch: list):
    """Compare two architecture lists and categorize each module."""
    base_map = {m["name"]: m for m in base_arch}
    curr_map = {m["name"]: m for m in curr_arch}

    all_names = set(base_map.keys()) | set(curr_map.keys())

    added = []
    removed = []
    modified = []
    unchanged = []

    for name in sorted(all_names):
        if name not in base_map:
            added.append(curr_map[name])
        elif name not in curr_map:
            removed.append(base_map[name])
        else:
            base_m = base_map[name]
            curr_m = curr_map[name]
            changes = []

            # Check for changes
            if base_m.get("depends_on", []) != curr_m.get("depends_on", []):
                old_deps = set(base_m.get("depends_on", []))
                new_deps = set(curr_m.get("depends_on", []))
                for d in new_deps - old_deps:
                    changes.append(f"+ depends on {d}")
                for d in old_deps - new_deps:
                    changes.append(f"- no longer depends on {d}")

            if base_m.get("role", "") != curr_m.get("role", ""):
                changes.append("~ role updated")

            if base_m.get("tech", []) != curr_m.get("tech", []):
                changes.append("~ tech stack changed")

            if base_m.get("path", "") != curr_m.get("path", ""):
                changes.append(f"~ path changed: {base_m.get('path','')} -> {curr_m.get('path','')}")

            # Compare components
            base_comps = {c["name"] for c in base_m.get("components", []) if isinstance(c, dict)}
            curr_comps = {c["name"] for c in curr_m.get("components", []) if isinstance(c, dict)}
            for c in curr_comps - base_comps:
                changes.append(f"+ new component: {c}")
            for c in base_comps - curr_comps:
                changes.append(f"- removed component: {c}")

            if changes:
                modified.append({"module": curr_m, "changes": changes})
            else:
                unchanged.append(curr_m)

    # Diff dependencies (added/removed edges)
    base_edges = set()
    curr_edges = set()
    for m in base_arch:
        for d in m.get("depends_on", []):
            base_edges.add((m["name"], d))
    for m in curr_arch:
        for d in m.get("depends_on", []):
            curr_edges.add((m["name"], d))

    added_edges = curr_edges - base_edges
    removed_edges = base_edges - curr_edges

    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "unchanged": unchanged,
        "added_edges": added_edges,
        "removed_edges": removed_edges,
    }


LIGHT_THEME_INIT = "%%{init: {'theme':'neutral'}}%%"


def render_diff_mermaid(diff: dict, curr_arch: list) -> str:
    direction = load_config().get("diagram_direction", "LR")
    lines = [LIGHT_THEME_INIT, f"graph {direction}"]

    added_names = {m["name"] for m in diff["added"]}
    removed_names = {m["name"] for m in diff["removed"]}
    modified_names = {m["module"]["name"] for m in diff["modified"]}

    all_modules = (
        diff["added"] + [m["module"] for m in diff["modified"]] +
        diff["unchanged"] + diff["removed"]
    )

    for mod in all_modules:
        mid = sanitize_id(mod["name"])
        is_external = mod.get("type") == "external"
        label = mod["name"]

        if mod["name"] in added_names:
            label += " [NEW]"
        elif mod["name"] in removed_names:
            label += " [REMOVED]"
        elif mod["name"] in modified_names:
            label += " [CHANGED]"

        tech = ", ".join(mod.get("tech", []))
        if tech and not is_external:
            label += f" ({tech})"

        if is_external:
            lines.append(f'    {shape_node(mid, escape_label(label), mod.get("kind"), True)}')
        else:
            comps = mod.get("components", [])
            if comps and isinstance(comps[0], dict):
                lines.append(f'    subgraph {mid}["{escape_label(label)}"]')
                for comp in comps:
                    if not isinstance(comp, dict):
                        continue
                    cid = sanitize_id(f'{mod["name"]}_{comp["name"]}')
                    lines.append(f'        {shape_node(cid, escape_label(comp["name"]), mod.get("kind"), False)}')
                lines.append("    end")
            else:
                lines.append(f'    {shape_node(mid, escape_label(label), mod.get("kind"), False)}')

    # Edges
    lines.append("")
    all_names = {m["name"] for m in all_modules}

    # Current edges
    for mod in all_modules:
        if mod["name"] in removed_names:
            continue
        mid = sanitize_id(mod["name"])
        for dep in mod.get("depends_on", []):
            if dep not in all_names:
                continue
            did = sanitize_id(dep)
            edge = (mod["name"], dep)
            if edge in diff["added_edges"]:
                lines.append(f"    {mid} -. new .-> {did}")
            else:
                lines.append(f"    {mid} --> {did}")

    # Removed edges (dashed red)
    for src, tgt in diff["removed_edges"]:
        if src in all_names and tgt in all_names:
            sid = sanitize_id(src)
            tid = sanitize_id(tgt)
            lines.append(f"    {sid} -. removed .-> {tid}")

    # Only style changed nodes — unchanged + external are left with default (no fill)
    lines.append("")
    lines.append("    classDef added fill:#d1fae5,stroke:#059669,stroke-width:2px,color:#064e3b")
    lines.append("    classDef removed fill:#fee2e2,stroke:#dc2626,stroke-width:2px,color:#7f1d1d,stroke-dasharray: 5 5")
    lines.append("    classDef modified fill:#fef3c7,stroke:#d97706,stroke-width:2px,color:#78350f")

    for mod in all_modules:
        mid = sanitize_id(mod["name"])
        if mod["name"] in added_names:
            lines.append(f"    class {mid} added")
        elif mod["name"] in removed_names:
            lines.append(f"    class {mid} removed")
        elif mod["name"] in modified_names:
            lines.append(f"    class {mid} modified")
        # Unchanged and external nodes: no class = default Mermaid styling (no fill)

    return "\n".join(lines)


def render_summary(diff: dict) -> str:
    lines = []

    if diff["added"]:
        lines.append("**Added:**")
        for m in diff["added"]:
            ext = " (external)" if m.get("type") == "external" else ""
            lines.append(f"  + {m['name']}{ext}")
        lines.append("")

    if diff["removed"]:
        lines.append("**Removed:**")
        for m in diff["removed"]:
            lines.append(f"  - {m['name']}")
        lines.append("")

    if diff["modified"]:
        lines.append("**Modified:**")
        for item in diff["modified"]:
            lines.append(f"  ~ {item['module']['name']}")
            for change in item["changes"]:
                lines.append(f"    {change}")
        lines.append("")

    if diff["added_edges"]:
        lines.append("**New dependencies:**")
        for src, tgt in sorted(diff["added_edges"]):
            lines.append(f"  + {src} -> {tgt}")
        lines.append("")

    if diff["removed_edges"]:
        lines.append("**Removed dependencies:**")
        for src, tgt in sorted(diff["removed_edges"]):
            lines.append(f"  - {src} -> {tgt}")
        lines.append("")

    total = len(diff["added"]) + len(diff["removed"]) + len(diff["modified"])
    if total == 0:
        lines.append("No architectural changes detected.")
    else:
        lines.append(f"**Total:** {len(diff['added'])} added, {len(diff['removed'])} removed, {len(diff['modified'])} modified")

    return "\n".join(lines)


def main():
    default_base = load_config().get("base_branch", "main")
    parser = argparse.ArgumentParser(description="Compare two unkode.yaml files and output diff")
    parser.add_argument("--base", help="Path to base unkode.yaml file")
    parser.add_argument("--base-branch", default=default_base, help=f"Git branch to extract base from (default: {default_base})")
    parser.add_argument("--current", default="unkode.yaml", help="Path to current unkode.yaml (default: unkode.yaml)")
    parser.add_argument("-o", "--output", help="Output markdown file (if omitted, prints to stdout)")
    args = parser.parse_args()

    # Load base
    if args.base:
        base_data = load_yaml(args.base)
    else:
        base_data = load_yaml_from_git(args.base_branch)
        if not base_data:
            print(f"Error: could not read unkode.yaml from branch '{args.base_branch}'", file=sys.stderr)
            sys.exit(1)

    # Load current
    curr_data = load_yaml(args.current)
    if not curr_data.get("architecture"):
        print("Error: no architecture section in current unkode.yaml", file=sys.stderr)
        sys.exit(1)

    base_arch = base_data.get("architecture", [])
    curr_arch = curr_data.get("architecture", [])

    diff = compute_diff(base_arch, curr_arch)

    # Build output
    has_changes = diff["added"] or diff["removed"] or diff["modified"]
    summary = render_summary(diff)

    if args.output:
        # File output: include Mermaid diagram for PR comments
        if not has_changes:
            output = f"# Architecture Diff\n\n{summary}\n"
        else:
            mermaid = render_diff_mermaid(diff, curr_arch)
            output = f"# Architecture Diff\n\n{summary}\n\n```mermaid\n{mermaid}\n```\n"
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Written: {args.output}")
    else:
        # Console output: summary only
        print(summary)


if __name__ == "__main__":
    main()
