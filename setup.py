from pathlib import Path
import re

from setuptools import find_packages, setup

_MODULE_NAME = "hubvault"
_PACKAGE_NAME = 'hubvault'

here = Path(__file__).resolve().parent
meta = {}
with (here / _MODULE_NAME / 'config' / 'meta.py').open('r', encoding='utf-8') as f:
    exec(f.read(), meta)


def _load_req(file: str):
    with (here / file).open('r', encoding='utf-8') as f:
        return [line.strip() for line in f.readlines() if line.strip()]


requirements = _load_req('requirements.txt')

_REQ_PATTERN = re.compile(r'^requirements-(\w+)\.txt$')
_REQ_BLACKLIST = {'zoo'}
group_requirements = {
    item.group(1): _load_req(item.group(0))
    for item in [_REQ_PATTERN.fullmatch(reqpath.name) for reqpath in here.iterdir()] if item
    if item.group(1) not in _REQ_BLACKLIST
}

with (here / 'README.md').open('r', encoding='utf-8') as f:
    readme = f.read()

setup(
    # information
    name=_PACKAGE_NAME,
    version=meta['__VERSION__'],
    packages=find_packages(include=(_MODULE_NAME, "%s.*" % _MODULE_NAME)),
    description=meta['__DESCRIPTION__'],
    long_description=readme,
    long_description_content_type='text/markdown',
    author=meta['__AUTHOR__'],
    author_email=meta['__AUTHOR_EMAIL__'],
    license='GPL-3.0-only',
    keywords='artifact storage, versioned storage, local repository, ml artifacts, huggingface hub, object store',
    url='https://github.com/hansbug/hubvault',

    # environment
    python_requires=">=3.7",
    install_requires=requirements,
    extras_require=group_requirements,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',

        # Intended Audience
        'Intended Audience :: End Users/Desktop',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'Intended Audience :: Information Technology',
        'Intended Audience :: System Administrators',

        # Programming Language
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Programming Language :: Python :: 3.14',
        'Programming Language :: Python :: Implementation :: CPython',

        # Operating System
        'Operating System :: OS Independent',
        'Operating System :: POSIX',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: MacOS',

        # Technical Topics
        'Topic :: Database',
        'Topic :: System :: Archiving',
        'Topic :: Software Development :: Libraries',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Software Development :: Version Control',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
        'Topic :: Utilities',

        'Natural Language :: Chinese (Simplified)',
        'Natural Language :: English',
    ],
    entry_points={
        'console_scripts': [
            'hubvault=hubvault.entry:hubvaultcli',
            'hv=hubvault.entry:hubvaultcli',
        ]
    },
    project_urls={
        'Bug Reports': 'https://github.com/hansbug/hubvault/issues',
        'Documentation': 'https://hubvault.readthedocs.io/en/latest/',
        'Documentation (ZH)': 'https://hubvault.readthedocs.io/zh/latest/',
        'Read the Docs': 'https://hubvault.readthedocs.io/',
        'Source': 'https://github.com/hansbug/hubvault',
    },
)
