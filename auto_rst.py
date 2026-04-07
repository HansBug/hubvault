"""Generate a simple API RST page for a Python module or package."""

import argparse
from pathlib import Path


def module_name_from_path(path: Path) -> str:
    if path.name == '__init__.py':
        path = path.parent
    else:
        path = path.with_suffix('')
    return '.'.join(path.parts)


def title_from_module(module_name: str) -> str:
    tail = module_name.split('.')[-1]
    if tail:
        return tail
    return module_name


def generate_rst(module_name: str) -> str:
    title = title_from_module(module_name)
    underline = '=' * len(title)
    return f"""{title}
{underline}

.. automodule:: {module_name}
   :members:
   :undoc-members:
   :show-inheritance:
"""


def main() -> None:
    parser = argparse.ArgumentParser(description='Generate RST documentation for one Python module.')
    parser.add_argument('-i', '--input', required=True, help='Input Python file path')
    parser.add_argument('-o', '--output', required=True, help='Output RST file path')
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    project_root = Path.cwd().resolve()
    module_name = module_name_from_path(input_path.relative_to(project_root))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(generate_rst(module_name), encoding='utf-8')


if __name__ == '__main__':
    main()
