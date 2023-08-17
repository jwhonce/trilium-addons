#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Curate tasks for Task Manager in trilium notes.

Note(s):
    * This is a work in progress and an exercise in learning typer and TriliumAlchemy
    * The labels, relations and widgets of TaskManager are leveraged to manage tasks
"""
import os
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from typing import Annotated, Generator, Optional

import typer
from rich.console import Console
from rich.table import Table
from trilium_alchemy import Label, Note, Session

__version__ = "0.1.2"


cli = typer.Typer(
    rich_markup_mode="markdown",
    context_settings={"help_option_names": ["--help", "-h"], "allow_interspersed_args": True},
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


def complete_description(ctx: typer.Context, incomplete: str) -> Generator[str, None, None]:
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
    str, typer.Argument(help="Description of Task.", autocompletion=complete_description)
]


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
            "-V",
            help="Display additional columns, defaults to False.",
        ),
    ] = False,
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            "-v",
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
        typer.Option("--due", formats=["%Y-%m-%d"], help="Date Task is due, defaults to None."),
    ] = None,
    location: Annotated[
        Optional[str], typer.Option("--location", help="Location field for Task, defaults to None.")
    ] = None,
    tags: Annotated[
        Optional[list[str]],
        typer.Option(
            "--tag", "-t", help="Tag field(s) for Task, repeat as needed, defaults to None."
        ),
    ] = None,
    message: Annotated[
        Optional[str],
        typer.Option("--message", "-m", help="Optional content for Task, defaults to None."),
    ] = None,
    content: Annotated[Optional[typer.FileText], typer.Option()] = None,
) -> None:
    """Add Task to TaskManager."""

    if message and content:
        raise typer.BadParameter("Cannot specify both --message and --content")

    session: Session = open_session(ctx)
    task_template = session.search('#task note.title="task template"')[0]
    todo_root = session.search("#taskTodoRoot")[0]

    if ctx.obj.dry_run:
        typer.echo(
            f"{ctx.command.name} {description} (todoDate={due},"
            f" tags={None if not tags else ', '.join(tags)}, location={location})"
        )
        raise typer.Exit()

    task: Note
    match ctx.command.name:
        case "add":
            task = Note(title=description, template=task_template, parents=todo_root)
        case "update":
            task = session.search(f'#task note.title="{description}"', ancestor_note=todo_root)[0]
        case _:
            raise AssertionError(f"Command {ctx.command.name} not in (add, update)")

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

    table = Table("Due", "Description", title="Tasks", box=None, header_style="underline2")
    if ctx.obj.verbose:
        table.add_column("Location")
        table.add_column("Tag(s)")

    session: Session = open_session(ctx)
    todo_root = session.search("#taskTodoRoot")[0]
    for task in todo_root.children:
        row = []

        row.append("N/A" if "todoDate" not in task else task["todoDate"])
        row.append(task.title)

        if ctx.obj.verbose:
            row.append("N/A" if "location" not in task else task["location"])

            tags: str = "N/A"
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
    confirm: bool = typer.Option(
        False, "--confirm", is_flag=True, help="Confirm delete, defaults to False."
    ),
) -> None:
    """Delete Task."""

    session: Session = open_session(ctx)
    task = session.search(f'#task note.title="{description}"', include_archived_notes=True)[0]

    if ctx.obj.dry_run:
        typer.echo(f"{ctx.command.name} {description} (confirm={confirm})")
        raise typer.Exit()

    if not confirm:
        typer.confirm(f"Delete {description}?", default=False, show_default=True, abort=True)

    task.delete()


@cli.command()
def done(
    ctx: typer.Context,
    description: Description,
    done: Annotated[
        Optional[datetime],
        typer.Option(
            "--completed", formats=["%Y-%m-%d"], help="Date task was completed, defaults to today."
        ),
    ] = None,
) -> None:
    """Mark Task as done."""

    now = (done or datetime.now()).strftime("%Y-%m-%d")

    # Note: All the heavy lifting is done by the JavaScript Implementation of TaskManager.
    session: Session = open_session(ctx)
    task = session.search(f'#task note.title="{description}"')[0]

    if ctx.obj.dry_run:
        typer.echo(f"#doneDate={now} #cssClass=done {description}")
        raise typer.Exit()

    task["doneDate"] = now
    task["cssClass"] = "done"


@cli.command()
def archive(ctx: typer.Context, description: Description) -> None:
    """Archive Task."""

    session: Session = open_session(ctx)
    task = session.search(f'#task note.title="{description}"')[0]

    if ctx.obj.dry_run:
        typer.echo(f"{ctx.command.name} {description}")
        raise typer.Exit()

    task["archived"] = ""


if __name__ == "__main__":
    cli()
