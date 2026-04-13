import importlib

import pytest

from hubvault.optional import MissingOptionalDependencyError, import_optional_dependency


@pytest.mark.unittest
class TestOptionalDependencyHelpers:
    def test_import_optional_dependency_wraps_direct_and_transitive_missing_modules(self, monkeypatch):
        def _raise_direct(_module_name):
            raise ModuleNotFoundError("missing optional module", name="fastapi")

        monkeypatch.setattr(importlib, "import_module", _raise_direct)

        with pytest.raises(MissingOptionalDependencyError, match="hubvault\\[api\\]") as exc_info:
            import_optional_dependency(
                "fastapi",
                extra="api",
                feature="embedded server",
                missing_names={"starlette", "pydantic"},
            )

        assert exc_info.value.extra == "api"
        assert exc_info.value.feature == "embedded server"
        assert exc_info.value.missing_name == "fastapi"

        def _raise_transitive(_module_name):
            raise ModuleNotFoundError("missing transitive module", name="starlette")

        monkeypatch.setattr(importlib, "import_module", _raise_transitive)

        with pytest.raises(MissingOptionalDependencyError, match="Missing module: 'starlette'"):
            import_optional_dependency(
                "fastapi",
                extra="api",
                feature="embedded server",
                missing_names={"starlette", "pydantic"},
            )

    def test_import_optional_dependency_preserves_unrelated_module_not_found(self, monkeypatch):
        def _raise_unrelated(_module_name):
            raise ModuleNotFoundError("nested import failed", name="urllib3")

        monkeypatch.setattr(importlib, "import_module", _raise_unrelated)

        with pytest.raises(ModuleNotFoundError, match="nested import failed"):
            import_optional_dependency(
                "httpx",
                extra="remote",
                feature="remote client",
                missing_names={"httpcore"},
            )

    def test_missing_optional_dependency_error_omits_missing_module_suffix_when_name_is_absent(self):
        err = MissingOptionalDependencyError(
            extra="api",
            feature="embedded server",
        )

        assert "hubvault[api]" in str(err)
        assert "Missing module:" not in str(err)
