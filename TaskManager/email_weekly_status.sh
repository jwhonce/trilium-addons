#!/usr/bin/bash

link='https://docs.google.com/document/d/1dsfo-VEQkMbUSa0c_YU8pTbgblhNJ1dvmvqc_YiEH0w/edit'
title='Email Node Life Cycle Weekly Status Updates'

$HOME/Projects/trilium-addons/TaskManager/task.py add "$title" \
    --due=$(date -d "today" +%Y-%m-%d) \
    --location=work \
    --tag=process \
    --message="<p><a href=\"$link\">Google Doc</a></p><p>Query: project = OCPNODE AND issueFunction in epicsOf(\"updated > -2d\") AND status not in (Closed) ORDER BY key ASC</p>"
