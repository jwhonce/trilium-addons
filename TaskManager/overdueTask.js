/**
 * Clone overdue tasks from previous day(s) to today
 * 
 * Note(s):
 * 1. As written this script may clone Demo tasks...
 * 2. I use `#run=hourly #runAtHour=0400 #runOnInstance=sync-server`
 *    to run my instance of this script daily
 */
"use strict";

const scriptNote = api.currentNote;

const now = new Date();
const dayOfWeek = now.getDay();

// Skip weekends
if (dayOfWeek === 0 || dayOfWeek === 6) {
    api.log(`${scriptNote.title}: Info: Skip weekend`);
    return;
}

const taskTodoRoot = api.getNoteWithLabel("taskTodoRoot");
if (!taskTodoRoot?.hasChildren()) {
    api.log(`${scriptNote.title}: Info: No tasks found`);
    return;
}

const overdueTasks = api.searchForNotes("#task AND #!doneDate AND #todoDate < TODAY",
    { ancestorNoteId: taskTodoRoot.noteId }
);

const today = api.getTodayNote();
overdueTasks.forEach(async (task) => await api.toggleNoteInParent(true, task.noteId, today.noteId, "TODO"));
