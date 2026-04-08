# hubvault

[![PyPI](https://img.shields.io/pypi/v/hubvault)](https://pypi.org/project/hubvault/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/hubvault)
![Loc](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/hansbug/c4ea4ea07f389f18c6e9473aca82f1b9/raw/loc.json)
![Comments](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/hansbug/c4ea4ea07f389f18c6e9473aca82f1b9/raw/comments.json)

[![Code Test](https://github.com/hansbug/hubvault/workflows/Code%20Test/badge.svg)](https://github.com/hansbug/hubvault/actions?query=workflow%3A%22Code+Test%22)
[![Package Release](https://github.com/hansbug/hubvault/workflows/Package%20Release/badge.svg)](https://github.com/hansbug/hubvault/actions?query=workflow%3A%22Package+Release%22)
[![codecov](https://codecov.io/gh/hansbug/hubvault/branch/main/graph/badge.svg?token=XJVDP4EFAT)](https://codecov.io/gh/hansbug/hubvault)

![GitHub Org's stars](https://img.shields.io/github/stars/hansbug)
[![GitHub stars](https://img.shields.io/github/stars/hansbug/hubvault)](https://github.com/hansbug/hubvault/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/hansbug/hubvault)](https://github.com/hansbug/hubvault/network)
![GitHub commit activity](https://img.shields.io/github/commit-activity/m/hansbug/hubvault)
[![GitHub issues](https://img.shields.io/github/issues/hansbug/hubvault)](https://github.com/hansbug/hubvault/issues)
[![GitHub pulls](https://img.shields.io/github/issues-pr/hansbug/hubvault)](https://github.com/hansbug/hubvault/pulls)
[![Contributors](https://img.shields.io/github/contributors/hansbug/hubvault)](https://github.com/hansbug/hubvault/graphs/contributors)
[![GitHub license](https://img.shields.io/github/license/hansbug/hubvault)](https://github.com/hansbug/hubvault/blob/master/LICENSE)

`hubvault` is a local, embedded, API-first versioned repository for machine
learning artifacts. It is built for the case where you want Hugging Face style
file APIs and Git-like history semantics, but you want the repository itself to
live entirely inside one portable directory instead of behind a remote service.

The repository root is the whole product. You can move it, zip it, unpack it on
another machine, or reopen it from a different absolute path without any sidecar
database, daemon, or host-specific metadata. Public APIs intentionally stay close
to `huggingface_hub` where that alignment improves usability, while the storage
engine remains local-first, explicit, and crash-safe.

## Why hubvault exists

Many local artifact stores break down in one of two ways:

- they are easy to read but provide no real history, integrity checks, or safe rollback
- they provide version control semantics, but only when backed by Git itself or by a remote service

hubvault is meant to cover the space in between:

- a **self-contained local repository** rather than a remote-first system
- **explicit commits and refs** rather than an ad-hoc file cache
- **HF-style file operations** rather than a raw Git plumbing interface
- **safe detached read views** rather than direct writable aliases of committed truth

If you need a portable local repository for weights, datasets, generated outputs,
evaluation bundles, or similar ML artifacts, that is the intended use case.

## What hubvault is and is not

hubvault is:

- an embedded repository format stored completely under one directory
- a public API centered around `HubVaultApi`
- a local versioned object store with commits, trees, refs, tags, reflogs, merges, and verification
- a git-like CLI exposed as both `hubvault` and `hv`

hubvault is not:

- a hosted Hub service
- a general replacement for Git remotes, pull requests, or CI review flows
- a mutable workspace/index/staging area system
- a writable download cache where editing a returned file path mutates repository truth

That last point is deliberate: read APIs materialize detached user views, while
write APIs remain explicit commit operations.

## Core capabilities

### 1. Portable local repository roots

All durable state lives under the repository root. A valid repo continues to work
after:

- moving the directory to another absolute path
- archiving it and restoring it later
- handing the whole directory to another process or machine

No absolute host paths are persisted as repository truth.

### 2. Git-like history and refs

hubvault exposes:

- commits, trees, and blobs with Git-style 40-hex OIDs
- named branches and tags
- reflogs for public auditability of ref updates
- merge operations with fast-forward, merge-commit, and conflict results

This makes it possible to reason about local artifact evolution with the same
broad mental model people already use for Git history.

### 3. Hugging Face style file APIs

The public API is designed around operations familiar to `huggingface_hub`
users, including:

- `upload_file()` and `upload_folder()`
- `hf_hub_download()` and `snapshot_download()`
- `list_repo_files()`, `list_repo_tree()`, `get_paths_info()`
- `list_repo_commits()`, `list_repo_refs()`, `list_repo_reflog()`

When the user-visible shape is worth aligning, hubvault follows HF closely. When
an HF parameter has no meaning for a local embedded repository, hubvault drops it
instead of carrying dead compatibility surface.

### 4. Detached read views

Returned download paths are safe user views, not writable aliases of committed
storage. In practice that means:

- `hf_hub_download("artifacts/model.safetensors")` returns a file path ending in
  `artifacts/model.safetensors`
- that file path is readable like a normal file path
- deleting or editing the returned file does not damage committed repository data
- the view can be rebuilt from committed history the next time it is requested

This is one of the most important design differences from a naive local cache.

### 5. Large-file storage with public hash metadata

hubvault stores small files directly and switches large files to chunked storage
when they meet the configured `large_file_threshold`. Public callers can still
work with a normal repo-relative path, while metadata remains useful and familiar:

- file `oid` / `blob_id` are Git/HF-style public identifiers
- file `sha256` is a bare 64-hex digest, matching HF expectations
- large files expose LFS-style metadata including `sha256`, `size`, and pointer information

Internal object addressing is separate from public file metadata; the repository
can change its internal storage strategy without making the public model useless.

### 6. Verification and maintenance

Maintenance is not hidden behind private tooling. Public APIs include:

- `quick_verify()` for a low-cost consistency pass
- `full_verify()` for deeper object and storage validation
- `get_storage_overview()` for total usage, reclaimable bytes, and recommendations
- `gc()` for reclaiming unreachable and cache data
- `squash_history()` for rewriting retained history so old bytes become reclaimable

This matters once a repository starts carrying multiple generations of large artifacts.

## Compatibility with Hugging Face and Git

hubvault follows a simple rule: align where the alignment improves user experience,
and keep local semantics where pretending to be something else would be misleading.

### Aligned behavior

- commit, tree, and blob IDs use Git-style 40-hex OIDs
- public file `sha256` values are bare 64-hex digests
- downloadable paths preserve the repo-relative suffix
- `CommitOperationAdd`, `CommitOperationDelete`, and `CommitOperationCopy` follow the HF public style where it matters
- list/read metadata models are designed to feel familiar to HF and Git users

### Deliberate differences

- there is no remote repository, authentication, or network transport layer
- there is no workspace or staging area to mutate before a commit
- mutation only happens through explicit public write APIs or CLI commands
- returned read paths are detached views and must not be treated like repo internals

The goal is close hand-feel, not false equivalence.

## Safety, atomicity, and concurrency

The storage engine is designed around a strict rule: if a write does not finish
and the API does not report success, the observable repository state should be
equivalent to that write never having happened.

The current model is:

- **cross-process reader/writer locking**: multiple readers may coexist; writers block everyone else
- **atomic publish**: object and ref updates are published as a unit
- **rollback-only recovery**: interrupted writes are rolled back instead of being resumed
- **quarantine and maintenance tooling**: damaged or stale temporary state can be verified and cleaned explicitly

This is why hubvault insists on detached read views and explicit write operations.

## Quick start with the Python API

Install from PyPI:

```bash
pip install hubvault
```

Create a repository, write a few commits, then read it back:

```python
from pathlib import Path

from hubvault import CommitOperationAdd, HubVaultApi

repo_dir = Path("demo-repo")
api = HubVaultApi(repo_dir)

info = api.create_repo()
print(info.default_branch)               # main
print(info.head is not None)             # True; the repo already has "Initial commit"

weights_commit = api.upload_file(
    path_or_fileobj=b"weights-v1",
    path_in_repo="artifacts/model.safetensors",
    commit_message="add model weights",
)
print(weights_commit.commit_message)     # add model weights

readme_commit = api.create_commit(
    operations=[CommitOperationAdd("README.md", b"# Demo repo\n")],
    commit_message="add readme",
)
print(readme_commit.oid)                 # 40-hex commit id, value varies per run

print(api.list_repo_files())
# ['README.md', 'artifacts/model.safetensors']

print([item.title for item in api.list_repo_commits(formatted=True)])
# ['add readme', 'add model weights', 'Initial commit']

print(api.read_bytes("README.md").decode("utf-8").strip())
# # Demo repo

download_path = api.hf_hub_download("artifacts/model.safetensors")
print(Path(download_path).as_posix().endswith("artifacts/model.safetensors"))
# True

snapshot_dir = api.snapshot_download()
print(sorted(path.name for path in Path(snapshot_dir).rglob("*") if path.is_file()))
# ['README.md', 'model.safetensors']

print(api.quick_verify().ok)
# True
```

Important observations:

- `create_repo()` creates an empty initial commit immediately
- `upload_file()` and `create_commit()` both return public commit metadata
- `hf_hub_download()` preserves the repo-relative suffix
- `snapshot_download()` gives you a detached tree view, not a writable repo alias

## Quick start with the CLI

The CLI is intentionally git-like, but it stays honest about hubvault's local
embedded model. There is no workspace; each commit operation is explicit.

```bash
hubvault init demo-repo
printf 'weights-v1' > model.bin
printf '# Demo repo\n' > README.md

hubvault -C demo-repo commit -m "add weights" --add artifacts/model.bin=./model.bin
hubvault -C demo-repo branch feature
hubvault -C demo-repo commit -r feature -m "add readme" --add README.md=./README.md
hubvault -C demo-repo merge feature --target main
hubvault -C demo-repo log --oneline
hubvault -C demo-repo verify
```

Typical output shape:

```text
Initialized empty HubVault repository in demo-repo
[main 9f0d2d7] add weights
[feature 46d1c4d] add readme
Updating 9f0d2d7..46d1c4d
Fast-forward
46d1c4d add readme
9f0d2d7 add weights
34d6b75 Initial commit
Quick verification OK
```

Both `hubvault` and `hv` point to the same CLI entry point.

## Repository model in one page

The shortest accurate mental model is:

1. A repository root contains durable object storage, refs, logs, caches, lock files, and transaction state.
2. Public write APIs stage and publish new immutable objects, then update refs atomically.
3. Public read APIs resolve a revision and materialize detached file or snapshot views when a filesystem path is needed.
4. Verification and maintenance APIs inspect or reclaim storage without exposing private internals.

Typical top-level directories include:

- `objects/` for commits, trees, files, and blobs
- `refs/` and `logs/refs/` for named references and reflogs
- `chunks/` for pack/index data used by large files
- `cache/` for detached user views
- `txn/` and `quarantine/` for transactional safety and recovery workflows
- `locks/` for cross-process synchronization

The detailed walkthrough lives in the structure tutorial linked below.

## Documentation map

- English docs: https://hansbug.github.io/hubvault/main/index_en.html
- 中文文档: https://hansbug.github.io/hubvault/main/index_zh.html
- Architecture and execution notes: [plan/init/README.md](plan/init/README.md)

Recommended reading order:

1. Installation
2. Quick start
3. Branch / tag / merge workflow
4. CLI workflow
5. Verification, GC, and history squashing
6. Repository structure and storage format

## Development

Install development dependencies:

```bash
pip install -r requirements.txt -r requirements-test.txt
```

Common commands:

```bash
make unittest
make docs_en
make docs_zh
make package
```

Useful focused commands:

```bash
pytest test -sv -m unittest --cov=hubvault
make unittest RANGE_DIR=./entry
make unittest WORKERS=4 MIN_COVERAGE=80
make test_cli
```

## Status

hubvault is still pre-stable software, but the repository API, CLI, storage
format, maintenance flow, portability guarantees, and safety model described
above are implemented and exercised in CI across Linux, macOS, and Windows.
