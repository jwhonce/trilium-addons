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
    * TRILIUM_API_TOKEN should be set to the API token for the Trilium Notes server.
        If not set, the default is None.
        
TODO: Why does the trilium UI lag showing the updated attributes?
"""
import argparse
import os
import sys
from datetime import datetime

from trilium_py.client import ETAPI

service_url = os.environ.get("TRILIUM_URL", "http://localhost:8080")
service_token = os.environ.get("TRILIUM_API_TOKEN", None)

parser = argparse.ArgumentParser(description="Publish File to Trilium Notes")
parser.add_argument(
    "filename",
    help="File to publish to Trilium Notes",
)
parser.add_argument(
    "-s",
    "--server",
    dest="url",
    help="Your Trilium sync server URL",
    default=service_url,
)
parser.add_argument(
    "-t",
    "--token",
    help="Trilium API Token",
    default=service_token,
)

args = parser.parse_args(sys.argv[1:])
trilium = ETAPI(args.url, args.token)

title = os.path.basename(args.filename)
response = trilium.search_note(f'note.title="{title}"')
if len(response["results"]) == 0:
    print(f"Note '{title}' not found", file=sys.stderr)
    exit(1)
elif len(response["results"]) > 1:
    print(f"More than 1 matching note '{title}' found", file=sys.stderr)
    exit(1)
note = response["results"][0]

# Determine the last time this file was uploaded
uploadedDate = None
for a in note["attributes"]:
    if a["name"] == "lastUploadedDate":
        uploadedDate = a["attributeId"]
        break

with open(args.filename, "r") as f:
    if not trilium.update_note_content(note["noteId"], f.read()):
        print(f"Failed to update note {title}", file=sys.stderr)
        exit(1)

if uploadedDate is None:
    response = trilium.create_attribute(
        attributeId=None,
        noteId=note["noteId"],
        type="label",
        name="lastUploadedDate",
        value=note["utcDateModified"],
        isInheritable=False,
    )
else:
    response = trilium.patch_attribute(uploadedDate, note["utcDateModified"])

exit(0)
