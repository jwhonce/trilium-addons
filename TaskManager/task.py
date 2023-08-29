#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Curate tasks for Task Manager in trilium notes.

Note(s):
    * This is a work in progress and an exercise in learning typer
      and TriliumAlchemy
    * The labels, relations, widgets and JavaScript of TaskManager are
      leveraged to manage tasks
"""
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from typing import Annotated, Any, Generator, List, Optional
import click

import typer
from rich.console import Console
from rich.table import Table
from trilium_alchemy import Label, Note, Session

__version__ = "0.1.3"

if sys.version_info < (3, 10):
    # minimum version for trilium-alchemy
    typer.echo("Python 3.10 or higher is required.", err=True)
    sys.exit(1)

cli = typer.Typer(
    rich_markup_mode="markdown",
    context_settings={"help_option_names": ["--help", "-h"]},
)


def version_callback(value: bool):
    """Print version and exit."""
    if value:
        typer.echo(f"task v: {__version__}")
        raise typer.Exit()


@cache
def open_session(ctx: typer.Context) -> Session:
    session = Session(os.environ["TRILIUM_URL"], os.environ["TRILIUM_TOKEN"])
    ctx.with_resource(session)
    return session


def complete_description(
    ctx: typer.Context, incomplete: str
) -> Generator[str, None, None]:
    """Helper for autocompletion of description.

    :param ctx: typer context
    :param incomplete: partial description
    :return: list of matching descriptions
    """
    session: Session = open_session(ctx)

    # Build query string based on command
    query = "#task"

    if ctx.command.name not in ("archive", "delete", "rm"):
        query += " #!doneDate"

    if incomplete:
        query += f' note.title =* "{incomplete}"'

    for task in session.search(query):
        yield task.title


Description = Annotated[
    List[str],
    typer.Argument(
        autocompletion=complete_description, help="Description of Task."
    ),
]


class BadDescription(typer.BadParameter):
    """Raised when description is not found."""

    def __init__(
        self,
        description: list[str],
        ctx: typer.Context,
        param: Any = None,
        param_hint="Description",
    ) -> None:
        super().__init__(
            f'"{" ".join(description)}" not found.',
            ctx,
            param=param,
            param_hint=param_hint,
        )


@dataclass(frozen=True)
class State:
    """Record state of application.

    :param verbose: display additional columns or data
    :param dry_run: render table rather than updating Trilium
    """

    verbose: bool
    dry_run: bool


@cli.callback()
def main(
    ctx: typer.Context,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Render Tasks to console rather than updating Trilium.",
        ),
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Display additional columns, defaults to False.",
        ),
    ] = False,
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = None,
) -> None:
    """Curate Tasks for TaskManager in trilium notes.

    * **#taskTodoRoot** is the root of Due Tasks.

    * **#taskDoneRoot** is the root for Done Tasks.
    """

    ctx.obj = State(verbose=verbose, dry_run=dry_run)


@cli.command(name="update", help="Update Task.")
@cli.command()
def add(
    ctx: typer.Context,
    description: Description,
    due: Annotated[
        Optional[datetime],
        typer.Option(
            "--due",
            formats=["%Y-%m-%d"],
            help="Date Task is due, defaults to None.",
        ),
    ] = None,
    location: Annotated[
        Optional[str],
        typer.Option(
            "--location", help="Location field for Task, defaults to None."
        ),
    ] = None,
    tags: Annotated[
        Optional[List[str]],
        typer.Option(
            "--tag",
            "-t",
            help="Tag field(s) for Task, repeat as needed, defaults to None.",
        ),
    ] = None,
    message: Annotated[
        Optional[str],
        typer.Option(
            "--message",
            "-m",
            help="Optional content for Task, defaults to None.",
        ),
    ] = None,
    content: Annotated[
        Optional[typer.FileText], typer.Option(encoding="utf-8")
    ] = None,
) -> None:
    """Add Task to TaskManager."""

    if message and content:
        raise typer.BadParameter("Cannot specify both --message and --content")

    session: Session = open_session(ctx)
    task_template = session.search('#task note.title="task template"')[0]
    todo_root = session.search("#taskTodoRoot")[0]
    title = " ".join(description)

    if ctx.obj.dry_run:
        typer.echo(
            f"{ctx.command.name} {title} (todoDate={due},"
            f" tags={None if not tags else ', '.join(tags)}, location={location})"
        )
        raise typer.Exit()

    task: Note
    match ctx.command.name:
        case "add":
            task = Note(title=title, template=task_template, parents=todo_root)
        case "update":
            try:
                task = session.search(
                    f'#task note.title="{title}"', ancestor_note=todo_root
                )[0]
            except IndexError:
                raise BadDescription(description, ctx=ctx)
        case _:
            raise AssertionError(
                f"Command {ctx.command.name} not in (add, update)"
            )

    if due:
        task["todoDate"] = due.strftime("%Y-%m-%d")

    if location:
        task["location"] = location

    if message:
        task.content = message

    if content:
        task.content = content.read()

    if tags and len(tags) > 0:
        task += [Label("tag", t) for t in tags]

    todo_root += task


@cli.command(name="ls")
@cli.command()
def list(ctx: typer.Context) -> None:
    """List due Tasks."""

    table = Table(title="Tasks", box=None, header_style="underline2")

    table.add_column(header="Due", justify="center")
    table.add_column(header="Description")
    if ctx.obj.verbose:
        table.add_column("Location")
        table.add_column("Tag(s)")

    session: Session = open_session(ctx)
    todo_root: Note = session.search("#taskTodoRoot")[0]
    tasks = sorted(
        todo_root.children, key=lambda t: t.get("todoDate", "9999-99-99")
    )
    for task in tasks:
        row = []
        row.append(task.get("todoDate", "-"))
        row.append(task.title)

        if ctx.obj.verbose:
            row.append(task.get("location", "-"))

            tags: str = "-"
            if "tag" in task.attributes and len(task.attributes["tag"]) > 0:
                tags = ", ".join([t.value for t in task.attributes["tag"]])
            row.append(tags)

        table.add_row(*row)

    if table.columns:
        with Console() as console:
            console.print(table)


@cli.command("rm")
@cli.command()
def delete(
    ctx: typer.Context,
    description: Description,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            prompt="Confirm delete?",
            help="Force delete.",
        ),
    ] = False,
) -> None:
    """Delete Task."""

    if not force:
        raise typer.Abort()

    session: Session = open_session(ctx)
    title = " ".join(description)

    if ctx.obj.dry_run:
        typer.echo(f"{ctx.command.name} {title} (force={force})")
        raise typer.Exit()

    try:
        task = session.search(
            f'#task note.title="{title}"', include_archived_notes=True
        )[0]
        task.delete()
    except IndexError:
        raise BadDescription(description, ctx=ctx)


@cli.command()
def done(
    ctx: typer.Context,
    description: Description,
    done: Annotated[
        Optional[datetime],
        typer.Option(
            "--completed",
            formats=["%Y-%m-%d"],
            help="Date task was completed, defaults to today.",
        ),
    ] = None,
) -> None:
    """Mark Task as done."""

    # Note: All the heavy lifting is done by the JavaScript Implementation of TaskManager.
    session: Session = open_session(ctx)
    title = " ".join(description)
    now = (done or datetime.now()).strftime("%Y-%m-%d")

    if ctx.obj.dry_run:
        typer.echo(f'#doneDate={now} #cssClass=done note.title="{title}"')
        raise typer.Exit()

    try:
        task = session.search(f'#task note.title="{title}"')[0]
        task["doneDate"] = now
        task["cssClass"] = "done"
    except IndexError:
        raise BadDescription(description, ctx=ctx)


@cli.command()
def archive(ctx: typer.Context, description: Description) -> None:
    """Archive Task."""

    session: Session = open_session(ctx)
    title = " ".join(description)

    if ctx.obj.dry_run:
        typer.echo(f'{ctx.command.name} #archived note.title="{title}"')
        raise typer.Exit()

    try:
        task = session.search(f'#task note.title="{title}"')[0]
        task["archived"] = ""
    except IndexError:
        raise BadDescription(description, ctx=ctx)


if __name__ == "__main__":
    cli()
