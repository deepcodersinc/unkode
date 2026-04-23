import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { createRoot } from 'react-dom/client';
import ReactFlow, { Background, Controls, MiniMap, Handle, Position } from 'reactflow';
import htm from 'htm';
import yaml from 'js-yaml';
import dagre from '@dagrejs/dagre';

const html = htm.bind(React.createElement);

const LATEST_URL = 'latest_unkode.yaml';
const PREV_URL   = 'prev_unkode.yaml';

const NODE_W = 220;
const NODE_H = 72;

// ---- YAML loaders -----------------------------------------------------------

async function loadYaml(url) {
  const res = await fetch(url, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${url}`);
  return yaml.load(await res.text());
}

// ---- Graph build + layout ---------------------------------------------------

function buildNodes(arch, diffByName) {
  return arch.map((mod) => {
    const diff = diffByName ? diffByName[mod.name] : null;
    return {
      id: mod.name,
      type: 'archNode',
      position: { x: 0, y: 0 },
      data: {
        label: mod.name,
        tech: mod.tech || [],
        role: mod.role || '',
        kind: mod.kind || (mod.type === 'external' ? 'other' : 'backend'),
        isExternal: mod.type === 'external',
        components: mod.components || [],
        depends_on: mod.depends_on || [],
        raw: mod,
        status: diff ? diff.status : 'unchanged',   // 'added' | 'removed' | 'modified' | 'unchanged'
        changes: diff ? diff.changes : [],
      },
    };
  });
}

function buildEdges(arch, nodeIds, edgeStatus) {
  const edges = [];
  arch.forEach((mod) => {
    (mod.depends_on || []).forEach((dep) => {
      if (!nodeIds.has(dep)) return;
      const key = mod.name + '__' + dep;
      const status = edgeStatus ? (edgeStatus[key] || 'unchanged') : 'unchanged';
      edges.push({
        id: key,
        source: mod.name,
        target: dep,
        type: 'smoothstep',
        data: { status },
      });
    });
  });
  return edges;
}

function layout(nodes, edges) {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: 'LR', ranksep: 120, nodesep: 48, edgesep: 24 });
  g.setDefaultEdgeLabel(() => ({}));

  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));

  dagre.layout(g);

  return {
    nodes: nodes.map((n) => {
      const pos = g.node(n.id);
      return {
        ...n,
        position: { x: pos.x - NODE_W / 2, y: pos.y - NODE_H / 2 },
      };
    }),
    edges,
  };
}

// ---- Diff logic -------------------------------------------------------------

function computeDiff(prevArch, currArch) {
  const prevMap = new Map(prevArch.map((m) => [m.name, m]));
  const currMap = new Map(currArch.map((m) => [m.name, m]));

  const allNames = new Set([...prevMap.keys(), ...currMap.keys()]);

  const diffByName = {};       // name → { status, changes[] }
  let added = 0, removed = 0, modified = 0;

  for (const name of allNames) {
    const p = prevMap.get(name);
    const c = currMap.get(name);
    if (!p) {
      diffByName[name] = { status: 'added', changes: [] };
      added++;
      continue;
    }
    if (!c) {
      diffByName[name] = { status: 'removed', changes: [] };
      removed++;
      continue;
    }

    const changes = [];
    const oldDeps = new Set(p.depends_on || []);
    const newDeps = new Set(c.depends_on || []);
    for (const d of newDeps) if (!oldDeps.has(d)) changes.push({ type: 'dep_add', text: '+ depends on ' + d });
    for (const d of oldDeps) if (!newDeps.has(d)) changes.push({ type: 'dep_remove', text: '- no longer depends on ' + d });

    const oldTech = (p.tech || []).join(',');
    const newTech = (c.tech || []).join(',');
    if (oldTech !== newTech) changes.push({ type: 'tech', text: '~ tech: ' + (oldTech || '—') + ' → ' + (newTech || '—') });

    if ((p.role || '') !== (c.role || '')) changes.push({ type: 'role', text: '~ role updated' });
    if ((p.path || '') !== (c.path || '')) changes.push({ type: 'path', text: '~ path: ' + (p.path || '') + ' → ' + (c.path || '') });

    const pComps = new Set((p.components || []).filter((x) => typeof x === 'object').map((x) => x.name));
    const cComps = new Set((c.components || []).filter((x) => typeof x === 'object').map((x) => x.name));
    for (const cc of cComps) if (!pComps.has(cc)) changes.push({ type: 'comp_add', text: '+ new component: ' + cc });
    for (const cc of pComps) if (!cComps.has(cc)) changes.push({ type: 'comp_remove', text: '- removed component: ' + cc });

    if (changes.length) {
      diffByName[name] = { status: 'modified', changes };
      modified++;
    } else {
      diffByName[name] = { status: 'unchanged', changes: [] };
    }
  }

  // Edge status
  const edgeStatus = {};
  const prevEdges = new Set();
  const currEdges = new Set();
  prevArch.forEach((m) => (m.depends_on || []).forEach((d) => prevEdges.add(m.name + '__' + d)));
  currArch.forEach((m) => (m.depends_on || []).forEach((d) => currEdges.add(m.name + '__' + d)));

  for (const e of currEdges) edgeStatus[e] = prevEdges.has(e) ? 'unchanged' : 'added';
  for (const e of prevEdges) if (!currEdges.has(e)) edgeStatus[e] = 'removed';

  return { diffByName, edgeStatus, summary: { added, removed, modified } };
}

// ---- Node component ---------------------------------------------------------

const KIND_ICON = {
  frontend: '◨', backend: '◼', worker: '◇', library: '◉', cli: '›_',
  database: '▤', cache: '▥', queue: '⇥', api: '⟐', storage: '▦', other: '◦',
};

const STATUS_TAG = {
  added:    'NEW',
  removed:  'REMOVED',
  modified: 'CHANGED',
};

function ArchNode({ data, selected }) {
  const icon = KIND_ICON[data.kind] || KIND_ICON.other;
  const tech = (data.tech || []).slice(0, 2).join(', ');
  const status = data.status || 'unchanged';
  const tag = STATUS_TAG[status];

  const cls = [
    'archNode',
    data.isExternal ? 'archNodeExternal' : 'archNodeInternal',
    selected ? 'archNodeSelected' : '',
    status !== 'unchanged' ? 'archNode_' + status : '',
  ].join(' ').trim();

  return html`
    <div class=${cls}>
      <${Handle} type="target" position=${Position.Left} style=${{ opacity: 0 }} />
      <div class="archNodeIcon">${icon}</div>
      <div class="archNodeBody">
        <div class="archNodeName">${data.label}</div>
        ${tech ? html`<div class="archNodeTech">${tech}</div>` : null}
      </div>
      ${tag ? html`<div class=${'archNodeTag archNodeTag_' + status}>${tag}</div>` : null}
      <${Handle} type="source" position=${Position.Right} style=${{ opacity: 0 }} />
    </div>
  `;
}

const nodeTypes = { archNode: ArchNode };

// ---- Sidebars ---------------------------------------------------------------

function SidebarDetails({ selected }) {
  if (!selected) {
    return html`
      <div class="sidebarEmpty">
        <div class="sidebarEmptyIcon">◆</div>
        <div class="sidebarEmptyTitle">Click a module to see details</div>
        <div class="sidebarEmptyDesc">
          This is a live architecture rendered from <code>unkode.yaml</code>.
        </div>
      </div>
    `;
  }
  const d = selected.data;
  const kindLabel = d.isExternal ? `external · ${d.kind}` : d.kind;
  return html`
    <div class="sidebarContent">
      <div class="sidebarKind">${kindLabel}</div>
      <div class="sidebarName">${d.label}</div>
      ${d.role ? html`<div class="sidebarRole">${d.role}</div>` : null}
      ${d.tech && d.tech.length ? html`
        <div class="sidebarSection">
          <div class="sidebarSectionTitle">Tech</div>
          <div class="sidebarTags">
            ${d.tech.map((t) => html`<span class="sidebarTag" key=${t}>${t}</span>`)}
          </div>
        </div>` : null}
      ${d.depends_on && d.depends_on.length ? html`
        <div class="sidebarSection">
          <div class="sidebarSectionTitle">Depends on</div>
          <ul class="sidebarList">${d.depends_on.map((dep) => html`<li key=${dep}>${dep}</li>`)}</ul>
        </div>` : null}
      ${d.components && d.components.length ? html`
        <div class="sidebarSection">
          <div class="sidebarSectionTitle">Components</div>
          <ul class="sidebarList sidebarComponents">
            ${d.components.map((c) => {
              const name = typeof c === 'string' ? c : c.name;
              const desc = typeof c === 'object' ? c.description : null;
              return html`
                <li key=${name}>
                  <div class="sidebarComponentName">${name}</div>
                  ${desc ? html`<div class="sidebarComponentDesc">${desc}</div>` : null}
                </li>`;
            })}
          </ul>
        </div>` : null}
    </div>
  `;
}

function SidebarChanges({ selected, summary }) {
  if (!selected) {
    return html`
      <div class="sidebarContent">
        <div class="sidebarKind">Changes overview</div>
        <div class="sidebarName">This release</div>
        <div class="sidebarRole">
          Compared against the previous baseline. Click a highlighted module to see exactly what changed.
        </div>
        <div class="sidebarSection">
          <div class="sidebarSectionTitle">Summary</div>
          <div class="changeLegend">
            <div class="changeLegendRow"><span class="changeDot changeDot_added"></span><span>${summary.added} added</span></div>
            <div class="changeLegendRow"><span class="changeDot changeDot_removed"></span><span>${summary.removed} removed</span></div>
            <div class="changeLegendRow"><span class="changeDot changeDot_modified"></span><span>${summary.modified} modified</span></div>
          </div>
        </div>
      </div>
    `;
  }
  const d = selected.data;
  const status = d.status;
  return html`
    <div class="sidebarContent">
      <div class=${'sidebarKind sidebarKind_' + status}>${STATUS_TAG[status] || 'unchanged'}</div>
      <div class="sidebarName">${d.label}</div>
      ${d.role ? html`<div class="sidebarRole">${d.role}</div>` : null}
      ${status === 'added' ? html`<div class="changeNote">This module did not exist in the previous version.</div>` : null}
      ${status === 'removed' ? html`<div class="changeNote">This module has been removed from the current version.</div>` : null}
      ${status === 'modified' && d.changes && d.changes.length ? html`
        <div class="sidebarSection">
          <div class="sidebarSectionTitle">What changed</div>
          <ul class="changeList">
            ${d.changes.map((c, i) => html`<li key=${i} class=${'changeItem changeItem_' + c.type}>${c.text}</li>`)}
          </ul>
        </div>` : null}
      ${status === 'unchanged' ? html`<div class="changeNote">No changes to this module.</div>` : null}
    </div>
  `;
}

// ---- App root ---------------------------------------------------------------

function App() {
  const [tab, setTab] = useState('architecture');
  const [latest, setLatest] = useState(null);
  const [prev, setPrev] = useState(null);
  const [status, setStatus] = useState('loading');
  const [errorMsg, setErrorMsg] = useState('');
  const [selectedId, setSelectedId] = useState(null);

  // Listen to tab changes from TabsBar
  useEffect(() => {
    function onTab(e) { setTab(e.detail); }
    window.addEventListener('unkode:tab', onTab);
    return () => window.removeEventListener('unkode:tab', onTab);
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const [latestY, prevY] = await Promise.all([
          loadYaml(LATEST_URL),
          loadYaml(PREV_URL),
        ]);
        setLatest(latestY);
        setPrev(prevY);
        setStatus('ready');
      } catch (err) {
        setErrorMsg(err.message || 'Load error');
        setStatus('error');
      }
    })();
  }, []);

  // Clear selection when tab changes
  useEffect(() => setSelectedId(null), [tab]);

  const archData = useMemo(() => {
    if (!latest) return null;
    const arch = latest.architecture || [];
    const nodes = buildNodes(arch, null);
    const nodeIds = new Set(nodes.map((n) => n.id));
    const edges = buildEdges(arch, nodeIds, null);
    return layout(nodes, edges);
  }, [latest]);

  const diffData = useMemo(() => {
    if (!latest || !prev) return null;
    const prevArch = prev.architecture || [];
    const currArch = latest.architecture || [];
    const { diffByName, edgeStatus, summary } = computeDiff(prevArch, currArch);

    // Build combined module list (union)
    const combinedMap = new Map();
    currArch.forEach((m) => combinedMap.set(m.name, m));
    prevArch.forEach((m) => { if (!combinedMap.has(m.name)) combinedMap.set(m.name, m); });
    const combinedArch = Array.from(combinedMap.values());

    const nodes = buildNodes(combinedArch, diffByName);
    const nodeIds = new Set(nodes.map((n) => n.id));

    // Edges from both sides
    const allEdgeMap = new Map();
    currArch.forEach((m) =>
      (m.depends_on || []).forEach((d) => {
        if (!nodeIds.has(d)) return;
        allEdgeMap.set(m.name + '__' + d, { source: m.name, target: d });
      })
    );
    prevArch.forEach((m) =>
      (m.depends_on || []).forEach((d) => {
        if (!nodeIds.has(d)) return;
        const key = m.name + '__' + d;
        if (!allEdgeMap.has(key)) allEdgeMap.set(key, { source: m.name, target: d });
      })
    );

    const edges = Array.from(allEdgeMap.entries()).map(([key, e]) => ({
      id: key,
      source: e.source,
      target: e.target,
      type: 'smoothstep',
      data: { status: edgeStatus[key] || 'unchanged' },
    }));

    const laidOut = layout(nodes, edges);
    return { ...laidOut, summary };
  }, [latest, prev]);

  const active = tab === 'architecture' ? archData : diffData;

  // Styled edges based on tab + selection
  const connectedIds = useMemo(() => {
    if (!selectedId || !active) return null;
    const set = new Set([selectedId]);
    active.edges.forEach((e) => {
      if (e.source === selectedId) set.add(e.target);
      if (e.target === selectedId) set.add(e.source);
    });
    return set;
  }, [active, selectedId]);

  const displayNodes = useMemo(() => {
    if (!active) return [];
    return active.nodes.map((n) => {
      let style;
      if (connectedIds && !connectedIds.has(n.id)) style = { opacity: 0.35 };
      return { ...n, selected: n.id === selectedId, style };
    });
  }, [active, connectedIds, selectedId]);

  const displayEdges = useMemo(() => {
    if (!active) return [];
    return active.edges.map((e) => {
      const s = (e.data && e.data.status) || 'unchanged';
      const baseStyle = edgeStyleByStatus(s);
      const isConnected = selectedId && (e.source === selectedId || e.target === selectedId);
      if (!selectedId) return { ...e, style: baseStyle, animated: s === 'added' };
      if (isConnected) {
        return {
          ...e,
          animated: true,
          style: { ...baseStyle, strokeWidth: (baseStyle.strokeWidth || 1.5) + 0.8, opacity: 1 },
          zIndex: 10,
        };
      }
      return { ...e, style: { ...baseStyle, opacity: 0.2 }, zIndex: 0 };
    });
  }, [active, selectedId]);

  const selectedNode = useMemo(
    () => (active ? active.nodes.find((n) => n.id === selectedId) : null),
    [active, selectedId]
  );

  // Publish selection + tab to sidebar root
  useEffect(() => {
    window.dispatchEvent(new CustomEvent('unkode:sidebar', {
      detail: {
        tab,
        selected: selectedNode || null,
        summary: (diffData && diffData.summary) || { added: 0, removed: 0, modified: 0 },
      },
    }));
  }, [tab, selectedNode, diffData]);

  const onNodeClick = useCallback((_, node) => setSelectedId(node.id), []);
  const onPaneClick = useCallback(() => setSelectedId(null), []);

  // Tabs render into their own root
  useEffect(() => {
    const hint = document.getElementById('dashHint');
    if (hint) {
      hint.textContent = tab === 'architecture'
        ? 'Click a module to see details'
        : `${diffData ? diffData.summary.added : 0} added · ${diffData ? diffData.summary.removed : 0} removed · ${diffData ? diffData.summary.modified : 0} modified`;
    }
  }, [tab, diffData]);

  // ---- renders -----
  if (status === 'loading') {
    return html`
      <div class="dashState">
        <div class="spinner"></div>
        <div class="stateText">Loading…</div>
      </div>
    `;
  }
  if (status === 'error') {
    return html`
      <div class="dashState">
        <div class="stateIcon">◆</div>
        <div class="stateTitle">Couldn't load demo data</div>
        <div class="stateDesc">${errorMsg}</div>
        <div class="stateActions">
          <button class="ctaSecondary" onClick=${() => location.reload()}>Retry</button>
          <a class="ctaSecondary" href="/">← Home</a>
        </div>
      </div>
    `;
  }

  return html`
    <${ReactFlow}
      nodes=${displayNodes}
      edges=${displayEdges}
      nodeTypes=${nodeTypes}
      onNodeClick=${onNodeClick}
      onPaneClick=${onPaneClick}
      fitView
      fitViewOptions=${{ padding: 0.15 }}
      proOptions=${{ hideAttribution: true }}
      minZoom=${0.2}
      maxZoom=${2}
      nodesDraggable
      nodesConnectable=${false}
      elementsSelectable
    >
      <${Background} color="#1e2838" gap=${24} />
      <${Controls} showInteractive=${false} />
      <${MiniMap} pannable zoomable style=${{ background: '#0f1623', border: '1px solid #1e2838' }} nodeColor=${() => '#00ad00'} />
    <//>
  `;
}

function edgeStyleByStatus(status) {
  if (status === 'added')   return { stroke: '#00ad00', strokeWidth: 2,   strokeDasharray: '5 4' };
  if (status === 'removed') return { stroke: '#dc2626', strokeWidth: 2,   strokeDasharray: '5 4', opacity: 0.85 };
  return { stroke: '#2e3c52', strokeWidth: 1.5 };
}

// ---- Tabs bar ---------------------------------------------------------------

function TabsBar() {
  const [tab, setTab] = useState('architecture');

  useEffect(() => {
    window.dispatchEvent(new CustomEvent('unkode:tab', { detail: tab }));
  }, [tab]);

  return html`
    <div class="tabsBar">
      <button
        class=${'tabBtn ' + (tab === 'architecture' ? 'tabBtnActive' : '')}
        onClick=${() => setTab('architecture')}
      >Latest</button>
      <button
        class=${'tabBtn ' + (tab === 'changes' ? 'tabBtnActive' : '')}
        onClick=${() => setTab('changes')}
      >Changes</button>
    </div>
  `;
}

// ---- Sidebar root -----------------------------------------------------------

function SidebarRoot() {
  const [state, setState] = useState({
    tab: 'architecture',
    selected: null,
    summary: { added: 0, removed: 0, modified: 0 },
  });
  useEffect(() => {
    function onUpd(e) { setState(e.detail); }
    window.addEventListener('unkode:sidebar', onUpd);
    return () => window.removeEventListener('unkode:sidebar', onUpd);
  }, []);
  if (state.tab === 'changes') {
    return html`<${SidebarChanges} selected=${state.selected} summary=${state.summary} />`;
  }
  return html`<${SidebarDetails} selected=${state.selected} />`;
}

// ---- Mount ------------------------------------------------------------------

createRoot(document.getElementById('dashTabs')).render(html`<${TabsBar} />`);
createRoot(document.getElementById('flow')).render(html`<${App} />`);
createRoot(document.getElementById('sidebar')).render(html`<${SidebarRoot} />`);
