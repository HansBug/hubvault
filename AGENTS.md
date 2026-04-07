# Repository Guidelines

## Project Structure & Module Organization
`hubvault/` contains the Python package. The only implemented module today is `hubvault/config/meta.py`, which holds package metadata. `test/` mirrors the package layout and currently contains pytest-based checks under `test/config/`. Repository automation lives in `.github/workflows/`. Packaging files are at the root: `setup.py`, `requirements*.txt`, `pytest.ini`, and `Makefile`. Design notes and scope drafts live in `plan/` and should be treated as reference material, not runtime code.

## Build, Test, and Development Commands
Create a local environment and install dependencies with `pip install -r requirements.txt -r requirements-test.txt`.

Use these commands during development:

- `make unittest`: run the default pytest suite with coverage and retry settings from the Makefile.
- `pytest test -sv -m unittest --cov=hubvault`: run tests directly when iterating on a specific change.
- `make package`: build source and wheel distributions into `dist/`.
- `make clean`: remove build artifacts such as `build/`, `dist/`, and `*.egg-info`.

`make build` is intended for standalone CLI packaging through PyInstaller, but contributors should verify the required build helpers exist before relying on it.

## Coding Style & Naming Conventions
Use 4-space indentation and follow existing Python style: snake_case for modules, functions, and variables; PascalCase for test classes; UPPER_CASE for exported constants such as `__VERSION__`. Keep modules small and explicit. Prefer short docstrings and comments only where intent is not obvious. No formatter configuration is checked in, so match the surrounding code and keep imports clean and grouped.

## Testing Guidelines
This project uses `pytest` with markers declared in `pytest.ini` (`unittest`, `benchmark`, `ignore`). Name test files `test_*.py`, classes `Test*`, and methods `test_*`. Place tests under `test/` following the source layout. Coverage is uploaded in CI; local changes should keep coverage stable or improve it. Add targeted tests for every behavior change, even when only metadata or packaging code is touched.

## Commit & Pull Request Guidelines
Current history uses short, imperative commit subjects, for example: `Add initial hubvault design docs`. Follow that pattern. Keep commits focused and avoid bundling packaging, workflow, and feature work together unless tightly related. PRs should include a clear summary, list of commands run locally, linked issues when applicable, and screenshots only for UI or badge-output changes.

## Security & Configuration Tips
Never commit `.env`, tokens, or PyPI credentials. GitHub Actions expects repository secrets such as `PYPI_PASSWORD`, `GIST_SECRET`, `BADGE_GIST_ID`, and `CODECOV_TOKEN`. Do not commit generated artifacts like `__pycache__/`, `build/`, or `dist/`.
