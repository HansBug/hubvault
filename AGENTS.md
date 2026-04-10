CLAUDE.md and AGENTS.md are the same repository guidance file. `CLAUDE.md` is a symbolic link to `AGENTS.md`, so do not
edit both files separately or duplicate changes in both places.

# Repository Guidelines

## Repo Snapshot

`hubvault/` is the main Python package. The current runtime modules are:

- public API:
  - `hubvault/api.py`
  - `hubvault/errors.py`
  - `hubvault/models.py`
  - `hubvault/operations.py`
- repository runtime:
  - `hubvault/repo/backend.py`
  - `hubvault/repo/sqlite.py`
  - `hubvault/repo/constants.py`
- storage substrate:
  - `hubvault/storage/chunk.py`
  - `hubvault/storage/pack.py`
  - `hubvault/storage/index.py`
- CLI:
  - `hubvault/entry/base.py`
  - `hubvault/entry/cli.py`
  - `hubvault/entry/content.py`
  - `hubvault/entry/context.py`
  - `hubvault/entry/dispatch.py`
  - `hubvault/entry/formatters.py`
  - `hubvault/entry/history.py`
  - `hubvault/entry/refs.py`
  - `hubvault/entry/repo.py`
  - `hubvault/entry/style.py`
- package metadata:
  - `hubvault/config/meta.py`

`test/` should mirror the public source tree as closely as practical. Typical mappings:

- `hubvault/api.py` -> `test/test_api.py`
- `hubvault/repo/backend.py` -> `test/repo/test_backend.py`
- `hubvault/repo/sqlite.py` -> prefer indirect coverage through public `hubvault` behavior; if a new public surface is added, add the corresponding test file
- `hubvault/storage/chunk.py` -> `test/storage/test_chunk.py`
- `hubvault/entry/repo.py` -> `test/entry/test_repo.py`

Design notes, execution plans, and phase conclusions live under `plan/`. Benchmark evidence is currently centered under `build/benchmark/phase15/`.

## Current Runtime Truth Model

The repository is already in its Phase 15 completed state. The steady-state runtime rules are:

- repo-root `metadata.sqlite3` is the metadata / object truth-store
- SQLite currently owns:
  - `repo_meta`
  - `refs`
  - `reflog`
  - `txn_log`
  - `chunk_visible`
  - `objects_commits`
  - `objects_trees`
  - `objects_files`
  - `objects_blobs`
- payload bytes remain in the filesystem:
  - `objects/blobs/*.data`
  - `chunks/packs/*.pack`
- `locks/repo.lock` is the outer shared / exclusive serialization boundary
- read APIs must return detached user views rather than writable aliases of repository truth
- old layouts such as `repo.json`, `refs/`, `logs/refs/`, and `chunks/index/*.idx` must not be reintroduced as steady-state dual truth sources

Implementation layering expectations:

- keep SQLite schema, connection policy, and common metadata access logic in `hubvault/repo/sqlite.py`
- keep repository orchestration, transaction ordering, public semantics, and recovery flow in `hubvault/repo/backend.py`
- do not spread large amounts of ad-hoc SQL back into `backend.py`

## Compatibility Envelope

This repository must continue to support:

- Windows, mainstream Linux distributions, and macOS
- older system environments such as Windows 7
- Python `3.7` through `3.14`

That means all implementation and dependency choices must honor these constraints:

- the repo root must remain a self-contained portable artifact
- persisted truth must remain inside the repo root
- no absolute host paths, external sidecar databases, background daemons, or host-local registry state may become correctness-critical
- newer SQLite features must not become correctness prerequisites
- the minimum supported Python version must not be raised casually

The current SQLite baseline is:

- stdlib `sqlite3`
- `journal_mode=DELETE`
- prefer `synchronous=EXTRA`, explicitly fall back to `FULL` when unavailable
- `temp_store=MEMORY`
- WAL is not the default mode
- one short-lived connection per public API call while holding `repo.lock`
- no shared cross-thread connection reuse

Do not make JSON1, `RETURNING`, `UPSERT`, generated columns, external extensions, or similar higher-version SQLite features required for correctness.

## Build, Test, and Common Commands

Install dependencies with:

```bash
pip install -r requirements.txt -r requirements-test.txt
```

Common commands:

- `make help`: show the maintained command list
- `make test`: alias of `make unittest`
- `make unittest`: default full unit-test run with coverage / junit output
- `pytest test -sv -m unittest --cov=hubvault`: direct pytest loop for focused iteration
- `make unittest RANGE_DIR=./entry`: narrowed subtree regression
- `make unittest WORKERS=4 MIN_COVERAGE=80`: parallel test run with coverage floor
- `make benchmark`: run the benchmark suite
- `make benchmark_phase12_standard`: run the maintained standard benchmark summary flow
- `make build`: build the standalone CLI executable with PyInstaller
- `make test_cli`: smoke test the built CLI executable
- `make package`: build sdist and wheel artifacts
- `make docs`, `make docs_en`, `make docs_zh`: build documentation
- `make rst_auto`: regenerate `docs/source/api_doc/*.rst`
- `make clean`: remove build artifacts

Common variables:

- `RANGE_DIR=<dir>`
- `COV_TYPES="xml term-missing"`
- `MIN_COVERAGE=<n>`
- `WORKERS=<n>`
- `BENCHMARK_SCALE=<smoke|standard|nightly|stress|pressure>`

## Coding Rules

### General Python Style

- use 4-space indentation
- use snake_case for modules, functions, and variables
- use PascalCase for classes
- use UPPER_CASE for exported constants
- keep import grouping and local formatting aligned with surrounding code
- keep comments and docstrings concise, and only add them where intent is not obvious

### Repository Design Rules

- treat the repository root as the only portable artifact
- public read APIs must never expose writable aliases of repository truth
- effective mutations must go through explicit public write APIs
- interrupted writes must preserve rollback semantics rather than rolling forward automatically
- do not reintroduce homemade lock protocols such as owner files, heartbeat files, or PID-probe directories
- the file-lock baseline is `portalocker` plus repo-local shared / exclusive `locks/repo.lock`

### SQLite and Storage Rules

- centralize SQLite metadata helper code in `hubvault/repo/sqlite.py`
- keep payload bytes in the filesystem; do not move all `*.data` / `*.pack` payload into SQLite
- do not allow old file-protocol state outside `metadata.sqlite3` to regain steady-state truth responsibilities
- write paths should clearly separate payload publish, SQLite transaction commit, and residue cleanup
- all correctness-critical SQLite writes must run inside explicit transaction boundaries

### Public API and HF Alignment

When `huggingface_hub` already exposes mature public semantics, treat that as the default alignment target unless a concrete local embedded-repository constraint forces a difference.

These constraints must hold:

- downloadable paths preserve the repo-relative suffix
- public file metadata distinguishes internal object identity from HF-style `oid` / `blob_id` / `sha256`
- `CommitInfo` and `GitCommitInfo` stay semantically distinct rather than collapsing into one local hybrid model
- public exceptions should stay aligned with HF-style naming and behavior where applicable

Do not:

- keep compatibility-only parameters with no real behavior
- add no-op switches just to resemble HF signatures
- leak local internal-only fields back into public models

### Error Handling

- do not use bare `except`
- do not use `except Exception` in normal repository logic
- catch the narrowest real exception type that matches the failure mode
- broad catches are only acceptable at explicit process boundaries or best-effort cleanup / diagnostic boundaries, and must document why they exist

## Testing Rules

This repository uses `pytest` with these markers:

- `unittest`
- `benchmark`
- `ignore`

Testing expectations:

- test files use `test_*.py`
- test classes use `Test*`
- test methods use `test_*`
- prefer real filesystem behavior, temporary directories, `CliRunner`, and ordinary in-process execution
- use mocks only for external boundaries or failure modes that cannot be exercised deterministically otherwise

Public-behavior-first rule:

- new or updated unit tests should exercise only public `hubvault/` behavior
- do not import, call, monkeypatch, or assert private internals merely to increase coverage
- do not write unit tests whose primary assertions target `plan/`, `README.md`, `AGENTS.md`, or generated docs

Layout expectations:

- keep `test/` close to one-to-one with the `hubvault/` public module tree
- when a new public module is added, add or update the corresponding `test/**/test_<module>.py`
- package `__init__.py` re-export behavior may be tested through top-level public-surface tests

## Regression Expectations

Run regression commands that match the change surface before declaring work complete:

- Python source changes under `hubvault/`: run `make unittest`
- CLI changes: run `make unittest`; if the standalone CLI path is affected, also run `make build` and `make test_cli`
- packaging / dependency changes: run `make unittest` and `make package`
- public docstring / API-doc structure changes: run `make rst_auto`, plus any relevant regression tests
- benchmark-sensitive changes: rerun the relevant benchmark flow and update evidence files or analysis docs

Do not claim completion without actually running the relevant regression set unless tooling is unavailable, and if tooling is unavailable, record that clearly.

## Docs and Planning Rules

### README and Benchmark Docs

- README is a project-introduction document, not an execution log or an academic analysis report
- performance claims must be grounded in existing evidence files rather than intuition
- benchmark conclusions should cite preserved records under `build/benchmark/` or `plan/`
- when README highlights performance wins, it should also mention the known regression or boundary conditions that still matter

### Planning Documents

Execution-oriented documents under `plan/` must describe the current real repository state rather than an imagined future state.

Requirements:

- organize execution plans by phase
- every executable phase must include both `Todo` and `Checklist`
- use Markdown checkboxes written exactly as `* [ ]`
- call out MVP cuts and deferred items explicitly
- do not turn planning-document structure into a unit-test target

### Python Docstrings

Public API docstrings use reStructuredText.

Minimum expectations:

- a one-line summary at the top
- longer explanation for non-trivial objects
- `:param:` / `:type:` for parameters
- `:return:` / `:rtype:` for return values
- `:raises:` for exceptions
- a short `Example` when helpful
- reST cross-references such as `:class:`, `:func:`, and `:mod:`

`__init__.py` modules should stay thin:

- package docstring
- re-exports
- `__all__`

Do not move real business logic into package `__init__.py` modules.

If you change public APIs, CLI surface, or doc structure, update the relevant docs and generated API rst files as needed.

## Security and Secrets

- never commit `.env`, tokens, or PyPI credentials
- do not commit `dist/`, `build/`, `__pycache__/`, or `*.egg-info`
- GitHub Actions secrets belong in repository secret configuration, not in the tree

## Commit and PR Rules

Use the dominant repository commit style:

- prefer `type(scope): imperative summary`
- common types:
  - `feat`
  - `fix`
  - `docs`
  - `test`
  - `refactor`
  - `chore`
- keep the scope lowercase when present
- keep the summary imperative and without a trailing period

Examples:

```text
feat(repo): complete phase15 sqlite truth-store migration
fix(repo): harden sqlite bootstrap recovery
docs(plan): close phase14 and add phase15 sqlite execution plan
```

For non-trivial changes:

- leave a blank line after the subject
- add a short overview paragraph
- then use `-` bullets for concrete changes, tests, compatibility notes, or documentation updates

PR descriptions should include at least:

- what changed
- what commands were run locally
- the related issue or motivation
- screenshots or output excerpts when CLI or UI output changed
