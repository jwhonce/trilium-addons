#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Upload a file to a note in Trilium Notes.

The script is intended to be a method of publishing a file to a Trilium Notes sync server
written in an IDE or editor.The script will use the filename as the title of the note.
If the note does not exist, an error will be returned.

The script will also set #lastUploadedDate of the note's #utcDateModified.

Example:
    $ pushToNote.py ~/Documents/notes/2020-01-01.md

Environment variables:
    * TRILIUM_URL should be set to the URL of the Trilium Notes server.
        If not set, the default is http://localhost:8080.
    * TRILIUM_TOKEN should be set to the API token for the Trilium Notes server.
        If not set, the default is None.
"""
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

import typer
from trilium_alchemy import Session

if sys.version_info < (3, 10):
    # minimum version for trilium-alchemy
    typer.echo("Python 3.10 or higher is required.", err=True)
    sys.exit(1)

__version__ = "0.2.0"

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
    title: Annotated[
        Optional[str],
        typer.Option(help="title of Note to update. Defaults to filename"),
    ],
    url: Annotated[str, typer.Option("--trilium-url", envvar="TRILIUM_URL")],
    token: Annotated[str, typer.Option("--trilium-token", envvar="TRILIUM_TOKEN")],
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
    """Upload named file to Trilium note of same title.

    :param ctx: typer context
    :param url: URL for Trilium service
    :param token: Trilium API token
    :param version: display version and exit
    """
    _ = version

    if dry_run:
        typer.echo(f"File: {file} (URL: {url}, Token: {token})")
        raise typer.Exit()

    if title is None:
        title = file.name

    with Session(url, token) as trilium:
        notes = trilium.search(f'note.title="{title}"')
        match len(notes):
            case 0:
                typer.echo(f"Note '{title}' not found", err=True)
                raise typer.Abort()
            case 1:
                notes[0].content = file.read_text()
                notes[0]["lastUploadedDate"] = datetime.utcnow().isoformat()
            case _:
                typer.echo(f"More than 1 matching note '{title}' found", err=True)
                raise typer.Abort()


if __name__ == "__main__":
    cli()
