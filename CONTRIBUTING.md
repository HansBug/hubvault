# Contributing to hubvault

This document is for contributors who want to submit code, tests, documentation, or benchmark evidence to `hubvault`.

If you are new to the repository, keep this sentence in mind first:

> `hubvault` is a repo-root portable embedded versioned repository; steady-state metadata truth already lives in `metadata.sqlite3`, while payload bytes intentionally remain in the filesystem.

## Understand the hard constraints first

Before you start coding, accept these project-level rules:

- the repository root must remain a self-contained portable artifact
- persisted truth must not move outside the repo root
- correctness must not depend on absolute host paths, external sidecar databases, or background daemons
- read APIs must not expose writable aliases of repository truth
- interrupted writes must preserve rollback semantics
- homemade lock protocols must not be reintroduced
- changes must stay compatible with Windows, Linux, macOS, and Python `3.7` through `3.14`

If your change needs to violate one of these rules, explain the deviation explicitly in the issue, PR description, or plan document before implementation.

## Current runtime state

The current mainline repository has already completed the Phase 15 SQLite truth-store migration:

- steady-state metadata / object truth lives in repo-root `metadata.sqlite3`
- SQLite currently manages `repo_meta`, `refs`, `reflog`, `txn_log`, `chunk_visible`, `objects_commits`, `objects_trees`, `objects_files`, and `objects_blobs`
- payload bytes remain in the filesystem:
  - `objects/blobs/*.data`
  - `chunks/packs/*.pack`
- repository-wide public concurrency still uses `locks/repo.lock`

As a result:

- generic SQLite helper code belongs in `hubvault/repo/sqlite.py`
- repository orchestration and public semantics belong in `hubvault/repo/backend.py`
- avoid scattering large amounts of SQL directly through `backend.py`
- do not let old file-protocol paths become steady-state truth sources again

## Environment setup

Use a virtual environment and install dependencies:

```bash
python -m venv venv
. venv/bin/activate
pip install -r requirements.txt -r requirements-test.txt
```

If you also need docs or packaging workflows:

```bash
pip install -r requirements-doc.txt
pip install -r requirements-build.txt
```

## Repository layout

Key directories:

- `hubvault/`: main source tree
- `test/`: pytest suite
- `docs/`: Sphinx documentation
- `plan/`: design records, execution plans, and phase notes
- `tools/`: benchmark tools, CLI smoke tests, and helper scripts
- `build/benchmark/`: preserved benchmark outputs and comparisons

Important source areas:

- `hubvault/api.py`: public API entry point
- `hubvault/repo/backend.py`: repository orchestration and core semantics
- `hubvault/repo/sqlite.py`: SQLite truth-store helpers
- `hubvault/storage/`: chunk / pack / index storage substrate
- `hubvault/entry/`: CLI

## Common commands

```bash
make help
make unittest
make unittest RANGE_DIR=./entry
make unittest WORKERS=4 MIN_COVERAGE=80
pytest test -sv -m unittest --cov=hubvault
make benchmark
make benchmark_phase12_standard
make build
make test_cli
make package
make docs
make docs_en
make docs_zh
make rst_auto
```

Useful variables:

- `RANGE_DIR=<dir>`: narrow the test or rst-generation scope
- `WORKERS=<n>`: pytest-xdist worker count
- `MIN_COVERAGE=<n>`: coverage floor
- `BENCHMARK_SCALE=<smoke|standard|nightly|stress|pressure>`: benchmark tier

## Recommended development flow

A good working order is:

1. Read the relevant source module, tests, and matching `plan/` document first.
2. Decide whether the change touches any of these sensitive boundaries:
   - SQLite truth-store
   - detached-view semantics
   - HF-compatible public models
   - rollback-only recovery behavior
   - cross-platform / Python 3.7 compatibility
3. Implement the change under `hubvault/` and update `test/` in the same pass.
4. If public APIs, CLI behavior, or documentation structure changed, update `docs/` and any needed rst files.
5. If the change affects benchmark claims or performance narratives, update the relevant benchmark record or analysis document.

## Code style

- use 4-space indentation
- keep naming, import grouping, and formatting aligned with nearby code
- use snake_case for modules, functions, and variables
- use PascalCase for classes
- use UPPER_CASE for constants
- write comments only when they add real intent, not noise

## Design and implementation requirements

### 1. Portability

- a repository must reopen correctly after moving directories, restoring from archives, or reopening on another machine
- do not persist absolute paths
- do not introduce repo-external sidecars

### 2. Read semantics

- `hf_hub_download()` and `snapshot_download()` must return detached or read-only user views
- deleting or editing those returned paths must not damage committed repository truth
- downloadable paths must preserve the repo-relative suffix

### 3. SQLite semantics

- use stdlib `sqlite3`
- keep `journal_mode=DELETE` as the default baseline
- fall back from `synchronous=EXTRA` to `FULL` when needed
- keep correctness-critical writes inside explicit transaction boundaries
- do not make JSON1, `RETURNING`, `UPSERT`, or similar newer SQLite features required

### 4. Concurrency and recovery

- the repository-wide serialization boundary is `portalocker` on `locks/repo.lock`
- do not reintroduce owner files, heartbeat directories, PID probes, or similar homemade lock schemes
- interrupted writes should recover to the observable state of "nothing happened"
- recovery may roll back and clean up, but it must not finish incomplete writes on behalf of the interrupted caller

### 5. HF alignment principles

- align with `huggingface_hub` public behavior where it makes sense
- do not keep compatibility-only parameters with no real behavior
- keep internal object identity separate from public `oid` / `blob_id` / `sha256`
- keep `CommitInfo` and `GitCommitInfo` distinct

### 6. Error handling

- do not write bare `except`
- do not use `except Exception` in normal repository logic
- catch narrow, real exception types only

## Testing expectations

This repository uses `pytest` with the `unittest`, `benchmark`, and `ignore` markers.

Follow these rules:

- keep tests close to the `hubvault/` module layout
- when a new public module is added, add the corresponding `test/**/test_<module>.py`
- test public behavior only
- do not assert private implementation details just to chase coverage
- prefer real filesystems, temporary directories, `CliRunner`, and ordinary execution
- use mocks only at external boundaries or for failure cases that cannot be exercised reliably

Minimum regression expectations:

- Python source changes: `make unittest`
- CLI changes: `make unittest`, plus `make build` and `make test_cli` when standalone behavior is affected
- packaging changes: `make unittest` and `make package`
- generated-doc API surface changes: `make rst_auto`
- benchmark-sensitive changes: rerun the relevant benchmark flow and update the evidence

## Documentation requirements

### README

- README is a project introduction, not an academic analysis report
- performance highlights are welcome, but they must come from preserved benchmark evidence
- when documenting wins, also mention the important known regressions or limits

### Planning documents

Execution-oriented documents under `plan/` should reflect the current real implementation state.

Requirements:

- organize by phase
- each executable phase includes both `Todo` and `Checklist`
- use `* [ ]` checkboxes
- call out MVP and deferred items explicitly

### Python docstrings

Public API docstrings use reStructuredText:

- `:param:` / `:type:`
- `:return:` / `:rtype:`
- `:raises:`
- add an example when it materially helps

`__init__.py` files should stay thin and mainly handle the package docstring, re-exports, and `__all__`.

## Commits and pull requests

Use the dominant commit format:

```text
type(scope): imperative summary
```

Examples:

```text
feat(repo): complete phase15 sqlite truth-store migration
fix(repo): harden sqlite bootstrap recovery
docs(plan): close phase14 and add phase15 sqlite execution plan
```

Recommendations:

- keep each commit focused
- for non-trivial commits, add a body with a short overview and `-` bullets for concrete changes
- in the PR description, state:
  - what changed
  - why it changed
  - which commands were run
  - whether public APIs, compatibility, or benchmark conclusions changed

## Security and housekeeping

- never commit `.env`, tokens, or PyPI credentials
- do not commit `build/`, `dist/`, `__pycache__/`, or `*.egg-info`
- if you change benchmark-related docs, plan docs, or README performance statements, update the evidence chain in the same change
