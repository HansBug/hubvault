import pytest

from hubvault.errors import HubVaultValidationError
from hubvault.server.schemas import (
    build_error_payload,
    normalize_paths_request,
    normalize_snapshot_plan_request,
)


@pytest.mark.unittest
class TestServerSchemas:
    def test_normalize_paths_request_accepts_strings_lists_and_objects(self):
        assert normalize_paths_request("demo.txt") == ["demo.txt"]
        assert normalize_paths_request(["a.txt", "b.txt"]) == ["a.txt", "b.txt"]
        assert normalize_paths_request({"paths": "nested/demo.txt"}) == ["nested/demo.txt"]

    def test_normalize_paths_request_rejects_invalid_shapes(self):
        with pytest.raises(HubVaultValidationError, match="paths items must be strings"):
            normalize_paths_request(["ok", 1])

        with pytest.raises(HubVaultValidationError, match="Request body must be a path string"):
            normalize_paths_request(1)

    def test_normalize_snapshot_plan_request_accepts_none_strings_and_lists(self):
        assert normalize_snapshot_plan_request(None) == {
            "allow_patterns": [],
            "ignore_patterns": [],
        }
        assert normalize_snapshot_plan_request(
            {
                "allow_patterns": "artifacts/*",
                "ignore_patterns": ["*.tmp"],
            }
        ) == {
            "allow_patterns": ["artifacts/*"],
            "ignore_patterns": ["*.tmp"],
        }

    def test_normalize_snapshot_plan_request_rejects_invalid_payloads(self):
        with pytest.raises(HubVaultValidationError, match="allow_patterns items must be strings"):
            normalize_snapshot_plan_request({"allow_patterns": ["ok", 2]})

        with pytest.raises(HubVaultValidationError, match="ignore_patterns must be a string or a list of strings"):
            normalize_snapshot_plan_request({"ignore_patterns": 1})

        with pytest.raises(HubVaultValidationError, match="Request body must be a JSON object"):
            normalize_snapshot_plan_request(1)

    def test_build_error_payload_returns_stable_shape(self):
        assert build_error_payload("ConflictError", "boom") == {
            "error": {
                "type": "ConflictError",
                "message": "boom",
            }
        }
