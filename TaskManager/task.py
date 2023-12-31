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
from typing import Annotated, Any, Generator, Optional

import typer
from rich.console import Console
from rich.table import Table
from trilium_alchemy import Label, Note, Session

if sys.version_info < (3, 10):
    # minimum version for trilium-alchemy
    typer.echo("Python 3.10 or higher is required.", err=True)
    sys.exit(1)

__version__ = "0.1.3"

cli = typer.Typer(
    rich_markup_mode="markdown",
    context_settings={"help_option_names": ["--help", "-h"]},
)


@dataclass(frozen=True)
class State:
    """Record state of application."""

    verbose: bool
    dry_run: bool


def _version(value: bool):
    """Print version and exit."""
    if value:
        typer.echo(f"task v: {__version__}")
        raise typer.Exit()


@cache
def _open_session(ctx: typer.Context) -> Session:
    session = Session(os.environ["TRILIUM_URL"], os.environ["TRILIUM_TOKEN"])
    ctx.with_resource(session)
    return session


def _complete_description(
    ctx: typer.Context, incomplete: str
) -> Generator[str, None, None]:
    session: Session = _open_session(ctx)

    include_archived_notes = ctx.command.name in ("delete", "rm")

    fields: list[str] = ["#task"]
    if ctx.command.name == "done":
        fields.append("#!doneDate")

    if incomplete:
        fields.append(f'note.title =* "{incomplete}"')

    query = " ".join(fields)
    for task in session.search(
        query, include_archived_notes=include_archived_notes
    ):
        yield task.title


class BadDescription(typer.BadParameter):
    """Raised when description does not match any note titles in trilium."""

    def __init__(
        self,
        description: list[str],
        ctx: typer.Context,
        param: Any = None,
        param_hint="Description",
    ) -> None:
        """Initialize BadDescription Error.

        :param description: Words given for Task description
        :param ctx: Context of command
        :param param: See typer.BadParameter#param, defaults to None
        :param param_hint: See typer.BadParameter#param_hint, defaults to "Description"
        """
        super().__init__(
            f'"{" ".join(description)}" not found.',
            ctx,
            param=param,
            param_hint=param_hint,
        )


# list[str] used as type to allow input with or without quotes
Description = Annotated[
    list[str],
    typer.Argument(
        metavar="TITLE",
        autocompletion=_complete_description,
        show_default=False,
        help="Description of Task.",
    ),
]


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
            callback=_version,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = None,
) -> None:
    """Curate Tasks for TaskManager in trilium notes.

    * **#taskTodoRoot** is the root of Due Tasks.

    * **#taskDoneRoot** is the root for Done Tasks.
    """
    _ = version
    ctx.obj = State(verbose=verbose, dry_run=dry_run)


@cli.command(name="update", help="Update Task.")
@cli.command()
def add(  # pylint: disable=too-many-arguments
    ctx: typer.Context,
    description: Description,
    due: Annotated[
        Optional[datetime],
        typer.Option(
            "--due",
            formats=["%Y-%m-%d"],
            help="Date Task is due.",
        ),
    ] = None,
    location: Annotated[
        Optional[str],
        typer.Option("--location", "-l", help="Location field for Task."),
    ] = None,
    tags: Annotated[
        Optional[list[str]],
        typer.Option(
            "--tag",
            "-t",
            help="Tag field(s) for Task, repeat as needed.",
        ),
    ] = None,
    message: Annotated[
        Optional[str],
        typer.Option(
            "--message",
            "-m",
            help="Content for Task.",
        ),
    ] = None,
    content: Annotated[
        Optional[typer.FileText],
        typer.Option(encoding="utf-8", help="Content for Task read from file."),
    ] = None,
) -> None:
    """Add Task to TaskManager."""
    if message and content:
        raise typer.BadParameter("Cannot specify both --message and --content")

    session: Session = _open_session(ctx)
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
            except IndexError as exc:
                raise BadDescription(description, ctx=ctx) from exc
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


@cli.command(name="list")
@cli.command()
def ls(ctx: typer.Context) -> None:  # pylint: disable=invalid-name
    """List due Tasks."""
    table = Table(title="Tasks", box=None, header_style="underline2")

    table.add_column(header="Due", justify="center")
    table.add_column(header="Description")
    if ctx.obj.verbose:
        table.add_column("Location")
        table.add_column("Tag(s)")

    session: Session = _open_session(ctx)
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
            help="Skip confirming delete.",
        ),
    ] = False,
) -> None:
    """Delete Task."""
    if not force:
        raise typer.Abort()

    session: Session = _open_session(ctx)
    title = " ".join(description)

    if ctx.obj.dry_run:
        typer.echo(f"{ctx.command.name} {title} (force={force})")
        raise typer.Exit()

    try:
        task = session.search(
            f'#task note.title="{title}"', include_archived_notes=True
        )[0]
        task.delete()
    except IndexError as exc:
        raise BadDescription(description, ctx=ctx) from exc


@cli.command("done")
def complete(
    ctx: typer.Context,
    description: Description,
    done: Annotated[
        datetime,
        typer.Option(
            formats=["%Y-%m-%d"],
            default_factory=datetime.now,
            show_default="today",  # type: ignore
            help="Date task was completed.",
        ),
    ],
) -> None:
    """Mark Task as done."""
    # Note: All the heavy lifting is done by the JavaScript Implementation of TaskManager.
    session: Session = _open_session(ctx)
    title = " ".join(description)

    if ctx.obj.dry_run:
        typer.echo(f'#doneDate={done} #cssClass=done note.title="{title}"')
        raise typer.Exit()

    try:
        task = session.search(f'#task note.title="{title}"')[0]
        task["doneDate"] = done.strftime("%Y-%m-%d")
        task["cssClass"] = "done"
    except IndexError as exc:
        raise BadDescription(description, ctx=ctx) from exc


@cli.command()
def archive(ctx: typer.Context, description: Description) -> None:
    """Archive Task."""
    session: Session = _open_session(ctx)
    title = " ".join(description)

    if ctx.obj.dry_run:
        typer.echo(f'{ctx.command.name} #archived note.title="{title}"')
        raise typer.Exit()

    try:
        task = session.search(f'#task note.title="{title}"')[0]
        task["archived"] = ""
    except IndexError as exc:
        raise BadDescription(description, ctx=ctx) from exc


if __name__ == "__main__":
    cli()
