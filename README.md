# trilium-addons

Repository contains scrips that I wrote to enhance trilium-notes for my use.
I published them in hopes they help others and to feedback as I learn JavaScript.

## archiveDoneTask/archiveDoneTask.js

trilium background JavaScript that marks any #task as #archived older then #archivedAgeInDays.

## gistMirror/gistMirror.js

trilium background JavaScript that mirrors #gistUsername 's GitHub Gists to a subtree in trilium-notes anchored at #gistRoot.
Use #run to schedule how often to update mirror.

## pushToNote/pushToNote.py

An ETAPI script that will publish a file's content to a trilium sync server where note.title matches the file's name. If the note
cannot be found an exit code of 1 is returned.
