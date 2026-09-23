pragma ComponentBehavior: Bound
import QtQuick
import qs.Commons
import qs.Ui as OmarchyUi

// Study 02 N-15: only settings with a real consumer.
//
// Host-side, that is exactly what `omodachi-host preferences` stores:
// allow_dynamic_resolution, quality, host_audio_playback. Remote's backend,
// placement and takeover bar edge are arguments of a single `remote start`
// call, not stored defaults, so they are not offered here as if they were.
//
// Panel-side, the two UI preferences are written to this widget's own entry in
// shell.json through the official inline settings API, so `omarchy bar set`
// and the official settings UI see the same values.
Item {
    id: root
    property QtObject service: null
    property bool setupExpanded: false
    readonly property var preferences: service && service.hostPreferencesReady ? service.hostPreferences : null
    readonly property bool hostReady: !!preferences
    readonly property bool editable: hostReady && !service.hostPreferencesBusy
    signal setupRequested(bool expanded)
    signal focusRequested(Item item)
    implicitHeight: content.implicitHeight

    Column {
        id: content
        width: parent.width
        spacing: Style.spacing.controlGap

        OmarchyUi.PanelSectionHeader { text: "REMOTE" }
        Text {
            width: parent.width
            visible: !root.hostReady
            text: "Connect to the host service to load its Remote defaults. The panel preferences below are always available."
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }
        Column {
            width: parent.width
            visible: root.hostReady
            spacing: Style.spacing.controlGap

            OmarchyUi.Toggle {
                width: parent.width
                label: "Dynamic resolution"
                description: "Let Remote change this computer's output while a session runs. Off keeps the stream running at whatever it already is."
                checked: root.hostReady && root.preferences.values.allow_dynamic_resolution
                enabled: root.editable
                onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                onClicked: root.service.saveHostPreference("allow_dynamic_resolution", !checked)
            }
            PreferenceChoices {
                width: parent.width
                label: "Default quality"
                value: root.hostReady ? root.preferences.values.quality : ""
                enabled: root.editable && root.preferences.runtime.profile_defaults
                options: [{value: "balanced", label: "Balanced"}, {value: "quality", label: "Sharper"}, {value: "performance", label: "Performance"}]
                description: root.hostReady
                    ? "FPS and bitrate for a device that follows this computer: " + root.preferences.profile.fps + " fps · "
                      + root.preferences.profile.bitrate_kbps + " kbps. A device can pick its own in the app's Settings; Remote still chooses the pixels."
                    : ""
                onFocusRequested: function(item) { root.focusRequested(item) }
                onSelectedValue: function(value) { root.service.saveHostPreference("quality", value) }
            }
            OmarchyUi.Toggle {
                width: parent.width
                label: "Speaker"
                description: "Keep this computer's speakers audible while a device is connected. Applies on the next connection."
                checked: root.hostReady && root.preferences.values.host_audio_playback
                enabled: root.editable && root.preferences.runtime.host_audio_default
                onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                onClicked: root.service.saveHostPreference("host_audio_playback", !checked)
            }
            Text {
                width: parent.width
                text: root.hostReady && root.preferences.runtime.remote_available
                    ? "A Remote backend is available on this computer."
                    : "No Remote backend is available on this computer yet. Saving these defaults does not create one."
                color: Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.font.bodySmall
                wrapMode: Text.WordWrap
            }
        }
        Text {
            width: parent.width
            visible: !!root.service && root.service.hostPreferencesError !== ""
            text: root.service ? root.service.hostPreferencesError : ""
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }
        Text {
            width: parent.width
            visible: !!root.service && root.service.hostPreferencesMessage !== ""
            text: root.service ? root.service.hostPreferencesMessage : ""
            color: Color.foreground
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }

        OmarchyUi.PanelSeparator { }
        OmarchyUi.PanelSectionHeader { text: "SECURITY" }
        // AUTH-1 has two switches and this is one of them. The other lives in
        // the app on each device, so turning this on does not hand anything to
        // any device by itself - a device also has to register its own key and
        // keep its own switch on. Off is what a host ships with.
        OmarchyUi.Toggle {
            width: parent.width
            visible: root.hostReady && root.preferences.runtime.biometric_auth_supported
            label: "Approve password prompts from a paired device"
            description: "Let a paired device with Face ID or Touch ID answer this computer's sudo and permission prompts. The device has to turn it on too. Every failure - no device, no answer, or a refusal - goes back to the password."
            checked: root.hostReady && root.preferences.values.biometric_auth
            enabled: root.editable
            onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
            onClicked: root.service.saveHostPreference("biometric_auth", !checked)
        }
        Text {
            width: parent.width
            visible: root.hostReady && !root.preferences.runtime.biometric_auth_supported
            text: "This host does not offer device approval for password prompts. Update the Omodachi host service to use it."
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }

        OmarchyUi.PanelSeparator { }
        OmarchyUi.PanelSectionHeader { text: "CLIPBOARD" }
        // CLIP-1, and the same two switches as above: this one says what this
        // computer is willing to share, and each device has its own. Off is
        // what a host ships with, because a clipboard carries passwords.
        PreferenceChoices {
            width: parent.width
            visible: root.hostReady && root.preferences.runtime.clipboard_sync_supported
            label: "Share this clipboard"
            value: root.hostReady ? root.preferences.values.clipboard_sync : ""
            enabled: root.editable
            options: [{value: "off", label: "Off"}, {value: "host_to_device", label: "One way"}, {value: "both", label: "Both ways"}]
            description: "One way lets a paired device paste what you copied here. Both ways also lets it copy into this computer. The device has to turn it on too. Text only, up to 64 KB."
            onFocusRequested: function(item) { root.focusRequested(item) }
            onSelectedValue: function(value) { root.service.saveHostPreference("clipboard_sync", value) }
        }
        Text {
            width: parent.width
            visible: root.hostReady && root.preferences.runtime.clipboard_sync_supported
                     && !root.preferences.runtime.clipboard_supported
            text: "No clipboard is reachable on this computer yet. The choice is saved and takes effect when the desktop session is back."
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }
        Text {
            width: parent.width
            visible: root.hostReady && !root.preferences.runtime.clipboard_sync_supported
            text: "This host does not share its clipboard. Update the Omodachi host service to use it."
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
        }

        OmarchyUi.PanelSeparator { }
        OmarchyUi.PanelSectionHeader { text: "PANEL" }
        PreferenceChoices {
            width: parent.width
            label: "Default page"
            value: root.service && root.service.uiPreferences ? root.service.uiPreferences.default_page : "overview"
            enabled: !!root.service && root.service.uiPreferencesReady
            options: [{value: "overview", label: "Overview"}, {value: "devices", label: "Devices"}, {value: "settings", label: "Settings"}]
            description: "Where a left click lands. Right-click always opens Settings."
            onFocusRequested: function(item) { root.focusRequested(item) }
            onSelectedValue: function(value) { root.service.saveUiPreference("default_page", value) }
        }
        PreferenceChoices {
            width: parent.width
            label: "Click while open"
            value: root.service && root.service.uiPreferences ? root.service.uiPreferences.icon_click : "toggle"
            enabled: !!root.service && root.service.uiPreferencesReady
            options: [{value: "toggle", label: "Close"}, {value: "open", label: "Keep open"}]
            description: "Stored in this widget's own shell.json entry, through the official bar settings API."
            onFocusRequested: function(item) { root.focusRequested(item) }
            onSelectedValue: function(value) { root.service.saveUiPreference("icon_click", value) }
        }
        Text {
            width: parent.width
            visible: !!root.service && root.service.uiPreferencesMessage !== ""
            text: root.service ? root.service.uiPreferencesMessage : ""
            color: Color.muted
            font.family: Style.font.family
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
            textFormat: Text.PlainText
        }

        OmarchyUi.PanelSeparator { }
        Row {
            spacing: Style.spacing.controlGap
            OmarchyUi.Button {
                id: setupButton
                text: root.setupExpanded ? "Hide Host setup" : "Host setup"
                selected: root.setupExpanded
                focusable: true
                onActiveFocusChanged: if (activeFocus) root.focusRequested(this)
                onClicked: root.setupRequested(!root.setupExpanded)
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: root.service ? root.service.hostUnit + " · " + root.service.hostUnitState : ""
                color: Color.muted
                font.family: Style.font.family
                font.pixelSize: Style.font.caption
                textFormat: Text.PlainText
            }
        }
        HostSetup {
            width: parent.width
            visible: root.setupExpanded
            service: root.service
            onFocusRequested: function(item) { root.focusRequested(item) }
        }
    }
}
