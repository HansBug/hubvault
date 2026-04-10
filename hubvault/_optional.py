"""Private helpers for optional dependency handling."""

import importlib
from typing import Iterable, Optional


class MissingOptionalDependencyError(ImportError):
    """Raised when an optional extra is required at runtime."""

    def __init__(
        self,
        *,
        extra: str,
        feature: str,
        package: str = "hubvault",
        missing_name: Optional[str] = None,
    ) -> None:
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
    """Import one optional dependency with a user-facing install hint."""

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
