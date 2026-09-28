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
    Component.onCompleted: { widget.resolveService(); Qt.callLater(registerAnchor); Qt.callLater(widget.refreshSections) }
    Component.onDestruction: {
        widget.leaving = true
        if (registeredService) registeredService.unregisterAnchor(widget)
    }

    // ---- REMOTE-SAFE-1: this screen's bar clears the device's corners -------
    //
    // A bar surface is built per monitor, so this widget is alive once per
    // screen (shell/plugins/bar/Bar.qml `Variants { model: Quickshell.screens }`).
    // The instance whose own window is on the session's OMODACHI output, in a
    // live session of either mode (REMOTE-SAFE-1b: a takeover's output is the
    // same device shape), moves that bar's two end sections inward by what core
    // says the device's corners cover (`remote_bar.bar_insets`). Every other
    // instance - every other screen - computes null and does nothing at all.
    //
    // How, and why not the window's `margins` (which the research suggested):
    // Omarchy's popups assume the bar window starts at the screen edge.
    // KeyboardPanel.cardOrigin and its click forwarding (`barPoint`) and
    // Bar.windowScreenPoint all use bar-content coordinates as screen
    // coordinates along the bar, so a shortened window would put every panel
    // popped from this bar N px off its icon and send a click on one icon to
    // the icon N px further along. Moving the end sections instead keeps the
    // window, its exclusive zone and every coordinate the shell computes
    // exactly as they are; only LeftModules' / RightModules' own margin
    // (`Style.space(8)` in Bar.qml's verticalBar/horizontalBar) grows.
    //
    // Nothing is written: no shell.json, no shell IPC setter. Each override is
    // a `Binding` with RestoreBindingOrValue, so when `when` goes false (the
    // session ended or the value went to zero) the shell's own
    // binding comes back, and when this widget or that screen goes away the
    // Binding goes with it.
    readonly property var hostWindow: widget.QsWindow.window
    readonly property string screenName: hostWindow && hostWindow.screen ? String(hostWindow.screen.name || "") : ""
    readonly property string barPosition: bar && typeof bar.position === "string" ? bar.position : ""
    readonly property var cornerInsets: Model.barInsetsFor(scopedService ? scopedService.snapshot : null,
                                                           screenName, barPosition)
    readonly property int shellEndMargin: Style.space(8)
    property Item leadingSection: null
    property Item trailingSection: null
    // A Binding that is destroyed while active does not give the shell its
    // binding back (measured on the VM: taking this widget out of the bar in
    // the middle of a session left both ends pushed in until the output went
    // away). So the widget turns its Bindings off - which does restore - on
    // the way out, before they are destroyed with it.
    property bool leaving: false
    readonly property bool applying: !leaving && !!cornerInsets

    onCornerInsetsChanged: Qt.callLater(widget.refreshSections)
    onHostWindowChanged: Qt.callLater(widget.refreshSections)

    // contentItem -> Loader -> verticalBar/horizontalBar Item -> {CenterModules,
    // LeftModules, RightModules}. The two ends are the ModuleLists that carry
    // region "left"/"right" (Bar.qml `component LeftModules: ModuleList`); a
    // ModuleSlot has `entry`, not `entries`, and the center lists say "center".
    function barSections() {
        var found = {leading: null, trailing: null}
        var window = widget.QsWindow.window
        var queue = window && window.contentItem ? [{item: window.contentItem, depth: 0}] : []
        while (queue.length > 0) {
            var next = queue.shift()
            var kids = next.item.children || []
            for (var i = 0; i < kids.length; i++) {
                var child = kids[i]
                if (!child) continue
                if (child.entries !== undefined && child.region === "left") { if (!found.leading) found.leading = child }
                else if (child.entries !== undefined && child.region === "right") { if (!found.trailing) found.trailing = child }
                else if (next.depth < 3) queue.push({item: child, depth: next.depth + 1})
            }
        }
        return found
    }

    function refreshSections() {
        if (!widget.cornerInsets) {
            widget.leadingSection = null
            widget.trailingSection = null
            return
        }
        var found = widget.barSections()
        widget.leadingSection = found.leading
        widget.trailingSection = found.trailing
    }

    Binding {
        target: widget.leadingSection
        property: "anchors.topMargin"
        when: widget.applying && !!widget.leadingSection && widget.cornerInsets.vertical
        value: Model.sectionMargin(widget.shellEndMargin, widget.cornerInsets ? widget.cornerInsets.leading : 0)
        restoreMode: Binding.RestoreBindingOrValue
    }
    Binding {
        target: widget.trailingSection
        property: "anchors.bottomMargin"
        when: widget.applying && !!widget.trailingSection && widget.cornerInsets.vertical
        value: Model.sectionMargin(widget.shellEndMargin, widget.cornerInsets ? widget.cornerInsets.trailing : 0)
        restoreMode: Binding.RestoreBindingOrValue
    }
    Binding {
        target: widget.leadingSection
        property: "anchors.leftMargin"
        when: widget.applying && !!widget.leadingSection && !widget.cornerInsets.vertical
        value: Model.sectionMargin(widget.shellEndMargin, widget.cornerInsets ? widget.cornerInsets.leading : 0)
        restoreMode: Binding.RestoreBindingOrValue
    }
    Binding {
        target: widget.trailingSection
        property: "anchors.rightMargin"
        when: widget.applying && !!widget.trailingSection && !widget.cornerInsets.vertical
        value: Model.sectionMargin(widget.shellEndMargin, widget.cornerInsets ? widget.cornerInsets.trailing : 0)
        restoreMode: Binding.RestoreBindingOrValue
    }

    // `omarchy-shell omodachi barGeometry` (Service.qml) asks every instance
    // this. It is what core's bar_geometry reads the Omarchy logo from, so
    // the App's mark (A-67) lands on the logo wherever the user put it -
    // `center` included - and after the ends moved. Output-local logical px.
    function logoSlot(root) {
        var stack = root ? [root] : [], seen = 0
        while (stack.length > 0 && seen < 4096) {
            var item = stack.pop()
            seen += 1
            if (item.moduleName === "omarchy.menu" && item.activeItem !== undefined
                && item.visible === true && item.width > 0 && item.height > 0) return item
            var kids = item.children || []
            for (var i = 0; i < kids.length; i++) if (kids[i]) stack.push(kids[i])
        }
        return null
    }

    function barReport() {
        var window = widget.QsWindow.window
        if (!window || !window.contentItem || !window.screen) return null
        var screenSize = {width: window.screen.width, height: window.screen.height}
        var windowSize = {width: window.width, height: window.height}
        var logo = null, slot = widget.logoSlot(window.contentItem)
        if (slot) {
            var point = slot.mapToItem(window.contentItem, 0, 0)
            logo = Model.outputRect({x: point.x, y: point.y, width: slot.width, height: slot.height},
                                    widget.barPosition, screenSize, windowSize)
        }
        var applied = null
        if (widget.cornerInsets) {
            applied = {vertical: widget.cornerInsets.vertical,
                       leading: widget.leadingSection ? Math.round(widget.cornerInsets.vertical
                                ? widget.leadingSection.anchors.topMargin : widget.leadingSection.anchors.leftMargin) : null,
                       trailing: widget.trailingSection ? Math.round(widget.cornerInsets.vertical
                                ? widget.trailingSection.anchors.bottomMargin : widget.trailingSection.anchors.rightMargin) : null}
        }
        return {output: widget.screenName, position: widget.barPosition, screen: screenSize,
                window: windowSize, insets: widget.cornerInsets, applied: applied, logo: logo}
    }

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
