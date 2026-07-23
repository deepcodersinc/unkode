#!/usr/bin/env python3
"""Convert unkode.yaml to a standalone, interactive React Flow diagram (HTML).

Produces a single self-contained .html file that renders an interactive
architecture diagram in any browser — no server, no build step, no install.
React + React Flow + dagre are loaded from a CDN via an import map (https
fetches, which browsers allow from file:// pages); the architecture itself is
inlined as JSON, so the page works when opened by double-click.

Usage:
    python yaml_to_reactflow.py unkode.yaml                 # outputs arch_map.html
    python yaml_to_reactflow.py unkode.yaml -o arch.html    # custom output path
"""

import argparse
import json
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
    """Convert a name to a safe node ID (matches the Mermaid generator)."""
    return "".join(c if c.isalnum() else "_" for c in name).strip("_")


# ── Model → graph ────────────────────────────────────────────────────────────

def build_graph(architecture: list) -> dict:
    """Turn the architecture list into nodes + edges for React Flow.

    Modules and external services become nodes; `depends_on` becomes edges.
    Components are attached to their module node's data for the detail panel
    (matching how the Mermaid generator groups them inside a subgraph).
    """
    all_names = {m["name"] for m in architecture}
    id_of = {m["name"]: sanitize_id(m["name"]) for m in architecture}

    nodes = []
    for mod in architecture:
        is_external = mod.get("type") == "external"
        nodes.append({
            "id": id_of[mod["name"]],
            "name": mod["name"],
            "kind": mod.get("kind") or ("other" if is_external else "backend"),
            "isExternal": is_external,
            "tech": mod.get("tech", []),
            "role": mod.get("role", ""),
            "path": mod.get("path", ""),
            "dependsOn": [d for d in mod.get("depends_on", []) if d in all_names],
            "components": [
                {"name": c["name"], "description": c.get("description", "")}
                for c in mod.get("components", []) if isinstance(c, dict)
            ],
            # status is reserved for the diff view: added | removed | modified | None
            "status": mod.get("_status"),
        })

    edges = []
    seen = set()
    for mod in architecture:
        src = id_of[mod["name"]]
        for dep in mod.get("depends_on", []):
            if dep not in all_names:
                continue
            tgt = id_of[dep]
            key = (src, tgt)
            if key in seen:
                continue
            seen.add(key)
            edges.append({"id": f"{src}__{tgt}", "source": src, "target": tgt})

    return {"nodes": nodes, "edges": edges}


# ── HTML template ────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>__TITLE__</title>
<link rel="stylesheet" href="https://esm.sh/reactflow@11.11.4/dist/style.css" />
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  html, body, #root { height: 100%; margin: 0; }
  body {
    font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    background: #f8fafc;
    color: #0f172a;
  }
  #root { display: flex; }
  .flow-wrap { flex: 1 1 auto; position: relative; }
  header {
    position: absolute; top: 0; left: 0; right: 0; z-index: 5;
    display: flex; align-items: center; gap: 12px;
    padding: 10px 16px;
    background: rgba(248,250,252,0.9);
    border-bottom: 1px solid #e2e8f0;
    backdrop-filter: blur(6px);
  }
  header h1 { font-size: 14px; font-weight: 650; margin: 0; letter-spacing: .2px; }
  header .legend { display: flex; gap: 14px; margin-left: auto; font-size: 12px; color: #475569; }
  header .legend span { display: inline-flex; align-items: center; gap: 5px; }
  header .dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block; border: 1.5px solid; }

  .node {
    padding: 9px 13px; border-radius: 9px; border: 1.5px solid;
    background: #ffffff; min-width: 120px; max-width: 230px;
    box-shadow: 0 1px 2px rgba(15,23,42,0.06);
    cursor: pointer; transition: box-shadow .12s, transform .12s;
  }
  .node:hover { box-shadow: 0 4px 14px rgba(15,23,42,0.14); transform: translateY(-1px); }
  .node.selected { box-shadow: 0 0 0 3px rgba(59,130,246,0.35); }
  .node .title { font-size: 13px; font-weight: 620; line-height: 1.25; }
  .node .kind { font-size: 10px; text-transform: uppercase; letter-spacing: .6px; opacity: .65; margin-top: 2px; }
  .node .tech { font-size: 11px; opacity: .7; margin-top: 4px; }
  .node.external { border-style: dashed; background: #f1f5f9; }

  /* diff status */
  .node.added    { background: #d1fae5; border-color: #059669; color: #064e3b; }
  .node.removed  { background: #fee2e2; border-color: #dc2626; color: #7f1d1d; border-style: dashed; }
  .node.modified { background: #fef3c7; border-color: #d97706; color: #78350f; }

  aside {
    width: 340px; flex: 0 0 340px; border-left: 1px solid #e2e8f0;
    background: #ffffff; padding: 20px; overflow-y: auto;
  }
  aside.empty { color: #94a3b8; font-size: 13px; display: flex; align-items: center; justify-content: center; text-align: center; }
  aside h2 { font-size: 17px; margin: 0 0 2px; }
  aside .k { font-size: 11px; text-transform: uppercase; letter-spacing: .6px; color: #64748b; margin-bottom: 14px; }
  aside .row { margin-bottom: 14px; }
  aside .row .label { font-size: 11px; text-transform: uppercase; letter-spacing: .5px; color: #94a3b8; margin-bottom: 4px; }
  aside .row .val { font-size: 13px; line-height: 1.5; }
  aside code { background: #f1f5f9; padding: 1px 6px; border-radius: 4px; font-size: 12px; }
  aside .chip { display: inline-block; background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe;
                padding: 2px 9px; border-radius: 999px; font-size: 12px; margin: 0 5px 5px 0; }
  aside .comp { border: 1px solid #e2e8f0; border-radius: 8px; padding: 9px 11px; margin-bottom: 8px; }
  aside .comp .cn { font-size: 13px; font-weight: 600; }
  aside .comp .cd { font-size: 12px; color: #475569; margin-top: 2px; line-height: 1.45; }

  @media (prefers-color-scheme: dark) {
    body { background: #0b1120; color: #e2e8f0; }
    header { background: rgba(11,17,32,0.9); border-color: #1e293b; }
    header .legend { color: #94a3b8; }
    .node { background: #1e293b; box-shadow: 0 1px 2px rgba(0,0,0,0.4); }
    .node.external { background: #172033; }
    aside { background: #0f172a; border-color: #1e293b; }
    aside code { background: #1e293b; }
    aside .chip { background: #172033; color: #93c5fd; border-color: #1e3a5f; }
    aside .comp { border-color: #1e293b; }
    aside .comp .cd { color: #94a3b8; }
  }
</style>
<script type="importmap">
{
  "imports": {
    "react": "https://esm.sh/react@18.3.1",
    "react-dom": "https://esm.sh/react-dom@18.3.1",
    "react-dom/client": "https://esm.sh/react-dom@18.3.1/client",
    "reactflow": "https://esm.sh/reactflow@11.11.4?deps=react@18.3.1,react-dom@18.3.1",
    "@dagrejs/dagre": "https://esm.sh/@dagrejs/dagre@1.1.4",
    "htm": "https://esm.sh/htm@3.1.1"
  }
}
</script>
</head>
<body>
<div id="root"></div>
<script type="module">
import React, { useState, useMemo, useCallback } from "react";
import { createRoot } from "react-dom/client";
import ReactFlow, { Background, Controls, MiniMap, Handle, Position, ReactFlowProvider } from "reactflow";
import dagre from "@dagrejs/dagre";
import htm from "htm";

const html = htm.bind(React.createElement);

const DATA = __UNKODE_DATA__;
const DIRECTION = "__DIRECTION__"; // "LR" or "TB"

// kind → accent color for the plain (non-diff) view
const KIND_COLOR = {
  frontend: "#8b5cf6", backend: "#3b82f6", worker: "#f59e0b",
  library: "#10b981", cli: "#64748b", other: "#94a3b8",
  database: "#0ea5e9", cache: "#ef4444", queue: "#f97316",
  api: "#ec4899", storage: "#14b8a6",
};

const NODE_W = 190, NODE_H = 62;

function layout(nodes, edges, direction) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: direction, nodesep: 45, ranksep: 80, marginx: 30, marginy: 30 });
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);
  return nodes.map((n) => {
    const p = g.node(n.id);
    return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } };
  });
}

function ArchNode({ data, selected }) {
  const accent = KIND_COLOR[data.kind] || KIND_COLOR.other;
  const cls = ["node"];
  if (data.isExternal) cls.push("external");
  if (data.status) cls.push(data.status);
  if (selected) cls.push("selected");
  const style = data.status ? {} : { borderColor: accent };
  return html`
    <div class=${cls.join(" ")} style=${style}>
      <${Handle} type="target" position=${DIRECTION === "LR" ? Position.Left : Position.Top} style=${{ opacity: 0 }} />
      <div class="title">${data.name}</div>
      <div class="kind">${data.isExternal ? "ext · " : ""}${data.kind}</div>
      ${data.tech && data.tech.length
        ? html`<div class="tech">${data.tech.join(", ")}</div>` : null}
      <${Handle} type="source" position=${DIRECTION === "LR" ? Position.Right : Position.Bottom} style=${{ opacity: 0 }} />
    </div>`;
}

function DetailPanel({ node }) {
  if (!node) {
    return html`<aside class="empty">Click a module to see its role, dependencies, and components.</aside>`;
  }
  const d = node.data;
  return html`
    <aside>
      <h2>${d.name}</h2>
      <div class="k">${d.isExternal ? "External · " : ""}${d.kind}</div>
      ${d.role ? html`<div class="row"><div class="label">Role</div><div class="val">${d.role}</div></div>` : null}
      ${d.path ? html`<div class="row"><div class="label">Path</div><div class="val"><code>${d.path}</code></div></div>` : null}
      ${d.tech && d.tech.length ? html`
        <div class="row"><div class="label">Tech</div><div class="val">
          ${d.tech.map((t) => html`<span class="chip" key=${t}>${t}</span>`)}
        </div></div>` : null}
      ${d.dependsOn && d.dependsOn.length ? html`
        <div class="row"><div class="label">Depends on</div><div class="val">
          ${d.dependsOn.map((t) => html`<span class="chip" key=${t}>${t}</span>`)}
        </div></div>` : null}
      ${d.components && d.components.length ? html`
        <div class="row"><div class="label">Components</div><div class="val">
          ${d.components.map((c) => html`
            <div class="comp" key=${c.name}>
              <div class="cn">${c.name}</div>
              ${c.description ? html`<div class="cd">${c.description}</div>` : null}
            </div>`)}
        </div></div>` : null}
    </aside>`;
}

function App() {
  const nodeTypes = useMemo(() => ({ arch: ArchNode }), []);
  const [selectedId, setSelectedId] = useState(null);

  const rfNodes = useMemo(() => {
    const laid = layout(DATA.nodes, DATA.edges, DIRECTION);
    return laid.map((n) => ({
      id: n.id, type: "arch", position: n.position, data: n,
    }));
  }, []);

  const rfEdges = useMemo(() =>
    DATA.edges.map((e) => ({
      ...e, animated: false,
      markerEnd: { type: "arrowclosed" },
      style: { stroke: "#94a3b8", strokeWidth: 1.5 },
    })), []);

  const selectedNode = rfNodes.find((n) => n.id === selectedId) || null;
  const onNodeClick = useCallback((_e, node) => setSelectedId(node.id), []);
  const onPaneClick = useCallback(() => setSelectedId(null), []);

  return html`
    <div class="flow-wrap">
      <header>
        <h1>${DATA.title}</h1>
        <div class="legend">
          <span><span class="dot" style=${{ borderColor: KIND_COLOR.frontend }}></span>frontend</span>
          <span><span class="dot" style=${{ borderColor: KIND_COLOR.backend }}></span>backend</span>
          <span><span class="dot" style=${{ borderColor: KIND_COLOR.worker }}></span>worker</span>
          <span><span class="dot" style=${{ borderColor: KIND_COLOR.library }}></span>library</span>
          <span><span class="dot" style=${{ borderColor: KIND_COLOR.other, borderStyle: "dashed" }}></span>external</span>
        </div>
      </header>
      <${ReactFlowProvider}>
        <${ReactFlow}
          nodes=${rfNodes.map((n) => ({ ...n, selected: n.id === selectedId }))}
          edges=${rfEdges}
          nodeTypes=${nodeTypes}
          onNodeClick=${onNodeClick}
          onPaneClick=${onPaneClick}
          fitView
          minZoom=${0.15}
          proOptions=${{ hideAttribution: true }}
        >
          <${Background} gap=${20} size=${1} color="#cbd5e1" />
          <${Controls} showInteractive=${false} />
          <${MiniMap} pannable zoomable nodeColor=${(n) => KIND_COLOR[n.data.kind] || KIND_COLOR.other} />
        <//>
      <//>
    </div>
    <${DetailPanel} node=${selectedNode} />`;
}

createRoot(document.getElementById("root")).render(html`<${App} />`);
</script>
</body>
</html>
"""


# ── Staleness banner (mirrors yaml_to_mermaid.check_staleness) ───────────────

def head_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def render_html(graph: dict, title: str, direction: str) -> str:
    payload = {"title": title, "nodes": graph["nodes"], "edges": graph["edges"]}
    data_json = json.dumps(payload, ensure_ascii=False)
    # Guard against the data accidentally closing the inline <script>.
    data_json = data_json.replace("</", "<\\/")
    return (
        HTML_TEMPLATE
        .replace("__UNKODE_DATA__", data_json)
        .replace("__DIRECTION__", "LR" if direction == "LR" else "TB")
        .replace("__TITLE__", title)
    )


def main():
    parser = argparse.ArgumentParser(description="Convert unkode.yaml to a standalone React Flow HTML diagram")
    parser.add_argument("input", help="Path to unkode.yaml")
    parser.add_argument("-o", "--output", default="arch_map.html", help="Output HTML file (default: arch_map.html)")
    parser.add_argument("--title", default="Architecture — unkode", help="Diagram title shown in the header")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    architecture = data.get("architecture", [])
    if not architecture:
        print("Error: no architecture section found in YAML", file=sys.stderr)
        sys.exit(1)

    direction = load_config().get("diagram_direction", "LR")
    graph = build_graph(architecture)
    html_out = render_html(graph, args.title, direction)

    output_path = Path(args.output)
    output_path.write_text(html_out, encoding="utf-8")
    print(f"Written: {output_path}")


if __name__ == "__main__":
    main()
