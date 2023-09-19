#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Query Jira for active epics and update task with information for email status."""

import logging
import sys
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from typing import Annotated, Optional
from urllib.parse import urlparse

import jira as Jira
import pytz
import typer
from jinja2 import Environment, Template
from jira.client import ResultList
from rich.console import Console
from rich.styled import Styled
from rich.table import Table
from trilium_alchemy import Note, Session

__version__ = "0.2.1"

if sys.version_info < (3, 10):
    # minimum version for trilium-alchemy
    typer.echo("Python 3.10 or higher is required.", err=True)
    sys.exit(1)

logging.basicConfig(level=logging.WARN)

JINJA_SOURCE = r"""<table style="padding:0px;width:100%;">
<caption>
Active Epics: {{epics|length}} &rarr; Week: {{ now().isocalendar().week }}  &#10098; Updated: {{now().strftime("%Y-%m-%d %H:%M:%S") }} &#10099;
</caption>
<thread>
<tr>
<th>Key</th><th>Status</th><th>Summary</th><th>Updated</th>
</tr>
</thread>
{%- for epic in epics %}
<tr>
<td><a href={{ epic.url }}>{{ epic.key }}</a></td>
<td>{{ epic.status }}</td>
<td>{{ epic.summary }}</td>
{%- if epic.week == week %}
<td>{{ epic.updated.strftime("%Y-%m-%d %H:%M:%S") }}*</td>
{%- else %}
<td>{{ epic.updated.strftime("%Y-%m-%d %H:%M:%S") }}</td>
{%- endif %}
</tr>
{%- endfor %}
</table>
"""

cli = typer.Typer(
    rich_markup_mode="markdown",
    context_settings={"help_option_names": ["--help", "-h"]},
)


@dataclass(frozen=True)
class State:
    """Record state for tm application."""

    jira: Jira.JIRA
    trilium: Session
    verbose: bool
    dry_run: bool


@dataclass(order=True, slots=True)
class Ticket:  # pylint: disable=too-many-instance-attributes
    """Record Jira issue information."""

    sort_index: datetime = field(init=False, repr=False)
    title: str = field(init=False, repr=False, compare=False)
    week: int = field(init=False, repr=False, compare=False)
    key: str
    summary: str
    url: str
    status: str
    labels: list[str]
    priority: str
    created: datetime
    updated: datetime
    assignee: str | None

    def __post_init__(self) -> None:
        """Set internal fields after __init__."""
        self.sort_index = self.created

        self.title = self.summary
        if len(self.summary) > 45:
            self.title = self.summary[:42] + "..."

        self.week = self.updated.isocalendar().week


def _version(value: bool):
    """Print version and exit."""
    if value:
        typer.echo(f"jira_sla v: {__version__}")
        raise typer.Exit()


def _validate_url(url: str) -> str:
    """Validate URL."""
    result = urlparse(url)
    if not all([result.scheme, result.netloc]):
        raise typer.BadParameter(f"Invalid URL: {url}")
    return url


@cli.callback()
def main(  # pylint: disable=too-many-arguments
    ctx: typer.Context,
    trilium_token: Annotated[str, typer.Option(envvar="TRILIUM_TOKEN")],
    jira_token: Annotated[str, typer.Option(envvar="JIRA_TOKEN")],
    trilium_url: Annotated[
        str,
        typer.Option(envvar="TRILIUM_URL", callback=_validate_url),
    ] = "http://localhost:8080",
    jira_url: Annotated[
        str, typer.Option(envvar="JIRA_URL", callback=_validate_url)
    ] = "https://issues.redhat.com",
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Display additional columns.",
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
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Render Tasks as table rather than updating Trilium.",
        ),
    ] = False,
) -> None:
    """Query Jira and update / create Trilium Task Manager task to write status report.

    * **#taskTodoRoot** is the root of due Tasks.
    """
    _ = version

    trilium = Session(trilium_url, trilium_token)
    ctx.with_resource(trilium)

    jira = Jira.JIRA(jira_url, token_auth=jira_token)
    ctx.with_resource(closing(jira))

    if verbose:
        logging.getLogger().setLevel(level=logging.DEBUG)
        logging.debug("%s v: %s", ctx.command.name, __version__)

    ctx.obj = State(
        dry_run=dry_run,
        jira=jira,
        trilium=trilium,
        verbose=verbose,
    )


@cli.command("list")
@cli.command()
def ls(ctx: typer.Context) -> None:  # pylint: disable=invalid-name
    """List active epics."""
    epics: list[Ticket] = _query_jira(ctx)

    table = Table(
        "Key",
        "Status",
        "Summary",
        "Updated",
        "URL",
        box=None,
        header_style="underline2",
        title=f"Active Epics: {len(epics)}",
        caption="*Updated this week",
        caption_justify="left",
    )

    this_week = datetime.now().isocalendar().week
    for epic in epics:
        if this_week == epic.week:
            flagged_updated = Styled(
                epic.updated.strftime("%Y-%m-%d*"), "bold italic"
            )
        else:
            flagged_updated = Styled(
                epic.updated.strftime("%Y-%m-%d"), style="dim"
            )

        table.add_row(
            epic.key,
            epic.status,
            epic.summary,
            flagged_updated,
            Styled(epic.url, style=f"link {epic.url}"),
        )

    with Console() as console:
        console.print(table)


@cli.command()
def publish(ctx: typer.Context) -> None:
    """Publish active epics to Trilium Note #."""
    # Console.export_html() does not create html that can be rendered by
    # Trilium.  Use Jinja2 to create html.
    trilium: Session = ctx.obj.trilium

    try:
        epics_root: Note = trilium.search("#jiraActiveEpicsRoot")[0]
    except IndexError as err:
        typer.echo("Unable to find #jiraActiveEpicsRoot", err=True)
        raise typer.Exit(1) from err

    epics: list[Ticket] = _query_jira(ctx)

    template: Template = Environment(
        trim_blocks=True, lstrip_blocks=True
    ).get_template(Template(JINJA_SOURCE))

    epics_root.content = template.render(
        epics=epics, now=datetime.now, week=datetime.now().isocalendar().week
    )


def _query_jira(ctx: typer.Context) -> list[Ticket]:
    """Query Jira for active epics."""
    ocpnode = ctx.obj.jira.boards(name="Node board")
    sprints = ctx.obj.jira.sprints(ocpnode[0].id, state="active")

    start_date = datetime.utcnow().replace(tzinfo=pytz.utc)
    for sprint in sprints:
        date = datetime.fromisoformat(sprint.startDate)
        if date < start_date:
            start_date = date

    issues: ResultList[Jira.Issue] = ResultList(
        ctx.obj.jira.search_issues(
            "project = OCPNODE AND status not in (Closed)"
            f'  AND issueFunction in epicsOf("updated > {start_date.strftime("%Y-%m-%d")}")'
            "  ORDER BY status ASC, key ASC"
        )
    )

    def _new_ticket(bug: Jira.Issue) -> Ticket:
        """Map Jira fields to Ticket fields, formatting as needed."""
        assignee = (
            bug.fields.assignee.displayName if bug.fields.assignee else None
        )

        return Ticket(
            assignee=assignee,
            created=datetime.fromisoformat(bug.fields.created),
            key=bug.key,
            labels=list(bug.fields.labels),
            priority=bug.fields.priority.name,
            status=bug.fields.status.name,
            summary=bug.fields.summary,
            updated=datetime.fromisoformat(bug.fields.updated),
            url=bug.permalink(),
        )

    tickets: list[Ticket] = []
    for issue in issues:
        tickets.append(_new_ticket(issue))
    return tickets


if __name__ == "__main__":
    cli()
