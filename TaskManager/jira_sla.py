#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Query Jira for issues that need to be triaged / escalated.

Environment variables:
    * TRILIUM_URL should be set to the URL of the Trilium Notes server.
        If not set, the default is http://localhost:8080.
    * TRILIUM_TOKEN should be set to the API token for the Trilium Notes server.
        If not set, the default is None.
"""
import logging
import sys
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from itertools import chain
from string import Template
from typing import Annotated, Optional
from urllib.parse import urlparse

import jira as Jira
import typer
from bs4 import BeautifulSoup
from jira.client import ResultList
from rich.console import Console
from rich.table import Table
from trilium_alchemy import Label, Note, Session

__version__ = "0.2.1"

if sys.version_info < (3, 10):
    # minimum version for trilium-alchemy
    typer.echo("Python 3.10 or higher is required.", err=True)
    sys.exit(1)

logging.basicConfig(level=logging.WARN)
LABEL_DATE = "%Y-%m-%d"

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
class Ticket:
    sort_index: datetime = field(init=False, repr=False)
    key: str
    summary: str
    title: str
    url: str
    status: str
    labels: list[str]
    priority: str
    created: datetime
    updated: datetime
    assignee: str | None

    def __post_init__(self):
        self.sort_index = self.created


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
def main(
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
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            "-n",
            help="Render Tasks as table rather than updating Trilium, defaults to False.",
        ),
    ] = False,
) -> None:
    """Query Jira and update / create tasks to track important tickets.

    * **#taskTodoRoot** is the root of Due Tasks.
    """
    _ = version

    trilium = Session(trilium_url, trilium_token)
    ctx.with_resource(trilium)

    jira = Jira.JIRA(jira_url, token_auth=jira_token)
    ctx.with_resource(closing(jira))

    if verbose:
        logging.basicConfig(level=logging.DEBUG)

    ctx.obj = State(
        trilium=trilium,
        jira=jira,
        verbose=verbose,
        dry_run=dry_run,
    )


@cli.command(name="list")
@cli.command()
def ls(ctx: typer.Context) -> None:  # pylint: disable=invalid-name
    """List Jira tickets that need to be triaged / escalated."""
    tickets = _get_tickets(ctx)

    table = Table(
        "Key",
        "Priority",
        "Status",
        "Title",
        box=None,
        header_style="underline2",
        title="Tasks",
    )
    if ctx.obj.verbose:
        table.add_column("Labels")
        table.add_column("Assignee")
        table.add_column("Created")

    for ticket in tickets:
        row = [ticket.key, ticket.priority, ticket.status, ticket.title]

        if ctx.obj.verbose:
            row.extend(
                [
                    "\n".join(ticket.labels),
                    ticket.assignee or "N/A",
                    ticket.created.strftime(LABEL_DATE),
                ]
            )

        table.add_row(*row)

    with Console() as console:
        console.print(table)
    raise typer.Exit()


@cli.command()
def publish(ctx: typer.Context) -> None:
    """Publish Jira tickets to Tasks in Trilium."""

    table = Table(
        "Key",
        "Priority",
        "Status",
        "Title",
        box=None,
        header_style="underline2",
        title="Tasks",
    )
    table.add_column("Labels")
    table.add_column("Assignee")
    table.add_column("Created")

    html_template = Template(
        '<h2><a href="$url">$key</a></h2>'
        "<h3>Summary</h3>"
        "<table>"
        '  <tr> <td colspan="2">$summary</td> </tr>'
        '  <tr> <td style="text-align:right;"> <strong>Initial Priority:</strong></td> <td>$priority</td> </tr>'
        '  <tr> <td style="text-align:right;"> <strong>Created:</strong></td> <td>$created</td> </tr>'
        '  <tr> <td style="text-align:right;"> <strong>Jira Label(s):</strong></td> <td>$labels</td> </tr>'
        '  <tr> <td style="text-align:right;"> <strong>Mark:</strong></td> <td>$now</td> </tr>'
        "</table>"
        "<h3>Notes</h3>"
        '<ul class="notes-list"><li></li></ul>'
    )

    tickets = _get_tickets(ctx)
    trilium: Session = ctx.obj.trilium

    task_root = trilium.search("#taskTodoRoot")[0]
    task_template = trilium.search('#task note.title="task template"')[0]
    today = trilium.get_today_note()

    for ticket in tickets:
        candidates = trilium.search(
            f'#task #!doneDate #jiraKey="{ticket.key}"', ancestor_note=task_root
        )
        match len(candidates):
            case 0:
                logging.debug("New Jira issue: %s", ticket.key)

                task = Note(
                    title=f"{ticket.key}: {ticket.title}",
                    template=task_template,
                    content=html_template.substitute(
                        {
                            "created": ticket.created.isoformat(),
                            "key": ticket.key,
                            "labels": ", ".join(ticket.labels),
                            "now": datetime.now().isoformat(),
                            "priority": ticket.priority,
                            "status": ticket.status,
                            "summary": ticket.summary,
                            "url": ticket.url,
                        }
                    ),
                )
                task["iconClass"] = "bx bx-bug"
                task["jiraKey"] = ticket.key
                task["location"] = "work"
                task["todoDate"] = ticket.created.strftime(LABEL_DATE)
                task += [Label("tag", "jira")]

                task_root += task
                trilium.flush()
                task ^= (today, "TODO")

            case 1:
                logging.debug("Updating Task with Jira issue: %s", ticket.key)
                task = candidates[0]

                soup = BeautifulSoup(str(task.content).encode("ascii", "ignore"), "html.parser")
                try:
                    # Add dated marker to comment section
                    list_item = soup.new_tag("li")
                    list_item.string = (
                        f'{datetime.now().strftime("%Y-%m-%d %H:%M")} Update from Jira'
                    )

                    try:
                        # Append sync marker to existing comment section
                        unbulleted_list = soup.find("ul", {"class": "notes-list"})
                        unbulleted_list.append(list_item)
                    except AttributeError:
                        # Create new comment section, append at end of note
                        unbulleted_list = soup.new_tag("ul", attrs={"class": "notes-list"})
                        unbulleted_list.append(list_item)
                        soup.append(unbulleted_list)

                    task.content = str(soup)
                finally:
                    soup.decompose()
                    del soup

            case _:
                typer.echo(f"Multiple Tasks matched for {ticket.key}", err=True)
                raise typer.Abort()

        # Update Task metadata whether new or existing
        task["jiraAssignee"] = ticket.assignee or "N/A"
        task["jiraPriority"] = ticket.priority
        task["jiraStatus"] = ticket.status
        task["jiraUpdated"] = ticket.updated.strftime(LABEL_DATE)
        task["jiraLabels"] = ":".join(sorted(ticket.labels))

        trilium.flush()

        table.add_row(
            ticket.key,
            ticket.priority,
            ticket.status,
            ticket.title,
            "\n".join(ticket.labels),
            ticket.assignee or "N/A",
            ticket.created.strftime(LABEL_DATE),
        )

    with Console() as console:
        console.print(table)
    raise typer.Exit()


def _get_tickets(ctx: typer.Context) -> list[Ticket]:
    if ctx.obj.dry_run:
        # Dry run, return a single known test ticket.
        summary = (
            "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor"
            " incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis"
            " nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."
            " Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore"
            " eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident,"
            " sunt in culpa qui officia deserunt mollit anim id est laborum."
        )

        return [
            Ticket(
                assignee="tester",
                created=datetime.now(),
                key="TEST-1",
                labels=["triaged", "testing"],
                priority="Blocker",
                status="Testing",
                summary=summary,
                title=(summary[:45] + "..." * (len(summary) > 45)),
                updated=datetime.now(),
                url="https://issues.example.com",
            )
        ]

    jira: Jira.JIRA = ctx.obj.jira

    # Gather RHOCPPRIO and untriaged tickets
    issues: ResultList[Jira.Issue] = ResultList(
        chain(
            jira.search_issues(
                r"project = rhocpprio AND status not in (Closed)"
                r' AND (component = Node OR assignee = "Jhon Honce")'
            ),
            jira.search_issues(
                r'filter = "Node Components"'
                r" AND (project = OCPBUGS OR project = OCPNODE AND issueType = Bug)"
                r" AND status = New"
                r" AND ((labels is EMPTY OR labels not in (triaged)) OR priority in (Undefined))"
                r" AND created < -6d"
                r" ORDER BY priority DESC, key DESC"
            ),
        )
    )

    def _new_ticket(bug: Jira.Issue) -> Ticket:
        """Map Jira fields to Ticket fields, formatting as needed."""
        assignee = bug.fields.assignee.displayName if bug.fields.assignee else None

        return Ticket(
            assignee=assignee,
            created=datetime.fromisoformat(bug.fields.created),
            key=bug.key,
            labels=[l for l in bug.fields.labels],
            priority=bug.fields.priority.name,
            status=bug.fields.status.name,
            summary=bug.fields.summary,
            title=(bug.fields.summary[:45] + "..." * (len(bug.fields.summary) > 45)),
            updated=datetime.fromisoformat(bug.fields.updated),
            url=bug.permalink(),
        )

    tickets: list[Ticket] = []
    for issue in issues:
        tickets.append(_new_ticket(issue))
    return tickets


if __name__ == "__main__":
    cli()
