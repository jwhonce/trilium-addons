/**
 * Clone overdue tasks from previous day(s) to today
 *
 * Note(s):
 * 1. As written this script may clone Demo tasks...
 * 2. I use #run=hourly #runAtHour=4 to run my instance of this script daily
 */
"use strict";

const utc = require("dayjs/plugin/utc");
api.dayjs.extend(utc)

const now = new Date();
const dayOfWeek = now.getDay();

// Skip weekends
if (dayOfWeek === 0 || dayOfWeek === 6) {
    api.log("Info: Skipping weekend");
    return;
}

const taskTodoRoot = api.getNoteWithLabel("taskTodoRoot");
if (!taskTodoRoot?.hasChildren()) {
    api.log("Info: No existing tasks found");
    return;
}

const overdueTasks = api.searchForNotes("#task AND #todoDate < TODAY AND #doneDate < TODAY",
    { ancestorNoteId: taskTodoRoot.noteId }
);

const today = api.getTodayNote();
overdueTasks.forEach(async (task) => await api.toggleNoteInParent(true, task.noteId, today.noteId, "TODO"));

const scriptNote = api.currentNote;
scriptNote.setLabel("lastUpdated", api.dayjs.utc().format());
