pragma ComponentBehavior: Bound
import QtQuick
import qs.Commons
import qs.Ui as OmarchyUi
import "../OmodachiModel.js" as Model

// TAIL-3b. The name a phone needs, where the person at this computer can read
// it: Overview while Tailscale runs here, Devices until a phone or tablet is
// paired. Copy puts it on this computer's clipboard (for Taildrop, LocalSend
// or a message to yourself); the point is that the name can be read. The page
// decides when the block is shown; every string comes from the model.
Column {
    id: root
    property QtObject service: null
    readonly property var tailnet: service && service.tailnet ? service.tailnet
        : ({running: false, dns_name: "", short_name: "", state: "", warnings: []})
    readonly property var copyText: Model.pairText(tailnet)
    signal focusRequested(Item item)
    spacing: Style.spacing.controlGap

    OmarchyUi.PanelSectionHeader { text: root.copyText.header }
    Text {
        width: root.width
        text: root.copyText.nameLabel
        color: Color.muted
        font.family: Style.font.family
        font.pixelSize: Style.font.bodySmall
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
    }
    Text {
        width: root.width
        text: root.tailnet.dns_name
        color: Color.foreground
        font.family: Style.font.family
        font.pixelSize: Style.font.subtitle
        wrapMode: Text.WrapAnywhere
        textFormat: Text.PlainText
    }
    Row {
        spacing: Style.spacing.controlGap
        OmarchyUi.Button {
            text: root.service && root.service.tailnetNameCopied ? root.copyText.copied : root.copyText.copy
            focusable: true
            onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
            onClicked: root.service.copyTailnetName()
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            visible: root.copyText.short !== ""
            text: root.copyText.short
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            textFormat: Text.PlainText
        }
    }
    Text {
        width: root.width
        text: root.copyText.how
        color: Color.foreground
        font.family: Style.font.family
        font.pixelSize: Style.font.body
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
    }
}
