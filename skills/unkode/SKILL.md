---
name: unkode
description: Generate and render an architecture map (.unkode/arch.yaml + Mermaid + React Flow diagrams) from the codebase
---

# Unkode — Architecture Map

## Configuration

Read `<skill-dir>/config.yaml` at the start. It contains:
- `exclude_paths` — directories to ignore during analysis (skip these when identifying modules)
- `diagram_direction` — diagram flow (LR or TB)
- `base_branch` — used by the PR check, not by these commands

Apply `exclude_paths` when scanning the codebase during Init. The converter scripts read the other settings automatically.

## Commands

Two commands. There is no bare `/unkode` — if the user gives no subcommand, show them the two options and stop.

| Command | What it does |
|---------|--------------|
| `init` | Analyze the codebase, write `.unkode/arch.yaml`, render both diagrams. Costs tokens. |
| `init --force` | Same, but overwrites an existing map. |
| `render` | Regenerate diagrams from `.unkode/arch.yaml`. No analysis, no tokens. |
| `render --mermaid` | Render only `.unkode/arch_map.md`. |
| `render --html` | Render only `.unkode/arch_map.html`. |

`init` takes no format flags — it always renders both. To produce just one, run `render` afterwards.

## File layout

Everything unkode owns lives in `.unkode/` in the project root:

```
.unkode/
  arch.yaml        the architecture map — source of truth
  arch_map.md      generated Mermaid diagram
  arch_map.html    generated React Flow diagram
```

Older versions wrote `unkode.yaml`, `arch_map.md`, and `arch_map.html` loose in the root. The scripts still read a root-level `unkode.yaml` so those repos keep working, but everything they generate goes into `.unkode/`.

**Never hand-write `.unkode/arch.yaml` wholesale.** Rewriting the whole map is what `init --force` is for. Outside of that, only targeted edits — fixing a name, correcting a dependency — are appropriate.

## Flow

The source of truth is `.unkode/arch.yaml`. Everything derived from it is deterministic and uses no tokens.

**`init`**
- A map exists (either `.unkode/arch.yaml` or a legacy root `unkode.yaml`) and `--force` was not passed → do not analyze anything. Tell the user:

  > Architecture map already exists (N modules, M externals). Use `/unkode render` to regenerate the diagrams, or `/unkode init --force` to discard it and re-analyze from scratch.

  Stop here.
- A legacy root `unkode.yaml` exists but `.unkode/arch.yaml` does not → **offer to migrate instead of re-analyzing**. Moving costs nothing and keeps the map. Run `git mv unkode.yaml .unkode/arch.yaml` (falling back to a plain move if the file isn't tracked), delete any root-level `arch_map.md` / `arch_map.html`, run the **Generate Step**, and stop. Do not run the Init Process — the existing map is still good.
- A map exists and `--force` was passed → warn that this overwrites the existing map including any manual corrections, then run the **Init Process**.
- No map anywhere → run the **Init Process**.

**`render`**
- No map found → tell the user "No architecture map found. Run `/unkode init` first." and stop. Do not analyze the codebase.
- Otherwise → run the **Generate Step**. Never modify `arch.yaml`.

## Generate Step

The scripts find the map and write into `.unkode/` on their own — pass no arguments:

- Mermaid → `python <skill-dir>/yaml_to_mermaid.py`
- React Flow → `python <skill-dir>/yaml_to_reactflow.py`

With no format flag, generate both. After generating, tell the user which file(s) were written, and when `arch_map.html` was among them add: "Open .unkode/arch_map.html in a browser for the interactive view."

---

## Init Process

Builds `.unkode/arch.yaml` from scratch.

Before starting, tell the user how long it takes — in **time, not tokens**:

> Analyzing the codebase to build your architecture map. This usually takes 2-5 minutes.

Do not ask for confirmation and do not ask the user to approve module boundaries. This runs end to end without questions; someone who doesn't read the code should be able to run it.

> **Source of truth is the code, not the docs.** Documentation files (README, ARCHITECTURE.md, CONTRIBUTING.md, diagrams in markdown) are often stale, aspirational, or incomplete. Use them only as starting hints. Always verify every module, component, and dependency by reading the actual file tree and import statements. If docs describe a module that doesn't exist in the code, skip it. If docs miss a module that clearly exists in the code, include it.

### Step 1: Understand the project
- Read the top-level directory structure (actual folders, not just what the README says)
- Identify the project type: monorepo, single app, infrastructure-only, or mixed
- Look for key indicators: package.json, go.mod, Cargo.toml, requirements.txt, terraform/, docker-compose.yml, k8s/, Dockerfile, etc.
- Docs can help you understand *intent*, but the file tree tells you what actually exists

### Step 2: Identify modules
- Modules are the major logical pieces of the system (aim for 5-15)
- In a monorepo: each package/app is typically a module
- In a single app: group by responsibility (API, auth, database, workers, etc.)
- Name them functionally — what they DO, not where they live
- "Payment Processing" not "src/pay", "User Authentication" not "auth-utils"
- For each module, set `kind` to one of:
  - `frontend` — UI apps (React, Vue, Remix, Next.js SPAs)
  - `backend` — API services, servers, tRPC routers
  - `worker` — background jobs, async processors, cron tasks
  - `library` — shared libs, utilities, schemas (no runtime)
  - `cli` — command-line tools, scripts
  - `other` — anything else or when unsure

### Step 3: Identify components within each module
- Components are logical sub-groupings within a module (2-6 per module)
- Group by shared responsibility, not by individual files
- Only go deeper (nested components) when a component is genuinely complex
- Small modules (< 5 files) may not need components at all

### Step 4: Identify external dependencies
- External = services this system communicates with OVER THE NETWORK
- Detect from: SDK imports, connection strings, API client code, environment variables
- NOT external: libraries, frameworks, dev tools — these are implementation details
- For each external, set `kind` to one of:
  - `database` — PostgreSQL, MongoDB, MySQL, etc.
  - `cache` — Redis, Memcached, etc.
  - `queue` — RabbitMQ, Kafka, SQS, Inngest, background job services
  - `api` — Third-party APIs like Stripe, Anthropic, Google OAuth, SendGrid
  - `storage` — S3, GCS, Azure Blob, object storage
  - `other` — CDN, DNS, monitoring, anything else or when unsure

### Step 5: Identify deployment topology
- ONLY if infrastructure-as-code exists in the repo (Terraform, Docker Compose, Kubernetes, Pulumi, CloudFormation, etc.)
- If no IaC files found, omit the deployment section entirely
- Map which architecture modules are hosted in which deployment resources using `hosts`

### Step 6: Trace dependencies
- `depends_on` means "this module/component needs the other to function"
- Trace from actual imports, API calls, database connections in the code — **never from what docs claim**
- If a README says Module A depends on Module B but there are no imports between them, do not include that dependency
- External services are dependencies too
- Avoid circular dependencies at the module level

### Step 7: Write the map
- Create `.unkode/` in the project root if it doesn't exist
- Write the map to `.unkode/arch.yaml`
- Set `_meta.last_sync_commit` to current HEAD SHA: run `git rev-parse HEAD`
- Set `_meta.last_sync` to current UTC timestamp
- If this was `--force` over a legacy root `unkode.yaml`, delete the old root file and any root-level `arch_map.md` / `arch_map.html` so there is only one map

### Step 8: Validate
- Run: `python <skill-dir>/validate.py`
- **Errors (exit 2)** mean the map contains things that aren't in the codebase — a path that doesn't exist, a `depends_on` that references nothing, a duplicate name. Fix `.unkode/arch.yaml` and re-run until it exits 0 or 1. Do not hand the user a map with unresolved errors.
- **Warnings (exit 1)** are judgement calls, not defects. Review each one:
  - *claimed by no module* — decide whether that directory deserves a module, or is genuinely not part of the architecture. Coverage does not need to be 100%.
  - *circular dependency* — re-check the imports; if the cycle is real, leave it and mention it to the user.
- Never edit `validate.py` to make a check pass.

### Step 9: Generate diagrams
- Run the **Generate Step** for both formats.

### Step 10: Done
- Tell the user: "Architecture baseline generated in `.unkode/`. Commit the folder." Add: "Open .unkode/arch_map.html in a browser for the interactive view."
- If validation left warnings worth knowing about, mention them in one line.

---

## YAML Format

```yaml
_meta:
  last_sync_commit: <HEAD SHA>
  last_sync: <UTC timestamp>
  version: 1

architecture:
  - name: Module Name
    path: relative/path
    kind: backend  # frontend | backend | worker | library | cli | other
    tech: [language, framework]
    role: One sentence describing what this module does.
    depends_on: [Other Module, External Service]
    components:
      - name: Component Name
        path: relative/path/subdir
        description: One sentence explaining what this component does.

  - name: External Service Name
    type: external
    kind: database  # database | cache | queue | api | storage | other
    role: What this external service provides.

deployment:
  - name: Resource Name
    tech: [provider, service-type]
    role: What this hosts or provides.
    hosts: [Module Name]
    depends_on: [Other Resource]
```

## Rules

1. Names must be functional and understandable by a CTO who doesn't read code.
2. External modules are ONLY network services/APIs — never libraries or frameworks.
3. `depends_on` references exact `name` strings from other entries.
4. `path` is a directory prefix, not individual files.
5. `deployment` section is omitted if no infrastructure-as-code is found.
6. `tech` lists primary language and framework, not every dependency.
7. Every source directory should belong to exactly one module. No overlaps.
8. Keep roles and descriptions to one sentence.
9. Do NOT include test directories, build output, or generated files as modules.
