"""
Request-normalization and small payload helpers for :mod:`hubvault.server`.

The current server phases keep request and response handling explicit instead
of introducing a large schema layer all at once. This module centralizes the
small validation helpers that readonly route modules need.

The module contains:

* :func:`normalize_paths_request` - Normalize path-selection request bodies
* :func:`normalize_snapshot_plan_request` - Normalize snapshot-plan request bodies
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
