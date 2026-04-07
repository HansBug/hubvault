"""CLI entrypoint for hubvault."""

import click

from hubvault.config.meta import __DESCRIPTION__, __TITLE__, __VERSION__


def _print_version(ctx: click.Context, param: click.Option, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    click.echo(f'{__TITLE__} {__VERSION__}')
    ctx.exit()


@click.group(context_settings={'help_option_names': ['-h', '--help']})
@click.option(
    '-v',
    '--version',
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=_print_version,
    help='Show version information and exit.',
)
def hubvaultcli() -> None:
    """Useful utilities for huggingface."""


@hubvaultcli.command('version')
def version_command() -> None:
    """Print the current hubvault version."""
    click.echo(f'{__TITLE__} {__VERSION__}')


@hubvaultcli.command('about')
def about_command() -> None:
    """Print a short project description."""
    click.echo(__DESCRIPTION__)
