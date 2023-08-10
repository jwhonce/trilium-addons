# trilium-addons

Repository contains scrips that I wrote to enhance trilium-notes for my use.
I published them in hopes they help others and to receive feedback as I learn JavaScript.

## TaskManager/archiveDoneTask.js

trilium background JavaScript that marks any #task as #archived if completed more than #archivedAgeInDays ago.

## gistMirror/gistMirror.js

trilium background JavaScript that mirrors #gistUsername 's GitHub Gists to a subtree in trilium-notes anchored at #gistRoot.
Use #run to schedule how often to update mirror.

## pushToNote/pushToNote.py

An ETAPI script that will publish a file's content to a trilium sync server where note.title matches the file's name.
If the note cannot be found an exit code of 1 is returned.

## TaskManager/overdueTask.js

trilium background JavaScript that clones any overdue #task to current Day's note.
Use #run to schedule how often and when to run.

## TaskManager/tm.py

Python script using [trilium-alchemy](https://github.com/mm21/trilium-alchemy) and [Typer](https://typer.tiangolo.com/) to implement a CLI to curate tasks in TaskManager.
