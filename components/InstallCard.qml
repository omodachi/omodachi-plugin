pragma ComponentBehavior: Bound
import QtQuick
import qs.Commons
import qs.Ui as OmarchyUi
import "../OmodachiModel.js" as Model

// Study 02 §10, the no-Host artboard: one sentence, one button, no page
// switcher and no JSON error. This is the whole panel until Host answers.
Item {
    id: root
    property QtObject service: null
    signal focusRequested(Item item)
    readonly property string connectionState: service ? service.connectionState : "setup_required"
    implicitHeight: content.implicitHeight

    Column {
        id: content
        width: parent.width
        spacing: Style.spacing.controlGap

        OmarchyUi.PanelSectionHeader { text: "OMODACHI HOST" }
        Text {
            width: parent.width
            text: root.connectionState === "loading"
                ? "Looking for Omodachi Host…"
                : "This computer does not have Omodachi Host running."
            color: Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.subtitle
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
        Text {
            width: parent.width
            text: "The plugin is installed, but it needs the host service to supply the menu, keybindings, the extended screen and the agent."
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }
        OmarchyUi.PanelSeparator { }
        Row {
            spacing: Style.spacing.controlGap
            OmarchyUi.Button {
                text: "Install…"
                selected: true
                focusable: true
                onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                onClicked: if (root.service) root.service.installHost()
            }
            OmarchyUi.Button {
                text: "Start"
                visible: !!root.service && root.service.hostUnitState !== "active" && root.service.hostUnitState !== "unknown"
                enabled: !!root.service && !root.service.hostUnitBusy
                focusable: true
                onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                onClicked: root.service.hostUnitAction("start")
            }
            OmarchyUi.Button {
                text: "Reconnect"
                focusable: true
                onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                onClicked: if (root.service) root.service.reconnect()
            }
        }
        Text {
            width: parent.width
            text: "A terminal opens and runs the installer, so every step is visible. The plugin reconnects on its own afterwards — there is nothing to come back here for."
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }
        // INSTALL-1: which step the installer is on, and which one failed.
        Text {
            width: parent.width
            visible: !!root.service && root.service.installStage !== ""
            text: root.service ? Model.installLine(root.service.installStage,
                                                   root.service.installMessage,
                                                   root.service.installDetail) : ""
            color: (!!root.service && root.service.installFailed) ? Color.urgent : Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
        Text {
            width: parent.width
            visible: root.connectionState !== "loading" && root.connectionState !== "setup_required"
            text: Model.connectionHelp(root.connectionState)
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
    }
}
