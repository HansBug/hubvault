"""Generate top-level API documentation index files for Sphinx."""

import argparse
from pathlib import Path


def iter_api_entries(input_dir: Path):
    for item in sorted(input_dir.iterdir(), key=lambda p: p.name):
        if item.is_dir() and (item / '__init__.py').exists():
            yield item.name, True
        elif item.is_file() and item.suffix == '.py' and not item.name.startswith('__'):
            yield item.stem, False


def build_index(title: str, input_dir: Path) -> str:
    lines = [
        title,
        '-' * len(title),
        '',
        '.. toctree::',
        '    :maxdepth: 2',
        f'    :caption: {title}',
        '    :hidden:',
        '',
    ]

    entries = list(iter_api_entries(input_dir))
    for name, is_package in entries:
        target = f'api_doc/{name}/index' if is_package else f'api_doc/{name}'
        lines.append(f'    {target}')

    lines.extend([''])
    for name, is_package in entries:
        target = f'api_doc/{name}/index' if is_package else f'api_doc/{name}'
        lines.append(f'* :doc:`{target}`')

    lines.append('')
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate API index files for Sphinx docs.')
    parser.add_argument('-i', '--input_dir', required=True, help='Input package directory')
    parser.add_argument('-o', '--output_dir', required=True, help='Output docs/source directory')
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / 'api_doc_en.rst').write_text(
        build_index('API Documentation', input_dir),
        encoding='utf-8',
    )
    (output_dir / 'api_doc_zh.rst').write_text(
        build_index('API 文档', input_dir),
        encoding='utf-8',
    )


if __name__ == '__main__':
    main()
