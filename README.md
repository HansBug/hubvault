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

API-first embedded versioned storage for local ML artifacts.

Current public ID semantics follow Git / Hugging Face where that alignment has
real user value: commit, tree, and blob identifiers are exposed as Git-style
40-hex OIDs, public file `sha256` values stay bare 64-hex digests, and
downloaded file paths preserve the original repo-relative suffix. Internal
storage objects remain self-contained under the repo root and continue to use
HubVault's own `sha256:<hex>` object addressing internally.

This repository is still a work in progress, and the API/CLI surface may change before the first stable release.
