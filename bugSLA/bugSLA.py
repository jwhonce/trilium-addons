#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Query Jira for bugs that have not been triaged in the last 7 days.

Example:
    $ bugSLA.py

Environment variables:
    * TRILIUM_URL should be set to the URL of the Trilium Notes server.
        If not set, the default is http://localhost:8080.
    * TRILIUM_TOKEN should be set to the API token for the Trilium Notes server.
        If not set, the default is None.
"""
import os
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Callable, Optional

import jira as Jira
import typer
from rich.console import Console
from rich.table import Table
from trilium_py.client import ETAPI

__version__ = "0.1.1"


@dataclass
class Service:
    type: str
    connection: Callable[[], Any]
    cache: list[Jira.Issue]
    update: Callable[[list[Any]], None]


jira = Service(
    "jira",
    lambda: Jira.JIRA("https://issues.redhat.com", token_auth=os.environ.get("JIRA_TOKEN")),
    [],
    lambda l: jira.cache.extend(l),
)


@dataclass
class Ticket:
    key: str
    summary: str
    url: str
    status: str
    labels: list[str]
    priority: str
    created: datetime


def get_tickets() -> list[Ticket]:
    # triage_cutoff = (datetime.utcnow() - timedelta(days=6)).replace(tzinfo=pytz.utc)

    with closing(jira.connection()) as client:
        jira.update(
            client.search_issues(
                "project = rhocpprio AND status not in (Closed) AND component = Node"
            )
        )

        jira.update(
            client.search_issues(
                (
                    r'filter = "Node Components"'
                    r" AND (project = OCPBUGS OR project = OCPNODE AND issueType = Bug)"
                    r" AND status = New"
                    r" AND ((labels is EMPTY OR labels not in (triaged)) OR priority in (Undefined))"
                    r" AND created < -6d"
                    r" ORDER BY priority DESC, key DESC"
                )
            )
        )

    tickets: list[Ticket] = []
    for bug in jira.cache:
        created = datetime.fromisoformat(bug.fields.created)
        # if created >= triage_cutoff:
        #     continue

        tickets.append(
            Ticket(
                key=bug.key,
                summary=bug.fields.summary,
                created=created,
                status=bug.fields.status.name,
                priority=bug.fields.priority.name,
                labels=[i for i in bug.fields.labels],
                url=bug.permalink(),
            )
        )
    tickets.sort(key=lambda x: x.created, reverse=True)
    return tickets


app = typer.Typer(add_completion=False)


def version_callback(value: bool):
    if value:
        typer.echo(f"tm version: {__version__}")
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    trilium_url: Annotated[str, typer.Option("--service-url", envvar="TRILIUM_URL", is_eager=True)],
    token: Annotated[str, typer.Option("--token", envvar="TRILIUM_TOKEN", is_eager=True)],
    verbose: Annotated[Optional[bool], typer.Option("--verbose", "-v", is_eager=True)] = False,
    version: Annotated[
        Optional[bool],
        typer.Option(
            "--version",
            callback=version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
    dry_run: Annotated[
        Optional[bool],
        typer.Option(
            "--dry-run",
            "-n",
            is_eager=True,
            help="Render Tasks as table rather than updating Trilium.",
        ),
    ] = False,
) -> None:
    client = ETAPI(trilium_url, token)
    ctx.with_resource(closing(client))

    title = "Tasks"
    review_bugs = "Review untriaged Node Bugs"
    if dry_run:
        render_table(title, review_bugs, get_tickets())
    else:
        update_trilium(client, title, review_bugs, get_tickets())


def render_table(title: str, static: str, tickets: list[Ticket]) -> None:
    """Render a table of tickets to stdout."""
    table = Table(
        "Key",
        "Priority",
        "Status",
        "Summary",
        box=None,
        header_style="underline2",
        title=title,
    )
    table.add_row("-", "-", "-", static)

    for ticket in tickets:
        table.add_row(ticket.key, ticket.priority, ticket.status, ticket.summary)

    with Console() as console:
        console.print(table)


def update_trilium(client: ETAPI, title: str, static: str, tickets: list[Ticket]) -> None:
    """Update Trilium with Jira tickets as Task list."""
    permalink = (
        r"https://issues.redhat.com/secure/Dashboard.jspa"
        r"?selectPageId=12345608"
        r"#SIGwKWmOqDAaNglROUEImIOqGjtpUxw8HF6BFOqSXIGgGAKIiiKmgQJB+jQlQMJUhQwQgYEeF1QlAA"
    )
    client.add_todo(f'<a href="{permalink}">{static}</a>', todo_caption=f"<h3>{title}</h3>")

    for ticket in tickets:
        client.add_todo(
            f"{ticket.key}: {ticket.priority} - {ticket.status}<br>"
            f'<a href="{ticket.url}">{ticket.summary}</a>'
        )


if __name__ == "__main__":
    app()
