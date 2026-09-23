pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import "OmodachiModel.js" as Model
import "MediaPairingModel.js" as MediaPairing
import "PreferencesModel.js" as Preferences

// The whole bridge to core: fixed argv, JSONL in, QML properties out. No
// credential ever reaches this file - `omodachi-host plugin-watch` holds the
// plugin credential and frames arrive already authenticated.
//
// Process/SplitParser usage follows the official menu plugin
// (/usr/share/omarchy/shell/plugins/menu/Menu.qml).
Item {
    id: service

    property QtObject shell: null
    property var manifest: null
    readonly property string pluginId: manifest && typeof manifest.id === "string" ? manifest.id : "com.omodachi.host"

    property string connectionState: "loading"
    property string lastError: ""
    property var snapshot: ({})
    property string lastInstanceId: ""
    property int lastRevision: -1
    property int lastEventCursor: -1
    property int retryDelayMs: 500
    property bool watchEnabled: true

    readonly property bool remoteActive: Model.remoteActive(service.snapshot)
    readonly property string remoteState: Model.remoteState(service.snapshot)
    // MENU-2 / A-67. During a takeover this machine's screens are off and the
    // user is on the tablet, so neither button on this icon has anything it can
    // usefully open here. It says so instead — and because the guard lives in
    // the plugin, a local mouse click during a takeover gets the same answer as
    // a tap from the device.
    readonly property bool takeoverLocked: Model.takeoverLocked(service.snapshot)
    property string lockNotice: ""
    readonly property string iconState: Model.iconState(service.connectionState, service.remoteActive)

    property var anchorEntries: []
    property Item anchorItem: null
    property QtObject anchorBar: null
    property QtObject panelInstance: null
    property int widgetActivationCount: 0
    // The last panel-summon this widget asked for, as the model classified it.
    // Diagnostics only: it is what tells a live host whether a click recalled
    // the device or fell back to a local view. No credential, no session body.
    property var lastSummon: null

    readonly property bool helperRunning: watchProcess.running
    readonly property var helperPid: watchProcess.processId

    signal snapshotChangedExternally(var value)
    signal stateError(string code)
    signal eventReceived(var value)
    signal summonResult(var value)
    signal pairingRequestFocused(string requestId)

    // ---- plugin-watch ------------------------------------------------------

    Process {
        id: watchProcess
        command: ["omodachi-host", "plugin-watch"]
        running: true
        stdout: SplitParser { onRead: function(data) { service.consumeFrame(data) } }
        stderr: StdioCollector { }
        onStarted: console.log("Omodachi helper started, pid=" + processId)
        onExited: function(exitCode, exitStatus) { service.watchUnavailable("plugin_watch_exited") }
        onRunningChanged: if (!running && service.watchEnabled) service.watchUnavailable("plugin_watch_stopped")
    }

    Timer {
        id: retryTimer
        // FailedToStart emits no `exited` signal, so a first install with no
        // omodachi-host on PATH would otherwise never retry. The timer runs
        // whenever the process is stopped, for any reason.
        interval: service.retryDelayMs
        repeat: true
        running: service.watchEnabled && !watchProcess.running
        onTriggered: {
            service.watchUnavailable("plugin_watch_unavailable")
            watchProcess.running = true
            service.retryDelayMs = Math.min(30000, service.retryDelayMs * 2)
        }
    }

    function watchUnavailable(code) {
        if (!service.watchEnabled) return
        if (service.connectionState !== "setup_required" && service.connectionState !== "permission_required") {
            service.connectionState = "setup_required"
            service.lastError = code
        }
    }

    function reconnect() {
        service.watchEnabled = true
        service.retryDelayMs = 500
        watchProcess.running = false
        service.connectionState = "loading"
        service.lastError = ""
        service.refreshDevices()
    }

    function consumeFrame(line) {
        var result = Model.consumeLine(line, service.snapshot, service.lastInstanceId)
        if (result.kind === "snapshot" || result.kind === "event") {
            service.snapshot = result.snapshot
            service.lastInstanceId = result.snapshot.instance_id
            service.lastRevision = result.snapshot.revision
            service.lastEventCursor = result.snapshot.event_cursor
            service.connectionState = Model.asState(result.snapshot)
            service.lastError = ""
            service.retryDelayMs = 500
            if (result.kind === "event") service.eventReceived(result.event)
            service.snapshotChangedExternally(result.snapshot)
            return true
        }
        if (result.kind === "resync") {
            service.snapshot = ({})
            service.lastInstanceId = ""
            service.lastRevision = -1
            service.lastEventCursor = -1
            service.connectionState = "loading"
            service.lastError = "resync_required"
            return false
        }
        service.connectionState = result.code || "error"
        service.lastError = result.message || "invalid_frame"
        service.stateError(service.connectionState)
        return false
    }

    // ---- diagnostics -------------------------------------------------------
    // `omarchy-shell omodachi status`. Process/QML state only: no credential,
    // no invitation, no snapshot body, no registry hash.

    IpcHandler {
        target: "omodachi"
        function status(): string {
            return JSON.stringify({connection: service.connectionState,
                helperRunning: service.helperRunning, helperPid: service.helperPid,
                runtimeSource: Qt.resolvedUrl("Service.qml").toString(),
                revision: service.lastRevision, eventCursor: service.lastEventCursor,
                remoteState: service.remoteState, iconState: service.iconState,
                anchorReady: !!service.anchorItem && !!service.anchorBar,
                takeoverLocked: service.takeoverLocked, lockNotice: service.lockNotice,
                panelLoaded: !!service.panelInstance,
                panelOpened: !!service.panelInstance && service.panelInstance.opened,
                popupVisible: !!service.panelInstance && service.panelInstance.popupVisible,
                popupWidth: service.panelInstance ? service.panelInstance.popupWidth : 0,
                popupHeight: service.panelInstance ? service.panelInstance.popupHeight : 0,
                popupGeometry: service.panelInstance ? service.panelInstance.geometry() : null,
                page: service.panelInstance ? service.panelInstance.page : "",
                widgetActivations: service.widgetActivationCount,
                lastSummon: service.lastSummon,
                hostUnit: service.hostUnit, hostUnitState: service.hostUnitState,
                devicesLoaded: service.devicesLoaded, deviceCount: service.devices.length,
                requestsLoaded: service.requestsLoaded,
                pendingPairRequests: service.pendingRequests.length,
                mediaApiReady: service.mediaApiReady,
                mediaRequestCount: service.mediaRequests.length,
                mediaApprovals: service.mediaApprovals.length,
                mediaError: service.mediaError,
                hostPreferencesReady: service.hostPreferencesReady,
                adminBusy: service.adminBusy, adminOperation: service.adminOperation,
                adminError: service.adminError, error: service.lastError})
        }
        function reconnect(): void { service.reconnect() }
    }

    // ---- bar anchor --------------------------------------------------------
    // The independent panel Loader is injected with service and shell but no
    // live bar anchor, so each owned widget registers its own Item and scoped
    // bar here and the panel follows that reference. No visual-parent walk.

    function registerAnchor(item, bar) {
        var next = service.anchorEntries.filter(function(entry) { return entry.item && entry.item !== item })
        next.push({item: item, bar: bar})
        service.anchorEntries = next
        if (!service.anchorItem) service.selectAnchor(item, bar)
    }
    function selectAnchor(item, bar) {
        service.anchorItem = item
        service.anchorBar = bar
    }
    function unregisterAnchor(item) {
        service.anchorEntries = service.anchorEntries.filter(function(entry) { return entry.item && entry.item !== item })
        if (service.anchorItem === item || !service.anchorItem) {
            var replacement = service.anchorEntries.length ? service.anchorEntries[0] : null
            service.selectAnchor(replacement ? replacement.item : null, replacement ? replacement.bar : null)
        }
    }

    // ---- panel summon ------------------------------------------------------
    // With a live session the panel belongs on the iPad: core publishes the
    // recall to the device that owns the session and nothing opens here.

    // The icon recalls a panel, so it asks for one by name. Without --view core
    // would default to overview, and the recall the iPad receives would not name
    // what it is recalling.
    // ARCH-1 / Study 04 A-59. A left click on this widget during a session is
    // the user asking for the app's own settings on the device they are looking
    // at. Before, it asked for `overview`, the menu and keybindings panel, which
    // the App already reaches from the bar's other icon — so there were two ways
    // to the same panel and none at all to this one.
    readonly property string summonView: "settings"

    Process {
        id: summonProcess
        command: Model.summonCommand(service.summonView)
        running: false
        stdout: StdioCollector {
            id: summonStdout
            waitForEnd: true
            onStreamFinished: service.consumeSummon(summonStdout.text)
        }
        stderr: StdioCollector { }
        onExited: function(exitCode, exitStatus) { if (exitCode !== 0) service.openLocal("setup") }
    }
    Timer {
        id: summonTimeout
        interval: 5000
        onTriggered: {
            summonProcess.running = false
            service.openLocal("setup")
        }
    }

    function openLocal(view) {
        summonTimeout.stop()
        if (service.shell) service.shell.summon(service.pluginId, JSON.stringify({view: view}))
    }

    function consumeSummon(raw) {
        var result
        summonTimeout.stop()
        try { result = JSON.parse(raw) } catch (error) {
            service.lastSummon = {ok: false, code: "invalid_reply"}
            service.openLocal("overview")
            return false
        }
        var decision = Model.classifySummon(result, service.summonView)
        if (!decision.ok) {
            service.lastSummon = {ok: false, code: decision.code}
            service.lastError = decision.code
            service.openLocal("overview")
            return false
        }
        service.lastSummon = {ok: true, route: decision.route, view: decision.view,
                              owner_device_id: decision.value.owner_device_id || "",
                              session_id: decision.value.session_id || ""}
        service.summonResult(decision.value)
        if (decision.route === "local") service.openLocal(service.uiPreferences.default_page)
        return true
    }

    /// MENU-2 / A-67. Both buttons, one answer, while a takeover is running.
    /// Returns true when the click was answered here and must go no further.
    function refuseWhileTakeover() {
        if (!service.takeoverLocked) { service.lockNotice = ""; return false }
        service.lockNotice = Model.TAKEOVER_LOCK_NOTICE
        lockNoticeTimer.restart()
        return true
    }

    Timer {
        id: lockNoticeTimer
        interval: 4000
        onTriggered: service.lockNotice = ""
    }

    // The lock ending is not something the user has to wait out: a takeover
    // that was released leaves no reason to keep saying no.
    onTakeoverLockedChanged: if (!service.takeoverLocked) { lockNoticeTimer.stop(); service.lockNotice = "" }

    // Left click. No session: the local panel. Live session: the recall.
    function activate() {
        service.widgetActivationCount += 1
        if (service.refuseWhileTakeover()) return
        if (!Model.isConnected(service.connectionState)) { service.openLocal("overview"); return }
        if (!service.remoteActive) { service.openLocal(service.uiPreferences.default_page); return }
        if (summonProcess.running) return
        summonTimeout.restart()
        summonProcess.running = true
    }

    // ---- preferences -------------------------------------------------------

    property var uiPreferences: ({default_page: "overview", icon_click: "toggle"})
    property string uiPreferencesMessage: ""
    readonly property bool uiPreferencesReady: !!service.shell && !!service.anchorItem
        && typeof service.shell.updateEntryInline === "function"
    property var hostPreferences: ({ok: false})
    readonly property bool hostPreferencesReady: hostPreferences.ok === true
    property string hostPreferencesError: ""
    property string hostPreferencesMessage: ""
    property var preferenceChange: null
    readonly property bool hostPreferencesBusy: preferencesSetProcess.running || preferenceChange !== null

    function readUiSettings(settings) { service.uiPreferences = Preferences.ui(settings) }
    function saveUiPreference(key, value) {
        if (!service.uiPreferencesReady) { service.uiPreferencesMessage = "Panel preferences need the bar entry; they cannot be saved yet."; return }
        if (service.uiPreferences[key] === value) { service.uiPreferencesMessage = "Already set."; return }
        var next = Preferences.uiChange(service.anchorItem.settings, key, value)
        if (!next || !service.shell.updateEntryInline(service.pluginId, next)) {
            service.uiPreferencesMessage = "The bar could not save this panel preference."
            return
        }
        // Official inline persistence writes only this plugin's own entry in
        // shell.json; bar injection refreshes the value again after reload.
        service.readUiSettings(next)
        service.uiPreferencesMessage = "Saved to this widget's bar entry."
    }

    Process {
        id: preferencesReadProcess
        command: ["omodachi-host", "preferences", "get"]
        stdout: StdioCollector {
            id: preferencesReadOutput
            waitForEnd: true
            onStreamFinished: service.consumePreferences(preferencesReadOutput.text, false)
        }
        stderr: StdioCollector { }
    }
    Process {
        id: preferencesSetProcess
        stdout: StdioCollector {
            id: preferencesSetOutput
            waitForEnd: true
            onStreamFinished: service.consumePreferences(preferencesSetOutput.text, true)
        }
        stderr: StdioCollector { }
    }
    Timer {
        id: preferencesReadTimeout
        interval: 14000
        onTriggered: {
            preferencesReadProcess.running = false
            service.hostPreferences = ({ok: false})
            service.hostPreferencesError = "Host settings are unavailable. Reconnect to load them."
        }
    }
    Timer {
        id: preferencesSetTimeout
        interval: 14000
        onTriggered: {
            preferencesSetProcess.running = false
            service.preferenceChange = null
            service.hostPreferencesError = "The save could not be confirmed. Reload settings before retrying."
            service.refreshPreferences()
        }
    }
    function refreshPreferences() {
        if (preferencesReadProcess.running || service.hostPreferencesBusy) return
        preferencesReadTimeout.restart()
        preferencesReadProcess.running = true
    }
    function saveHostPreference(key, value) {
        if (service.hostPreferencesBusy) return
        var command = Preferences.command(service.hostPreferences, key, value)
        if (!command) { service.hostPreferencesError = "This setting is not available from the current host."; return }
        if (service.hostPreferences.values[key] === value) {
            service.hostPreferencesError = ""
            service.hostPreferencesMessage = "Already saved."
            return
        }
        service.preferenceChange = {key: key, value: value, revision: service.hostPreferences.revision}
        service.hostPreferencesError = ""
        service.hostPreferencesMessage = ""
        preferencesSetProcess.command = command
        preferencesSetTimeout.restart()
        preferencesSetProcess.running = true
    }
    function consumePreferences(raw, saving) {
        if (saving) preferencesSetTimeout.stop()
        else preferencesReadTimeout.stop()
        var result = Preferences.parse(raw), expected = service.preferenceChange
        if (saving) service.preferenceChange = null
        if (!result.ok) {
            service.hostPreferencesError = Preferences.errorMessage(result.code)
            if (!saving) service.hostPreferences = ({ok: false})
            else service.refreshPreferences()
            return
        }
        if (!saving && service.hostPreferencesReady && result.revision < service.hostPreferences.revision) return
        service.hostPreferences = result
        if (saving) {
            if (!expected || result.revision < expected.revision || result.values[expected.key] !== expected.value) {
                service.hostPreferencesError = "The saved value did not match this change. Reload settings before retrying."
                return
            }
            service.hostPreferencesError = ""
            service.hostPreferencesMessage = expected.key === "allow_dynamic_resolution"
                ? "Host permission saved. The stream running now is unchanged."
                : "Saved for the next Remote connection."
        } else if (service.hostPreferencesError.indexOf("elsewhere") < 0) service.hostPreferencesError = ""
    }

    // ---- host unit ---------------------------------------------------------
    // Fixed argv against this user's own omodachid unit, nothing else.

    property string hostUnit: "omodachid.service"
    property string hostUnitState: "unknown"
    property string hostUnitMessage: ""
    readonly property bool hostUnitBusy: unitStateProcess.running || unitActionProcess.running

    Process {
        id: unitStateProcess
        command: ["systemctl", "--user", "is-active", service.hostUnit]
        stdout: StdioCollector {
            id: unitStateOutput
            waitForEnd: true
            onStreamFinished: service.hostUnitState = unitStateOutput.text.trim() || "unknown"
        }
        stderr: StdioCollector { }
    }
    Process {
        id: unitActionProcess
        stderr: StdioCollector { }
        onExited: function(exitCode, exitStatus) {
            service.hostUnitMessage = exitCode === 0 ? "Done." : "systemctl reported exit " + exitCode + "."
            service.refreshHostUnit()
            if (exitCode === 0) service.reconnect()
        }
    }
    Process { id: terminalProcess; stderr: StdioCollector { } }

    function refreshHostUnit() {
        if (unitStateProcess.running) return
        unitStateProcess.running = true
    }
    function hostUnitAction(verb) {
        if (service.hostUnitBusy || ["start", "stop", "restart"].indexOf(verb) < 0) return
        service.hostUnitMessage = ""
        unitActionProcess.command = ["systemctl", "--user", verb, service.hostUnit]
        unitActionProcess.running = true
    }
    // Study 02 §10 "no Host": one visible terminal running this plugin's own
    // tools/install_host.py, which fetches omodachi-core and then runs core's
    // installer. INSTALL-1: that file is tracked in this repository now, so a
    // clone made by `omarchy plugin add` has an Install button that works.
    // The argv is a fixed list of literals plus one path inside this plugin
    // directory - nothing here is assembled from anything a device sent.
    property string installSource: "https://github.com/omodachi/omodachi-core"
    // INSTALL-1 §1: the installer rewrites this file at each stage, so the
    // panel can say which step is running and which one failed without
    // reading the terminal. It is this user's own cache file; a missing or
    // unparseable one simply means "no install is being watched".
    property string installStatusPath: (Quickshell.env("HOME") || "~") + "/.cache/omodachi/install-status.json"
    property string installStage: ""
    property string installMessage: ""
    property string installDetail: ""
    readonly property bool installRunning: service.installStage !== "" && service.installStage !== "done" && service.installStage !== "failed"
    readonly property bool installFailed: service.installStage === "failed"

    Process {
        id: installStatusProcess
        stdout: StdioCollector {
            id: installStatusOutput
            waitForEnd: true
            onStreamFinished: service.consumeInstallStatus(installStatusOutput.text)
        }
        stderr: StdioCollector { }
    }
    Timer {
        id: installStatusTimer
        interval: 700
        repeat: true
        onTriggered: {
            if (installStatusProcess.running) return
            installStatusProcess.command = ["cat", service.installStatusPath]
            installStatusProcess.running = true
        }
    }

    function consumeInstallStatus(text) {
        var value = Model.parseInstallStatus(text)
        if (!value) return
        service.installStage = value.stage
        service.installMessage = value.message
        service.installDetail = value.detail
        if (value.stage === "done" || value.stage === "failed") {
            installStatusTimer.running = false
            if (value.stage === "done") service.reconnect()
        }
    }

    function installHost() {
        if (terminalProcess.running) return
        service.installStage = "starting"
        service.installMessage = "Starting…"
        service.installDetail = ""
        terminalProcess.command = ["omarchy-launch-terminal", "python3",
            Qt.resolvedUrl("tools/install_host.py").toString().replace("file://", "")]
        terminalProcess.running = true
        installStatusTimer.running = true
    }

    // ---- devices and pairing ----------------------------------------------

    property var devices: []
    property var pairRequests: []
    readonly property var pendingRequests: pairRequests.filter(function(row) { return row.status === "pending" })
    property bool devicesLoaded: false
    // PLUG-4 §3: how many revoked devices core kept out of the list. The page
    // offers one cleanup line for them instead of drawing 32 dead rows.
    property int revokedHidden: 0
    property bool requestsLoaded: false
    property string devicesError: ""
    property string pairingError: ""
    property string adminOperation: ""
    property string adminTarget: ""
    property var adminBinding: null
    property string adminMessage: ""
    property string adminError: ""
    readonly property bool adminBusy: adminProcess.running || adminOperation !== ""
    property var notifiedRequests: ({})

    property var mediaRequests: []
    property bool mediaApiReady: false
    property string mediaError: ""
    // PAIR-3 §1.3: Sunshine certificate attempts stopped on this host waiting
    // for a local Approve. core has had `approve_local` since SPEC-B2; nothing
    // ever drew it, so the app spun for 120 s and the attempt was cancelled.
    property var mediaApprovals: []
    // PAIR-3 §1.2: the device whose streaming grant did not land, and the
    // request that approved it, so its row can offer the repair.
    property string grantRemoteDeviceId: ""
    property string grantRemoteRequestId: ""

    Process {
        id: devicesProcess
        command: ["omodachi-host", "devices", "list"]
        stdout: StdioCollector {
            id: devicesOutput
            waitForEnd: true
            onStreamFinished: service.consumeDevices(devicesOutput.text)
        }
        stderr: StdioCollector { }
    }
    Process {
        id: requestsProcess
        command: ["omodachi-host", "pair", "pending"]
        stdout: StdioCollector {
            id: requestsOutput
            waitForEnd: true
            onStreamFinished: service.consumeRequests(requestsOutput.text)
        }
        stderr: StdioCollector { }
    }
    Process {
        id: mediaRequestsProcess
        command: ["omodachi-host", "media-pairing", "pending"]
        stdout: StdioCollector {
            id: mediaRequestsOutput
            waitForEnd: true
            onStreamFinished: service.consumeMediaRequests(mediaRequestsOutput.text)
        }
        stderr: StdioCollector { }
    }
    Process { id: adminProcess
        stdout: StdioCollector {
            id: adminOutput
            waitForEnd: true
            onStreamFinished: service.consumeAdmin(adminOutput.text)
        }
        stderr: StdioCollector { }
    }
    Process { id: notifyProcess; stderr: StdioCollector { } }

    Timer {
        id: adminTimeout
        // The local helper gives core's bounded worker 12 seconds.
        interval: 14000
        onTriggered: {
            adminProcess.running = false
            service.adminError = "The host did not respond. Try again."
            service.adminOperation = ""
            service.adminBinding = null
        }
    }
    // A pairing request has to reach the user without the panel being open, so
    // the panel polls while it is open and the watcher polls slowly always.
    Timer {
        interval: !!service.panelInstance && service.panelInstance.opened ? 4000 : 15000
        repeat: true
        running: Model.isConnected(service.connectionState)
        triggeredOnStart: true
        onTriggered: service.refreshDevices()
    }

    function reply(raw) {
        try {
            var decoded = JSON.parse(raw)
            return decoded && decoded.ok === true && decoded.result ? decoded.result : null
        } catch (error) { return null }
    }
    function refreshDevices() {
        if (!devicesProcess.running) devicesProcess.running = true
        if (!requestsProcess.running) requestsProcess.running = true
        if (!mediaRequestsProcess.running) mediaRequestsProcess.running = true
        if (service.panelInstance && service.panelInstance.page === "settings") service.refreshPreferences()
        service.refreshHostUnit()
    }
    function consumeDevices(raw) {
        // PLUG-2/PLUG-3: the projection lives in the model, so a field core adds
        // (PAIR-2 added `role`) is carried, not a reason to blank the page.
        var rows = Model.devices(service.reply(raw))
        if (!rows) {
            service.devicesError = "Device management is unavailable. Update the host service and reconnect."
            return
        }
        service.devices = rows
        service.revokedHidden = Model.revokedHidden(service.reply(raw))
        service.devicesLoaded = true
        service.devicesError = ""
    }
    function consumeRequests(raw) {
        var rows = Model.pairRequests(service.reply(raw))
        if (!rows) {
            service.pairingError = "Pairing is unavailable. Update the host service and reconnect."
            return
        }
        service.pairRequests = rows
        service.requestsLoaded = true
        service.pairingError = ""
        service.announcePending()
    }
    function consumeMediaRequests(raw) {
        var result = MediaPairing.parseLocalList(raw, Date.now())
        if (!result.ok) {
            service.mediaRequests = []
            service.mediaApprovals = []
            service.mediaApiReady = false
            service.mediaError = MediaPairing.errorMessage(result.code)
            return
        }
        service.mediaRequests = result.requests
        service.mediaApprovals = MediaPairing.localApprovals(result.requests, Date.now())
        service.mediaApiReady = true
        service.mediaError = ""
    }

    // #18: the request becomes an ordinary, clickable Omarchy notification.
    // --exec is the pattern Omarchy itself uses for first-run invitations.
    //
    // PAIR-2: nobody typed an invitation to get here, so the notification is
    // where the decision's evidence has to be - which device, from which
    // address, which key, and what one Approve hands over.
    function announcePending() {
        var seen = Object.assign({}, service.notifiedRequests)
        for (var i = 0; i < service.pendingRequests.length; i++) {
            var request = service.pendingRequests[i]
            if (seen[request.request_id]) continue
            var text = Model.requestNotification(request)
            if (!text) continue
            seen[request.request_id] = true
            if (notifyProcess.running) continue
            notifyProcess.command = ["omarchy-notification-send", "--app-name", "Omodachi",
                "-u", "critical", "-t", "30000",
                text.title, text.body,
                "--exec", "omarchy-shell", "shell", "summon", service.pluginId,
                JSON.stringify({view: "devices", request_id: request.request_id})]
            notifyProcess.running = true
        }
        service.notifiedRequests = seen
    }

    function startAdmin(operation, target, command, binding) {
        if (service.adminBusy || !command) return false
        service.adminOperation = operation
        service.adminTarget = target || ""
        service.adminBinding = binding || null
        service.adminMessage = ""
        service.adminError = ""
        adminProcess.command = command
        adminTimeout.restart()
        adminProcess.running = true
        return true
    }

    // One Approve. Core runs the Companion credential and the Sunshine grant
    // inside the same call.
    //
    // PAIR-3: this used to ask `mediaApiReady` first and, when the media list
    // had failed to parse, quietly issue an Approve without `--remote` - a
    // smaller approval than the card promised, with no way to tell. The flag
    // is now unconditional and the reply says whether the grant landed.
    function approve(requestId) {
        if (service.adminBusy) return
        var request = service.pendingRequests.filter(function(row) { return row.request_id === requestId })[0]
        var command = MediaPairing.approveCommand(service.pairRequests, requestId)
        if (!command || !request) {
            service.adminError = "This request changed. Refresh before approving."
            service.refreshDevices()
            return
        }
        service.startAdmin("approve_remote", requestId, command, {device_id: request.device_id})
    }
    // PAIR-3 §1.2: land the streaming grant on a device that only got the
    // companion half. The source request is the one that approved the device.
    function grantRemote(deviceId, sourceRequestId) {
        if (service.adminBusy) return
        var command = MediaPairing.grantRemoteCommand(deviceId, sourceRequestId)
        if (!command) { service.adminError = "This device has no approved pairing to grant Remote from."; return }
        service.startAdmin("grant_remote", deviceId, command, {device_id: deviceId})
    }
    // PAIR-3 §1.3: the local half of a Sunshine certificate attempt.
    function approveMedia(binding) {
        if (service.adminBusy) return
        var command = MediaPairing.mediaCommand(service.mediaRequests, binding, "approve", Date.now())
        if (!command) { service.adminError = "This pairing request changed. Refresh before approving."; service.refreshDevices(); return }
        service.startAdmin("media_approve", binding.attempt_id, command, binding)
    }
    function cancelMedia(binding) {
        if (service.adminBusy) return
        var command = MediaPairing.mediaCommand(service.mediaRequests, binding, "cancel", Date.now())
        if (!command) { service.adminError = "This pairing request changed. Refresh before cancelling."; service.refreshDevices(); return }
        service.startAdmin("media_cancel", binding.attempt_id, command, binding)
    }
    function reject(requestId) {
        if (service.adminBusy) return
        var command = MediaPairing.rejectCommand(service.pairRequests, requestId)
        if (!command) { service.adminError = "This request changed. Refresh before rejecting."; service.refreshDevices(); return }
        service.startAdmin("reject", requestId, command, null)
    }
    function revokeDevice(deviceId) {
        if (service.adminBusy) return
        // `revocable` is false for this plugin's own credential. The button is
        // not drawn for it either; this is the second of the two locks, and
        // core holds the third (`409 plugin_credential`).
        if (!service.devices.some(function(row) { return row.device_id === deviceId && row.revocable })) return
        service.startAdmin("revoke", deviceId, ["omodachi-host", "devices", "revoke", deviceId], null)
    }
    // PLUG-4 §3: clear the revoked devices core is holding out of the list. It
    // is the one action the footer offers, and core decides what is actually
    // removable - a device whose certificate is not back yet stays.
    function purgeDevices() {
        if (service.adminBusy || service.revokedHidden <= 0) return
        service.startAdmin("purge", "", ["omodachi-host", "devices", "purge"], null)
    }

    function consumeAdmin(raw) {
        adminTimeout.stop()
        var result = service.reply(raw), operation = service.adminOperation
        var target = service.adminTarget, binding = service.adminBinding
        service.adminOperation = ""
        service.adminBinding = null
        if (!result) {
            service.adminError = MediaPairing.errorMessage(MediaPairing.safeError(raw))
            service.refreshDevices()
            return
        }
        var outcome = MediaPairing.actionResult(operation, target, binding, result)
        if (outcome.grantRemote) {
            // The streaming half did not land. Remember which device and which
            // request, so its row can offer Grant Remote instead of the user
            // finding out on the iPad.
            service.grantRemoteDeviceId = outcome.deviceId
            service.grantRemoteRequestId = outcome.sourceRequestId
        } else if (operation === "grant_remote" && outcome.ok) {
            service.grantRemoteDeviceId = ""
            service.grantRemoteRequestId = ""
        }
        if (!outcome.ok) service.adminError = "The host's answer did not match this action. Refresh before retrying."
        else if (outcome.warning) service.adminError = outcome.message
        else service.adminMessage = outcome.message
        service.refreshDevices()
    }

    function mediaStatusFor(deviceId) {
        return service.mediaApiReady ? MediaPairing.deviceStatus(service.mediaRequests, deviceId) : "Remote status unavailable"
    }
    // PAIR-3 §1.2 / core §2.3: which request this device's Remote grant can be
    // repaired from. core reports it on the device row (it survives the
    // pairing request's 300 s TTL); a reply we just received wins, so the
    // repair is offered immediately after the Approve that missed it.
    function grantRemoteRequestFor(deviceId) {
        if (service.grantRemoteDeviceId === deviceId && service.grantRemoteRequestId !== "") return service.grantRemoteRequestId
        var row = service.devices.filter(function(value) { return value.device_id === deviceId })[0]
        return row && typeof row.source_request_id === "string" ? row.source_request_id : ""
    }
    // True only when core actually says so. An older core does not report the
    // column at all, and "not reported" must not be drawn as "not granted".
    function mediaAuthorizedFor(deviceId) {
        var row = service.devices.filter(function(value) { return value.device_id === deviceId })[0]
        return !!row && row.media_authorized === true
    }
    function mediaAuthorizationKnown(deviceId) {
        var row = service.devices.filter(function(value) { return value.device_id === deviceId })[0]
        return !!row && typeof row.media_authorized === "boolean"
    }
    function canGrantRemote(deviceId) {
        return service.mediaAuthorizationKnown(deviceId) && !service.mediaAuthorizedFor(deviceId)
            && service.grantRemoteRequestFor(deviceId) !== ""
    }

    function stop() {
        service.watchEnabled = false
        service.mediaApprovals = []
        summonTimeout.stop()
        adminTimeout.stop()
        preferencesReadTimeout.stop()
        preferencesSetTimeout.stop()
        service.preferenceChange = null
        preferencesReadProcess.running = false
        preferencesSetProcess.running = false
        mediaRequestsProcess.running = false
        devicesProcess.running = false
        requestsProcess.running = false
        adminProcess.running = false
        unitStateProcess.running = false
        unitActionProcess.running = false
        watchProcess.running = false
        summonProcess.running = false
    }
}
