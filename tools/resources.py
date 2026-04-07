"""Collect non-Python package resources for PyInstaller."""

import importlib
import os
import shlex
from pathlib import Path
from typing import Iterable, Iterator, Tuple


PROJECT_PACKAGE = 'hubvault'
EXTRA_PACKAGES: Tuple[str, ...] = ()


def iter_package_files(package: str) -> Iterator[Tuple[str, str]]:
    module = importlib.import_module(package)
    module_file = getattr(module, '__file__', None)
    if not module_file:
        return

    root_dir = Path(module_file).resolve().parent
    parent_dir = root_dir.parent
    for item in root_dir.rglob('*'):
        if not item.is_file():
            continue
        if '__pycache__' in item.parts or item.suffix == '.py':
            continue
        yield str(item), os.path.relpath(str(item.parent), str(parent_dir))


def get_resource_files() -> Iterable[Tuple[str, str]]:
    yield from iter_package_files(PROJECT_PACKAGE)
    for package in EXTRA_PACKAGES:
        yield from iter_package_files(package)


def print_resource_mappings() -> None:
    for src_file, dst_dir in get_resource_files():
        mapping = f'{src_file}{os.pathsep}{dst_dir}'
        print(f'--add-data {shlex.quote(mapping)}')


if __name__ == '__main__':
    print_resource_mappings()
