# Voltaris

Voltaris is an AI-assisted workflow platform for PCB schematic and circuit
design. It turns a natural-language hardware requirement into a staged design
process with reviewable Markdown artifacts, component-selection support, a
machine-readable CircuitIR YAML netlist, and a final engineering report.

The project is currently an early development prototype. It is useful for
exploring AI-assisted schematic workflows, agent orchestration, and structured
hardware design outputs, but generated designs still require review by qualified
engineers before fabrication or purchasing.

## Features

- Natural-language project input through a browser-based project workspace.
- A phased PCB design workflow covering requirements, architecture, component
  selection, circuit design, netlist generation, CircuitIR compilation, review,
  and final reporting.
- AI execution through provider adapters for Claude Code and Codex CLI.
- Provider-specific prompt synchronization into each project workdir before
  every run, so existing projects pick up prompt updates without migration.
- Local project workdirs with git history for each design run.
- Real-time WebSocket updates for agent messages, tool events, run completion,
  and Markdown file changes.
- Markdown previews for phase outputs, including tables and math rendering in
  the frontend.
- LCSC/JLCPCB component lookup helper backed by a local `jlcparts`
  `cache.sqlite3` database.
- Strict CircuitIR v1.0 validation for the generated
  `05_circuit.thinir.yaml` output.

## Architecture

```text
Voltaris/
├── backend/                 FastAPI API, run orchestration, providers, prompts
│   ├── main.py              HTTP routes and WebSocket mounting
│   ├── runner.py            AI CLI subprocess lifecycle and event fanout
│   ├── projects.py          Project CRUD, prompt sync, workdir git setup
│   ├── providers/           Claude Code and Codex CLI runtime adapters
│   ├── prompts/             Orchestrator, subagent prompts, CircuitIR refs
│   ├── tools/               CircuitIR validator and LCSC lookup helper
│   └── tests/               Backend provider and runner tests
├── frontend/                React, TypeScript, and Vite single-page app
└── data/                    Runtime SQLite metadata database, created locally
```

The backend stores metadata in SQLite and stores design artifacts in per-project
workdirs under `projects/<project-id>/`. Each project workdir is initialized as a
git repository, and each completed run is committed locally. Runtime data,
project workdirs, frontend builds, virtual environments, and large component
databases are ignored by git.

## Workflow

Voltaris uses a seven-stage design flow coordinated by the orchestrator prompt:

1. Requirements analysis -> `01_requirements.md`
2. Architecture design -> `02_architecture.md`
3. Component selection -> `03_components.md`
4. Circuit design -> `04_circuit_design.md`
5. Netlist generation -> `05_netlist.md`
6. CircuitIR compilation -> `05_circuit.thinir.yaml`
7. Design review and final report -> `06_review.md`, `final_report.md`

The `00_project_brief.md` file is the workflow state source. It tracks the
current phase, completed phases, whether the system is waiting for user
confirmation, and which files changed in the latest run. When a user asks for a
change after a paused phase, the change analyzer can roll the project back to
the phase that needs to be regenerated.

CircuitIR is the deterministic machine-readable output format. The validator in
`backend/tools/validate.py` rejects uncertain or unsupported fields and checks
that parts, nets, modules, and buses are internally consistent.

## Technology Stack

- Backend: Python 3.11+, FastAPI, Pydantic, aiosqlite, watchfiles, uvicorn.
- Frontend: React 18, TypeScript, Vite, TanStack Query, react-markdown, KaTeX,
  js-yaml.
- Runtime storage: SQLite metadata plus per-project git workdirs.
- AI runtimes: Claude Code by default; Codex CLI is available through
  `VOLTARIS_AGENT_PROVIDER=codex`.
- Component data: optional local `jlcparts` SQLite cache for LCSC/JLCPCB part
  lookup.

## Getting Started

Clone the repository, then install backend and frontend dependencies from the
repository root.

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..

# Frontend
cd frontend
npm install
cd ..
```

Start the backend from the repository root:

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

In another terminal, start the frontend:

```bash
cd frontend
npm run dev
```

Open the Vite URL shown in the terminal, normally `http://localhost:5173`. The
frontend proxies `/api/*` and `/ws/*` requests to the backend at
`http://localhost:8000`.

You can verify the backend with:

```bash
curl http://localhost:8000/health
```

The response includes the active agent provider:

```json
{"status":"ok","agent_provider":"claude"}
```

## Configuration

Voltaris runs AI work through a provider selected by environment variable.

| Variable | Default | Description |
|---|---|---|
| `VOLTARIS_AGENT_PROVIDER` | `claude` | Runtime provider: `claude` or `codex`. |
| `CLAUDE_BIN` | `claude` | Claude Code CLI executable path. |
| `CLAUDE_SKIP_PERMISSIONS` | `true` | Adds Claude Code's permission-skip flag. Use an outer sandbox in deployment. |
| `CODEX_BIN` | `codex` | Codex CLI executable path. |
| `CODEX_MODEL` | unset | Optional model passed to `codex exec --model`. |
| `CODEX_PROFILE` | unset | Optional profile passed to `codex exec --profile`. |
| `CODEX_SANDBOX` | `workspace-write` | Codex sandbox mode. |
| `CODEX_APPROVAL_POLICY` | `never` | Codex approval policy. |
| `CODEX_EPHEMERAL` | `true` | Runs Codex without keeping local Codex session files. |
| `CODEX_BYPASS_SANDBOX` | `false` | Only when explicitly true, enables Codex sandbox bypass. |
| `JLCPARTS_DB` | `backend/data/cache.sqlite3` | Optional path to the local jlcparts database. |

The default provider is Claude Code. To use Codex CLI:

```bash
export VOLTARIS_AGENT_PROVIDER=codex
python -m uvicorn backend.main:app --reload --port 8000
```

Claude Code supports the subagent protocol directly. The Codex provider keeps
the same output files and phase state machine by generating `AGENTS.md` plus
`.codex/agents/`, `.codex/refs/`, and `.codex/tools/` inside each project
workdir and instructing Codex to run the relevant subagent instructions inline.

## Component Database

The component lookup helper can query a local
`backend/data/cache.sqlite3` database from the community `jlcparts` dataset.
This database is large, roughly 27 GB after extraction, and is not committed to
the repository. See [backend/data/README.md](backend/data/README.md) for
download and indexing commands.

Without this database, the application can still run, but component lookup via
`backend/tools/lcsc_lookup.py` will fail until `cache.sqlite3` is available or
`JLCPARTS_DB` points to a valid copy.

## Development

Useful local commands:

```bash
# Backend tests
pip install -r backend/requirements.txt pytest pytest-asyncio
python -m pytest backend/tests

# Frontend typecheck and production build
cd frontend
npm run lint
npm run build
```

The backend also exposes these development docs:

- [Backend runtime notes](backend/README.md)
- [Frontend runtime notes](frontend/README.md)
- [Component database setup](backend/data/README.md)
- [CircuitIR specification](backend/prompts/refs/CircuitIR.md)

## Roadmap and Status

Implemented today:

- Project CRUD, per-project workdirs, and local git commits.
- Claude Code and Codex CLI provider adapters.
- Normalized run events persisted in SQLite and streamed over WebSockets.
- Prompt-driven phased workflow with design artifacts written as Markdown.
- CircuitIR reference format, example, and validator.
- Basic backend tests for providers and runner behavior.

Areas still in progress or intentionally limited:

- AI-generated electrical designs require human engineering review.
- CircuitIR-to-EDA export is described by the format direction but is not yet a
  complete generator in this repository.
- The large jlcparts database must be downloaded and indexed manually.
- Deployment hardening is still needed around AI CLI sandboxing, CORS, and
  multi-worker event sequencing.

## License

No license file has been committed yet. Add a license before distributing,
publishing packages, or accepting external contributions.
