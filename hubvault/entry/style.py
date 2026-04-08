"""
ANSI-aware CLI styling helpers for :mod:`hubvault.entry`.

This module centralizes optional terminal styling so command implementations do
not need to repeat environment checks or ad hoc color branching. Styling stays
strictly optional and can be disabled completely through standard or
repository-specific environment variables.

The module contains:

* :func:`colors_enabled` - Decide whether ANSI styling should be emitted
* :func:`style_text` - Style one text fragment when colors are enabled
* :func:`echo` - Click-backed output helper with centralized color handling

Example::

    >>> style_text("hello", tone="success")  # doctest: +ELLIPSIS
    '\\x1b...hello\\x1b[0m'
    >>> style_text("hello", tone="success", env={"NO_COLOR": "1"})
    'hello'

.. note::
   Styling is disabled whenever ``NO_COLOR`` or ``HUBVAULT_NO_COLOR`` is
   present in the environment.
"""

import os
from typing import IO, Mapping, Optional

import click

_TONE_STYLES = {
    "success": {"fg": "green", "bold": True},
    "warning": {"fg": "yellow", "bold": True},
    "error": {"fg": "red", "bold": True},
    "accent": {"fg": "cyan", "bold": True},
}


def colors_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """
    Return whether CLI ANSI styling is enabled.

    :param env: Environment mapping to inspect. Defaults to :data:`os.environ`
    :type env: Optional[Mapping[str, str]], optional
    :return: ``True`` when styling may be emitted
    :rtype: bool

    Example::

        >>> colors_enabled(env={})
        True
        >>> colors_enabled(env={"HUBVAULT_NO_COLOR": "1"})
        False
    """

    env = os.environ if env is None else env
    return "NO_COLOR" not in env and "HUBVAULT_NO_COLOR" not in env


def style_text(
    text: object,
    tone: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    **style_kwargs: object
) -> str:
    """
    Style one text fragment when ANSI output is enabled.

    :param text: Source text fragment
    :type text: object
    :param tone: Named style tone such as ``"success"`` or ``"error"``
    :type tone: Optional[str], optional
    :param env: Environment mapping used for color-disable detection
    :type env: Optional[Mapping[str, str]], optional
    :param style_kwargs: Extra :func:`click.style` keyword arguments
    :type style_kwargs: object
    :return: Styled or plain text
    :rtype: str

    Example::

        >>> style_text("warning", tone="warning", env={"NO_COLOR": "1"})
        'warning'
    """

    text = str(text)
    if not colors_enabled(env=env):
        return text

    merged_kwargs = dict(_TONE_STYLES.get(str(tone), {}))
    merged_kwargs.update(style_kwargs)
    if not merged_kwargs:
        return text
    return click.style(text, **merged_kwargs)


def echo(
    message: Optional[object] = None,
    tone: Optional[str] = None,
    file: Optional[IO] = None,
    err: bool = False,
    nl: bool = True,
    color: Optional[bool] = None,
    env: Optional[Mapping[str, str]] = None,
    **style_kwargs: object
) -> None:
    """
    Emit CLI output with centralized optional ANSI styling.

    :param message: Text to print
    :type message: Optional[object]
    :param tone: Named style tone such as ``"success"`` or ``"error"``
    :type tone: Optional[str], optional
    :param file: Optional output stream
    :type file: Optional[IO], optional
    :param err: Whether to write to stderr, defaults to ``False``
    :type err: bool, optional
    :param nl: Whether to append a trailing newline, defaults to ``True``
    :type nl: bool, optional
    :param color: Explicit Click color mode. When omitted, color is disabled
        automatically if the environment requests plain output.
    :type color: Optional[bool], optional
    :param env: Environment mapping used for color-disable detection
    :type env: Optional[Mapping[str, str]], optional
    :param style_kwargs: Extra :func:`click.style` keyword arguments
    :type style_kwargs: object
    :return: ``None``.
    :rtype: None

    Example::

        >>> echo("plain output", env={"NO_COLOR": "1"})  # doctest: +SKIP
    """

    environment = os.environ if env is None else env
    if message is not None:
        message = style_text(message, tone=tone, env=environment, **style_kwargs)
    if color is None:
        if not colors_enabled(env=environment):
            color = False
        else:
            context = click.get_current_context(silent=True)
            if context is not None:
                color = context.color
    click.echo(message=message, file=file, err=err, nl=nl, color=color)
