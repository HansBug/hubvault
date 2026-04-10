"""
Small response-shape helpers for :mod:`hubvault.server`.

The current server skeleton keeps response assembly lightweight and explicit so
route modules can return stable JSON payloads without introducing a full
Pydantic schema layer yet.
"""


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
