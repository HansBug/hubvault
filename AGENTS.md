CLAUDE.md and AGENTS.md are the same repository guidance file. `CLAUDE.md` is a symbolic link to `AGENTS.md`, so do not
edit both files separately or duplicate changes in both places.

# Repository Guidelines

## Project Structure & Module Organization

`hubvault/` contains the Python package. Current runtime modules include the public API in `hubvault/api.py`,
`hubvault/errors.py`, `hubvault/models.py`, `hubvault/operations.py`, the local repository package in
`hubvault/repo/` (`__init__.py`, `backend.py`, `constants.py`), the Phase 3 storage package in `hubvault/storage/`
(`__init__.py`, `chunk.py`, `pack.py`, `index.py`), package metadata in `hubvault/config/meta.py`, and the CLI surface
in `hubvault/entry/` (`base.py`, `cli.py`, `dispatch.py`, and package re-exports in `__init__.py`). `test/` contains
pytest-based checks and should mirror `hubvault/` as closely as practical, for example `hubvault/api.py` →
`test/test_api.py`, `hubvault/repo/backend.py` → `test/repo/test_backend.py`, `hubvault/repo/constants.py` →
`test/repo/test_constants.py`, `hubvault/storage/chunk.py` → `test/storage/test_chunk.py`,
`hubvault/storage/pack.py` → `test/storage/test_pack.py`, `hubvault/storage/index.py` →
`test/storage/test_index.py`, and `hubvault/entry/dispatch.py` → `test/entry/test_dispatch.py`. Repository automation
lives in `.github/workflows/`. Packaging files are at the root: `setup.py`, `requirements*.txt`, `pytest.ini`, and
`Makefile`. CLI packaging helpers and smoke-test tooling live under `tools/`. Design notes and scope drafts live in
`plan/` and should be treated as reference material, not runtime code.

## Build, Test, and Development Commands

Create a local environment and install dependencies with `pip install -r requirements.txt -r requirements-test.txt`.

Use these commands during development:

- `make help`: print the maintained command list from the Makefile.
- `make test`: alias for `make unittest`.
- `make unittest`: run the default pytest suite with coverage and junit settings from the Makefile.
- `pytest test -sv -m unittest --cov=hubvault`: run tests directly when iterating on a specific change.
- `make unittest RANGE_DIR=./config`: run a narrowed test/source subtree.
- `make unittest WORKERS=4 MIN_COVERAGE=80`: run the suite with xdist workers and a coverage floor.
- `make build`: build the standalone CLI executable with PyInstaller.
- `make test_cli`: smoke-test the built CLI executable in `dist/`.
- `make package`: build source and wheel distributions into `dist/`.
- `make docs`, `make docs_en`, `make docs_zh`: build documentation with the repo's current docs entrypoints.
- `make pdocs`: build production/multi-version docs when the local environment supports it.
- `make rst_auto`: regenerate `docs/source/api_doc/*.rst` from Python source.
- `make clean`: remove build artifacts such as `build/`, `dist/`, and `*.egg-info`.

Common Make variables:

- `RANGE_DIR=<dir>`: narrow `make unittest` or `make rst_auto` to a subtree.
- `COV_TYPES="xml term-missing"`: choose coverage report outputs.
- `MIN_COVERAGE=<n>`: enforce a coverage threshold during `make unittest`.
- `WORKERS=<n>`: run pytest with xdist workers when available.

`make build` is intended for standalone CLI packaging through PyInstaller, but contributors should verify the required
build helpers exist before relying on it. `make test_cli` expects `make build` to have produced `dist/hubvault` or
`dist/hubvault.exe` first.

## Coding Style & Naming Conventions

Use 4-space indentation and follow existing Python style: snake_case for modules, functions, and variables; PascalCase
for test classes; UPPER_CASE for exported constants such as `__VERSION__`. Keep modules small and explicit. Prefer short
docstrings and comments only where intent is not obvious. No formatter configuration is checked in, so match the
surrounding code and keep imports clean and grouped.

## Testing Guidelines

This project uses `pytest` with markers declared in `pytest.ini` (`unittest`, `benchmark`, `ignore`). Name test files
`test_*.py`, classes `Test*`, and methods `test_*`. Place tests under `test/` following the source layout. Coverage is
uploaded in CI; local changes should keep coverage stable or improve it. Add targeted tests for every behavior change,
even when only metadata or packaging code is touched.

New and updated unit tests must exercise public behavior only. Do not import, call, inspect, monkeypatch, or assert
against private/protected modules, fields, classes, functions, or methods just to reach coverage. Unit tests must target
`hubvault/` source behavior only, through public APIs, public CLI commands, and other public symbols from the package.

Keep the test layout close to one-to-one with the source tree. When a new public module is added under `hubvault/`, add
or update the corresponding `test/**/test_<module>.py` file instead of relying on one large catch-all integration test
file. This rule also applies to package modules such as `__init__.py` and `__main__.py` where practical.

Prefer real behavior over mocks whenever the problem can be tested deterministically with the local filesystem,
`CliRunner`, temporary directories, or normal in-process execution. Use mocks only for external boundaries or failure
modes that cannot be exercised reliably in a normal local test.

Do not add unit tests whose primary assertions target `plan/`, `AGENTS.md`, `README.md`, generated docs, or other non-
`hubvault/` files. Documentation and repository guidance should be reviewed directly, while the unit-test suite remains
focused on the package source tree.

## Commit & Pull Request Guidelines

Current history uses short, imperative commit subjects, for example: `Add initial hubvault design docs`. Follow that
pattern. Keep commits focused and avoid bundling packaging, workflow, and feature work together unless tightly related.
PRs should include a clear summary, list of commands run locally, linked issues when applicable, and screenshots only
for UI or badge-output changes.

## Security & Configuration Tips

Never commit `.env`, tokens, or PyPI credentials. GitHub Actions expects repository secrets such as `PYPI_PASSWORD`,
`GIST_SECRET`, `BADGE_GIST_ID`, and `CODECOV_TOKEN`. Do not commit generated artifacts like `__pycache__/`, `build/`, or
`dist/`.

## Additional Repository Rules

This repository must support cross-platform environments (Windows, mainstream Linux distributions, and macOS), older
system platforms (for example Windows 7), older Python versions (for example Python 3.7), and a broad Python version
range (3.7-3.14), so always account for that compatibility envelope when writing code or introducing dependencies.

For the local-path repository design itself, treat the repository root as a self-contained portable artifact. Persisted
repository state must live under the repo root and must not depend on absolute host paths, external sidecar databases,
or metadata stored elsewhere. A closed repo should remain valid after moving the directory, restoring it from an
archive, or unpacking it at another location.

When designing or implementing file-download APIs and file metadata, preserve Hugging Face style public semantics where
the project explicitly claims compatibility. In particular, returned downloadable file paths should preserve the
repo-relative suffix, and public file metadata should distinguish internal storage object identifiers from Hugging Face
compatible file `oid` / `blob_id` and `sha256` values.

Read/download APIs must never expose a writable alias of repository truth. Any path returned by `hf_hub_download`,
`snapshot_download`, or similar read-facing APIs must be a detached or read-only user view whose deletion or
modification cannot corrupt committed repo data. Effective repository mutations must go through explicit public write
APIs such as commit/upload/delete flows.

Repository synchronization must rely on mature third-party file-lock primitives instead of custom heartbeat/owner-file
lock protocols. The current repo-level baseline is a cross-process reader-writer lock built on
`fasteners.InterProcessReaderWriterLock`, chosen because this local repository requires shared reads plus exclusive
writes; do not reintroduce ad-hoc lock directories, PID probes, owner metadata, or any other home-grown lock protocol as
correctness-critical mechanisms.

Interrupted write transactions must be treated as rolled back, not rolled forward. If a write is interrupted before its
durable completion marker is reached, recovery must restore the pre-operation ref state and leave the repo equivalent to
“nothing happened” from the public API point of view. Recovery may clean or roll back, but it must not continue an
incomplete write to completion on behalf of the interrupted caller.

This is a new repository with no compatibility burden for legacy internal lock layouts. Remove obsolete lock schemes
outright instead of keeping fallback behavior. Do not preserve, document, or implement compatibility-only behavior for
hypothetical old `write.lock` / `owner.json` schemes or similar historical artifacts.

Public APIs must not keep compatibility-only placeholder parameters that have no real behavior in this repository. If an
argument such as `repo_id`, `expand`, or a similar field does not affect the local-path design, validation, storage, or
results, remove it instead of carrying dead signature surface.

Do not introduce `except Exception` or bare `except` in repository code. Catch the narrowest real exception types
instead. A broad catch is only acceptable at an explicit process boundary or a best-effort diagnostic/cleanup boundary,
and even there it must document the reason inline and either emit a visible warning or convert the failure into a
domain-specific error instead of silently swallowing it.

For Hugging Face compatibility work, treat the `huggingface_hub` public API and data model as the default target. Unless
a concrete local-repository requirement makes a difference necessary, public names, signatures, parameter semantics,
return-field formats, and user-facing behavior should match HF as closely as possible. Any intentional deviation should
be minimized and documented explicitly in code-facing docs and planning notes.

This also applies to public model boundaries. When `huggingface_hub` already exposes distinct public models for
different use cases, keep the same split instead of collapsing them into a local hybrid model. In particular,
`CommitInfo` should stay aligned with HF commit-creation results, while `GitCommitInfo` should stay aligned with HF
commit-listing results; local-only commit internals must not be pushed back into the public `CommitInfo` shape.

Apply the same rule to public exceptions. Where `huggingface_hub` already exposes meaningful public exception names and
semantics, prefer the aligned `hubvault` counterpart naming and behavior instead of inventing a parallel local exception
family. Do not keep dead exception types that no longer correspond to real behavior.

At the same time, do not keep parameters or flags that exist only for superficial compatibility and have no real
behavior in this repository. If a Hugging Face API detail such as a progress/UI flag, transport-only option, or similar
placeholder would be a no-op in `hubvault`, drop it instead of preserving dead signature surface.

This applies equally to small helper method flags and compatibility sugar. For example, do not add or keep a `with_tqdm`
-style option on a local file helper if the repository does not actually provide distinct progress behavior for it.

## Planning Document Rules

Execution-oriented documents under `plan/` must reflect the current repository state, not an imagined future
implementation state.

- When a planning document is intended to drive implementation work, organize it into explicit phases.
- Each executable phase must include both a `Todo` section and a `Checklist` section.
- Use Markdown checkboxes written exactly as `* [ ]` for `plan/` task lists.
- Call out the MVP cut and deferred items explicitly so contributors know what is intentionally left for later phases.
- Do not turn planning-document structure into unit-test targets; keep these expectations enforced by review and by
  implementing matching source behavior under `hubvault/`.

## Python Docstring Style Guide

Use **reStructuredText (reST)** format exclusively, following PEP 257 and Sphinx standards.

### Core Principles

1. **Format**: reST markup exclusively
2. **Completeness**: Document all public APIs (modules, classes, functions, methods)
3. **Clarity**: Explain "why" and "what", not just "how"
4. **Cross-references**: Use reST roles (`:class:`, `:func:`, `:mod:`)
5. **Examples**: Include practical usage examples for public APIs
6. **Tone**: Professional, clear, technical but accessible

### Docstring Templates

**Module**:

```python
"""
Brief one-line description.

Longer description of purpose, main capabilities, and fit in the larger system.

The module contains:
* :class:`ClassName` - Brief description
* :func:`function_name` - Brief description

.. note::
   Important caveats about usage or requirements.

Example::

    >>> from module import something
    >>> result = something()
    >>> result
    expected_output
"""
```

**Class**:

```python
class ClassName:
    """
    Brief one-line description.

    Longer explanation of purpose, responsibilities, and usage patterns.

    :param param_name: Description of constructor parameter
    :type param_name: ParamType
    :param optional_param: Description, defaults to ``default_value``
    :type optional_param: ParamType, optional

    :ivar instance_var: Description of instance variable
    :vartype instance_var: VarType
    :cvar class_var: Description of class variable
    :type class_var: ClassVarType

    Example::

        >>> obj = ClassName(param_name=value)
        >>> obj.method()
        expected_result
    """
```

**Function/Method**:

```python
def function_name(param1: Type1, param2: Type2 = default) -> ReturnType:
    """
    Brief one-line description.

    Longer explanation of behavior, algorithm, or important details.

    :param param1: Description of the first parameter
    :type param1: Type1
    :param param2: Description, defaults to ``default``
    :type param2: Type2, optional
    :return: Description of what is returned
    :rtype: ReturnType
    :raises ExceptionType: Description of when raised

    Example::

        >>> result = function_name(arg1, arg2)
        >>> result
        expected_output
    """
```

**Dataclass**:

```python
@dataclass
class DataClassName:
    """
    Brief description of what this dataclass represents.

    :param field1: Description of the first field
    :type field1: Type1
    :param field2: Description of the second field
    :type field2: Type2

    Example::

        >>> obj = DataClassName(field1=value1, field2=value2)
        >>> obj.field1
        value1
    """
    field1: Type1
    field2: Type2
```

### `__init__.py` Format

Package-level `__init__.py` files should stay thin. Use them to define the package import surface, re-export stable
public symbols, and document what the package exposes. Avoid placing real business logic in `__init__.py`.

Preferred structure:

1. Module-level reST docstring
2. Explicit re-export imports
3. `__all__` for the intended public surface

Example:

```python
"""
Entry points for the :mod:`hubvault.entry` package.

This package exposes the command-line interface (CLI) entry point for the
``hubvault`` application. The primary public object is the CLI group imported
as :data:`hubvaultcli`, which can be used to invoke CLI commands programmatically
or to register it with external tooling.

The package contains the following main components:

* :data:`hubvaultcli` - CLI group object for the ``hubvault`` command-line tool

Example::

    >>> from hubvault.entry import hubvaultcli
    >>> # The object is typically used by CLI frameworks.
    >>> # Actual invocation is usually handled by the CLI framework itself.

.. note::
   The underlying CLI implementation is defined in :mod:`hubvault.entry.cli`.
   This package module merely re-exports the CLI group for convenience.

"""

from .cli import cli as hubvaultcli

__all__ = ["hubvaultcli"]
```

### Parameter, Return, and Exception Patterns

```python
:param
param_name: Description  # Required parameter
:type param_name: type_annotation
:param
param_name: Description, defaults
to
``value``  # Optional parameter
:type param_name: type_annotation, optional
:return: Description
of
what is returned
:rtype: ReturnType
:return: ``None``.  # For None-returning functions
:rtype: None
:raises
ExceptionType: When
this
exception is raised
```

### Cross-References and Markup

- `:class:`ClassName``, `:func:`function_name``, `:meth:`Class.method_name``
- `:mod:`module.name``, `:exc:`ExceptionType``, `:data:`variable_name``, `:attr:`attribute_name``
- Instance variables: `:ivar:` / `:vartype:`; Class variables: `:cvar:` / `:type:`
- Inline code: double backticks `` ``value`` `` (not single backticks)

### Special Directives

```python
..note::
Important
information or caveats
about
usage.
..warning::
Critical
warnings
about
potential
issues or dangers.
```

### Checklist

- [ ] Brief one-line summary at the top
- [ ] Longer explanation for non-trivial functions/classes
- [ ] All params documented with `:param:` and `:type:`
- [ ] Return value with `:return:` and `:rtype:`
- [ ] All exceptions with `:raises:`
- [ ] Cross-references use reST roles (`:class:`, `:func:`, etc.)
- [ ] Examples for public APIs
- [ ] Inline code uses double backticks
- [ ] Optional params marked with `, optional`; defaults shown in description

### Anti-Patterns

**DON'T**: Google/NumPy style; omit types (always include `:type:` and `:rtype:`); single backticks for inline code;
vague descriptions ("Does something");
bare class/function names without reST roles; volatile implementation details.

**DO**: reST format consistently; explain "why" and "what"; use cross-references; include practical examples;
update docstrings when code changes.

## Testing Strategy

- Tests in `test/`; use `@pytest.mark.unittest`
- Unit tests must not depend on local files ignored by version control (for example, gitignored files).
- Test timeout: 300 seconds (configured in `pytest.ini`)
- When storage/runtime implementation is added, include public-surface regression coverage for repository relocatability
  where relevant, such as moving a repo directory or reopening an archived-and-restored repo without losing correctness.

### Test File Organization

Organize tests so they mirror the source tree wherever practical.

- `hubvault/config/meta.py` → `test/config/test_meta.py`
- `hubvault/entry/__init__.py` → `test/test_entry.py`

For package-level public surfaces, it is acceptable to keep one top-level test file that exercises the exported API
directly.

- `hubvault/entry/__init__.py` re-exports `hubvaultcli`, so `test/test_entry.py` is an acceptable public-surface test
  file.

Naming rules:

- Test files use `test_<module>.py`
- Test classes use `Test<Subject>`
- Test methods use `test_<behavior>`
- Keep package `__init__.py` files under `test/` when the subtree is treated as a Python package

### Test Code Example

```python
import pytest
from click.testing import CliRunner

from hubvault.entry import hubvaultcli


@pytest.mark.unittest
class TestEntryCli:
    def test_version_flag(self):
        runner = CliRunner()
        result = runner.invoke(hubvaultcli, ['-v'])

        assert result.exit_code == 0
        assert 'hubvault' in result.output.lower()

    def test_help_flag(self):
        runner = CliRunner()
        result = runner.invoke(hubvaultcli, ['-h'])

        assert result.exit_code == 0
        assert 'usage' in result.output.lower()
```

### Testing Examples

```bash
make unittest                                        # Run all tests
make unittest RANGE_DIR=./config                     # Specific directory
make unittest COV_TYPES="xml term-missing"           # With coverage types
make unittest MIN_COVERAGE=80                        # With minimum coverage
make unittest WORKERS=4                              # With parallel workers
make build                                           # Build standalone CLI
make test_cli                                        # Smoke-test built CLI executable
make package                                         # Build sdist and wheel
make rst_auto RANGE_DIR=entry                        # Regenerate API rst for a subtree

# Run a single test file or function directly:
pytest test/test_entry.py -v
pytest test/test_entry.py::TestEntryCli::test_help_flag -v
```

## Regression Rules

After writing code, run regression checks before considering the work complete. The minimum expected command depends on
the change surface:

- Python source changes under `hubvault/`: run `make unittest` unless a narrower scope is explicitly justified during
  iteration.
- CLI entry changes under `hubvault/entry/`, `hubvault_cli.py`, or standalone packaging logic: run `make unittest`, and
  if the standalone path is affected, also run `make build` followed by `make test_cli`.
- Packaging or dependency changes (`setup.py`, `requirements*.txt`, workflow packaging logic): run `make unittest` and
  `make package`.
- Docstring/public API surface changes that affect generated API docs: run `make rst_auto` and then run at least the
  relevant regression tests.
- Changes under `plan/` or `AGENTS.md` should not add doc-only unit tests; when they alter expected implementation
  behavior, reflect that through source-facing tests under `test/` that exercise `hubvault/` public behavior and run
  `make unittest`.

During development, rerun a narrowed regression after meaningful edits when feasible so breakage is caught close to
where it was introduced. Before declaring the task complete, run the full required regression set for the touched
surface.

Do not claim a change is finished if the relevant regression command set has not been run, unless the environment is
missing required tooling; in that case, explicitly record what could not be executed and why.

**Commit Message Style**: Follow the dominant repository convention from recent history.

- For normal commits, prefer `type(scope): imperative summary`, such as
  `feat(model): add StateMachine.resolve_state path resolver` or
  `test(utils): strengthen fixed-int tests with live Z3 BitVec alignment`.
- Use short lowercase types such as `feat`, `fix`, `docs`, `test`, `refactor`, `chore`; keep the scope lowercase when
  present
  (`model`, `solver`, `utils`, `makefile`, `verify`, etc.). Omit the scope only when the change genuinely spans the
  whole repository.
- Write the summary as a concise imperative phrase starting with a lowercase verb (`add`, `update`, `improve`, `align`,
  `compress`,
  `clean up`); do not add a trailing period.
- For non-trivial changes, add a blank line and then a body. Match the common repository pattern:
  a short overview sentence or paragraph first, followed by `-` bullet points for concrete changes, tests, compatibility
  notes,
  docs updates, or behavior clarifications.
- When a bullet needs to wrap, continue it on the next line with indentation rather than starting a new bullet.
- Preserve standard trailers when applicable, especially `Co-Authored-By: Name <email>`.
- Merge commits should keep the generated style used in history, such as `Merge branch 'main' into dev/...` or
  `Merge pull request #52 from HansBug/dev/fixed`.

### Commit Message Examples From git log

Example 1:

```text
docs(cli): add visualize command guide and cross-links
Follow up the visualize CLI work from #65 by documenting the new command in the CLI guide and clarifying how it relates to the existing visualization guide.

- add visualize command coverage to the English and Chinese CLI tutorial pages
- explain when to use plantuml versus visualize and document renderer-related options
- point CLI readers to the visualization guide for detailed PlantUML output configuration
- point visualization readers back to the CLI guide for renderer, check, and auto-open behavior
```

Example 2:

```text
feat(entry): add visualize CLI command
Add a PlantUML-backed visualize command that renders FCSTM diagrams through the plantumlcli Python API and optionally opens the generated output with the system default viewer.

- add the new visualize subcommand with auto/local/remote renderer selection and built-in plantumlcli check support
- share PlantUML generation logic between the plantuml and visualize commands
- add runtime dependency and entry-point tests for rendering, headless fallback, and check behavior
- include generated API docs for the new entry module
```
