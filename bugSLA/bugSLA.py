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
from collections import namedtuple
from contextlib import closing
from datetime import datetime, timedelta

import jira as Jira
import pytz
from trilium_py.client import ETAPI

service_url = os.environ.get("TRILIUM_URL", "http://localhost:8080")
service_token = os.environ.get("TRILIUM_TOKEN", None)

Service = namedtuple("Service", ["type", "options", "connection", "cache", "update"])

jira = Service(
    "jira",
    None,
    lambda: Jira.JIRA("https://issues.redhat.com", token_auth=os.environ.get("JIRA_TOKEN")),
    [],
    lambda l: jira.cache.extend(l),
)

Ticket = namedtuple("Ticket", ["key", "summary", "url", "status", "labels", "priority", "created"])
tickets: list[Ticket] = []

triage_cutoff = (datetime.utcnow() - timedelta(days=6)).replace(tzinfo=pytz.utc)

with closing(jira.connection()) as client:
    jira.update(
        client.search_issues(
            (
                r'filter = "Node Components"'
                r" AND ((project = OCPBUGS"
                r"  OR project = RHOCPPRIO AND issueType in (Bug, Task))"
                r"  OR project = OCPNODE AND issueType = Bug)"
                r" AND status = New"
                r" AND ((labels is EMPTY OR labels not in (triaged)) OR priority in (Undefined))"
                r" ORDER BY priority DESC, key DESC"
            )
        )
    )
    jira.update(
        client.search_issues(
            (
                "project = RHOCPPRIO"
                ' AND (filter = "Node Components" OR assignee = "Jhon Honce")'
                " AND status not in (Closed)"
            )
        )
    )

    for bug in jira.cache:
        created = datetime.fromisoformat(bug.fields.created)
        if created >= triage_cutoff:
            continue

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

trilium = ETAPI(service_url, service_token)
for ticket in tickets:
    trilium.add_todo(
        f'{ticket.key} [{ticket.priority}] <a href="{ticket.url}">{ticket.summary}</a>'
    )
permalink = (
    r"https://issues.redhat.com/secure/Dashboard.jspa"
    r"?selectPageId=12345608"
    r"#SIGwKWmOqDAaNglROUEImIOqGjtpUxw8HF6BFOqSXIGgGAKIiiKmgQJB+jQlQMJUhQwQgYEeF1QlAA"
)
trilium.add_todo(f'<a href="{permalink}">Untriaged Node Bugs</a>')
