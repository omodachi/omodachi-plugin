pragma ComponentBehavior: Bound
import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Ui as OmarchyUi
import "../OmodachiModel.js" as Model

// Devices: the paired rows with a two-step inline revoke (Study 02 N-14, no
// modal dialog), and above them the pending requests as one-step confirm cards
// (N-12). A request card becomes a device row in place - there is no success
// dialog and no second window to close.
Item {
    id: root
    property QtObject service: null
    property string highlightRequestId: ""
    property string revokeTarget: ""
    signal focusRequested(Item item)
    implicitHeight: content.implicitHeight

    // CORE-2 §1: the theme's own yellow for a credential in its last week,
    // read from the colors.toml Omarchy renders; the accent when it has none.
    property color warningColor: Color.accent
    // Seconds since the epoch, refreshed with the list, for the expiry lines.
    property int nowSeconds: Math.floor(Date.now() / 1000)
    onServiceChanged: nowSeconds = Math.floor(Date.now() / 1000)
    FileView {
        id: themeColors
        path: Color.currentThemePath + "/colors.toml"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: root.warningColor = Model.themeYellow(text(), Color.accent)
    }
    Timer {
        interval: 60000
        running: root.visible
        repeat: true
        onTriggered: root.nowSeconds = Math.floor(Date.now() / 1000)
    }

    readonly property var pending: service ? service.pendingRequests : []
    // PAIR-3 §1.3: Sunshine certificate attempts waiting for a local Approve.
    readonly property var mediaApprovals: service ? service.mediaApprovals : []

    Column {
        id: content
        width: parent.width
        spacing: Style.spacing.controlGap

        // --- pending requests -------------------------------------------
        OmarchyUi.PanelSectionHeader {
            visible: root.pending.length > 0
            text: root.pending.length === 1 ? "PAIRING REQUEST" : "PAIRING REQUESTS"
        }
        Repeater {
            model: root.pending
            delegate: Column {
                id: requestCard
                required property var modelData
                width: content.width
                spacing: Style.spacing.controlGap

                Text {
                    width: parent.width
                    text: "“" + requestCard.modelData.device_name + "” wants to connect"
                    color: root.highlightRequestId === requestCard.modelData.request_id ? Color.accent : Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.subtitle
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }
                // PAIR-2: no invitation vouched for this request, so the card
                // says where it came from and which key it is about to trust.
                Text {
                    width: parent.width
                    text: Model.requestDetail(requestCard.modelData)
                    color: Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WrapAnywhere
                    textFormat: Text.PlainText
                }
                Text {
                    width: parent.width
                    text: Model.GRANT_LINE
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }
                Row {
                    spacing: Style.spacing.controlGap
                    OmarchyUi.Button {
                        text: root.service && root.service.adminBusy && root.service.adminOperation.indexOf("approve") === 0
                            ? "Approving…" : "Approve"
                        selected: true
                        focusable: true
                        enabled: !!root.service && !root.service.adminBusy
                        onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                        onClicked: root.service.approve(requestCard.modelData.request_id)
                    }
                    OmarchyUi.Button {
                        text: "Reject"
                        focusable: true
                        enabled: !!root.service && !root.service.adminBusy
                        onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                        onClicked: root.service.reject(requestCard.modelData.request_id)
                    }
                }
                Text {
                    width: parent.width
                    // PAIR-3: one sentence, always the same. Approve always
                    // asks for Remote as well; whether it landed is reported
                    // afterwards on the device's row, never guessed at here.
                    text: "Approving finishes everything: the companion credential and this host's Remote certificate, in one call. No PIN, no Sunshine page."
                    color: Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }
                OmarchyUi.PanelSeparator { }
            }
        }

        // --- streaming certificate requests ------------------------------
        // PAIR-3 §1.3. core has answered `media-pairing approve` since SPEC-B2,
        // but nothing ever drew the attempt, so a device that asked for a
        // Sunshine certificate waited 120 s and was cancelled with no trace in
        // the panel. This is that card.
        OmarchyUi.PanelSectionHeader {
            visible: root.mediaApprovals.length > 0
            text: root.mediaApprovals.length === 1 ? "STREAMING CERTIFICATE REQUEST" : "STREAMING CERTIFICATE REQUESTS"
        }
        Repeater {
            model: root.mediaApprovals
            delegate: Column {
                id: mediaCard
                required property var modelData
                width: content.width
                spacing: Style.spacing.controlGap

                Text {
                    width: parent.width
                    text: "\u201c" + mediaCard.modelData.device_id + "\u201d is asking for a streaming certificate"
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.subtitle
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }
                Text {
                    width: parent.width
                    text: mediaCard.modelData.needs_pin_resubmission
                        ? "Its one-time code was already spent. Open Remote on the device again to restart pairing."
                        : "Approve to finish Remote pairing for this device. " + mediaCard.modelData.seconds_left + "s left."
                    color: Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }
                Row {
                    spacing: Style.spacing.controlGap
                    OmarchyUi.Button {
                        visible: mediaCard.modelData.can_approve
                        text: root.service && root.service.adminBusy && root.service.adminOperation === "media_approve" ? "Approving\u2026" : "Approve"
                        selected: true
                        focusable: true
                        enabled: !!root.service && !root.service.adminBusy
                        onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                        onClicked: root.service.approveMedia({attempt_id: mediaCard.modelData.attempt_id,
                            request_id: mediaCard.modelData.request_id,
                            client_cert_sha256: mediaCard.modelData.client_cert_sha256})
                    }
                    OmarchyUi.Button {
                        text: "Cancel"
                        focusable: true
                        enabled: !!root.service && !root.service.adminBusy
                        onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                        onClicked: root.service.cancelMedia({attempt_id: mediaCard.modelData.attempt_id,
                            request_id: mediaCard.modelData.request_id,
                            client_cert_sha256: mediaCard.modelData.client_cert_sha256})
                    }
                }
                OmarchyUi.PanelSeparator { }
            }
        }

        // --- paired devices ----------------------------------------------
        OmarchyUi.PanelSectionHeader { text: "PAIRED DEVICES" }
        Text {
            width: parent.width
            visible: !root.service || !root.service.devicesLoaded || root.service.devices.length === 0
            text: root.service && root.service.devicesLoaded ? "No device credentials are registered." : "Loading devices…"
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }
        Repeater {
            model: root.service ? root.service.devices : []
            delegate: Column {
                id: deviceRow
                required property var modelData
                width: content.width
                spacing: Style.spacing.controlGap

                Text {
                    width: parent.width
                    text: deviceRow.modelData.device_id
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    wrapMode: Text.WrapAnywhere
                    textFormat: Text.PlainText
                }
                Text {
                    width: parent.width
                    // The panel's own credential is not a paired device and has
                    // no Remove button: revoking it would take away the page
                    // this row is drawn on. Core refuses it too, with
                    // `409 plugin_credential` unless `devices revoke --force`.
                    text: deviceRow.modelData.role === "plugin"
                        ? "This plugin (cannot be revoked)"
                        : (deviceRow.modelData.status === "authorized"
                            ? String(deviceRow.modelData.active_credentials) + " active credential(s)"
                            : deviceRow.modelData.status === "expired" ? "Credential expired" : "Access revoked")
                          + " · " + (root.service ? root.service.mediaStatusFor(deviceRow.modelData.device_id) : "")
                    color: Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }
                // CORE-2 §1: when this device's credential ends. Yellow inside its
                // last seven days - the device renews it by itself when it next
                // opens, so a row that stays yellow is a device that has not.
                Text {
                    readonly property var expiry: Model.deviceExpiry(deviceRow.modelData, root.nowSeconds)
                    width: parent.width
                    visible: expiry.text.length > 0
                    text: expiry.text
                    color: expiry.soon ? root.warningColor : Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }
                // PAIR-3 §1.2: the state that made Remote look unpaired for a
                // whole evening - companion granted, streaming not - said in
                // one line, with the repair next to it.
                Text {
                    width: parent.width
                    visible: !!root.service && root.service.canGrantRemote(deviceRow.modelData.device_id)
                    text: "Remote streaming is not authorized for this device."
                    color: Color.foreground
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }
                Row {
                    visible: deviceRow.modelData.revocable === true
                    spacing: Style.spacing.controlGap
                    OmarchyUi.Button {
                        visible: !!root.service && root.service.canGrantRemote(deviceRow.modelData.device_id)
                        text: root.service && root.service.adminBusy && root.service.adminOperation === "grant_remote" ? "Granting\u2026" : "Grant Remote"
                        selected: true
                        focusable: true
                        enabled: !!root.service && !root.service.adminBusy
                        onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                        onClicked: root.service.grantRemote(deviceRow.modelData.device_id,
                            root.service.grantRemoteRequestFor(deviceRow.modelData.device_id))
                    }
                    OmarchyUi.Button {
                        // Two steps, inline. The first click turns this row's
                        // button into Confirm; the second is what acts.
                        text: root.revokeTarget === deviceRow.modelData.device_id ? "Confirm" : "Remove"
                        focusable: true
                        enabled: !!root.service && !root.service.adminBusy
                        onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                        onClicked: {
                            if (root.revokeTarget === deviceRow.modelData.device_id) {
                                root.service.revokeDevice(root.revokeTarget)
                                root.revokeTarget = ""
                            } else root.revokeTarget = deviceRow.modelData.device_id
                        }
                    }
                    OmarchyUi.Button {
                        visible: root.revokeTarget === deviceRow.modelData.device_id
                        text: "Cancel"
                        focusable: true
                        onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                        onClicked: root.revokeTarget = ""
                    }
                }
                Text {
                    width: parent.width
                    visible: root.revokeTarget === deviceRow.modelData.device_id
                    text: "This device loses its companion credential and its Remote certificate. It has to be approved again next time."
                    color: Color.muted
                    font.family: Style.font.family
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                    textFormat: Text.PlainText
                }
            }
        }

        // --- PLUG-4 §3: the revoked devices, as one line -----------------
        // This page used to list every device that had ever been revoked: 32
        // dead test devices against one real one, each with no action on it.
        // They are a number and a cleanup now, and nothing when there are none.
        Row {
            visible: !!root.service && root.service.revokedHidden > 0
            spacing: Style.spacing.controlGap
            Text {
                text: root.service
                    ? String(root.service.revokedHidden) + (root.service.revokedHidden === 1
                        ? " revoked device is not shown" : " revoked devices are not shown")
                    : ""
                color: Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
                textFormat: Text.PlainText
                anchors.verticalCenter: parent.verticalCenter
            }
            OmarchyUi.Button {
                text: root.service && root.service.adminBusy && root.service.adminOperation === "purge"
                    ? "Clearing\u2026" : "Clear"
                focusable: true
                enabled: !!root.service && !root.service.adminBusy
                onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                onClicked: root.service.purgeDevices()
            }
        }
        Text {
            width: parent.width
            text: "This is the credential registry. Authorized does not prove a device is online."
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }
        Text {
            width: parent.width
            visible: !!root.service && root.service.devicesError !== ""
            text: root.service ? root.service.devicesError : ""
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
        OmarchyUi.Button {
            text: "Refresh"
            focusable: true
            onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
            onClicked: if (root.service) root.service.refreshDevices()
        }
    }
}
