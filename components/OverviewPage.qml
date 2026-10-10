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
    // REMOTE-STOP-1: the live session this page can end, or "".
    readonly property string sessionId: Model.liveSessionId(snapshot)
    readonly property bool ending: !!service && service.adminOperation === "remote_stop"
    readonly property var tailnet: service && service.tailnet ? service.tailnet
        : ({running: false, dns_name: "", short_name: "", state: "", warnings: []})
    // TAIL-3b: the one paragraph a computer without a running Tailscale gets.
    readonly property var pairText: Model.pairText(tailnet)
    readonly property var odomo: service && service.odomo ? service.odomo : ({known: false, on: false, url: "", text: "", command: ""})
    property bool endArmed: false
    onSessionIdChanged: endArmed = false
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

        // TAIL-2 P1-1 / P1-2 / P1-4. Only when Tailscale runs here. The red
        // ones are the two that change what Approve and Remove mean, or break
        // the LAN; the fix for a swallowed LAN is shown, never run.
        // TAIL-3b: the name itself moved to the pair block below.
        OmarchyUi.PanelSeparator { visible: root.tailnet.running || root.tailnet.state === "signed_out" }
        OmarchyUi.PanelSectionHeader {
            visible: root.tailnet.running || root.tailnet.state === "signed_out"
            text: "TAILSCALE"
        }
        // TAIL-3b P02: installed, not signed in. One paragraph, no button: the
        // panel never runs `tailscale up` for anyone.
        Text {
            width: content.width
            visible: root.tailnet.state === "signed_out"
            text: root.pairText.note
            color: Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.body
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
        Repeater {
            model: root.tailnet.warnings
            delegate: Text {
                required property var modelData
                width: content.width
                text: modelData.text
                color: modelData.severe ? Color.error : Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
            }
        }

        // TAIL-3b P03: no Tailscale here. One line, no header.
        OmarchyUi.PanelSeparator { visible: root.tailnet.state === "absent" }
        Text {
            width: content.width
            visible: root.tailnet.state === "absent"
            text: root.pairText.note
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }

        // TAIL-3b P01: the name a phone pastes, while Tailscale runs here.
        OmarchyUi.PanelSeparator { visible: pairBlock.visible }
        PairPhoneBlock {
            id: pairBlock
            width: content.width
            visible: Model.showPairBlock(root.tailnet)
            service: root.service
            onFocusRequested: function(item) { root.focusRequested(item) }
        }

        // LITE-1b. Odomo, the web app: the address to open on a phone (it is the
        // computer's own page, reached through `tailscale serve`), with a copy
        // button - or why there is none and the command that gives it one.
        OmarchyUi.PanelSeparator { visible: root.odomo.known }
        OmarchyUi.PanelSectionHeader {
            visible: root.odomo.known
            text: Model.ODOMO_HEADER
        }
        Row {
            visible: root.odomo.on
            width: content.width
            spacing: Style.spacing.controlGap
            Text {
                width: parent.width - copyButton.width - parent.spacing
                anchors.verticalCenter: parent.verticalCenter
                text: root.odomo.url
                color: Color.foreground
                font.family: Style.font.family
                font.pixelSize: Style.font.body
                wrapMode: Text.WrapAnywhere
                textFormat: Text.PlainText
            }
            OmarchyUi.Button {
                id: copyButton
                text: root.service && root.service.odomoCopied ? "Copied" : "Copy"
                focusable: true
                onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                onClicked: root.service.copyOdomoUrl()
            }
        }
        // LITE-1d: how many phones it reaches, in one line.
        Text {
            width: content.width
            visible: root.odomo.on && text !== ""
            text: Model.odomoPushLine(root.service ? root.service.devices : [], !!root.service && root.service.devicesLoaded)
            color: Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
        Text {
            width: content.width
            visible: root.odomo.known
            text: root.odomo.text + (root.odomo.command ? "\n    " + root.odomo.command : "")
            color: root.odomo.on ? Color.muted : Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }

        // REMOTE-STOP-1. The person at this computer can always end a Remote
        // session, whoever's it is - a phone whose own panel will not open
        // included. Two steps, inline, like Remove on Devices (Study 02 N-14).
        Row {
            visible: root.sessionId !== ""
            spacing: Style.spacing.controlGap
            OmarchyUi.Button {
                id: endButton
                text: root.ending ? "Ending\u2026" : root.endArmed ? "Confirm" : "End Remote session"
                selected: root.endArmed
                focusable: true
                enabled: !!root.service && !root.service.adminBusy
                onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                onClicked: {
                    if (root.endArmed) {
                        root.endArmed = false
                        root.service.endRemote(root.sessionId)
                    } else root.endArmed = true
                }
            }
            OmarchyUi.Button {
                visible: root.endArmed
                text: "Cancel"
                focusable: true
                onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                onClicked: root.endArmed = false
            }
        }
        Text {
            width: parent.width
            visible: root.sessionId !== "" && root.endArmed
            text: "Ends the session on the device holding it. This computer's screens, workspaces, bar, keyboard and mouse go back to how they were."
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
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
