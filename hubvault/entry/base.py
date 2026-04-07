"""
Click command utilities and exception helpers for the :mod:`hubvault.entry` package.

This module provides standardized exception classes and a command wrapper that
integrates with :mod:`click` to ensure consistent error reporting in CLI
commands. It also includes a utility to print detailed exception information
with tracebacks for unexpected errors.

The main public components are:

* :class:`ClickWarningException` - Warning-style Click exception with yellow output
* :class:`ClickErrorException` - Error-style Click exception with red output
* :class:`KeyboardInterrupted` - Specialized warning for keyboard interrupts
* :func:`print_exception` - Pretty-print exception details with traceback
* :func:`command_wrap` - Decorator to wrap Click commands with standardized handling

Example::

    >>> import click
    >>> from hubvault.entry.base import command_wrap
    >>>
    >>> @click.command()
    ... @command_wrap()
    ... def main():
    ...     raise ValueError("Boom")
    ...
    >>> # Running the command prints a formatted error and exits.

"""

import builtins
import itertools
import os
import sys
import traceback
from functools import wraps, partial
from typing import Optional, IO, Callable, TypeVar

try:
    from typing import ParamSpec
except ImportError:
    from typing_extensions import ParamSpec

import click
from click.exceptions import ClickException

CONTEXT_SETTINGS = dict(
    help_option_names=['-h', '--help']
)

P = ParamSpec("P")
R = TypeVar("R")


class ClickWarningException(ClickException):
    """
    Custom exception class for displaying warnings in yellow color.

    :param message: The error message.
    :type message: str

    Example::

        >>> err = ClickWarningException("warn")
        >>> err.format_message()
        'warn'
    """

    def show(self, file: Optional[IO] = None) -> None:
        """
        Display the warning message in yellow.

        :param file: File to write the output to. This parameter is ignored and
                     output is always written to ``sys.stderr``.
        :type file: Optional[IO]
        :return: ``None``.
        :rtype: None

        Example::

            >>> err = ClickWarningException("warn")
            >>> err.show()  # doctest: +SKIP
        """
        click.secho(self.format_message(), fg='yellow', file=sys.stderr)


class ClickErrorException(ClickException):
    """
    Custom exception class for displaying errors in red color.

    :param message: The error message.
    :type message: str

    Example::

        >>> err = ClickErrorException("error")
        >>> err.format_message()
        'error'
    """

    def show(self, file: Optional[IO] = None) -> None:
        """
        Display the error message in red.

        :param file: File to write the output to. This parameter is ignored and
                     output is always written to ``sys.stderr``.
        :type file: Optional[IO]
        :return: ``None``.
        :rtype: None

        Example::

            >>> err = ClickErrorException("error")
            >>> err.show()  # doctest: +SKIP
        """
        click.secho(self.format_message(), fg='red', file=sys.stderr)


def print_exception(err: BaseException, print_func: Optional[Callable[..., None]] = None) -> None:
    """
    Print exception information, including a formatted traceback.

    The output includes the traceback header and frames (if available), followed
    by the exception class name and message. A custom ``print`` callable can be
    provided to control where output goes (e.g., a Click ``secho`` function).

    :param err: The exception object to display.
    :type err: BaseException
    :param print_func: Custom print function. If not provided, uses built-in ``print``.
    :type print_func: Optional[Callable[..., None]]
    :return: ``None``. The function prints directly to the output stream.
    :rtype: None

    Example::

        >>> try:
        ...     1 / 0
        ... except ZeroDivisionError as exc:
        ...     print_exception(exc)
        Traceback (most recent call last):
        ...
        ZeroDivisionError: division by zero
    """
    print_func = print_func or builtins.print

    lines = list(itertools.chain(*map(
        lambda x: x.splitlines(keepends=False),
        traceback.format_tb(err.__traceback__)
    )))

    if lines:
        print_func('Traceback (most recent call last):')
        print_func(os.linesep.join(lines))

    if len(err.args) == 0:
        print_func(f'{type(err).__name__}')
    elif len(err.args) == 1:
        print_func(f'{type(err).__name__}: {err.args[0]}')
    else:
        print_func(f'{type(err).__name__}: {err.args}')


class KeyboardInterrupted(ClickWarningException):
    """
    Exception class for handling keyboard interruptions.

    This exception is raised when the wrapped Click command receives a
    :class:`KeyboardInterrupt`. It is a warning-level exception with a specific
    exit code.

    :param msg: Custom message to display. Defaults to ``"Interrupted."``.
    :type msg: Optional[str]

    Example::

        >>> err = KeyboardInterrupted()
        >>> err.exit_code
        7
    """
    exit_code = 0x7

    def __init__(self, msg: Optional[str] = None) -> None:
        """
        Initialize the exception.

        :param msg: Custom message to display. Defaults to ``"Interrupted."``.
        :type msg: Optional[str]
        :return: ``None``.
        :rtype: None

        Example::

            >>> err = KeyboardInterrupted()
            >>> err.format_message()
            'Interrupted.'
        """
        ClickWarningException.__init__(self, msg or 'Interrupted.')


def command_wrap() -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator factory for wrapping Click commands with consistent error handling.

    The wrapper provides the following behavior:

    * Re-raises :class:`click.ClickException` without modification.
    * Converts :class:`KeyboardInterrupt` into :class:`KeyboardInterrupted`.
    * For any other exception, prints a red error header, outputs a traceback
      using :func:`print_exception`, and exits the current Click context with
      exit code ``1``.

    :return: A decorator that wraps Click command functions.
    :rtype: Callable[[Callable[..., R]], Callable[..., R]]

    Example::

        >>> import click
        >>> from hubvault.entry.base import command_wrap
        >>>
        >>> @click.command()
        ... @command_wrap()
        ... def main():
        ...     raise RuntimeError("Unexpected")
        ...
        >>> # Running the command emits a formatted error and exits with code 1.
    """

    def _decorator(func: Callable[P, R]) -> Callable[P, R]:
        """
        Wrap a single command callback with standardized error handling.

        :param func: Original command callback
        :type func: Callable[P, R]
        :return: Wrapped callback
        :rtype: Callable[P, R]

        Example::

            >>> import click
            >>> wrapper = command_wrap()
            >>> wrapped = wrapper(click.Command("demo", callback=lambda: None))
            >>> callable(wrapped)
            True
        """

        @wraps(func)
        def _new_func(*args: P.args, **kwargs: P.kwargs) -> R:
            """
            Invoke the wrapped command callback.

            :param args: Positional arguments forwarded to the wrapped callback
            :type args: P.args
            :param kwargs: Keyword arguments forwarded to the wrapped callback
            :type kwargs: P.kwargs
            :return: Callback return value
            :rtype: R
            :raises click.ClickException: Re-raised for expected Click errors.
            :raises KeyboardInterrupted: Raised when a keyboard interrupt is
                converted into the public CLI exception.

            Example::

                >>> import click
                >>> @command_wrap()
                ... def callback():
                ...     return "ok"
                >>> callback()
                'ok'
            """

            try:
                return func(*args, **kwargs)
            except ClickException:
                raise
            except KeyboardInterrupt:
                raise KeyboardInterrupted
            # CLI dispatch is the outermost process boundary. Convert unexpected
            # runtime failures into a visible error instead of leaking a raw traceback.
            except Exception as err:
                click.secho('Unexpected error found when running hubvault!', fg='red', file=sys.stderr)
                print_exception(err, partial(click.secho, fg='red', file=sys.stderr))
                click.get_current_context().exit(1)

        return _new_func

    return _decorator
