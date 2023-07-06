/**
 * Mirror GitHub Gists to Trilium Note tree
 *
 * To install: 
 *   1. Create note of type `JS backend` with the following attributes:
 *      a. #gistRoot anchors the gist mirror (required)
 *      b. #gistUsername set to the GitHub username
 *   2. When the script runs it will create any missing templates and set missing attributes
 */
"use strict";

const fetch = require("node-fetch");
const process = require("process");
const sql = require("./sql");

let utc = require("dayjs/plugin/utc");
api.dayjs.extend(utc);

const gistRootNote = api.getNoteWithLabel("gistRoot");
if (!gistRootNote) {
    api.log("Info: gistRoot does not exist");
    return;
}

let gistUsername = gistRootNote.getLabelValue("gistUsername");
if (!gistUsername) {
    gistUsername =
        process.env.SUDO_USER ||
        process.env.C9_USER ||
        process.env.LOGNAME ||
        process.env.USER ||
        process.env.LNAME ||
        process.env.USERNAME;
}
if (!gistUsername) {
    throw new Error("gistUsername not set and unable to determine user name");
}

verifyTemplate(api.currentNote, gistRootNote);

// TODO: Add support for authentication
// TODO: Should private gist be imported as protected?
fetch(`https://api.github.com/users/${gistUsername}/gists`, {
    headers: {
        Accept: "application/vnd.github+json",
    },
})
    .then(async (response) => {
        if (!response.ok) {
            api.log(`Error: Listing gists failed with ${response.status}: ${response.url}`);
            return;
        }
        return await response.json();
    })
    .then((gists) => {
        for (const gist of gists) {
            // TODO: Search should be anchored at #gistRoot
            const note = api.searchForNote(`note.title="${gist.description}"`);
            if (note) {
                updateNote(note, gist);
            } else {
                newNote(gistRootNote, gist);
            }
        }
    })
    .then(() => {
        gistRootNote.setLabel("lastUpdated", api.dayjs.utc().format());
    })
    .catch((err) => {
        api.log(`Error: Failed fetching gists, ${err}`);
    });

/**
 * Add given gist to existing root note including attached files
 *
 * @param {BNote} parent BNote to add new note to
 * @param {Object} gist GitHub Gist object
 */
function newNote(parent, gist) {
    const lastUpdated = api.dayjs.utc();
    const gistUpdatedAt = api.dayjs.utc(gist.updated_at);

    const note = api.transactional(() => {
        const note = api.createNewNote({
            parentNoteId: parent.noteId,
            title: gist.description,
            content: "",
            type: "text",
            isProtected: false,
        }).note;
        // The labels #gistId and #gistUrl are promoted in the default template
        note.setLabel("gistId", gist.id);
        note.setLabel("gistUrl", gist.url);
        note.setLabel("iconClass", "bx bxl-github");
        note.setLabel("lastUpdated", lastUpdated.utc().format());
        note.setLabel("gistUpdatedAt", gistUpdatedAt.utc().format());
        note.setLabel("readOnly");
        note.setRelation("isChildOf", parent.noteId);
        return note;
    });

    for (const file of Object.values(gist.files)) {
        fetch(file.raw_url, {
            headers: {
                Accept: "application/vnd.github.raw",
            },
        })
            .then(async (response) => {
                if (!response.ok) {
                    throw new Error(
                        `Failed to fetch file with ${response.status}, ${response.url}`
                    );
                }
                return await response.text();
            })
            .then((content) => {
                api.transactional(() => {
                    const n = createFileNote(note.noteId, file, content);
                    // n.setLabel('readOnly'); TODO why does this break syntax highlighting?
                    n.setRelation("isChildOf", note.noteId);
                });
            })
            .catch((err) => {
                api.log(`Error: fetching ${file.filename}, ${err}`);
            });
    }
}

/**
 * Update existing note with latest gist data, new notes created if needed
 *
 * @param {BNote} note Trilium note to update
 * @param {Object} gist GitHub Gist object holding updated data
 */
function updateNote(note, gist) {
    let lastUpdated = api.dayjs.utc(note.getLabelValue("lastUpdated"));
    if (!lastUpdated.isValid()) {
        lastUpdated = api.dayjs.utc("1970-01-01T00:00:00Z");
    }
    const gistUpdatedAt = api.dayjs.utc(gist.updated_at);

    if (gistUpdatedAt.isAfter(lastUpdated)) {
        for (const file of Object.values(gist.files)) {
            // TODO: search should be anchored at note
            const childNote = api.searchForNote(`note.title="${file.filename}"`);

            fetch(file.raw_url, {
                headers: {
                    Accept: "application/vnd.github.raw",
                },
            })
                .then(async (response) => {
                    if (!response.ok) {
                        throw new Error(
                            `Failed to fetch file with ${response.status}, ${response.url}`
                        );
                    }
                    return await response.text();
                })
                .then((content) => {
                    if (childNote) {
                        childNote.setContent(content);
                    } else {
                        api.transactional(() => {
                            const n = createFileNote(note.noteId, file, content);
                            n.setRelation("isChildOf", note.noteId);
                        });
                    }
                })
                .catch((err) => {
                    api.log(`Error: fetching ${file.filename}, ${err}`);
                });
        }
    }
}

// TODO: How to call the mimeTypesService.getMimeTypes()from here?
const langDetails = [
    { name: "Go", mime: "text/x-go", icon: "bx bxl-go-lang" },
    { name: "Markdown", mime: "text/x-markdown", icon: "bx bxs-file-md" },
    { name: "Python", mime: "text/x-python", icon: "bx bxl-python" },
    { name: "Ruby", mime: "text/x-ruby", icon: "bx bx-code-alt" },
    { name: "Shell", mime: "text/x-sh", icon: "bx bx-terminal" },
    { name: "Text", mime: "text/plain", icon: "bx bxs-file-txt" },
    { name: "TypeScript", mime: "text/typescript", icon: "bx bxl-typescript" },
    { name: "JavaScript", mime: "text/javascript", icon: "bx bxl-javascript" },
];

/**
 * Transform GitHub Gist language to Trilium mime type
 *
 * @param {string} lang GitHub Gist language type
 * @returns trilium mime type
 */
function transformMimeType(lang) {
    const props = langDetails.find((obj) => obj.name === lang);
    return props ? props.mime : lang;
}

/**
 * Map GitHub Gist language to boxicon icon class
 *
 * @param {string} lang GitHub Gist language type
 * @returns boxicon icon class
 *
 * @see https://boxicons.com/
 */
function mapIcon(lang) {
    const props = langDetails.find((obj) => obj.name === lang);
    return props ? props.icon : "bx bx-file-blank";
}

/**
 * Create new note with given file as content
 *
 * @param {string} parentId Id of parent note
 * @param {Object} file gist attachment data
 * @param {string} content content of file
 * @returns BNote representing new file
 */
function createFileNote(parentId, file, content) {
    // TODO: Could this be refactored to use importSingleFile()?
    const note = api.createNewNote({
        parentNoteId: parentId,
        title: file.filename,
        content: content,
        type: "code",
        mime: transformMimeType(file.language),
        isProtected: false,
    }).note;
    note.setLabel("iconClass", mapIcon(file.language));
    return note;
}

/**
 * Verify template note exists and #gistRootNote defines relationship ~child:template
 *
 * Note:
 * 1. If #gistRoot has a child note, it will be used as ~template, otherwise a 
 *    default template note will be created
 *    a. the new template will be initialized with the labels #readOnly and #iconClass,
 *       and the promoted labels: #gistId and #gistUrl
 * 2.Verify #gistRoot contains the relation ~child:template
 *
 * @param {BNote} scriptNote note holding this script
 * @param {BNote} rootNote note anchoring the gist tree
 * @returns BNote template note
 */
function verifyTemplate(scriptNote, rootNote) {
    let template;
    if (scriptNote.hasChildren()) {
        template = scriptNote?.getChildNotes()[0];
    } else {
        api.transactional(() => {
            template = api.createNewNote({
                parentNoteId: scriptNote.noteId,
                title: "template",
                content: "",
                type: "text",
                isProtected: false,
            }).note;
            template.setLabel("label:gistId", "promoted,single,text");
            template.setLabel("label:gistUrl", "promoted,single,url");
            template.setLabel("iconClass", "bx bxl-github");
            template.setLabel("readOnly");
        });
    }

    if (!rootNote.hasRelation("child:template")) {
        rootNote.setRelation("child:template", template.noteId);
    }

    if (!rootNote.hasLabel("iconClass")) {
        rootNote.setLabel("iconClass", "bx bxl-github");
    }

    if (!rootNote.hasLabel("sorted")) {
        rootNote.setLabel("sorted", "gistUpdatedAt");
    }
    return template;
}
