#!/usr/bin/bash

link='https://docs.google.com/document/d/1U0fZxiQ059l6JAP2ywPWqXe8rB0wHXWmn_vsvbAeBqM/edit'
title='Update MCO / Container Tools / CoreOS Rollup'

$HOME/Projects/trilium-addons/TaskManager/task.py add "$title" \
    --due=$(date -d "today" +%Y-%m-%d) \
    --location=work \
    --tag=process \
    --message="<p><a href=\"$link\">Google Doc</a></p><p><a class=\"reference-link\" href=\"#root/PorP86rPHgQp/wsf3TDLmbeOo\" data-note-path=\"root/PorP86rPHgQp/wsf3TDLmbeOo\">Active Epics</a></p"
