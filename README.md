# hubvault

[中文说明](README_zh.md)

[![PyPI](https://img.shields.io/pypi/v/hubvault)](https://pypi.org/project/hubvault/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/hubvault)
[![Code Test](https://github.com/hansbug/hubvault/workflows/Code%20Test/badge.svg)](https://github.com/hansbug/hubvault/actions?query=workflow%3A%22Code+Test%22)
[![Package Release](https://github.com/hansbug/hubvault/workflows/Package%20Release/badge.svg)](https://github.com/hansbug/hubvault/actions?query=workflow%3A%22Package+Release%22)
[![codecov](https://codecov.io/gh/hansbug/hubvault/branch/main/graph/badge.svg?token=XJVDP4EFAT)](https://codecov.io/gh/hansbug/hubvault)
[![GitHub license](https://img.shields.io/github/license/hansbug/hubvault)](https://github.com/hansbug/hubvault/blob/master/LICENSE)

`hubvault` is an API-first, embedded, portable versioned repository for local ML artifacts such as model weights, datasets, evaluation outputs, and experiment bundles.

It gives you Hugging Face style file APIs and Git-like commit / branch / tag / merge semantics, while the repository itself remains a single movable local directory. There is no remote service requirement and no repo-external database to operate.

## Quick Start

Install from PyPI:

```bash
pip install hubvault
```

Create a local repository, commit files, read them back, and materialize detached download views:

```python
from pathlib import Path

from hubvault import CommitOperationAdd, HubVaultApi

repo_dir = Path("demo-repo")
api = HubVaultApi(repo_dir)

info = api.create_repo()
print(info.default_branch)  # main

api.upload_file(
    path_or_fileobj=b"weights-v1",
    path_in_repo="artifacts/model.safetensors",
    commit_message="add model weights",
)

api.create_commit(
    operations=[CommitOperationAdd("README.md", b"# Demo repo\n")],
    commit_message="add readme",
)

print(api.list_repo_files())
print(api.read_bytes("README.md").decode("utf-8").strip())

download_path = api.hf_hub_download("artifacts/model.safetensors")
print(Path(download_path).as_posix().endswith("artifacts/model.safetensors"))

snapshot_dir = api.snapshot_download()
print(snapshot_dir)

print(api.quick_verify().ok)
```

Use the CLI when you want a git-like shell workflow without a Git workspace:

```bash
hubvault init demo-repo
printf 'weights-v1' > model.bin

hubvault -C demo-repo commit -m "add weights" --add artifacts/model.bin=./model.bin
hubvault -C demo-repo ls-tree
hubvault -C demo-repo download artifacts/model.bin
hubvault -C demo-repo verify
```

`hubvault` and `hv` point to the same CLI entry point. Current commands include `init`, `commit`, `branch`, `tag`, `merge`, `log`, `ls-tree`, `download`, `snapshot`, `verify`, `reset`, and `status`.

## Performance Snapshot

The numbers below are current benchmark snapshot values from a Linux `x86_64` machine running CPython `3.10.10`. They are shown as absolute measured throughput, together with the same-run local filesystem sequential read/write baselines.

Treat these as a concrete reference point, not as a universal guarantee. Warm-cache rows can exceed the raw disk-read baseline because they mostly measure detached-view reuse and cache hits rather than physical disk reads.

### Byte-Oriented Workloads

| Workload | Benchmark profile | Measured throughput | Same-run disk baseline | Approx. ratio |
| --- | --- | ---: | ---: | ---: |
| Local filesystem sequential read | standard | `9296.92 MiB/s` | read baseline | `100.00%` |
| Local filesystem sequential write | standard | `360.61 MiB/s` | write baseline | `100.00%` |
| Large file upload | standard | `230.69 MiB/s` | write `360.61 MiB/s` | `63.97%` |
| Large range read | standard | `1113.59 MiB/s` | read `9296.92 MiB/s` | `11.98%` |
| Cold file download | standard | `846.98 MiB/s` | read `9296.92 MiB/s` | `9.11%` |
| Warm file download | standard | `13761.47 MiB/s` | read `9296.92 MiB/s` | `148.02%` |
| Cache-heavy warm download | standard | `19704.43 MiB/s` | read `9296.92 MiB/s` | `211.95%` |
| Large file upload | pressure | `332.13 MiB/s` | write `360.22 MiB/s` | `92.20%` |
| Large range read | pressure | `910.23 MiB/s` | read `9532.68 MiB/s` | `9.55%` |
| Cold file download | pressure | `422.80 MiB/s` | read `9532.68 MiB/s` | `4.44%` |
| Warm file download | pressure | `637608.97 MiB/s` | read `9532.68 MiB/s` | cache/view hit |
| Cache-heavy warm download | pressure | `39457.46 MiB/s` | read `9532.68 MiB/s` | `413.92%` |

### Metadata and Maintenance Workloads

These workloads are not pure byte-stream reads or writes, so comparing them directly to raw disk bandwidth is misleading. They are included because they are the operations that usually make a versioned artifact repository feel fast or slow once history grows.

| Workload | Public API surface | Measured result | Wall time |
| --- | --- | ---: | ---: |
| Deep history listing | `list_repo_commits` / `list_repo_refs` / `list_repo_reflog` | `15221.94 ops/s` | `4.40 s` |
| Recursive nested tree listing | `list_repo_tree(recursive=True)` | `31185.03 ops/s` | `0.88 s` |
| Heavy non-fast-forward merge | `merge` | `126.65 MiB/s` | `0.43 s` |
| Squash history with follow-up cleanup | `squash_history` | `146.83 MiB/s` | `1.48 s` |
| Chunk threshold sweep | `upload_file` + `get_paths_info` | `74.20 MiB/s` | `0.27 s` |
| Small-file read-all path | `read_bytes` | `5.76 MiB/s`, `1473.64 ops/s` | `0.91 s` |

The practical reading is straightforward: large uploads are close to the measured write baseline, range reads and cold downloads are real byte-moving workloads with non-trivial repository overhead, and warm downloads are cache/view-hit paths. The clearest remaining performance work is small-file hot reads and warm-path metadata short-circuiting.

## What hubvault Is For

`hubvault` fits these use cases:

- local artifact repositories that can be moved, archived, restored, and reopened directly
- explicit history, refs, rollback, and verification rather than an ad-hoc cache directory
- Hugging Face style file operations on top of a local embedded repository
- safe detached read paths so downloaded files cannot silently mutate repository truth

`hubvault` is not:

- a hosted Hub service
- a Git remote / PR / review platform
- a Git workspace or staging-area replacement
- a writable cache that returns raw repository-truth file paths

## What You Get Today

- repository metadata, refs, reflog, transaction state, chunk visibility, and object metadata live in repo-root `metadata.sqlite3`
- payload bytes remain as ordinary filesystem data:
  - `objects/blobs/*.data`
  - `chunks/packs/*.pack`
- repository-wide public concurrency is serialized by `locks/repo.lock`
- read APIs return detached user views rather than writable aliases of repository truth
- `quick_verify()`, `full_verify()`, `gc()`, `squash_history()`, and `get_storage_overview()` are available as public maintenance APIs

In practice, you get a repo-local metadata database with filesystem-managed payload storage. You do not need to operate the database directly; the public API stays focused on repository operations.

## Core Strengths

### 1. The repository root is the product

All durable state stays under the repository root. A repo remains valid after:

- moving it to another absolute path
- archiving and restoring it later
- handing the directory to another process or machine

Repository truth does not depend on absolute paths, host-local registries, or external sidecar databases.

### 2. Git-like history semantics without pretending to be Git workspace

`hubvault` exposes:

- Git-style 40-hex commit / tree / blob OIDs
- branches, tags, and reflog
- fast-forward, merge-commit, and conflict merge outcomes
- explicit commit APIs rather than implicit staging-area behavior

The mental model is closer to "a local artifact repository with Git-like history" than "Git transplanted onto large-file storage."

### 3. Hugging Face style file APIs

The public surface is centered on `HubVaultApi`, including:

- `upload_file()` / `upload_folder()`
- `hf_hub_download()` / `snapshot_download()`
- `list_repo_files()` / `list_repo_tree()` / `get_paths_info()`
- `list_repo_commits()` / `list_repo_refs()` / `list_repo_reflog()`

Where alignment with `huggingface_hub` improves usability, `hubvault` follows it closely. Parameters that would be meaningless no-ops for a local embedded repository are intentionally omitted.

### 4. Detached read views are a first-class rule

- `hf_hub_download("artifacts/model.safetensors")` preserves the repo-relative suffix in the returned path
- the returned path is a user-facing readable view
- editing or deleting that path does not corrupt committed repository truth
- the system can materialize the view again when needed

In other words, read APIs expose safe views, not writable aliases of committed truth.

### 5. Small and large files share one versioned model

- small files can be stored as ordinary versioned objects
- large files switch to chunk / pack storage after the configured threshold
- public metadata still exposes HF-style `oid` / `blob_id` / `sha256`
- internal addressing remains decoupled from the public file model

## Runtime Layout

The current layout is best understood like this:

```text
repo/
├── FORMAT
├── metadata.sqlite3
├── locks/
│   └── repo.lock
├── objects/
│   └── blobs/
│       └── ... *.data
├── chunks/
│   └── packs/
│       └── ... *.pack
├── cache/
├── txn/
└── quarantine/
```

You usually do not need to inspect these files directly. The layout is shown to explain why the repository can be copied, archived, and reopened as one directory.

## Good Fits and Non-Goals

Good fits:

- local model repositories
- dataset and evaluation snapshot archives
- training outputs and reproducible experiment bundles
- offline artifact repositories that need branch / merge / verify / GC behavior

Current non-goals:

- remote sync protocols
- multi-tenant server deployment
- a Git workspace or staging compatibility layer
- storing all payload bytes directly inside SQLite

## Docs and Contributor Entry Points

- English docs: https://hansbug.github.io/hubvault/main/index_en.html
- Chinese docs: https://hansbug.github.io/hubvault/main/index_zh.html
- Contribution guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Repository collaboration rules: [AGENTS.md](AGENTS.md)
- Benchmark records: [build/benchmark/](build/benchmark/)

## Project Status

The current published version is still `0.0.1`, and the project remains pre-stable. That said, the following capabilities are already implemented:

- SQLite truth-store
- detached read views
- local history / refs / merge / reflog
- verify / gc / squash / storage overview
- both Python API and CLI entry points

If you need a local, portable, ML-artifact-oriented versioned repository, `hubvault` is already a serious experimental foundation. If you need a mature remote collaboration platform or fully optimized hot-read performance, the project is still converging.
