pragma ComponentBehavior: Bound
import QtQuick
import qs.Commons
import qs.Ui as OmarchyUi

Item {
    id: root
    property string label: ""
    property string description: ""
    property string value: ""
    property var options: []
    signal selectedValue(string value)
    signal focusRequested(Item item)
    implicitHeight: content.implicitHeight
    Column {
        id: content
        width: parent.width
        spacing: Style.spacing.controlGap
        Text {
            width: parent.width
            text: root.label
            color: Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.body
            font.bold: true
            textFormat: Text.PlainText
        }
        Flow {
            width: parent.width
            spacing: Style.spacing.controlGap
            Repeater {
                model: root.options
                delegate: OmarchyUi.Button {
                    required property var modelData
                    text: modelData.label
                    selected: root.value === modelData.value
                    focusable: true
                    onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                    onClicked: root.selectedValue(modelData.value)
                }
            }
        }
        Text {
            width: parent.width
            visible: root.description !== ""
            text: root.description
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
    }
}
