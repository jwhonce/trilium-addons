/*
 * This defines a custom widget which displays Jira labels of current task note.
 */
const TPL = `<div style="padding: 10px; border-top: 1px solid var(--main-border-color); contain: none;">
    &radic; <span class="jira-updated"></span>
    &nbsp; <span class="jira-assignee" style="color: rgb(112 175 164 / 60%)"></span>

    &nbsp; &#10098; <span class="jira-status" style="color:red"></span>
    &#124; <span class="jira-priority" style="color:green"></span>
    &#10099; &nbsp; <span class="jira-labels" style="color:violet"></span>
</div>`;

class JiraWidget extends api.NoteContextAwareWidget {
    get position() { return 100; } // higher value means position towards the bottom/right

    get parentWidget() { return 'center-pane'; }

    isEnabled() {
        return super.isEnabled()
            && this.note.type === 'text'
            && this.note.hasLabel('jiraKey');
    }

    doRender() {
        this.$widget = $(TPL);
        this.$jiraAssignee = this.$widget.find('.jira-assignee');
        this.$jiraLabels = this.$widget.find('.jira-labels');
        this.$jiraPriority = this.$widget.find('.jira-priority');
        this.$jiraStatus = this.$widget.find('.jira-status');
        this.$jiraUpdated = this.$widget.find('.jira-updated');
        return this.$widget;
    }

    async refreshWithNote(note) {
        this.$jiraAssignee.text(note.getAttributeValue("label", "jiraAssignee"));
        this.$jiraLabels.text(note.getAttributeValue("label", "jiraLabels"));
        this.$jiraPriority.text(note.getAttributeValue("label", "jiraPriority"));
        this.$jiraStatus.text(note.getAttributeValue("label", "jiraStatus"));
        this.$jiraUpdated.text(note.getAttributeValue("label", "jiraUpdated"));
    }

    async entitiesReloadedEvent({ loadResults }) {
        if (loadResults.isNoteContentReloaded(this.noteId)) {
            this.refresh();
        }
    }
}

module.exports = new JiraWidget();
