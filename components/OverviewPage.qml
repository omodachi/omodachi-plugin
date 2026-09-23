pragma ComponentBehavior: Bound
import QtQuick
import qs.Commons
import qs.Ui as OmarchyUi
import "../OmodachiModel.js" as Model

// Study 02 §10 Overview answers four questions and stops: who this machine is,
// whether Host is there, whether anyone is connected right now, and with what.
Item {
    id: root
    property QtObject service: null
    signal focusRequested(Item item)
    readonly property var snapshot: service ? service.snapshot : ({})
    readonly property string connectionState: service ? service.connectionState : "setup_required"
    implicitHeight: content.implicitHeight

    Column {
        id: content
        width: parent.width
        spacing: Style.spacing.controlGap

        OmarchyUi.PanelSectionHeader { text: "HOST" }

        Repeater {
            model: Model.overviewRows(root.snapshot, root.connectionState)
            delegate: Row {
                required property var modelData
                width: content.width
                spacing: Style.spacing.controlGap
                Text {
                    width: parent.width * 0.36
                    text: modelData.label
                    color: Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    textFormat: Text.PlainText
                }
                Text {
                    width: parent.width * 0.64 - parent.spacing
                    text: modelData.value
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    textFormat: Text.PlainText
                    wrapMode: Text.Wrap
                }
            }
        }

        OmarchyUi.PanelSeparator { }

        Text {
            width: parent.width
            text: Model.overviewHint(root.connectionState, root.snapshot,
                                     root.service ? root.service.devices : [],
                                     root.service ? root.service.lastSummon : null)
            visible: text !== ""
            color: Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }

        Text {
            width: parent.width
            visible: !!root.service && root.service.lastError !== ""
            text: root.service ? root.service.lastError.replace(/_/g, " ") : ""
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
    }
}
