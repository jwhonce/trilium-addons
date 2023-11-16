#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Query Jira for active epics and update task with information for status report.

An exercise in using jinja2 to create html for Trilium.

Environment variables:
    * TRILIUM_URL should be set to the URL of the Trilium Notes server.
        [default: http://localhost:8080]
    * TRILIUM_TOKEN should be set to the API token for the Trilium Notes server.
        [default: None]
    * JIRA_URL should be set to the URL of the Jira server.
        [default: https://issues.redhat.com]
    * JIRA_TOKEN should be set to the API token for the Jira server.
        [default: None]
"""

import logging
import sys
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from functools import cache
from typing import Annotated, Optional, Tuple
from urllib.parse import urlparse

import jira as Jira
import typer
from dateutil.relativedelta import MO, relativedelta
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

# <tr style="border:2px solid white;">
#
JINJA_SOURCE = r"""
<h3>Sprint "{{ sprint.name }}" Start Date: {{ sprint.start_date.strftime("%Y-%m-%d") }}</h3>
<figure class="table" style="width:100%">
<table style="padding:0px;">
<caption>
Active Issues: {{epics|length}} &rarr; Week: {{ now().isocalendar().week }}  &#10098; Updated: {{now().strftime("%Y-%m-%d %H:%M:%S") }} &#10099;
</caption>
<thead>
<tr>
<th style="background-color:#99d0df70;">Key</th>
<th style="background-color:#99d0df70;">Status</th>
<th style="background-color:#99d0df70;">Summary</th>
<th style="background-color:#99d0df70;">Updated</th>
</tr>
</thead>
<tbody>
{%- for epic in epics %}
<tr>
<td><a href={{ epic.url }}>{{ epic.key }}</a></td>
<td>{{ epic.status }}</td>
<td style="text-align:justify;white-space:wrap;">{{ epic.summary }}</td>
{%- if epic.updated > _last_monday %}
<td><strong>{{ epic.updated.strftime("%Y-%m-%d %H:%M:%S") }}*</strong></td>
{%- else %}
<td><small>{{ epic.updated.strftime("%Y-%m-%d %H:%M:%S") }}</small></td>
{%- endif %}
</tr>
{%- endfor %}
</tbody>
</table>
</figure>
"""

cli = typer.Typer(
    rich_markup_mode="markdown",
    context_settings={"help_option_names": ["--help", "-h"]},
)


@dataclass(frozen=True)
class State:
    """Record state for application."""

    jira: Jira.JIRA
    trilium: Session
    verbose: bool
    dry_run: bool


@dataclass(order=True, slots=True)
class Sprint:  # pylint: disable=too-many-instance-attributes
    """Record Jira sprint information."""

    sort_index: datetime = field(init=False, repr=False)
    end_date: datetime
    name: str
    sprint_id: int
    start_date: datetime
    state: str

    def __post_init__(self) -> None:
        """Set internal fields after __init__."""
        self.sort_index = self.start_date


@dataclass(order=True, slots=True)
class Ticket:  # pylint: disable=too-many-instance-attributes
    """Record Jira issue information."""

    sort_index: datetime = field(init=False, repr=False)
    title: str = field(init=False, repr=False, compare=False)
    week: int = field(init=False, repr=False, compare=False)
    assignee: str | None
    created: datetime
    key: str
    labels: list[str]
    priority: str
    status: str
    summary: str
    updated: datetime
    url: str

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


@cache
def _last_monday() -> date:
    """Return date of Monday before last..."""
    today = datetime.now(UTC)
    offset = -1 if today.weekday() == 0 else -2
    return today - relativedelta(weekday=MO(offset))


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
    sprint, issues = _query_jira(ctx)

    table = Table(
        "Key",
        "Status",
        "Summary",
        "Updated",
        box=None,
        header_style="underline2",
        title=f"Active Issues for '{sprint.name}': {len(issues)}",
        caption="*Updated this week",
        caption_justify="left",
    )

    for epic in epics:
        if epic.updated >= _last_monday():
            flagged_updated = Styled(
                epic.updated.strftime("%Y-%m-%d*"), "bold italic"
            )
        else:
            flagged_updated = Styled(
                epic.updated.strftime("%Y-%m-%d"), style="dim"
            )

        table.add_row(
            Styled(issue.key, style=f"link {issue.url}"),
            issue.status,
            issue.summary,
            flagged_updated,
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

    (sprint, issues) = _query_jira(ctx)

    template: Template = Environment(trim_blocks=True, lstrip_blocks=True).get_template(
        Template(JINJA_SOURCE)
    )

    epics_root.content = template.render(
        epics=issues,
        now=datetime.now,
        _last_monday=_last_monday(),
        sprint=sprint,
    )


def _query_jira(ctx: typer.Context) -> Tuple[Sprint, list[Ticket]]:
    """Query Jira for active issues."""
    ocpnode = ctx.obj.jira.boards(name="RUN board")
    sprints = ctx.obj.jira.sprints(ocpnode[0].id, state="active")

    start_date = datetime.now(UTC)
    current_sprint = None
    for sprint in sprints:
        date = datetime.fromisoformat(sprint.startDate)
        if date < start_date:
            current_sprint = Sprint(
                end_date=datetime.fromisoformat(sprint.endDate),
                name=sprint.name,
                sprint_id=sprint.id,
                start_date=date,
                state=sprint.state,
            )
            start_date = date
    if current_sprint is None:
        typer.echo("Unable to find current sprint.", err=True)
        raise typer.Exit(1)

    issues: ResultList[Jira.Issue] = ResultList(
        ctx.obj.jira.search_issues(
            f"issueFunction in epicsOf('sprint = {current_sprint.sprint_id}') ORDER BY status ASC, key ASC",
        )
    )

    def _new_ticket(bug: Jira.Issue) -> Ticket:
        """Map Jira fields to Ticket fields, formatting as needed."""
        assignee = bug.fields.assignee.displayName if bug.fields.assignee else None

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
    return (current_sprint, tickets)


if __name__ == "__main__":
    cli()
