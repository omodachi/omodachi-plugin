pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import qs.Commons
import qs.Ui as OmarchyUi
import "assets/OmodachiBrand.js" as Brand
import "OmodachiModel.js" as Model

// One slot on the official bar. The host injects bar/moduleName/settings; the
// scoped facade is bar.shell, never a direct `shell` injection. The root must
// export an implicit size - shell/plugins/bar/Bar.qml lays slots out by
// implicit dimensions, so an explicit width leaves a zero-size invisible slot.
//
// Study 02 D-13: four states, expressed only through opacity, the theme's
// bar.active colour and one indicator. No colour of our own enters the bar.
OmarchyUi.BarWidget {
    id: widget

    property QtObject shell: bar && bar.shell ? bar.shell : null
    property var manifest: null
    readonly property string pluginId: manifest && typeof manifest.id === "string" ? manifest.id : "com.omodachi.host"
    // serviceFor() is a call, not a bindable property, so a widget built before
    // its own service is mounted would keep a null forever and never register
    // an anchor. Re-resolve until it answers, then stop.
    property QtObject scopedService: null
    property QtObject registeredService: null

    function resolveService() {
        var next = shell && typeof shell.serviceFor === "function" ? shell.serviceFor(pluginId) : null
        if (next !== widget.scopedService) widget.scopedService = next
    }

    Timer {
        interval: 500
        repeat: true
        running: widget.scopedService === null
        triggeredOnStart: true
        onTriggered: widget.resolveService()
    }

    readonly property string status: scopedService ? scopedService.connectionState : "setup_required"
    readonly property bool remoteActive: !!scopedService && scopedService.remoteActive
    readonly property bool takeoverLocked: !!scopedService && scopedService.takeoverLocked
    readonly property string lockNotice: scopedService ? scopedService.lockNotice : ""
    readonly property string iconState: Model.iconState(status, remoteActive)

    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight
    Accessible.name: "Omodachi"
    Accessible.description: "Open the Omodachi panel. Right-click for Settings."

    onScopedServiceChanged: registerAnchor()
    onBarChanged: { widget.resolveService(); Qt.callLater(registerAnchor) }
    onSettingsChanged: if (scopedService && typeof scopedService.readUiSettings === "function") scopedService.readUiSettings(widget.settings)
    Component.onCompleted: { widget.resolveService(); Qt.callLater(registerAnchor) }
    Component.onDestruction: if (registeredService) registeredService.unregisterAnchor(widget)

    function registerAnchor() {
        if (registeredService && registeredService !== scopedService) registeredService.unregisterAnchor(widget)
        registeredService = scopedService
        if (scopedService && bar) {
            scopedService.registerAnchor(widget, bar)
            if (typeof scopedService.readUiSettings === "function") scopedService.readUiSettings(widget.settings)
        }
    }

    OmarchyUi.BarIconButton {
        id: button
        anchors.fill: parent
        bar: widget.bar

        iconComponent: Item {
            Image {
                anchors.fill: parent
                // An SVG file does not inherit a QML colour: bind the bar's own
                // foreground (or bar.active) into the source text instead.
                source: "data:image/svg+xml;utf8," + encodeURIComponent(
                    Brand.symbol.replace("currentColor", String(button.active && button.useActiveColor ? button.activeColor : button.foreground)))
                fillMode: Image.PreserveAspectFit
                sourceSize.width: width * Screen.devicePixelRatio
                sourceSize.height: height * Screen.devicePixelRatio
                smooth: false
            }
            // The fourth state's indicator. Same language as the official
            // indicator glyphs: the theme's active colour, nothing else.
            Rectangle {
                visible: widget.iconState === "remote"
                width: Math.max(2, Math.round(parent.width / 5))
                height: width
                radius: 0
                color: button.activeColor
                anchors.right: parent.right
                anchors.bottom: parent.bottom
            }
        }

        // absent -> 0.45 (WidgetButton.dimmed); idle -> plain bar foreground;
        // linked/remote -> Color.bar.active, which is what the theme calls
        // "this machine is being used from somewhere else".
        // MENU-2 / A-67. A takeover leaves this icon with nothing to open, so
        // it reads as unavailable while one is running — and the tooltip and
        // the notice both say the same sentence.
        dimmed: widget.iconState === "absent" || widget.takeoverLocked
        active: widget.iconState === "linked" || widget.iconState === "remote"
        useActiveColor: true
        tooltipText: widget.lockNotice !== ""
            ? widget.lockNotice
            : Model.iconTooltip(widget.status, widget.remoteActive,
                                widget.scopedService ? widget.scopedService.snapshot.remote : null)

        onPressed: function(mouseButton) {
            if (mouseButton === Qt.RightButton) widget.openSettings()
            else widget.activate()
        }
    }

    // MENU-2 / A-67: the right button is refused by the same guard as the left,
    // so "locked" is not a thing one button knows and the other does not.
    function openSettings() {
        if (scopedService && scopedService.refuseWhileTakeover()) return
        widget.registerAnchor()
        if (scopedService) scopedService.selectAnchor(widget, widget.bar)
        if (shell) shell.summon(pluginId, JSON.stringify({view: "settings"}))
    }

    // Study 02 N-13: with a live Remote session the user's hands are on the
    // iPad, so the left click recalls the native panel there and nothing opens
    // on this screen. Without one it is the ordinary local toggle.
    function activate() {
        widget.registerAnchor()
        if (!scopedService) {
            if (shell) shell.summon(pluginId, JSON.stringify({view: "overview"}))
            return
        }
        scopedService.selectAnchor(widget, widget.bar)
        if (!scopedService.remoteActive && shell && shell.isPluginOpen(pluginId)
            && scopedService.uiPreferences.icon_click === "toggle") {
            scopedService.widgetActivationCount += 1
            shell.hide(pluginId)
            return
        }
        scopedService.activate()
    }
}
