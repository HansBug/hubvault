"""
Optional-dependency helpers for :mod:`hubvault`.

This module centralizes delayed imports for optional runtime integrations such
as the embedded HTTP server and remote HTTP client. Callers may import these
helpers in the base installation without triggering immediate import failures;
missing extras are reported only when the optional feature is actually used.

The module contains:

* :class:`MissingOptionalDependencyError` - User-facing import failure wrapper
* :func:`import_optional_dependency` - Delayed import helper with install hints
"""

import importlib
from typing import Iterable, Optional


class MissingOptionalDependencyError(ImportError):
    """
    Raised when an optional extra is required at runtime.

    :param extra: Extra name that satisfies the missing dependency
    :type extra: str
    :param feature: User-facing feature description that needs the extra
    :type feature: str
    :param package: Package name used in the install hint, defaults to
        ``"hubvault"``
    :type package: str
    :param missing_name: Optional missing module name reported by Python import
        machinery
    :type missing_name: Optional[str]

    Example::

        >>> err = MissingOptionalDependencyError(
        ...     extra="api",
        ...     feature="embedded server",
        ...     missing_name="fastapi",
        ... )
        >>> "hubvault[api]" in str(err)
        True
    """

    def __init__(
        self,
        *,
        extra: str,
        feature: str,
        package: str = "hubvault",
        missing_name: Optional[str] = None,
    ) -> None:
        """
        Build one delayed-import failure with an actionable install message.

        :param extra: Extra name that satisfies the missing dependency
        :type extra: str
        :param feature: User-facing feature description that needs the extra
        :type feature: str
        :param package: Package name used in the install hint
        :type package: str
        :param missing_name: Optional missing module name reported by Python
            import machinery
        :type missing_name: Optional[str]
        :return: ``None``.
        :rtype: None
        """

        message = (
            f"{feature} requires optional dependencies from "
            f"'{package}[{extra}]'. Install them with "
            f"'pip install {package}[{extra}]'."
        )
        if missing_name:
            message = f"{message} Missing module: {missing_name!r}."

        super(MissingOptionalDependencyError, self).__init__(message)
        self.extra = extra
        self.feature = feature
        self.package = package
        self.missing_name = missing_name


def import_optional_dependency(
    module_name: str,
    *,
    extra: str,
    feature: str,
    package: str = "hubvault",
    missing_names: Optional[Iterable[str]] = None,
):
    """
    Import one optional dependency with a user-facing install hint.

    :param module_name: Fully qualified module name to import
    :type module_name: str
    :param extra: Extra name that satisfies the missing dependency
    :type extra: str
    :param feature: User-facing feature description that needs the dependency
    :type feature: str
    :param package: Package name used in the install hint, defaults to
        ``"hubvault"``
    :type package: str
    :param missing_names: Additional module names that should map to the same
        install hint
    :type missing_names: Optional[Iterable[str]]
    :return: The imported module object
    :rtype: module
    :raises MissingOptionalDependencyError: Raised when the requested optional
        dependency or one of its accepted transitive imports is missing.
    :raises ModuleNotFoundError: Raised when an unrelated nested import fails.

    Example::

        >>> json_module = import_optional_dependency(
        ...     "json",
        ...     extra="api",
        ...     feature="example loader",
        ... )
        >>> json_module.dumps({"ok": True})
        '{"ok": true}'
    """

    accepted_missing = set(missing_names or ())
    accepted_missing.add(module_name)
    accepted_missing.add(module_name.split(".", 1)[0])

    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as err:
        if err.name in accepted_missing:
            raise MissingOptionalDependencyError(
                extra=extra,
                feature=feature,
                package=package,
                missing_name=err.name,
            )
        raise
