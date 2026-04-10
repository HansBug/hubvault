"""Small response-shape helpers for the Phase 1-3 server skeleton."""


def build_error_payload(error_type: str, message: str) -> dict:
    """Build the stable JSON error wrapper used by the server layer."""

    return {
        "error": {
            "type": error_type,
            "message": message,
        }
    }
