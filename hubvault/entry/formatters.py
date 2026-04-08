"""
Human-readable CLI output helpers for :mod:`hubvault.entry`.

This module keeps git-like textual rendering logic separate from Click command
registration so commands stay focused on argument parsing and public API calls.
The helpers intentionally render familiar git-style summaries without
pretending that ``hubvault`` has a git workspace or index.

The module contains:

* :func:`short_oid` - Render a shortened object identifier
* :func:`format_status_output` - Render ``status`` output
* :func:`format_branch_output` - Render ``branch`` output
* :func:`format_log_output` - Render ``log`` output
* :func:`format_ls_tree_output` - Render ``ls-tree`` output
* :func:`format_merge_output` - Render ``merge`` output
* :func:`format_verify_output` - Render ``verify`` output
"""

from datetime import datetime
from typing import Dict, Optional, Sequence, Union

from ..models import GitCommitInfo, MergeConflict, MergeResult, RepoFile, RepoFolder, VerifyReport


def short_oid(oid: Optional[str], length: int = 7) -> str:
    """
    Return a shortened human-readable object identifier.

    :param oid: Full object identifier, or ``None``
    :type oid: Optional[str]
    :param length: Number of hexadecimal characters to keep, defaults to ``7``
    :type length: int, optional
    :return: Short object identifier or ``"0" * length`` when ``oid`` is ``None``
    :rtype: str

    Example::

        >>> short_oid("sha256:abcdef123456")
        'abcdef1'
    """

    if oid is None:
        return "0" * length
    return oid.split(":", 1)[-1][:length]


def format_status_output(branch: str, head: Optional[str], short: bool = False, show_branch: bool = False) -> str:
    """
    Render repository status output in a git-like style.

    :param branch: Branch name shown as the current CLI branch
    :type branch: str
    :param head: Current head commit ID, if any
    :type head: Optional[str]
    :param short: Whether short-format output is requested
    :type short: bool, optional
    :param show_branch: Whether branch information should be emitted in short mode
    :type show_branch: bool, optional
    :return: Formatted status text
    :rtype: str

    Example::

        >>> format_status_output("main", None, short=True, show_branch=True)
        '## No commits on main'
    """

    if short:
        if not show_branch:
            return ""
        if head is None:
            return "## No commits on {branch}".format(branch=branch)
        return "## {branch}".format(branch=branch)

    lines = ["On branch {branch}".format(branch=branch), ""]
    if head is None:
        lines.extend(["No commits yet", "", "nothing to commit, repository clean"])
    else:
        lines.append("nothing to commit, repository clean")
    return "\n".join(lines)


def format_branch_output(
    branch_names: Sequence[str],
    current_branch: str,
    commit_map: Optional[Dict[str, Optional[GitCommitInfo]]] = None,
    verbose: bool = False,
) -> str:
    """
    Render branch listings in a git-like style.

    :param branch_names: Branch names to render
    :type branch_names: Sequence[str]
    :param current_branch: Branch name marked with ``*``
    :type current_branch: str
    :param commit_map: Optional mapping from branch name to newest commit entry
    :type commit_map: Optional[Dict[str, Optional[GitCommitInfo]]]
    :param verbose: Whether verbose listing is requested
    :type verbose: bool, optional
    :return: Formatted branch listing
    :rtype: str

    Example::

        >>> format_branch_output(["dev", "main"], current_branch="main")
        '  dev\\n* main'
    """

    lines = []
    commit_map = commit_map or {}
    for name in branch_names:
        prefix = "*" if name == current_branch else " "
        if verbose:
            commit = commit_map.get(name)
            if commit is None:
                lines.append("{prefix} {name} (empty)".format(prefix=prefix, name=name))
            else:
                lines.append(
                    "{prefix} {name} {oid} {title}".format(
                        prefix=prefix,
                        name=name,
                        oid=short_oid(commit.commit_id),
                        title=commit.title,
                    )
                )
        else:
            lines.append("{prefix} {name}".format(prefix=prefix, name=name))
    return "\n".join(lines)


def _format_git_date(value: datetime) -> str:
    return value.strftime("%a %b %d %H:%M:%S %Y +0000")


def format_log_output(commits: Sequence[GitCommitInfo], oneline: bool = False) -> str:
    """
    Render commit history in a git-like style.

    :param commits: Commit entries to render
    :type commits: Sequence[GitCommitInfo]
    :param oneline: Whether to use the compact one-line format
    :type oneline: bool, optional
    :return: Formatted history text
    :rtype: str

    Example::

        >>> commit = GitCommitInfo("sha256:abcdef1", [], datetime(2024, 1, 1), "seed", "", None, None)
        >>> format_log_output([commit], oneline=True)
        'abcdef1 seed'
    """

    if oneline:
        return "\n".join(
            "{oid} {title}".format(oid=short_oid(item.commit_id), title=item.title)
            for item in commits
        )

    blocks = []
    for item in commits:
        authors = ", ".join(item.authors) if item.authors else "Unknown"
        block = [
            "commit {commit_id}".format(commit_id=item.commit_id),
            "Author: {authors}".format(authors=authors),
            "Date:   {date}".format(date=_format_git_date(item.created_at)),
            "",
            "    {title}".format(title=item.title),
        ]
        if item.message:
            for line in item.message.splitlines():
                block.append("    {line}".format(line=line))
        blocks.append("\n".join(block))
    return "\n\n".join(blocks)


def format_ls_tree_output(entries: Sequence[Union[RepoFile, RepoFolder]]) -> str:
    """
    Render tree entries in a git-like ``ls-tree`` style.

    :param entries: Tree entries returned by the public API
    :type entries: Sequence[Union[RepoFile, RepoFolder]]
    :return: Formatted tree listing
    :rtype: str

    Example::

        >>> format_ls_tree_output([RepoFolder("demo", "tree123")])
        '040000 tree tree123\\tdemo'
    """

    lines = []
    for item in entries:
        if isinstance(item, RepoFolder):
            lines.append("040000 tree {oid}\t{path}".format(oid=item.tree_id, path=item.path))
        else:
            lines.append("100644 blob {oid}\t{path}".format(oid=item.blob_id, path=item.path))
    return "\n".join(lines)


def _format_conflict(conflict: MergeConflict) -> str:
    path = conflict.path if conflict.related_path is None else "{path} -> {related}".format(
        path=conflict.path,
        related=conflict.related_path,
    )
    return "CONFLICT ({kind}): {path}".format(kind=conflict.conflict_type, path=path)


def format_merge_output(result: MergeResult) -> str:
    """
    Render merge results in a git-like but hubvault-aware style.

    :param result: Structured merge result returned by the public API
    :type result: MergeResult
    :return: Formatted merge text
    :rtype: str

    Example::

        >>> formatter = format_merge_output  # doctest: +SKIP
    """

    if result.status == "already-up-to-date":
        return "Already up to date."
    if result.status == "fast-forward":
        return "Updating {before}..{after}\nFast-forward".format(
            before=short_oid(result.target_head_before),
            after=short_oid(result.head_after),
        )
    if result.status == "merged":
        commit_id = result.commit.oid if result.commit is not None else result.head_after
        return "Merge made by the 'hubvault' strategy.\nCreated commit {oid}.".format(
            oid=short_oid(commit_id),
        )

    lines = [_format_conflict(conflict) for conflict in result.conflicts]
    lines.append("Automatic merge failed; no commit was created.")
    return "\n".join(lines)


def format_verify_output(report: VerifyReport, full: bool = False) -> str:
    """
    Render verification results for the CLI.

    :param report: Verification report returned by the public API
    :type report: VerifyReport
    :param full: Whether the report comes from ``full_verify()``
    :type full: bool, optional
    :return: Formatted verification output
    :rtype: str

    Example::

        >>> format_verify_output(VerifyReport(True), full=False)
        'Quick verification OK'
    """

    title = "Full verification OK" if full else "Quick verification OK"
    if not report.ok:
        title = "Full verification failed" if full else "Quick verification failed"

    lines = [title]
    if report.checked_refs:
        lines.append("Checked refs: {refs}".format(refs=", ".join(report.checked_refs)))
    if report.warnings:
        lines.append("Warnings:")
        lines.extend("- {item}".format(item=item) for item in report.warnings)
    if report.errors:
        lines.append("Errors:")
        lines.extend("- {item}".format(item=item) for item in report.errors)
    return "\n".join(lines)
