# unkode

> Catch architectural drift on every PR or local changes.

AI agents now write code faster than humans can review it. That speed comes at a cost — architecture drifts. New dependencies appear, boundaries break, and nobody notices until the system is unrecognizable.

**Unkode** makes architectural changes visible on every pull request. A color-coded diff shows exactly which modules were added, removed, or rewired. The architecture map stays in sync with the code — automatically, in the repo, versioned like everything else.

Visit **[unkode.dev](https://unkode.dev)** for updates.  
If you find this useful, a GitHub star ⭐ would be much appreciated.

---

## What it looks like

On every PR, unkode posts a clean text summary of what changed plus a link to the live interactive dashboard:

```
# Architecture Diff

**Added:**
  + Notifications
  + SMS

**Modified:**
  ~ tRPC API
    + depends on Authentication

**Total:** 2 added, 0 removed, 1 modified

---

[Open interactive view](https://unkode.dev/dashboard/?repo=owner/name&pr=123) — explore the changes in unkode.dev
```

Click the link → opens an interactive diagram at **[unkode.dev/dashboard](https://unkode.dev/dashboard/?repo=deepcodersinc/documenso)** with color-coded nodes (green = added, red = removed, amber = modified). Click any module to see exactly what changed — its dependencies, components, role.

**Try it now:** [unkode.dev/dashboard/?repo=deepcodersinc/documenso](https://unkode.dev/dashboard/?repo=deepcodersinc/documenso)

Artifacts in your repo, all under `.unkode/`:

- **`.unkode/arch.yaml`** — the architecture as structured data (source of truth)
- **`.unkode/arch_map.md`** — Mermaid diagram of the current state (auto-generated, renders inline on GitHub — useful when the repo is private)
- **`.unkode/arch_map.html`** — a standalone, interactive React Flow diagram (auto-generated). Double-click to open in any browser — pan, zoom, drag nodes, click a module for its role, dependencies, and components. No server, no build step, no install; works fully offline after the first open.
- **The dashboard** at unkode.dev needs nothing beyond that one YAML — it pulls live from your default branch

> Upgrading from an earlier version? The map used to sit loose in the repo root as `unkode.yaml`. Running `/unkode init` detects the old layout and offers to move it into `.unkode/` — your map is preserved, nothing is re-analyzed.

---

## Quick setup

One-time setup per repository.

### 1. Copy the skill to your repo

Unkode ships as a Claude Code skill (also compatible with other agents that read `.agents/skills/`).

```bash
# For Claude Code
cp -r unkode/skills/unkode .claude/skills/unkode

# For other agents (Codex, Cursor, Aider, etc.)
cp -r unkode/skills/unkode .agents/skills/unkode
```

### 2. Generate the baseline

In Claude Code, from your repo root:

```
/unkode init
```

This analyzes your codebase, writes `.unkode/arch.yaml`, validates it against the actual file tree, and renders both diagrams. Takes 2-5 minutes. Commit the `.unkode/` folder as your baseline.

### 3. (Recommended) Add the GitHub Action

On every PR, the action posts a color-coded diff diagram showing exactly what changed architecturally. Without it, drift still gets caught, but reviewers have to read the YAML manually.

```bash
# Copy the action
mkdir -p .github/actions/unkode
cp unkode/config/github/action.yml .github/actions/unkode/action.yml

# Copy the workflow
cp unkode/config/github/unkode_arch_check.yml .github/workflows/unkode_arch_check.yml
```

---

## Dev workflow

Once setup is done, this is what your day-to-day looks like:

```
 ┌──────────────┐     ┌──────────────┐     ┌────────────────┐
 │ /unkode init │────▶│ arch.yaml    │────▶│ arch_map.md    │
 │ (once)       │     │ (validated)  │     │ arch_map.html  │
 └──────────────┘     └──────┬───────┘     └────────────────┘
                             │
                      ┌──────▼───────┐     ┌────────────────┐
                      │ Commit to    │────▶│ PR opened      │
                      │ your branch  │     │ Action posts   │
                      └──────────────┘     │ the diff       │
                                           └────────────────┘
```

1. **Make code changes** on a branch as you normally would.
2. **Run `/unkode render`** to regenerate the diagrams from `.unkode/arch.yaml`:

   | Command | What it does |
   |---------|--------------|
   | `/unkode init` | Analyze the codebase, write `.unkode/arch.yaml`, render both diagrams. Costs tokens. |
   | `/unkode init --force` | Same, but overwrites an existing map — including any manual edits |
   | `/unkode render` | Regenerate **both** diagrams from `.unkode/arch.yaml` |
   | `/unkode render --mermaid` | Regenerate **only** `.unkode/arch_map.md` |
   | `/unkode render --html` | Regenerate **only** `.unkode/arch_map.html` |

   `render` never analyzes code and never writes `arch.yaml` — it's instant and costs zero tokens. `init` is the only command that reads your codebase, and it refuses to run over an existing map unless you pass `--force`.
3. **Commit and open a PR.** The GitHub Action compares `.unkode/arch.yaml` against your base branch and posts a text summary of architectural changes plus a deep link to the interactive dashboard at [unkode.dev/dashboard](https://unkode.dev/dashboard/?repo=deepcodersinc/documenso). Reviewers click through to explore the diff visually.
4. **Merge.** The updated `.unkode/arch.yaml` on main becomes the new baseline for future PRs.

---

## Config

Edit `config.yaml` inside the installed skill — `.claude/skills/unkode/config.yaml` (or `.agents/skills/unkode/config.yaml`):

```yaml
# The branch to compare against for diffs
base_branch: main

# Directories to ignore when analyzing the codebase
exclude_paths: []

# Diagram flow direction: LR (left-right) or TB (top-bottom)
diagram_direction: LR
```

---

## Token usage & cost

unkode is frugal. Running it doesn't burn through your subscription.

| Operation | When | Cost | Time |
|-----------|------|------|------|
| `/unkode init` | Once per repo | Agent analysis | 2–5 min |
| `/unkode render` | Anytime | Free | instant |
| Validation | Inside `init` | Free | instant |
| PR diff on GitHub Action | Every PR | Free | seconds |
| Dashboard rendering at unkode.dev | Anytime, anyone | Free | instant |

The first run depends less on codebase size and more on **how well-documented the project is**. A 1.5M LOC monorepo with clear package boundaries and READMEs costs roughly the same as a smaller but less organized repo. For best results, add README files and module-level docs before running unkode for the first time — the agent picks up context quickly and produces a sharper architecture map.

Everything downstream of the YAML — validation, Mermaid generation, the React Flow diagram, PR diffs, the dashboard — is deterministic and rule-based. No agent involvement, no tokens used.

---

## Why Unkode

- **AI writes code 10x faster. Architecture drifts 10x faster too.** unkode flags drift on every PR so nothing slips through.
- **PRs hide architectural impact.** Code diffs don't show "this PR added a direct database dependency from the frontend." unkode does.
- **Diagrams in Confluence go stale. Diagrams in your repo don't.** Versioned, diffable, always the truth.
- **No vendor lock-in.** The YAML is yours. The Mermaid is yours. The tooling is open source. Use any diagram editor, any AI agent.

---

## What's next

Unkode works today, but I'm actively building a more rigorous pipeline with stronger accuracy guarantees and zero hallucination — plus new features like supporting more diagram formats, multi-repo dashboards, architecture history timelines and integration.

If you'd like to hear about major updates as they ship, drop your email on the [waitlist](https://tally.so/r/lb7odB).

No marketing, no spam — just a single notification when a new iteration is ready.

---

## Feedback

Unkode is early. What's working, what isn't, what would make it valuable for your team — please share.

- **Bugs and feature requests:** [GitHub Issues](https://github.com/deepcodersinc/unkode/issues)
- **Discussion, ideas, questions:** [GitHub Discussions](https://github.com/deepcodersinc/unkode/discussions)

---

## License

Apache 2.0 — see [LICENSE](LICENSE)

---

## Links

- Website: [unkode.dev](https://unkode.dev)
