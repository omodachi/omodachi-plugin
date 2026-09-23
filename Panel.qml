pragma ComponentBehavior: Bound
import QtQuick
import qs.Commons
import qs.Ui as OmarchyUi
import "components"
import "PreferencesModel.js" as Preferences
import "OmodachiModel.js" as Model

// Three pages inside one official KeyboardPanel. Every control, dimension and
// colour is Omarchy's own (Study 02 D-12): the only thing of ours on this
// desktop is the symbol in the bar. The panel Loader is injected with service
// and shell but no live anchor - the bar widget registers that on the service.
OmarchyUi.Panel {
    id: panel

    property QtObject service: null
    property QtObject shell: null
    property var manifest: null
    readonly property Item anchorItem: service ? service.anchorItem : null
    property var payload: ({})
    property string page: "overview"
    property bool setupExpanded: false
    property string focusRequestId: ""

    readonly property var snapshot: service ? service.snapshot : ({})
    readonly property string connectionState: service ? service.connectionState : "setup_required"
    readonly property bool hostPresent: Model.isConnected(connectionState) || connectionState === "loading"
    readonly property bool popupVisible: card.visible
    readonly property real popupWidth: card.contentWidth
    readonly property real popupHeight: card.contentHeight

    bar: service ? service.anchorBar : null
    manageIpc: false

    onServiceChanged: if (service) service.panelInstance = panel
    Component.onDestruction: if (service && service.panelInstance === panel) service.panelInstance = null

    function parsePayload(payloadJson) {
        var route = Preferences.route(payloadJson, service && service.uiPreferences ? service.uiPreferences.default_page : "overview")
        panel.page = route.page
        panel.setupExpanded = route.setupExpanded
        panel.focusRequestId = route.focusRequestId
        return route
    }

    function open(payloadJson) {
        panel.payload = panel.parsePayload(payloadJson)
        panel.controller.show()
        if (panel.service) {
            panel.service.refreshDevices()
            if (panel.page === "settings") panel.service.refreshPreferences()
        }
    }
    function close() { panel.controller.hide() }

    function geometry() {
        return {barPosition: card.barPos,
            screen: card.screen ? card.screen.name : "",
            screenWidth: card.screenW, screenHeight: card.screenH,
            cardX: card.cardOrigin.x, cardY: card.cardOrigin.y,
            cardWidth: card.contentWidth, cardHeight: card.contentHeight,
            anchorX: card.anchorScreenPos.x, anchorY: card.anchorScreenPos.y,
            anchorWidth: card.anchorW, anchorHeight: card.anchorH,
            backingWindowVisible: card.backingWindowVisible}
    }

    function ensureControlVisible(item) {
        if (!item || !panel.opened) return
        var point = item.mapToItem(content, 0, 0)
        if (point.y < scroller.contentY) scroller.contentY = point.y
        else if (point.y + item.height > scroller.contentY + scroller.height)
            scroller.contentY = point.y + item.height - scroller.height
        scroller.contentY = Math.max(0, Math.min(scroller.contentY, scroller.contentHeight - scroller.height))
    }

    onPageChanged: {
        scroller.contentY = 0
        if (panel.page === "settings" && panel.service) panel.service.refreshPreferences()
    }

    OmarchyUi.KeyboardPanel {
        id: card
        anchorItem: panel.anchorItem
        bar: panel.bar
        owner: panel
        focusTarget: panel.page === "settings" ? settingsButton : panel.page === "devices" ? devicesButton : overviewButton
        open: panel.opened && !!panel.anchorItem && !!panel.bar
        // Study 02 D-12: contentWidth 430, the height follows the content and
        // is capped, exactly like the rest of the kit's panels.
        contentWidth: fittedContentWidth(Style.space(430))
        contentHeight: fittedContentHeight(content.implicitHeight, Style.space(600))
        onVisibleChanged: console.log("Omodachi popup visible=" + visible + " page=" + panel.page)

        Item {
            id: keyCatcher
            anchors.fill: parent
            Keys.onEscapePressed: panel.close()

            Flickable {
                id: scroller
                anchors.fill: parent
                contentHeight: content.implicitHeight
                clip: true
                boundsBehavior: Flickable.StopAtBounds

                Column {
                    id: content
                    width: parent.width
                    spacing: Style.spacing.controlGap

                    // No Host at all: one sentence and one button, no page
                    // switcher and no JSON error anywhere (Study 02 §10).
                    InstallCard {
                        width: parent.width
                        visible: !panel.hostPresent
                        service: panel.service
                        onFocusRequested: function(item) { panel.ensureControlVisible(item) }
                    }

                    Row {
                        spacing: Style.spacing.controlGap
                        visible: panel.hostPresent
                        OmarchyUi.Button { id: overviewButton; text: "Overview"; selected: panel.page === "overview"; focusable: true
                            onActiveFocusChanged: if (activeFocus) panel.ensureControlVisible(this); onClicked: panel.page = "overview" }
                        OmarchyUi.Button { id: devicesButton; text: "Devices"; selected: panel.page === "devices"; focusable: true
                            onActiveFocusChanged: if (activeFocus) panel.ensureControlVisible(this); onClicked: panel.page = "devices" }
                        OmarchyUi.Button { id: settingsButton; text: "Settings"; selected: panel.page === "settings"; focusable: true
                            onActiveFocusChanged: if (activeFocus) panel.ensureControlVisible(this); onClicked: panel.page = "settings" }
                    }

                    OverviewPage {
                        width: parent.width
                        visible: panel.hostPresent && panel.page === "overview"
                        service: panel.service
                        onFocusRequested: function(item) { panel.ensureControlVisible(item) }
                    }

                    DevicesPage {
                        width: parent.width
                        visible: panel.hostPresent && panel.page === "devices"
                        service: panel.service
                        highlightRequestId: panel.focusRequestId
                        onFocusRequested: function(item) { panel.ensureControlVisible(item) }
                    }

                    SettingsPage {
                        id: settingsPage
                        width: parent.width
                        visible: panel.hostPresent && panel.page === "settings"
                        service: panel.service
                        setupExpanded: panel.setupExpanded
                        onSetupRequested: function(expanded) { panel.setupExpanded = expanded }
                        onFocusRequested: function(item) { panel.ensureControlVisible(item) }
                    }

                    Text {
                        width: parent.width
                        visible: panel.hostPresent && !!panel.service && panel.service.adminMessage !== ""
                        text: panel.service ? panel.service.adminMessage : ""
                        color: Color.foreground
                        font.family: Style.font.family
                        font.pixelSize: Style.font.bodySmall
                        wrapMode: Text.WordWrap
                        textFormat: Text.PlainText
                    }
                    Text {
                        width: parent.width
                        visible: panel.hostPresent && !!panel.service && panel.service.adminError !== ""
                        text: panel.service ? panel.service.adminError : ""
                        color: Color.muted
                        font.family: Style.font.family
                        font.pixelSize: Style.font.bodySmall
                        wrapMode: Text.WordWrap
                        textFormat: Text.PlainText
                    }

                    Row {
                        spacing: Style.spacing.controlGap
                        visible: panel.hostPresent
                        OmarchyUi.Button { text: "Reconnect"; focusable: true
                            onActiveFocusChanged: if (activeFocus) panel.ensureControlVisible(this)
                            onClicked: if (panel.service) panel.service.reconnect() }
                        OmarchyUi.Button { text: "Close"; focusable: true
                            onActiveFocusChanged: if (activeFocus) panel.ensureControlVisible(this)
                            onClicked: panel.close() }
                    }
                }
            }
        }
    }
}
