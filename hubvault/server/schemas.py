"""
Request-normalization and small payload helpers for :mod:`hubvault.server`.

The current server phases keep request and response handling explicit instead
of introducing a large schema layer all at once. This module centralizes the
small validation helpers that readonly route modules need.

The module contains:

* :func:`normalize_paths_request` - Normalize path-selection request bodies
* :func:`normalize_snapshot_plan_request` - Normalize snapshot-plan request bodies
* :func:`normalize_commit_manifest_request` - Normalize write-commit manifests
* :func:`normalize_gc_request` - Normalize GC request bodies
* :func:`normalize_squash_history_request` - Normalize history-squash request bodies
* :func:`build_error_payload` - Build the stable JSON error wrapper
"""

from typing import Iterable, List, Optional, Sequence

from ..errors import HubVaultValidationError


def _normalize_pattern_list(values, field_name: str) -> List[str]:
    """
    Normalize one optional glob-pattern field.

    :param values: Raw pattern value or values
    :type values: Optional[Union[Sequence[str], str]]
    :param field_name: Request field name used in validation messages
    :type field_name: str
    :return: Normalized pattern list
    :rtype: List[str]
    :raises HubVaultValidationError: Raised when the input is not a string or
        list of strings.
    """

    if values is None:
        return []
    if isinstance(values, str):
        return [values]
    if isinstance(values, Sequence):
        normalized = []
        for item in values:
            if not isinstance(item, str):
                raise HubVaultValidationError("%s items must be strings." % (field_name,))
            normalized.append(item)
        return normalized
    raise HubVaultValidationError("%s must be a string or a list of strings." % (field_name,))


def normalize_paths_request(payload) -> List[str]:
    """
    Normalize a ``paths-info`` request body.

    The body may be either a raw JSON array or an object carrying a ``paths``
    field.

    :param payload: Raw decoded JSON payload
    :type payload: object
    :return: Normalized repo-relative path list
    :rtype: List[str]
    :raises HubVaultValidationError: Raised when the payload shape is invalid.
    """

    values = payload
    if isinstance(payload, dict):
        values = payload.get("paths")

    if isinstance(values, str):
        return [values]
    if isinstance(values, Sequence):
        normalized = []
        for item in values:
            if not isinstance(item, str):
                raise HubVaultValidationError("paths items must be strings.")
            normalized.append(item)
        return normalized
    raise HubVaultValidationError("Request body must be a path string, a path array, or an object with a 'paths' field.")


def normalize_snapshot_plan_request(payload) -> dict:
    """
    Normalize a ``snapshot-plan`` request body.

    :param payload: Raw decoded JSON payload
    :type payload: object
    :return: Normalized snapshot-plan options
    :rtype: dict
    :raises HubVaultValidationError: Raised when the payload shape is invalid.
    """

    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise HubVaultValidationError("Request body must be a JSON object.")

    return {
        "allow_patterns": _normalize_pattern_list(payload.get("allow_patterns"), "allow_patterns"),
        "ignore_patterns": _normalize_pattern_list(payload.get("ignore_patterns"), "ignore_patterns"),
    }


def _normalize_optional_string(value, field_name: str) -> Optional[str]:
    """
    Normalize one optional string field.

    :param value: Raw field value
    :type value: object
    :param field_name: Field name used in validation messages
    :type field_name: str
    :return: Normalized string or ``None``
    :rtype: Optional[str]
    :raises HubVaultValidationError: Raised when the field is not a string.
    """

    if value is None:
        return None
    if not isinstance(value, str):
        raise HubVaultValidationError("%s must be a string." % (field_name,))
    return value


def _normalize_required_string(value, field_name: str) -> str:
    """
    Normalize one required string field.

    :param value: Raw field value
    :type value: object
    :param field_name: Field name used in validation messages
    :type field_name: str
    :return: Normalized string
    :rtype: str
    :raises HubVaultValidationError: Raised when the field is not a string.
    """

    normalized = _normalize_optional_string(value, field_name)
    if normalized is None:
        raise HubVaultValidationError("%s must be a string." % (field_name,))
    return normalized


def _normalize_bool(value, field_name: str, default: Optional[bool] = None) -> bool:
    """
    Normalize one boolean field.

    :param value: Raw field value
    :type value: object
    :param field_name: Field name used in validation messages
    :type field_name: str
    :param default: Optional default value when the field is missing
    :type default: Optional[bool]
    :return: Normalized boolean value
    :rtype: bool
    :raises HubVaultValidationError: Raised when the field is not boolean.
    """

    if value is None:
        if default is None:
            raise HubVaultValidationError("%s must be a boolean." % (field_name,))
        return bool(default)
    if not isinstance(value, bool):
        raise HubVaultValidationError("%s must be a boolean." % (field_name,))
    return value


def _normalize_non_negative_int(value, field_name: str) -> int:
    """
    Normalize one non-negative integer field.

    :param value: Raw field value
    :type value: object
    :param field_name: Field name used in validation messages
    :type field_name: str
    :return: Normalized integer value
    :rtype: int
    :raises HubVaultValidationError: Raised when the field is not a
        non-negative integer.
    """

    if not isinstance(value, int) or isinstance(value, bool):
        raise HubVaultValidationError("%s must be a non-negative integer." % (field_name,))
    if value < 0:
        raise HubVaultValidationError("%s must be a non-negative integer." % (field_name,))
    return int(value)


def _normalize_sha256_hex(value, field_name: str) -> str:
    """
    Normalize one public SHA-256 field.

    :param value: Raw field value
    :type value: object
    :param field_name: Field name used in validation messages
    :type field_name: str
    :return: Bare hexadecimal SHA-256 digest
    :rtype: str
    :raises HubVaultValidationError: Raised when the field is not a string.
    """

    normalized = _normalize_required_string(value, field_name).strip()
    if normalized.startswith("sha256:"):
        normalized = normalized[len("sha256:"):]
    return normalized


def _normalize_chunk_descriptor(payload, index: int) -> dict:
    """
    Normalize one chunk descriptor from a write manifest.

    :param payload: Raw chunk payload
    :type payload: object
    :param index: Chunk index used in validation messages
    :type index: int
    :return: Normalized chunk descriptor
    :rtype: dict
    :raises HubVaultValidationError: Raised when the payload shape is invalid.
    """

    if not isinstance(payload, dict):
        raise HubVaultValidationError("operations[%d].chunks[%d] must be a JSON object." % (index, index))
    return {
        "chunk_id": _normalize_required_string(payload.get("chunk_id"), "chunk_id"),
        "checksum": _normalize_required_string(payload.get("checksum"), "checksum"),
        "logical_offset": _normalize_non_negative_int(payload.get("logical_offset"), "logical_offset"),
        "logical_size": _normalize_non_negative_int(payload.get("logical_size"), "logical_size"),
        "stored_size": _normalize_non_negative_int(payload.get("stored_size"), "stored_size"),
        "compression": _normalize_required_string(payload.get("compression"), "compression"),
    }


def _normalize_manifest_operation(payload, index: int) -> dict:
    """
    Normalize one write-manifest operation.

    :param payload: Raw operation payload
    :type payload: object
    :param index: Operation index used in validation messages
    :type index: int
    :return: Normalized operation payload
    :rtype: dict
    :raises HubVaultValidationError: Raised when the payload shape is invalid.
    """

    if not isinstance(payload, dict):
        raise HubVaultValidationError("operations[%d] must be a JSON object." % (index,))

    operation_type = _normalize_required_string(payload.get("type"), "type")
    if operation_type == "add":
        chunks = payload.get("chunks") or []
        if not isinstance(chunks, list):
            raise HubVaultValidationError("operations[%d].chunks must be a JSON array." % (index,))
        return {
            "type": "add",
            "path_in_repo": _normalize_required_string(payload.get("path_in_repo"), "path_in_repo"),
            "size": _normalize_non_negative_int(payload.get("size"), "size"),
            "sha256": _normalize_sha256_hex(payload.get("sha256"), "sha256"),
            "chunks": [_normalize_chunk_descriptor(item, index) for item in chunks],
        }
    if operation_type == "delete":
        return {
            "type": "delete",
            "path_in_repo": _normalize_required_string(payload.get("path_in_repo"), "path_in_repo"),
            "is_folder": _normalize_bool(payload.get("is_folder"), "is_folder", default=False),
        }
    if operation_type == "copy":
        return {
            "type": "copy",
            "src_path_in_repo": _normalize_required_string(payload.get("src_path_in_repo"), "src_path_in_repo"),
            "path_in_repo": _normalize_required_string(payload.get("path_in_repo"), "path_in_repo"),
            "src_revision": _normalize_optional_string(payload.get("src_revision"), "src_revision"),
        }
    raise HubVaultValidationError("Unsupported write operation type: %s." % (operation_type,))


def _normalize_plan_operation(payload, index: int) -> dict:
    """
    Normalize one planned write operation.

    :param payload: Raw plan operation payload
    :type payload: object
    :param index: Operation index used in validation messages
    :type index: int
    :return: Normalized plan operation payload
    :rtype: dict
    :raises HubVaultValidationError: Raised when the payload shape is invalid.
    """

    if not isinstance(payload, dict):
        raise HubVaultValidationError("upload_plan.operations[%d] must be a JSON object." % (index,))

    missing_chunks = payload.get("missing_chunks") or []
    if not isinstance(missing_chunks, list):
        raise HubVaultValidationError("upload_plan.operations[%d].missing_chunks must be a JSON array." % (index,))

    normalized_missing_chunks = []
    for chunk_index, chunk_payload in enumerate(missing_chunks):
        if not isinstance(chunk_payload, dict):
            raise HubVaultValidationError(
                "upload_plan.operations[%d].missing_chunks[%d] must be a JSON object." % (index, chunk_index)
            )
        normalized_missing_chunks.append(
            {
                "chunk_id": _normalize_required_string(chunk_payload.get("chunk_id"), "chunk_id"),
                "chunk_index": _normalize_non_negative_int(chunk_payload.get("chunk_index"), "chunk_index"),
                "field_name": _normalize_required_string(chunk_payload.get("field_name"), "field_name"),
                "logical_size": _normalize_non_negative_int(chunk_payload.get("logical_size"), "logical_size"),
            }
        )

    return {
        "index": _normalize_non_negative_int(payload.get("index"), "index"),
        "type": _normalize_required_string(payload.get("type"), "type"),
        "path_in_repo": _normalize_optional_string(payload.get("path_in_repo"), "path_in_repo"),
        "strategy": _normalize_required_string(payload.get("strategy"), "strategy"),
        "field_name": _normalize_optional_string(payload.get("field_name"), "field_name"),
        "source_path_in_repo": _normalize_optional_string(payload.get("source_path_in_repo"), "source_path_in_repo"),
        "source_revision": _normalize_optional_string(payload.get("source_revision"), "source_revision"),
        "missing_chunks": normalized_missing_chunks,
        "reused_chunk_count": _normalize_non_negative_int(
            payload.get("reused_chunk_count", 0),
            "reused_chunk_count",
        ),
        "missing_chunk_count": _normalize_non_negative_int(
            payload.get("missing_chunk_count", len(normalized_missing_chunks)),
            "missing_chunk_count",
        ),
    }


def normalize_commit_manifest_request(payload) -> dict:
    """
    Normalize a write-commit manifest or apply payload.

    :param payload: Raw decoded JSON payload
    :type payload: object
    :return: Normalized write manifest payload
    :rtype: dict
    :raises HubVaultValidationError: Raised when the payload shape is invalid.
    """

    if not isinstance(payload, dict):
        raise HubVaultValidationError("Request body must be a JSON object.")

    operations = payload.get("operations")
    if not isinstance(operations, list):
        raise HubVaultValidationError("operations must be a JSON array.")

    upload_plan = payload.get("upload_plan")
    normalized_plan = None
    if upload_plan is not None:
        if not isinstance(upload_plan, dict):
            raise HubVaultValidationError("upload_plan must be a JSON object.")
        plan_operations = upload_plan.get("operations")
        if not isinstance(plan_operations, list):
            raise HubVaultValidationError("upload_plan.operations must be a JSON array.")
        normalized_plan = {
            "revision": _normalize_required_string(upload_plan.get("revision"), "upload_plan.revision"),
            "base_head": _normalize_optional_string(upload_plan.get("base_head"), "upload_plan.base_head"),
            "operations": [
                _normalize_plan_operation(item, index)
                for index, item in enumerate(plan_operations)
            ],
            "statistics": dict(upload_plan.get("statistics") or {}),
        }

    return {
        "revision": _normalize_optional_string(payload.get("revision"), "revision"),
        "parent_commit": _normalize_optional_string(payload.get("parent_commit"), "parent_commit"),
        "commit_message": _normalize_required_string(payload.get("commit_message"), "commit_message"),
        "commit_description": _normalize_optional_string(payload.get("commit_description"), "commit_description"),
        "operations": [_normalize_manifest_operation(item, index) for index, item in enumerate(operations)],
        "upload_plan": normalized_plan,
    }


def normalize_gc_request(payload) -> dict:
    """
    Normalize a GC request body.

    :param payload: Raw decoded JSON payload
    :type payload: object
    :return: Normalized GC options
    :rtype: dict
    :raises HubVaultValidationError: Raised when the payload shape is invalid.
    """

    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise HubVaultValidationError("Request body must be a JSON object.")
    return {
        "dry_run": _normalize_bool(payload.get("dry_run"), "dry_run", default=False),
        "prune_cache": _normalize_bool(payload.get("prune_cache"), "prune_cache", default=True),
    }


def normalize_squash_history_request(payload) -> dict:
    """
    Normalize a history-squash request body.

    :param payload: Raw decoded JSON payload
    :type payload: object
    :return: Normalized squash-history options
    :rtype: dict
    :raises HubVaultValidationError: Raised when the payload shape is invalid.
    """

    if not isinstance(payload, dict):
        raise HubVaultValidationError("Request body must be a JSON object.")
    return {
        "ref_name": _normalize_required_string(payload.get("ref_name"), "ref_name"),
        "root_revision": _normalize_optional_string(payload.get("root_revision"), "root_revision"),
        "commit_message": _normalize_optional_string(payload.get("commit_message"), "commit_message"),
        "commit_description": _normalize_optional_string(payload.get("commit_description"), "commit_description"),
        "run_gc": _normalize_bool(payload.get("run_gc"), "run_gc", default=True),
        "prune_cache": _normalize_bool(payload.get("prune_cache"), "prune_cache", default=False),
    }


def build_error_payload(error_type: str, message: str) -> dict:
    """
    Build the stable JSON error wrapper used by the server layer.

    :param error_type: Stable application error type name
    :type error_type: str
    :param message: Human-readable error message
    :type message: str
    :return: JSON-compatible error payload
    :rtype: dict
    """

    return {
        "error": {
            "type": error_type,
            "message": message,
        }
    }
