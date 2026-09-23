pragma ComponentBehavior: Bound
import QtQuick
import qs.Commons
import qs.Ui as OmarchyUi
import "../OmodachiModel.js" as Model

// The collapsed Host section of Settings. Three fixed-argv systemctl verbs
// against this user's own unit, plus the installer, which always runs in a
// visible terminal so every step stays readable.
Column {
    id: root
    property QtObject service: null
    signal focusRequested(Item item)
    spacing: Style.spacing.controlGap

    onVisibleChanged: if (visible && service) service.refreshHostUnit()

    Text {
        width: parent.width
        text: root.service && root.service.hostUnitState === "active"
            ? "Host is running."
            : "Host is not running on this computer."
        color: Color.foreground
        font.family: Style.font.family
        font.pixelSize: Style.font.bodySmall
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
    }
    Row {
        spacing: Style.spacing.controlGap
        OmarchyUi.Button {
            text: "Start"
            visible: !!root.service && root.service.hostUnitState !== "active"
            enabled: !!root.service && !root.service.hostUnitBusy
            focusable: true
            onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
            onClicked: root.service.hostUnitAction("start")
        }
        OmarchyUi.Button {
            text: "Stop"
            visible: !!root.service && root.service.hostUnitState === "active"
            enabled: !!root.service && !root.service.hostUnitBusy
            focusable: true
            onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
            onClicked: root.service.hostUnitAction("stop")
        }
        OmarchyUi.Button {
            text: "Restart"
            visible: !!root.service && root.service.hostUnitState === "active"
            enabled: !!root.service && !root.service.hostUnitBusy
            focusable: true
            onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
            onClicked: root.service.hostUnitAction("restart")
        }
        OmarchyUi.Button {
            text: "Install / Update…"
            focusable: true
            onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
            onClicked: if (root.service) root.service.installHost()
        }
        OmarchyUi.Button {
            text: "Refresh"
            enabled: !!root.service && !root.service.hostUnitBusy
            focusable: true
            onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
            onClicked: if (root.service) root.service.refreshHostUnit()
        }
    }
    Text {
        width: parent.width
        text: "Install / Update opens a terminal and installs Omodachi Host from " +
              (root.service ? root.service.installSource : "") + ". Every step stays visible."
        color: Color.muted
        font.family: Style.font.family
        font.pixelSize: Style.font.bodySmall
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
    }
    // INSTALL-1: the same stage the terminal is on, in the panel that started
    // it - so a user who moved the window away still knows what is happening,
    // and a failure names itself here instead of only scrolling past there.
    Text {
        width: parent.width
        visible: !!root.service && root.service.installStage !== ""
        text: root.service ? Model.installLine(root.service.installStage,
                                               root.service.installMessage,
                                               root.service.installDetail) : ""
        color: (!!root.service && root.service.installFailed) ? Color.urgent : Color.muted
        font.family: Style.font.family
        font.pixelSize: Style.font.bodySmall
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
    }
    Text {
        width: parent.width
        visible: !!root.service && root.service.hostUnitMessage !== ""
        text: root.service ? root.service.hostUnitMessage : ""
        color: Color.muted
        font.family: Style.font.family
        font.pixelSize: Style.font.bodySmall
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
    }
}
