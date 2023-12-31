#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diff a file with a note in Trilium Notes.

Example:
    $ diffNote.py Trilium Demo/Scripting examples/Task manager/Implementation

Environment variables:
    * TRILIUM_URL should be set to the URL of the Trilium Notes server.
        If not set, the default is http://localhost:8080.
    * TRILIUM_TOKEN should be set to the API token for the Trilium Notes server.
        If not set, the default is None.
"""

import difflib
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

import typer
from trilium_alchemy import Note, Session

if sys.version_info < (3, 10):
    # minimum version for trilium-alchemy
    typer.echo("Python 3.10 or higher is required.", err=True)
    sys.exit(1)

__version__ = "0.0.1"

cli = typer.Typer(
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version(value: bool):
    """Print version and exit."""
    if value:
        typer.echo(f"{sys.argv[0]} v: {__version__}")
        raise typer.Exit()


@dataclass(frozen=True)
class State:
    """Record state for the application.

    :param trilium: instance of Session
    :param verbose: display additional columns or data
    :param dry_run: render table rather than updating Trilium
    """

    trilium: Session
    verbose: bool = False
    dry_run: bool = False


@cli.callback(invoke_without_command=True)
def main(  # pylint: disable=too-many-arguments
    file: Annotated[
        Path,
        typer.Argument(
            exists=True,
            readable=True,
            help="Filename to upload to Trilium Notes",
        ),
    ],
    url: Annotated[str, typer.Option("--trilium-url", envvar="TRILIUM_URL")],
    token: Annotated[str, typer.Option("--trilium-token", envvar="TRILIUM_TOKEN")],
    title: Annotated[
        Optional[str],
        typer.Option(help="title of note containing file contents. Defaults to filename"),
    ] = None,
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            "-V",
            callback=_version,
            is_eager=True,
            help="Show version and exit",
        ),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Render data as table rather than updating Trilium, defaults to False",
        ),
    ] = False,
) -> None:
    """Diff a file with a note in Trilium Notes."""
    _ = version

    if dry_run:
        typer.echo(f"File: {file} (URL: {url}, Token: {token})")
        raise typer.Exit()

    if title is None:
        title = file.name

    with Session(url, token) as trilium:
        notes: list[Note] = trilium.search(f'note.title="{title}"')
        match len(notes):
            case 0:
                typer.echo(f"Note '{title}' not found", err=True)
                raise typer.Abort()
            case 1:
                content = file.read_text().split("\n")
                mtime = datetime.fromtimestamp(file.lstat().st_mtime, timezone.utc)
                timestamp = mtime.astimezone().isoformat()

                results = list(
                    difflib.unified_diff(
                        content,
                        notes[0].content.split("\n"),
                        fromfile=file.name,
                        fromfiledate=timestamp,
                        tofile=title,
                        tofiledate=notes[0].date_modified,
                    )
                )

                if len(results) == 0:
                    return

                for line in results:
                    typer.echo(line.rstrip())
                raise typer.Exit(code=1)

            case _:
                typer.echo(f"More than 1 matching note '{title}' found", err=True)
                raise typer.Abort()


if __name__ == "__main__":
    cli()
