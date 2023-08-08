"""Curate tasks for Task Manager in trilium notes.

Note:
    This is a work in progress and an exercise in learning typer and TriliumAlchemy
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table
from trilium_alchemy import Label, Note, Session

__version__ = "0.1.0"


cli = typer.Typer(context_settings={"help_option_names": ["-h", "--help"]})


def version_callback(value: bool):
    """Print version and exit"""
    if value:
        typer.echo(f"tm version: {__version__}")
        raise typer.Exit()


def complete_description(ctx: typer.Context, incomplete: str) -> list[str]:
    """Helper for autocompletion of description.

    :param ctx: typer context
    :param incomplete: partial description
    :return: list of matching descriptions
    """
    if incomplete == "" or incomplete is None:
        return [t.title for t in ctx.obj.root.children]
    return [t.title for t in ctx.obj.root.children if t.title.startswith(incomplete)]


# Type alias for description
Description = Annotated[
    str, typer.Argument(help="Description of task item", autocompletion=complete_description)
]


@dataclass(frozen=True)
class State:
    """Record state for tm application.

    :param trilium: instance of Session
    :param root: #taskTodoRoot note for TaskManager
    :param verbose: display additional columns or data
    :param dry_run: render table rather than updating Trilium
    """

    trilium: Session
    root: Note
    verbose: bool = False
    dry_run: bool = False


@cli.callback()
def main(
    ctx: typer.Context,
    trilium_url: Annotated[str, typer.Option("--service-url", envvar="TRILIUM_URL", is_eager=True)],
    token: Annotated[str, typer.Option("--token", envvar="TRILIUM_TOKEN", is_eager=True)],
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            is_flag=True,
            is_eager=True,
            help="Display additional columns, defaults to False",
        ),
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            callback=version_callback,
            is_flag=True,
            is_eager=True,
            help="Show version and exit",
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            is_flag=True,
            is_eager=True,
            help="Render Tasks as table rather than updating Trilium, defaults to False",
        ),
    ] = False,
) -> None:
    """Initialize application.

    :param ctx: typer context
    :param trilium_url: URL for Trilium service
    :param token: Trilium API token
    :param verbose: display additional columns or data
    :param version: show version and exit
    :param dry_run: render table rather than updating Trilium
    :raises typer.Abort: if taskTodoRoot not found
    """
    client = Session(trilium_url, token)
    ctx.with_resource(client)

    todo_root = client.search("#taskTodoRoot")
    if todo_root is None:
        typer.echo("taskTodoRoot not found", err=True)
        raise typer.Abort()

    ctx.obj = State(trilium=client, root=todo_root[0], verbose=verbose, dry_run=dry_run)


@cli.command(name="update", help="Update task in TaskManager")
@cli.command()
def add(
    ctx: typer.Context,
    description: Description,
    due: Annotated[
        Optional[datetime],
        typer.Option("--due", formats=["%Y-%m-%d"], help="Date Task is due, defaults to None"),
    ] = None,
    location: Annotated[
        Optional[str], typer.Option("--location", help="Location field for Task, defaults to None")
    ] = None,
    tags: Annotated[
        Optional[list[str]],
        typer.Option(
            "--tag", "-t", help="Tag field(s) for Task, repeat as needed, defaults to None"
        ),
    ] = None,
    content: Annotated[
        Optional[str],
        typer.Option("--message", "-m", help="Optional content for Task, defaults to None"),
    ] = None,
) -> None:
    """Add task to TaskManager.

    :param ctx: typer context
    :param description: description of task
    :param due: due date for task
    :param location: location for task
    :param tags: tag(s) for task
    :param content: additional content for task
    """
    session = ctx.obj.trilium
    todo_root = ctx.obj.root

    task_template = session.search('#task note.title="task template"')[0]

    if ctx.obj.dry_run:
        typer.echo(
            f"{ctx.command.name} {description} (todoDate={due}, tags={', '.join(tags or [])}, location={location})"
        )
        return

    task: Note
    match ctx.command.name:
        case "add":
            task = Note(title=description, template=task_template, parents=todo_root, leaf=True)
        case "update":
            task = session.search(f'#task note.title="{description}"', ancestor_note=todo_root)[0]
        case _:
            raise AssertionError(f"Command {ctx.command.name} not in (add, update)")

    if due:
        task["todoDate"] = due.strftime("%m-%d-%Y")

    if location:
        task["location"] = location

    if content:
        task.content = content

    task += [Label("tag", t) for t in tags or []]

    todo_root += task


@cli.command()
def list(ctx: typer.Context) -> None:
    """List due tasks from TaskManager

    :param ctx: typer context
    """
    table = Table("Due", "Description", box=None, header_style="underline2")
    if ctx.obj.verbose:
        table.add_column("Location")
        table.add_column("Tag(s)")

    todo_root: Note = ctx.obj.root
    for task in todo_root.children:
        row = []

        try:
            row.append(task["todoDate"])
        except KeyError:
            row.append("")
        row.append(task.title)

        if ctx.obj.verbose:
            try:
                row.append(task["location"])
            except KeyError:
                row.append("")

            try:
                row.append(", ".join([t.value for t in task.attributes["tag"]]))
            except KeyError:
                row.append("")

        table.add_row(*row)

    if table.columns:
        with Console() as console:
            console.print(table)


@cli.command()
def rm(
    ctx: typer.Context,
    description: Description,
    confirm: bool = typer.Option(
        False, "--confirm", is_flag=True, help="Confirm delete, defaults to False"
    ),
) -> None:
    """Delete task from TaskManager.

    :param ctx: typer context
    :param description: description of task
    :param confirm: confirm delete. Defaults to False.
    :raises typer.Abort: if failed to delete task not found
    """
    task = ctx.obj.trilium.search(f'#task note.title="{description}"', include_archived_notes=True)
    if len(task) == 0:
        typer.echo(f"Task '{description}'not found", err=True)
        raise typer.Abort()

    if ctx.obj.dry_run:
        typer.echo(f"{ctx.command.name} {description} (confirm={confirm})")
        return

    if not confirm:
        typer.confirm(f"Delete {description}?", default=False, show_default=True, abort=True)

    task[0].delete()


@cli.command()
def done(
    ctx: typer.Context,
    description: Description,
    done: Annotated[
        Optional[datetime],
        typer.Option(
            "--completed", formats=["%Y-%m-%d"], help="Date task was completed, defaults to today"
        ),
    ] = None,
) -> None:
    """Mark task as done in TaskManager.

    Note: All the heavy lifting is done by the JavaScript Implementation of TaskManager.

    :param ctx: typer context
    :param description: description of task
    :raises typer.Abort: if taskDoneRoot not found
    """
    task = ctx.obj.trilium.search(f'#task note.title="{description}"', ancestor_note=ctx.obj.root)
    if len(task) == 0:
        typer.echo(f"Task '{description}'not found", err=True)
        raise typer.Abort()

    now = datetime.utcnow().strftime("%Y-%m-%d") if done is None else done.strftime("%Y-%m-%d")

    if ctx.obj.dry_run:
        typer.echo(f"#doneDate={now} #cssClass=done {description}")
        return

    task[0]["doneDate"] = now
    task[0]["cssClass"] = "done"


@cli.command()
def archive(ctx: typer.Context, description: Description) -> None:
    """Archive TaskManager Task in Trilium.

    :param ctx: typer context
    :param description: description of task
    """
    task = ctx.obj.trilium.search(f'#task note.title="{description}"')
    if len(task) == 0:
        typer.echo(f"Task '{description}'not found", err=True)
        raise typer.Abort()

    if ctx.obj.dry_run:
        typer.echo(f"{ctx.command.name} {description}")
        return

    task[0]["archived"] = ""


if __name__ == "__main__":
    cli()
