"""
Serialization helpers for :mod:`hubvault.remote`.

The current remote skeleton does not yet transform payloads deeply, but the
module exists so future HTTP-model conversion logic has a stable home.

The module contains:

* :func:`decode_json_payload` - Normalize one decoded JSON payload
"""


def decode_json_payload(payload):
    """
    Return the decoded JSON payload unchanged for the skeleton stage.

    :param payload: Decoded JSON-compatible payload
    :type payload: object
    :return: The same payload value
    :rtype: object
    """

    return payload
