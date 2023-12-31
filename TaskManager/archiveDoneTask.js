/**
 * Archive Task Manager Done tasks older then archivedAgeInDays (default: 30)
 *
 * Note(s):
 * 1. As written this script may archive Demo tasks...
 * 2. #archiveAgeInDays is maintained on the script note to override the default
 * 3. #lastUpdated is maintained on the script note to verify script runs daily
 * 4. I use #run=daily to run my instance of this script daily
 */
"use strict";

let utc = require("dayjs/plugin/utc");
let isSameOrAfter = require("dayjs/plugin/isSameOrAfter");
api.dayjs.extend(utc);
api.dayjs.extend(isSameOrAfter);

const scriptNote = api.currentNote;

function log(msg) {
    api.log(`${scriptNote.title}: ${msg}`);
}

const taskDoneRoot = api.getNoteWithLabel("taskDoneRoot");
if (!taskDoneRoot?.hasChildren()) {
    log("Warning: Task Manager not configured");
    return;
}

let lastUpdated = api.dayjs.utc(scriptNote.getLabelValue("lastUpdated"));
if (!lastUpdated.isValid()) {
    // Need to start sometime...
    lastUpdated = api.dayjs.utc("1970-01-01T00:00:00Z");
}
if (lastUpdated.isSameOrAfter(api.dayjs.utc(), "day")) {
    log(`Info: Script already run today @ ${lastUpdated.utc().format()}`);
    return;
}

const archiveAge = scriptNote.getLabelValue("archivedAgeInDays") ?? "30";
const agedTasks = api.searchForNotes(`#task AND #doneDate < TODAY-${archiveAge}`,
    { ancestorNoteId: taskDoneRoot.noteId }
);
agedTasks.forEach(async (task) => await task.toggleLabel(true, "archived"));

scriptNote.setLabel("lastUpdated", api.dayjs.utc().format());

