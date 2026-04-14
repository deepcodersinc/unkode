---
name: unkode
description: Generate, sync, and diff architecture map (unkode.yaml + arch_map.md) from the codebase
---

# Unkode — Architecture Map

## Configuration

Read `<skill-dir>/config.yaml` at the start. It contains:
- `base_branch` — the branch to compare diffs against
- `exclude_paths` — directories to ignore during analysis (skip these when identifying modules)
- `diagram_direction` — diagram flow (LR or TB)

Apply `exclude_paths` when scanning the codebase in Init and Sync. The converter and diff script read the other settings automatically.

## Pre-check

Run: `python <skill-dir>/preflight.py`

- If output is `INIT` → tell the user: "No baseline architecture found. I'll analyze the codebase and generate the architecture diagram. After this, commit unkode.yaml and arch_map.md to main as your baseline. Continue?" Wait for confirmation. Then follow the **Init** process below. After init, stop — do not run diff (there's no baseline to compare against yet).
- If output is `UP_TO_DATE` → skip sync, go directly to the **Diff** process below.
- If output starts with `SYNC` (e.g. `SYNC 12`) → follow the **Sync** process below, then the **Diff** process.

---

## Init Process

Use this when no `unkode.yaml` exists (first-time setup).

### Step 1: Understand the project
- Read the top-level directory structure
- Identify the project type: monorepo, single app, infrastructure-only, or mixed
- Look for key indicators: package.json, go.mod, Cargo.toml, requirements.txt, terraform/, docker-compose.yml, k8s/, Dockerfile, etc.

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
- Trace from actual imports, API calls, database connections — not guesses
- External services are dependencies too
- Avoid circular dependencies at the module level

### Step 7: Write unkode.yaml
- Output to `unkode.yaml` in the project root
- Set `_meta.last_sync_commit` to current HEAD SHA: run `git rev-parse HEAD`
- Set `_meta.last_sync` to current UTC timestamp

### Step 8: Generate Mermaid diagram
- Run: `python <skill-dir>/yaml_to_mermaid.py unkode.yaml -o arch_map.md`

### Step 9: Done
- Tell the user: "Architecture baseline generated. Commit unkode.yaml and arch_map.md to main."
- Stop here. Do not run diff after init.

---

## Sync Process

Use this when `unkode.yaml` exists but is out of date.

### Step 1: Read the current state
- Read `unkode.yaml` from the project root
- Note the `_meta.last_sync_commit`

### Step 2: Find what changed
- Run: `git diff --name-status <last_sync_commit>..HEAD` for committed changes
- Run: `git diff --name-status HEAD` for uncommitted changes
- Run: `git diff --name-status --cached` for staged changes
- Combine all three lists (deduplicate)
- Exclude `unkode.yaml` and `arch_map.md` from the list
- If `last_sync_commit` is not reachable, fall back to analyzing the full codebase

### Step 3: Determine impact
For each changed file, check:
- Does it belong to an existing module? (match by `path` prefix)
- Does it introduce a new dependency? (check imports)
- Does it belong to a module/component that no longer exists? (deleted files)
- Does it represent a new area of code not covered by any module? (new directories)

### Step 4: Update the YAML
- **New directory/area** → add a new module or component
- **Deleted directory** → remove the module or component
- **New imports to external services** → add external module if not already listed
- **Changed dependencies** → update `depends_on`
- **Renamed/moved code** → update `path` fields
- **No architectural change** (just logic within existing files) → update only `_meta`

### Step 5: Update metadata
- Set `_meta.last_sync_commit` to current HEAD SHA: run `git rev-parse HEAD`
- Set `_meta.last_sync` to current UTC timestamp

### Step 6: Write the updated YAML
- Write to `unkode.yaml`, preserving the same format
- Do NOT reorder modules — keep existing order to minimize diff noise

### Step 7: Regenerate Mermaid diagram
- Run: `python <skill-dir>/yaml_to_mermaid.py unkode.yaml -o arch_map.md`

---

## Diff Process

Run after sync (or directly if UP_TO_DATE). Shows architectural changes vs main.

### Step 1: Run the diff script
- Run: `python <skill-dir>/yaml_diff.py --base-branch main --current unkode.yaml`
- If the script can't find unkode.yaml on main, tell the user "No baseline on main to compare against."

### Step 2: Show the output
- If no changes: "No architectural changes vs main."
- If changes detected: show the text summary to the user.

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
