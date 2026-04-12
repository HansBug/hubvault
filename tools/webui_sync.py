"""Sync placeholder frontend build artifacts into the Python package tree."""

import argparse
import shutil
from pathlib import Path
from typing import Optional, Sequence


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def sync_webui(dist_dir: Path, target_dir: Path) -> None:
    """Copy one built web UI directory into the packaged static tree."""

    if not dist_dir.is_dir():
        raise FileNotFoundError("Frontend build directory does not exist: %s" % (dist_dir,))

    target_dir.mkdir(parents=True, exist_ok=True)
    for child in target_dir.iterdir():
        if child.name == "__init__.py":
            continue
        if child.is_dir():
            shutil.rmtree(str(child))
        else:
            child.unlink()

    for source in dist_dir.iterdir():
        destination = target_dir / source.name
        if source.is_dir():
            shutil.copytree(str(source), str(destination))
        else:
            shutil.copy2(str(source), str(destination))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync webui/dist into the packaged static directory.")
    parser.add_argument(
        "--dist-dir",
        default=str(_project_root() / "webui" / "dist"),
        help="Path to the built frontend assets.",
    )
    parser.add_argument(
        "--target-dir",
        default=str(_project_root() / "hubvault" / "server" / "static" / "webui"),
        help="Path to the packaged frontend static directory.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    sync_webui(Path(args.dist_dir), Path(args.target_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
