#!/usr/bin/env python3
"""Convert unkode.yaml to Mermaid diagram(s).

Usage:
    python yaml_to_mermaid.py unkode.yaml                  # outputs arch_map.md
    python yaml_to_mermaid.py unkode.yaml -o output.md     # custom output path
    python yaml_to_mermaid.py unkode.yaml --split          # separate files
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml


def load_config() -> dict:
    """Load config.yaml from the same directory as this script."""
    cfg_path = Path(__file__).parent / "config.yaml"
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def sanitize_id(name: str) -> str:
    """Convert a name to a safe Mermaid node ID."""
    return "".join(c if c.isalnum() else "_" for c in name).strip("_")


def escape_label(text: str) -> str:
    """Escape special Mermaid characters in labels."""
    return text.replace('"', "&quot;").replace("[", "(").replace("]", ")")


# Shape map: kind → (open, close) Mermaid shape brackets
INTERNAL_SHAPES = {
    "frontend": ("[/", "\\]"),       # trapezoid
    "backend":  ("[", "]"),           # rectangle
    "worker":   ("[\\", "/]"),        # inverted trapezoid
    "library":  ("([", "])"),         # stadium
    "cli":      (">", "]"),           # asymmetric
    "other":    ("(", ")"),           # rounded
}
EXTERNAL_SHAPES = {
    "database": ("[(", ")]"),         # cylinder
    "cache":    ("[(", ")]"),         # cylinder
    "storage":  ("[(", ")]"),         # cylinder
    "queue":    ("[/", "/]"),         # parallelogram
    "api":      ("[[", "]]"),         # subroutine
    "other":    ("(", ")"),           # rounded
}


def shape_node(node_id: str, label: str, kind: str | None, is_external: bool) -> str:
    """Render a Mermaid node with shape based on kind."""
    shapes = EXTERNAL_SHAPES if is_external else INTERNAL_SHAPES
    default = "other" if is_external else "backend"
    o, c = shapes.get(kind or default, shapes[default])
    return f'{node_id}{o}"{label}"{c}'


# ── Architecture diagram ────────────────────────────────────────────────────

LIGHT_THEME_INIT = "%%{init: {'theme':'neutral'}}%%"


def render_architecture(modules: list) -> str:
    direction = load_config().get("diagram_direction", "LR")
    lines = [LIGHT_THEME_INIT, f"graph {direction}"]

    externals = [m for m in modules if m.get("type") == "external"]
    internals = [m for m in modules if m.get("type") != "external"]

    for mod in internals:
        mid = sanitize_id(mod["name"])
        tech = ", ".join(mod.get("tech", []))
        label = f'{mod["name"]}'
        if tech:
            label += f" [{tech}]"

        comps = mod.get("components", [])
        if comps:
            lines.append(f'    subgraph {mid}["{escape_label(label)}"]')
            for comp in comps:
                cid = sanitize_id(f'{mod["name"]}_{comp["name"]}')
                lines.append(f'        {shape_node(cid, escape_label(comp["name"]), mod.get("kind"), False)}')
            lines.append("    end")
        else:
            lines.append(f'    {shape_node(mid, escape_label(label), mod.get("kind"), False)}')

    if externals:
        lines.append("")
        for ext in externals:
            eid = sanitize_id(ext["name"])
            lines.append(f'    {shape_node(eid, escape_label(ext["name"]), ext.get("kind"), True)}')

    lines.append("")
    all_names = {m["name"] for m in modules}
    for mod in internals:
        mid = sanitize_id(mod["name"])
        for dep in mod.get("depends_on", []):
            if dep not in all_names:
                continue
            did = sanitize_id(dep)
            lines.append(f"    {mid} --> {did}")

    for mod in internals:
        for comp in mod.get("components", []):
            cid = sanitize_id(f'{mod["name"]}_{comp["name"]}')
            for dep in comp.get("depends_on", []):
                found = False
                for other_mod in internals:
                    for other_comp in other_mod.get("components", []):
                        if other_comp["name"] == dep:
                            did = sanitize_id(f'{other_mod["name"]}_{other_comp["name"]}')
                            lines.append(f"    {cid} --> {did}")
                            found = True
                            break
                    if found:
                        break
                if not found and dep in all_names:
                    lines.append(f"    {cid} --> {sanitize_id(dep)}")

    return "\n".join(lines)


# ── Deployment diagram ──────────────────────────────────────────────────────

def render_deployment(deployment: list, architecture: list) -> str:
    if not deployment:
        return ""

    lines = [LIGHT_THEME_INIT, "graph TB"]

    for res in deployment:
        rid = sanitize_id(res["name"])
        tech = ", ".join(res.get("tech", []))
        label = res["name"]
        if tech:
            label += f" [{tech}]"

        hosts = res.get("hosts", [])
        if hosts:
            lines.append(f'    subgraph {rid}["{escape_label(label)}"]')
            for h in hosts:
                hid = sanitize_id(f'{res["name"]}_{h}')
                lines.append(f'        {hid}["{escape_label(h)}"]')
            lines.append("    end")
        else:
            lines.append(f'    {rid}[("{escape_label(label)}")]')

    lines.append("")
    dep_names = {r["name"] for r in deployment}
    for res in deployment:
        rid = sanitize_id(res["name"])
        for dep in res.get("depends_on", []):
            if dep in dep_names:
                lines.append(f"    {rid} --> {sanitize_id(dep)}")

    return "\n".join(lines)


# ── Combined single diagram ─────────────────────────────────────────────────

def render_combined(architecture: list, deployment: list) -> str:
    direction = load_config().get("diagram_direction", "LR")
    lines = [LIGHT_THEME_INIT, f"graph {direction}"]

    externals = [m for m in architecture if m.get("type") == "external"]
    internals = [m for m in architecture if m.get("type") != "external"]
    all_names = {m["name"] for m in architecture}

    # Group architecture modules inside deployment subgraphs
    hosted_modules = set()
    if deployment:
        internal_names = {m["name"] for m in internals}
        for res in deployment:
            hosts = [h for h in res.get("hosts", []) if h not in hosted_modules and h in internal_names]
            if not hosts:
                continue
            for h in hosts:
                hosted_modules.add(h)

            rid = sanitize_id(res["name"])
            tech = ", ".join(res.get("tech", []))
            res_label = res["name"]
            if tech:
                res_label += f" [{tech}]"

            lines.append(f'    subgraph {rid}["{escape_label(res_label)}"]')
            for mod in internals:
                if mod["name"] not in hosts:
                    continue
                mid = sanitize_id(mod["name"])
                tech_m = ", ".join(mod.get("tech", []))
                label = mod["name"]
                if tech_m:
                    label += f" [{tech_m}]"
                comps = mod.get("components", [])
                if comps:
                    lines.append(f'        subgraph {mid}["{escape_label(label)}"]')
                    for comp in comps:
                        cid = sanitize_id(f'{mod["name"]}_{comp["name"]}')
                        lines.append(f'            {shape_node(cid, escape_label(comp["name"]), mod.get("kind"), False)}')
                    lines.append("        end")
                else:
                    lines.append(f'        {shape_node(mid, escape_label(label), mod.get("kind"), False)}')
            lines.append("    end")

    # Unhosted internal modules
    for mod in internals:
        if mod["name"] in hosted_modules:
            continue
        mid = sanitize_id(mod["name"])
        tech = ", ".join(mod.get("tech", []))
        label = mod["name"]
        if tech:
            label += f" [{tech}]"
        comps = mod.get("components", [])
        if comps:
            lines.append(f'    subgraph {mid}["{escape_label(label)}"]')
            for comp in comps:
                cid = sanitize_id(f'{mod["name"]}_{comp["name"]}')
                lines.append(f'        {shape_node(cid, escape_label(comp["name"]), mod.get("kind"), False)}')
            lines.append("    end")
        else:
            lines.append(f'    {shape_node(mid, escape_label(label), mod.get("kind"), False)}')

    # External services
    if externals:
        lines.append("")
        for ext in externals:
            eid = sanitize_id(ext["name"])
            lines.append(f'    {shape_node(eid, escape_label(ext["name"]), ext.get("kind"), True)}')

    # Module-level dependency edges
    lines.append("")
    for mod in internals:
        mid = sanitize_id(mod["name"])
        for dep in mod.get("depends_on", []):
            if dep not in all_names:
                continue
            lines.append(f"    {mid} --> {sanitize_id(dep)}")

    return "\n".join(lines)


# ── Markdown output ─────────────────────────────────────────────────────────

def to_markdown(architecture: list, deployment: list, split: bool = False):
    if split:
        arch_md = f"# Architecture\n\n```mermaid\n{render_architecture(architecture)}\n```\n"
        dep_md = ""
        if deployment:
            dep_md = f"# Deployment\n\n```mermaid\n{render_deployment(deployment, architecture)}\n```\n"
        return arch_md, dep_md
    else:
        combined = render_combined(architecture, deployment)
        sections = [f"# Architecture\n\n```mermaid\n{combined}\n```\n"]

        # Module index
        internals = [m for m in architecture if m.get("type") != "external"]
        if internals:
            sections.append("---\n")
            for mod in internals:
                tech = ", ".join(mod.get("tech", []))
                sections.append(f"### {mod['name']}" + (f" `{tech}`" if tech else ""))
                sections.append(f"\n{mod.get('role', '')}\n")
                if mod.get("path"):
                    sections.append(f"**Path:** `{mod['path']}`\n")
                deps = mod.get("depends_on", [])
                if deps:
                    sections.append(f"**Depends on:** {', '.join(deps)}\n")
                for comp in mod.get("components", []):
                    sections.append(f"- **{comp['name']}** — {comp.get('description', '')}")
                sections.append("")

        # Deployment diagram
        if deployment:
            dep_diagram = render_deployment(deployment, architecture)
            sections.append("---\n")
            sections.append(f"## Deployment\n\n```mermaid\n{dep_diagram}\n```\n")

            for res in deployment:
                tech = ", ".join(res.get("tech", []))
                hosts = res.get("hosts", [])
                deps = res.get("depends_on", [])
                sections.append(f"**{res['name']}**" + (f" `{tech}`" if tech else ""))
                sections.append(f": {res.get('role', '')}")
                if hosts:
                    sections.append(f"  Hosts: {', '.join(hosts)}")
                if deps:
                    sections.append(f"  Depends on: {', '.join(deps)}")
                sections.append("")

        return "\n".join(sections), None


# ── CLI ─────────────────────────────────────────────────────────────────────

def check_staleness(meta: dict) -> str:
    """Check if unkode.yaml is in sync with current HEAD. Returns warning string or empty."""
    last_sync = meta.get("last_sync_commit", "")
    if not last_sync:
        return ""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""

    if head[:7] == str(last_sync)[:7]:
        return ""
    return f"> :warning: **Architecture may be outdated** (last synced at `{str(last_sync)[:7]}`, current HEAD is `{head[:7]}`). Run `/unkode` to update.\n\n"


def main():
    parser = argparse.ArgumentParser(description="Convert unkode.yaml to Mermaid diagrams")
    parser.add_argument("input", help="Path to unkode.yaml")
    parser.add_argument("-o", "--output", default="arch_map.md", help="Output markdown file (default: arch_map.md)")
    parser.add_argument("--split", action="store_true", help="Generate separate files for architecture and deployment")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    architecture = data.get("architecture", [])
    deployment = data.get("deployment", [])
    meta = data.get("_meta", {})

    if not architecture:
        print("Error: no architecture section found in YAML", file=sys.stderr)
        sys.exit(1)

    arch_md, dep_md = to_markdown(architecture, deployment, split=args.split)

    # Prepend staleness warning if needed
    warning = check_staleness(meta)
    if warning:
        arch_md = warning + arch_md

    output_path = Path(args.output)
    output_path.write_text(arch_md, encoding="utf-8")
    print(f"Written: {output_path}")

    if args.split and dep_md:
        dep_path = output_path.with_name("deployment.md")
        dep_path.write_text(dep_md, encoding="utf-8")
        print(f"Written: {dep_path}")


if __name__ == "__main__":
    main()
