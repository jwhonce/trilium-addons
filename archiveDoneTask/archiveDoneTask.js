/**
 * Archive Task Manager Done tasks older then archivedAgeInDays (default: 30)
 *
 * Note(s):
 * 1. As written this script may archive Demo tasks...
 * 2. attribute #archiveAgeInDays is maintained on the script note to override the default
 * 2. attribute #lastUpdated is maintained on the script note to verify script runs daily
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
    lastUpdated = api.dayjs.utc("1970-01-01T00:00:00Z");
}
if (lastUpdated.isSameOrAfter(api.dayjs.utc(), "day")) {
    log(`Info: Script already run today @ ${lastUpdated.utc().format()}`);
    return;
}

const archiveAge = scriptNote.getLabelValue("archivedAgeInDays") ?? "30";
const dateToArchive = api.dayjs().subtract(archiveAge, "day");

// TODO: Is there a method to anchor a search at taskDoneRoot?
// Set 'archived' attribute on aged finished tasks
for (const child of taskDoneRoot.getChildNotes()) {
    if (!child.hasLabel("task")) {
        continue;
    }

    const doneDate = api.dayjs(child.getLabelValue("doneDate"));
    if (doneDate?.isAfter(dateToArchive, "day")) {
        continue;
    }
    child.toggleLabel(true, "archived");
}
scriptNote.setLabel("lastUpdated", api.dayjs.utc().format());
