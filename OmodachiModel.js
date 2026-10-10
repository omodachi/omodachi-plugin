.pragma library

// The frame vocabulary of `omodachi-host plugin-watch`, and nothing else.
// Everything the panel shows is derived here so the QML stays declarative and
// the same code can be driven from Node against ../omodachi-core/contracts.
//
// Core contract revision: omodachi.v1 (docs/local-integration.md).

// PLUG-2 validation policy — check only what this panel reads.
//
// Core keeps growing its frames: `bar.modules`, the agent_usage/panel/network/
// audio/power bar roles and the summon `view` all arrived after this file was
// written, and every time a closed whitelist here met one of them the plugin
// went to `connection: error` while the host was perfectly healthy. So a frame
// is checked for the fields the panel actually reads, by presence and type
// only. Unknown fields are ignored — `normalizeSnapshot` projects the frame
// down to the keys this file names, so a field nobody reads can never reach
// QML — and unknown enum values are carried through and drawn with a neutral
// fallback: an unrecognised bar role is a generic module, an unrecognised
// remote state is simply "not live", an unrecognised error code reads as
// "cannot reach the host service". Nothing unrecognised rejects a whole frame.
//
// What is still rejected is genuine malformation: a non-object result, a
// missing or non-numeric `revision`/`event_cursor`, an absent `instance_id`,
// and a state field that must be an object and is not.

// LITE-1c: the web app's name, in this one place. Every string the panel shows
// that names the web app is built from it, so a rename is this line.
var ODOMO_NAME = "Odomo"

var REQUIRED_STATE_FIELDS = ["host", "workspace", "focus", "agent", "herdr", "capabilities", "catalog", "remote"]
var OPTIONAL_STATE_FIELDS = ["bar", "remote_bar", "wake"]
var STATE_FIELDS = REQUIRED_STATE_FIELDS.concat(OPTIONAL_STATE_FIELDS)
var ENVELOPE_FIELDS = ["instance_id", "revision", "event_cursor", "device_id", "contract_revision"]
var STATES = ["loading", "ready", "limited", "setup_required", "permission_required", "unsupported", "error"]
// The error codes this panel has copy for. A code outside the list is still
// reported; connectionLabel/connectionHelp/iconTooltip all end in a fallback.
var ERROR_CODES = ["setup_required", "permission_required", "unavailable", "unsupported", "error"]
function validErrorCode(value) { return typeof value === "string" && /^[a-z][a-z0-9_.:-]{0,63}$/.test(value) }
// A host may report any of these - and, one day, one more. ready/resizing are
// the two in which the iPad is actually holding a screen, so they are the two
// the bar icon marks; every other name, known or not, is simply not live.
var REMOTE_STATES = ["offline", "creating", "ready", "resizing", "stopping", "released", "failed", "expired"]
var REMOTE_LIVE_STATES = ["ready", "resizing"]
// omodachi_core/bar.py:_REVIEWED_ROLES, verbatim, plus the unsupported slot.
// This is the vocabulary the panel has drawing for, NOT a filter: core adds
// roles (agent_usage, panel, network, audio and power all arrived this way)
// and a role we have never seen is a module we simply draw generically.
var BAR_ROLES = ["logo", "workspaces", "focused_window", "clock", "system_tray",
                 "agent_usage", "panel", "stream", "audio", "power", "network", "unsupported"]
// omodachi_core/bar_modules.py:STATUS_ROLES - the subset core can read a live
// status for. bar.modules carries one row per such widget the host has.
var BAR_STATUS_ROLES = ["audio", "power", "network"]
// Documented for readers; the panel does not gate a frame on it.
var BAR_SOURCE_STATUS = ["fixture", "available", "unavailable"]
// The neutral fallback: every bar entry is at least a module.
var BAR_ROLE_FALLBACK = "module"
function barRole(value) {
    return typeof value === "string" && BAR_ROLES.indexOf(value) >= 0 ? value : BAR_ROLE_FALLBACK
}
var ICON_STATES = ["absent", "idle", "linked", "remote"]

function clone(value) { try { return JSON.parse(JSON.stringify(value)) } catch (error) { return null } }
function hasOwn(value, key) { return value && Object.prototype.hasOwnProperty.call(value, key) }
function isObject(value) { return !!value && typeof value === "object" && !Array.isArray(value) }
function validNonEmptyString(value) { return typeof value === "string" && value.length > 0 && value.length <= 256 }
function validNonNegativeInteger(value) { return Number.isInteger(value) && value >= 0 }
function utf8ByteLength(value) {
    var bytes = 0
    for (var i = 0; i < value.length; i++) {
        var code = value.charCodeAt(i)
        if (code < 0x80) bytes += 1
        else if (code < 0x800) bytes += 2
        else if (code >= 0xd800 && code <= 0xdbff && i + 1 < value.length && value.charCodeAt(i + 1) >= 0xdc00 && value.charCodeAt(i + 1) <= 0xdfff) { bytes += 4; i++ }
        else if (code >= 0xd800 && code <= 0xdfff) return 0x7fffffff
        else bytes += 3
    }
    return bytes
}

// The panel reads `bar.position` and, when it draws the layout, the entries'
// ids and roles. Everything else in this object — source, source_status,
// revision, and whatever core adds next — is carried but never gated on.
function validBar(value) {
    if (!isObject(value)) return false
    if (hasOwn(value, "position") && value.position !== null && typeof value.position !== "string") return false
    for (var i = 0; i < 3; i++) {
        var region = ["left", "center", "right"][i]
        if (!hasOwn(value, region) || value[region] === null) continue
        if (!Array.isArray(value[region]) || value[region].length > 256) return false
        for (var j = 0; j < value[region].length; j++) {
            var item = value[region][j]
            if (!isObject(item) || !validNonEmptyString(item.id)) return false
        }
    }
    if (hasOwn(value, "modules") && value.modules !== null && !validBarModules(value.modules)) return false
    return true
}

// The projection the UI draws from: one row per bar entry, every role resolved
// through barRole so an entry core invented after this build still has a shape.
function barEntries(value) {
    var rows = []
    if (!isObject(value)) return rows
    for (var i = 0; i < 3; i++) {
        var region = ["left", "center", "right"][i], list = value[region]
        if (!Array.isArray(list)) continue
        for (var j = 0; j < list.length; j++) {
            var item = list[j]
            if (!isObject(item) || !validNonEmptyString(item.id)) continue
            rows.push({id: item.id, region: region, role: barRole(item.role),
                       known: barRole(item.role) === item.role})
        }
    }
    return rows
}

// A status is a small flat object of JSON scalars, or null when the host has
// no reading. Null is the answer for "unknown"; it is never a zero. A row with
// a role we do not know, or a reading we cannot draw, is not an error - it is
// a row the panel has nothing to say about, so it is projected away by
// barModules() rather than rejected here.
function validBarModules(value) {
    if (!Array.isArray(value) || value.length > 256) return false
    for (var i = 0; i < value.length; i++) {
        var row = value[i]
        if (!isObject(row) || !validNonEmptyString(row.id)) return false
        if (hasOwn(row, "status") && row.status !== null && !isObject(row.status)) return false
    }
    return true
}

// The readings the panel can actually draw: flat JSON scalars only. A nested
// or oversized value is dropped from its row; the row and the frame survive.
function barModules(value) {
    var rows = [], list = isObject(value) ? value.modules : null
    if (!Array.isArray(list)) return rows
    for (var i = 0; i < list.length; i++) {
        var row = list[i]
        if (!isObject(row) || !validNonEmptyString(row.id)) continue
        var status = null
        if (isObject(row.status)) {
            status = {}
            var keys = Object.keys(row.status)
            for (var k = 0; k < keys.length && k < 16; k++) {
                var item = row.status[keys[k]]
                if (item === null || typeof item === "boolean"
                    || (typeof item === "number" && Number.isFinite(item))
                    || (typeof item === "string" && item.length <= 256)) status[keys[k]] = item
            }
        }
        rows.push({id: row.id, role: barRole(row.role), status: status,
                   known: BAR_STATUS_ROLES.indexOf(row.role) >= 0})
    }
    return rows
}

// A host is not limited to ten workspaces. Opening a Remote screen creates
// more of them (the owned output gets its own), and those extra rows arrive
// with null catalog entries because there is no keybinding for them. A model
// that insisted on exactly ten, indexed 1..10, rejected every frame after a
// session started - which is how the panel ended up reporting an error while
// the session it was describing was running perfectly.
function validWorkspace(value) {
    if (!isObject(value)) return false
    if (value.active !== null && value.active !== undefined && (!Number.isInteger(value.active) || value.active < 1)) return false
    if (value.items === undefined) return true
    if (!Array.isArray(value.items) || value.items.length > 1024) return false
    var seen = {}
    for (var i = 0; i < value.items.length; i++) {
        var item = value.items[i]
        if (!isObject(item) || !Number.isInteger(item.id) || item.id < 1 || seen[item.id]) return false
        seen[item.id] = true
        if (item.label !== undefined && typeof item.label !== "string") return false
        if (item.active !== undefined && typeof item.active !== "boolean") return false
        if (item.window_count !== null && item.window_count !== undefined && !validNonNegativeInteger(item.window_count)) return false
        if (item.occupied !== null && item.occupied !== undefined && typeof item.occupied !== "boolean") return false
        var keys = ["select_entry_id", "move_entry_id"]
        for (var k = 0; k < keys.length; k++) {
            var entry = item[keys[k]]
            if (entry !== null && entry !== undefined && !validNonEmptyString(entry)) return false
        }
    }
    return true
}

// state.remote is the whole Remote session as the panel needs it: one session
// per host, one monotonic revision, no lease epochs (docs/remote-api.md).
// `state` must be a name; it does not have to be a name we already know. A
// state outside REMOTE_LIVE_STATES is simply not a live screen, which is the
// right answer for a state this build has never heard of. Likewise a backend
// or a mode core adds later is displayed verbatim rather than refused.
function validRemote(value) {
    if (!isObject(value)) return false
    if (!validNonEmptyString(value.state)) return false
    if (hasOwn(value, "revision") && value.revision !== null && !validNonNegativeInteger(value.revision)) return false
    if (value.session_id !== null && value.session_id !== undefined && !validNonEmptyString(value.session_id)) return false
    if (value.mode !== null && value.mode !== undefined && typeof value.mode !== "string") return false
    if (value.backend !== null && value.backend !== undefined && typeof value.backend !== "string") return false
    return true
}

// remote_bar is a complete projection, never a recursively merged patch.
// Clearing it must not retain the previous session's output or workspaces.
//
// Shape: omodachi_core/remote/session.py:bar_projection and
// omodachi_core/protocol.py:IDLE_REMOTE_BAR. Note `revision` is a string there
// and each workspace row is {id, monitor, windows, active, remote} - the client
// bar needs to know which rows live on the owned output, not a label.
function normalizeRemoteBar(value) {
    var inactive = {active: false}
    if (!isObject(value) || value.active !== true) return inactive
    if (!validNonEmptyString(value.session_id) || !validNonEmptyString(value.output_name)) return inactive
    var revision = typeof value.revision === "number" && validNonNegativeInteger(value.revision)
        ? String(value.revision) : value.revision
    if (!validNonEmptyString(revision)) return inactive
    var viewport = value.viewport
    if (!viewport || !Number.isFinite(viewport.width) || viewport.width <= 0
        || !Number.isFinite(viewport.height) || viewport.height <= 0) return inactive
    // An orientation core invents later still describes a live screen; only
    // the absence of one is a projection we cannot use.
    var orientation = validNonEmptyString(value.orientation) ? value.orientation : "landscape"
    if (!Array.isArray(value.workspaces) || value.workspaces.length > 1024) return inactive
    var rows = [], seen = {}
    for (var i = 0; i < value.workspaces.length; i++) {
        var row = value.workspaces[i]
        if (!isObject(row) || !Number.isInteger(row.id) || row.id < 1 || seen[row.id]) return inactive
        if (typeof row.active !== "boolean" || typeof row.remote !== "boolean") return inactive
        if (row.monitor !== null && row.monitor !== undefined && !validNonEmptyString(row.monitor)) return inactive
        if (row.windows !== null && row.windows !== undefined && !validNonNegativeInteger(row.windows)) return inactive
        seen[row.id] = true
        rows.push({id: row.id, monitor: validNonEmptyString(row.monitor) ? row.monitor : null,
                   windows: validNonNegativeInteger(row.windows) ? row.windows : 0,
                   active: row.active, remote: row.remote})
    }
    var result = {active: true, session_id: value.session_id, output_name: value.output_name,
        viewport: {width: viewport.width, height: viewport.height}, orientation: orientation,
        revision: revision, workspaces: rows, bar_insets: normalizeBarInsets(value.bar_insets)}
    if (value.logical_size && Number.isFinite(value.logical_size.width) && value.logical_size.width > 0
        && Number.isFinite(value.logical_size.height) && value.logical_size.height > 0)
        result.logical_size = {width: value.logical_size.width, height: value.logical_size.height}
    return result
}

// ---- REMOTE-SAFE-1: the bar clears the device's corners ----------------------
//
// In a Remote session - Extend or Take over (REMOTE-SAFE-1b) - the owned
// output is the device's exact shape, so the ends of the host bar on it sit
// under the device's rounded corners. In a takeover the whole desktop is on
// that output and `official_bar_position` puts the bar on its long edge; the
// laptop's own screens are off, and are never touched here anyway. Core publishes, on
// `remote_bar.bar_insets`, how many logical px of the owned output each corner
// covers at each end of the bar (top/bottom = the ends of a vertical bar,
// left/right = the ends of a horizontal one). The bar widget on *that* output,
// and only that one, moves the bar's two end sections inward by that much.
//
// A value this file cannot read is no insets at all, never a broken frame.
var BAR_INSET_EDGES = ["top", "bottom", "left", "right"]
// Anything larger is not a corner; core already caps it at a quarter of the bar.
var BAR_INSET_MAX = 1024
// hyprland.py:OWNED_NAME. The only outputs this plugin will ever touch the bar
// of are the ones core created for a session.
var OWNED_OUTPUT = /^OMODACHI-[0-9a-f]{16}$/
function normalizeBarInsets(value) {
    if (!isObject(value)) return null
    var result = {}, any = false
    for (var i = 0; i < BAR_INSET_EDGES.length; i++) {
        var edge = BAR_INSET_EDGES[i], number = value[edge]
        if (!Number.isInteger(number) || number < 0 || number > BAR_INSET_MAX) return null
        result[edge] = number
        if (number > 0) any = true
    }
    return any ? result : null
}

// What the bar on `screenName` should do, or null for "leave it exactly as the
// shell built it". Non-null only when all of these hold:
//   * a live Remote session (ready/resizing), in either mode - a finished
//     session gives null, which is what puts the bar back;
//   * `remote_bar` names this very screen, and it is one of core's own
//     OMODACHI-<16 hex> outputs - every other screen, including the laptop's,
//     always gets null;
//   * the bar's position is one this knows the axis of;
//   * at least one of the two ends is actually covered.
// `leading` is the bar's top (vertical) or left (horizontal) end, `trailing`
// the bottom or right one - Bar.qml's LeftModules and RightModules.
function barInsetsFor(snapshot, screenName, position) {
    if (!remoteActive(snapshot)) return null
    if (typeof screenName !== "string" || !OWNED_OUTPUT.test(screenName)) return null
    var bar = snapshot.remote_bar
    if (!isObject(bar) || bar.active !== true || bar.output_name !== screenName) return null
    var insets = normalizeBarInsets(bar.bar_insets)
    if (!insets) return null
    var result
    if (position === "left" || position === "right") result = {leading: insets.top, trailing: insets.bottom, vertical: true}
    else if (position === "top" || position === "bottom") result = {leading: insets.left, trailing: insets.right, vertical: false}
    else return null
    return result.leading > 0 || result.trailing > 0 ? result : null
}

// The end section's margin inside the bar: the shell's own (Style.space(8))
// unless the corner reaches further than that. Never less than the shell's.
function sectionMargin(shellMargin, inset) {
    var base = Number.isFinite(shellMargin) && shellMargin > 0 ? shellMargin : 0
    return Number.isInteger(inset) && inset > base ? inset : base
}

// A rectangle in the bar window's own coordinates, moved into its output's.
// A left or top bar window starts at the output's origin; a right or bottom
// one ends at the output's far edge. Null for anything that is not a rectangle.
function outputRect(local, position, screenSize, windowSize) {
    if (!isObject(local) || !isObject(screenSize) || !isObject(windowSize)) return null
    var values = [local.x, local.y, local.width, local.height, screenSize.width, screenSize.height,
                  windowSize.width, windowSize.height]
    for (var i = 0; i < values.length; i++) if (!Number.isFinite(values[i])) return null
    if (local.width <= 0 || local.height <= 0) return null
    var x = local.x, y = local.y
    if (position === "right") x += Math.max(0, screenSize.width - windowSize.width)
    else if (position === "bottom") y += Math.max(0, screenSize.height - windowSize.height)
    return {x: Math.round(x), y: Math.round(y), width: Math.round(local.width), height: Math.round(local.height)}
}

function normalizeSnapshot(value) {
    if (!isObject(value)) return null
    var result = {}, allowed = ENVELOPE_FIELDS.concat(STATE_FIELDS)
    for (var i = 0; i < allowed.length; i++) if (hasOwn(value, allowed[i])) result[allowed[i]] = clone(value[allowed[i]])
    if (hasOwn(value, "remote_bar")) result.remote_bar = normalizeRemoteBar(value.remote_bar)
    return result
}

// No key whitelist. A field this build does not know is a field core added,
// and normalizeSnapshot has already dropped it before we get here; a frame is
// never refused for carrying one.
function isStateSnapshot(snapshot) {
    if (!isObject(snapshot)) return false
    if (!validNonEmptyString(snapshot.instance_id) || !validNonNegativeInteger(snapshot.revision) || !validNonNegativeInteger(snapshot.event_cursor)) return false
    for (var i = 0; i < REQUIRED_STATE_FIELDS.length; i++) {
        var field = REQUIRED_STATE_FIELDS[i]
        if (!hasOwn(snapshot, field) || !isObject(snapshot[field])) return false
    }
    if (!validRemote(snapshot.remote)) return false
    if (hasOwn(snapshot, "bar") && !validBar(snapshot.bar)) return false
    // A remote_bar we cannot read is an inactive one, not a broken frame:
    // normalizeRemoteBar answers {active: false} and the panel says "Not
    // started" rather than the whole panel saying "error".
    if (hasOwn(snapshot, "remote_bar") && snapshot.remote_bar !== null && !isObject(snapshot.remote_bar)) return false
    if (!validWorkspace(snapshot.workspace)) return false
    if (snapshot.focus.target_token !== null && snapshot.focus.target_token !== undefined && !validNonEmptyString(snapshot.focus.target_token)) return false
    return true
}

function remoteState(snapshot) {
    return isStateSnapshot(snapshot) ? snapshot.remote.state : "offline"
}
// The one predicate the bar icon branches on.
function remoteActive(snapshot) {
    return REMOTE_LIVE_STATES.indexOf(remoteState(snapshot)) >= 0
}

// MENU-2 / A-67. A takeover has the host's own screens blanked and the user's
// hands on the tablet, so this icon has nothing it can usefully open: a popup
// on this machine is a popup nobody is looking at, and the host's settings are
// not the App's to change from there. Both buttons say so instead.
//
// Extended screen is the opposite case — the user is sitting here, this screen
// is on, and the popup is exactly what they asked for — so the lock is the
// *mode*, not merely a live session.
function takeoverLocked(snapshot) {
    return remoteActive(snapshot) && remoteMode(snapshot) === "takeover"
}
function remoteMode(snapshot) {
    if (!isStateSnapshot(snapshot)) return null
    return typeof snapshot.remote.mode === "string" ? snapshot.remote.mode : null
}
// One short sentence with one verb, the same on both buttons.
var TAKEOVER_LOCK_NOTICE = "Locked while a takeover session is running"

function asState(snapshot) {
    if (!isStateSnapshot(snapshot)) return "loading"
    if (snapshot.host.connected !== true) return "setup_required"
    if (snapshot.capabilities.desktop === false && snapshot.capabilities.terminal === false) return "limited"
    return "ready"
}

function isConnected(state) { return ["ready", "limited"].indexOf(state) >= 0 }

// Study 02 D-13: four states, expressed only through opacity, activeColor and
// one indicator. Never through a second colour we invented.
function iconState(state, remoteIsActive) {
    if (!isConnected(state)) return state === "loading" ? "idle" : "absent"
    if (remoteIsActive === true) return "remote"
    return "linked"
}
// PLUGIN-COLOR-1: how each state wears the bar's two colours. The active
// colour is the shell's `bar.urgent` (theme `bar.active`, which falls back to
// `urgent` - red on most themes), so it means what a recording indicator
// means: someone sees or controls this screen right now. Only "remote" is
// that. A linked phone is the healthy everyday state and reads as the plain
// bar foreground; absent, and anything while a takeover holds the screen,
// is dimmed as before.
function iconLook(state, takeoverLocked) {
    var remote = state === "remote"
    return {dimmed: state === "absent" || takeoverLocked === true,
            active: remote,
            indicator: remote}
}
function iconTooltip(state, remoteIsActive, remote) {
    if (iconState(state, remoteIsActive) === "remote") {
        var mode = remote && remote.mode === "takeover" ? "Takeover" : "Extended screen"
        var backend = remote && typeof remote.backend === "string" ? " · " + remote.backend : ""
        // REMOTE-STOP-1: the left click belongs to the device; the right one
        // is this computer's own panel, which is where the session can end.
        var line = remote && remote.mode === "takeover"
            ? TAKEOVER_LOCK_NOTICE
            : "Click to bring the panel back to the device, right-click to end it here"
        return "Omodachi · Remote in progress — " + mode + backend + "\n" + line
    }
    if (state === "ready") return "Omodachi · connected\nClick for the panel, right-click for Settings"
    if (state === "limited") return "Omodachi · connected, some features unavailable\nClick for the panel, right-click for Settings"
    if (state === "loading") return "Omodachi · checking the host service"
    if (state === "permission_required") return "Omodachi · the panel needs permission from the host service"
    if (state === "setup_required") return "Omodachi · Host is not running on this computer\nClick to install or start it"
    return "Omodachi · cannot reach the host service\nClick for setup"
}

function sanitizeState(snapshot) {
    var valid = isStateSnapshot(snapshot) ? snapshot : {}
    var remote = valid.remote || {}
    return {state: asState(valid),
        hostName: valid.host && typeof valid.host.name === "string" ? valid.host.name : null,
        connected: !!(valid.host && valid.host.connected === true),
        workspace: valid.workspace && valid.workspace.active !== undefined ? valid.workspace.active : null,
        agentStatus: valid.agent && typeof valid.agent.status === "string" ? valid.agent.status : "unknown",
        herdrAvailable: !!(valid.herdr && valid.herdr.available === true),
        remoteState: typeof remote.state === "string" ? remote.state : "offline",
        remoteMode: typeof remote.mode === "string" ? remote.mode : null,
        remoteBackend: typeof remote.backend === "string" ? remote.backend : null,
        capabilityState: valid.capabilities || {},
        barPosition: valid.bar && typeof valid.bar.position === "string" ? valid.bar.position : null,
        revision: validNonNegativeInteger(valid.revision) ? valid.revision : null,
        eventCursor: validNonNegativeInteger(valid.event_cursor) ? valid.event_cursor : null,
        instanceId: validNonEmptyString(valid.instance_id) ? valid.instance_id : null}
}

function isDeviceEvent(event) {
    return !!(isObject(event) && Number.isInteger(event.seq) && event.seq > 0 && validNonEmptyString(event.event_id)
        && validNonEmptyString(event.type) && isObject(event.payload) && typeof event.ts === "number" && Number.isFinite(event.ts))
}

function parseFrame(line) {
    if (typeof line !== "string" || line.length === 0 || utf8ByteLength(line) > 4 * 1024 * 1024) return null
    var value
    try { value = JSON.parse(line) } catch (error) { return null }
    if (!isObject(value)) return null
    // Envelopes are recognised by the fields that decide what they are, not by
    // an exact key set: a `warnings` or `served_at` core adds to an envelope
    // used to turn every frame after it into invalid_frame.
    if (value.ok === true && hasOwn(value, "result")) {
        var normalized = normalizeSnapshot(value.result)
        if (isStateSnapshot(normalized)) return {kind: "snapshot", snapshot: normalized}
        return null
    }
    if (value.ok === false) {
        // An error code we have no copy for still reports as an error; the
        // presentation helpers all end in a "cannot reach the host" fallback.
        if (!validErrorCode(value.error)) return {kind: "error", code: "error", message: "unknown_error"}
        return {kind: "error", code: value.error,
                message: typeof value.message === "string" ? value.message : value.error}
    }
    if (hasOwn(value, "event") && validNonEmptyString(value.instance_id) && isDeviceEvent(value.event)
        && (value.after_cursor === undefined || value.after_cursor === null || validNonNegativeInteger(value.after_cursor)))
        return {kind: "event", event: clone(value.event), instance_id: value.instance_id,
                after_cursor: value.after_cursor === null ? undefined : value.after_cursor}
    return null
}

// Not every event is a state patch. `remote.session.changed` is a notification
// whose payload is {id, revision, state, reason} - and that `revision` is the
// session's, not the state's. Reading it as a state revision made every frame
// after a session start look stale, which stalled the whole stream. A payload
// with no state field carries no revision either; the event only moves the
// cursor forward.
function exactStatePatch(payload) {
    if (!isObject(payload)) return null
    var patch = {}, keys = Object.keys(payload), stateFields = 0
    for (var i = 0; i < keys.length; i++) {
        var key = keys[i]
        if (key === "revision" || STATE_FIELDS.indexOf(key) < 0) continue
        stateFields += 1
        if (key === "remote_bar") { patch[key] = normalizeRemoteBar(payload[key]); continue }
        if (!isObject(payload[key])) return null
        patch[key] = clone(payload[key])
    }
    if (stateFields > 0 && validNonNegativeInteger(payload.revision)) patch.revision = payload.revision
    return patch
}

function mergeObject(base, patch) {
    // PLUG-5, reproduced on the clean VM at the first event after `omarchy
    // plugin add`: a patch can name a state field the snapshot does not have
    // yet. `clone(undefined)` and `clone(null)` are both null, and assigning
    // into null throws "TypeError: Value is null and could not be converted to
    // an object" out of consumeLine - which took the whole frame with it and
    // left the panel in `error` with a daemon that was answering perfectly
    // well. There is nothing to merge with, so the patch *is* the value.
    if (!isObject(base)) return clone(patch)
    var result = clone(base)
    Object.keys(patch).forEach(function(key) {
        if (isObject(patch[key]) && isObject(result[key])) result[key] = mergeObject(result[key], patch[key])
        else result[key] = clone(patch[key])
    })
    return result
}

function mergePatch(snapshot, event, instanceId, afterCursor) {
    if (!isStateSnapshot(snapshot) || !isDeviceEvent(event) || instanceId !== event.instance_id) return null
    if (event.type === "resync.required") return {kind: "resync", instance_id: instanceId}
    if (event.seq <= snapshot.event_cursor) return null
    if (afterCursor === undefined ? event.seq !== snapshot.event_cursor + 1 : afterCursor !== snapshot.event_cursor) return null
    var next = clone(snapshot), patch = exactStatePatch(event.payload)
    if (patch) {
        if (patch.revision !== undefined && patch.revision <= snapshot.revision) return null
        Object.keys(patch).forEach(function(key) {
            // remote and remote_bar are replaced whole: a released session must
            // not keep the previous session's id, mode or output.
            if (key === "remote_bar" || key === "remote") next[key] = clone(patch[key])
            else if (key !== "revision") next[key] = mergeObject(next[key], patch[key])
        })
        if (patch.revision !== undefined) next.revision = patch.revision
    }
    next.event_cursor = event.seq
    if (!isStateSnapshot(next)) return null
    return {kind: "event", event: clone(event), snapshot: next}
}

function consumeLine(line, snapshot, instanceId) {
    var frame = parseFrame(line)
    if (!frame) return {kind: "invalid", code: "error", message: "invalid_frame"}
    if (frame.kind === "error") return frame
    if (frame.kind === "snapshot") return {kind: "snapshot", snapshot: frame.snapshot}
    if (!isStateSnapshot(snapshot) || frame.instance_id !== instanceId)
        return {kind: "invalid", code: "error", message: "event_requires_current_snapshot"}
    return mergePatch(snapshot, Object.assign({}, frame.event, {instance_id: frame.instance_id}), instanceId, frame.after_cursor)
        || {kind: "invalid", code: "error", message: "invalid_event_cursor"}
}

// `omodachi-host panel-summon [--view overview|keybindings|settings]` answers
// route=local when no session owns the host, and route=remote after publishing
// the recall to the session's device. The answer echoes the view, so the recall
// that reaches the iPad names the overlay it is recalling.
//
// omodachi_core/protocol.py:PANEL_VIEWS. The panel asks for a view core knows;
// anything else would make argparse exit non-zero, which reads as "the host is
// unavailable" and would put the local panel on top of a live session.
//
// ARCH-1 / Study 04 A-59: `settings` is the third. This widget is the way to
// *this app's* preferences, and while a session is up they are on the device
// holding the picture — so a left click from a session asks for that panel
// rather than for the overview it used to ask for. The right button still opens
// the local QML panel; nothing about that path changed.
var PANEL_VIEWS = ["overview", "keybindings", "settings"]

function summonCommand(view) {
    return ["omodachi-host", "panel-summon", "--view", PANEL_VIEWS.indexOf(view) >= 0 ? view : "overview"]
}

// Core keeps adding to this result - SPEC-E3 §1.5 put `view` in it - and a
// model frozen on the shape of the day reads every later core as a failure and
// falls back to opening the local panel, which is the one thing a live session
// must never cause. So: check only the fields this panel acts on, require
// `view` to be a view name rather than one particular name, and carry every
// other field through untouched.
function classifySummon(frame, requestedView) {
    if (!isObject(frame) || frame.ok !== true || !isObject(frame.result)) return {ok: false, code: "error"}
    var result = frame.result
    var route = result.route
    if (route !== "local" && route !== "remote") return {ok: false, code: "unsupported"}
    // A core older than SPEC-E3 §1.5 omits `view`; it acted on the one we asked for.
    var view = result.view === undefined || result.view === null
        ? (validNonEmptyString(requestedView) ? requestedView : "overview") : result.view
    if (!validNonEmptyString(view)) return {ok: false, code: "error"}
    if (route === "local" && result.opened !== false) return {ok: false, code: "error"}
    if (route === "remote" && (!validNonEmptyString(result.owner_device_id) || !validNonEmptyString(result.session_id)
        || !validNonNegativeInteger(result.revision))) return {ok: false, code: "error"}
    return {ok: true, route: route, view: view, value: result}
}

// ---- REMOTE-STOP-1: ending a session from this computer --------------------
// The person at this computer can always end a Remote session, whoever's it
// is. Overview offers it while one is live; the argv is a fixed list plus the
// id of the session the panel is showing, so a click can never end a session
// that started after the page was drawn. core checks the caller is this user
// (the verified Unix peer); the plugin sends no credential at all.
var SESSION_ID = /^rs_[0-9a-f]{32}$/

function liveSessionId(snapshot) {
    if (!remoteActive(snapshot)) return ""
    var id = snapshot.remote.session_id
    return typeof id === "string" && SESSION_ID.test(id) ? id : ""
}
function canEndRemote(snapshot) { return liveSessionId(snapshot) !== "" }

function remoteStopCommand(snapshot, sessionId) {
    var id = liveSessionId(snapshot)
    if (!id || id !== sessionId) return null
    return ["omodachi-host", "remote", "stop", "--session-id", id]
}

// The name a person gave the device when it paired - the one its pairing card
// showed - from the Devices list the panel already holds. "" when the list has
// no usable name for it: a raw device id is never a name to show here.
function deviceDisplayName(devices, deviceId) {
    if (!Array.isArray(devices) || !validNonEmptyString(deviceId)) return ""
    var row = devices.filter(function(item) { return isObject(item) && item.device_id === deviceId })[0]
    var name = row ? cleanName(row.device_name) : ""
    return name && name !== deviceId ? name : ""
}

// What the End button's one line under the panel says afterwards. `raw` is the
// CLI's stdout: JSON on success and on a refusal core explains, nothing at all
// from a core older than REMOTE-STOP-1 (argparse wants a credential there).
// `devices` is the panel's Devices list, for the holding device's name.
function remoteStopOutcome(raw, sessionId, devices) {
    var value = null
    try { value = JSON.parse(raw) } catch (error) { value = null }
    if (!isObject(value))
        return {ok: false, message: "This host service cannot end a session from here yet. Update Omodachi Host, or end it on the device."}
    if (value.ok !== true) {
        if (value.error === "session_not_found") return {ok: true, message: "That Remote session had already ended."}
        var code = validErrorCode(value.error) ? value.error.replace(/_/g, " ") : "error"
        return {ok: false, message: "The host did not end the session (" + code + ")."}
    }
    var result = isObject(value.result) ? value.result : {}
    var rows = Array.isArray(result.sessions) ? result.sessions : []
    var row = rows.filter(function(item) { return isObject(item) && item.session_id === sessionId })[0]
    if (!row) return {ok: true, message: "That Remote session had already ended."}
    if (row.released !== true) {
        var steps = (Array.isArray(row.errors) ? row.errors : []).map(function(item) {
            return isObject(item) && validErrorCode(item.step) ? item.step : ""
        }).filter(function(step) { return step !== "" })
        return {ok: false, message: "The session ended, but the host could not put back: "
            + (steps.length ? steps.join(", ") : "everything") + ". Run omodachi-host remote recover."}
    }
    var owner = deviceDisplayName(devices, row.owner_device_id) || "the device"
    return {ok: true, message: "Remote session ended; " + owner + " was told it ended on this computer."}
}

// ---- presentation ---------------------------------------------------------
// A reachable host service is not a connected Remote screen; say so exactly.

function display(value, fallback) {
    return value === undefined || value === null || value === "" ? fallback : String(value)
}

function connectionLabel(state) {
    if (state === "loading") return "Checking the host service…"
    if (state === "permission_required") return "Permission required"
    if (state === "setup_required") return "Host is not running"
    if (state === "unsupported") return "Host version unsupported"
    if (state === "limited") return "Connected · some features unavailable"
    if (state === "ready") return "Connected"
    return "Cannot reach the host service"
}

function remoteLabel(snapshot) {
    if (!isStateSnapshot(snapshot)) return "Not started"
    var remote = snapshot.remote
    if (REMOTE_LIVE_STATES.indexOf(remote.state) < 0) return "Not started"
    var bar = snapshot.remote_bar && snapshot.remote_bar.active ? snapshot.remote_bar : null
    var parts = [remote.mode === "takeover" ? "Takeover" : "Extended screen", display(remote.backend, "backend unknown")]
    if (bar) parts.push(Math.round(bar.viewport.width) + "×" + Math.round(bar.viewport.height))
    if (remote.state === "resizing") parts.push("resizing")
    return parts.join(" · ")
}

// Study 02 §10 Overview: who this machine is, whether Host is there, whether
// anyone is connected right now, and what they are connected with.
function overviewRows(snapshot, state) {
    var valid = isStateSnapshot(snapshot) ? snapshot : {}
    var host = valid.host || {}, agent = valid.agent || {}, herdr = valid.herdr || {}
    var capabilities = valid.capabilities || {}
    return [
        {label: "Machine", value: display(host.name, "Waiting for the host service")},
        {label: "Host", value: display(capabilities.contract_revision, "omodachi") + " · " + connectionLabel(state)},
        {label: "Remote", value: remoteLabel(valid)},
        {label: "Agent", value: display(agent.kind, "Agent") + " · " + display(agent.status, "unknown")},
        {label: "Herdr", value: herdr.available === true ? "Available" : "Unavailable"},
        {label: "Capabilities", value: (capabilities.desktop === true ? "Remote" : "no Remote")
            + " · " + (capabilities.terminal === true ? "terminal" : "no terminal")}
    ]
}

// --- PLUG-3: the devices list and the pairing requests ----------------------
//
// Both lists arrive from `omodachi-host devices list` / `pair pending`, and
// both grew fields in PAIR-2 (`role`, `remote_addr`). They are projected here
// under the same PLUG-2 rule as every other frame: read what the page draws,
// carry an unknown enum through with a neutral fallback, and never drop a whole
// list because one row used a name this build has not seen.
// LITE-1a: `web` is a browser running Odomo, the web app - the same credential
// reaching fewer routes, never the screen and never SSH.
var DEVICE_ROLES = ["companion", "plugin", "web"]
// A host from before PAIR-2 sends no `role` at all. Everything it lists is a
// companion, which is what it was before the plugin's own row was labelled.
function deviceRole(value) {
    return typeof value === "string" && DEVICE_ROLES.indexOf(value) >= 0 ? value : "companion"
}
function validDeviceId(value) {
    return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(value)
}
function devices(result) {
    if (!isObject(result) || !Array.isArray(result.devices)) return null
    var rows = []
    for (var i = 0; i < result.devices.length && i < 256; i++) {
        var row = result.devices[i]
        if (!isObject(row) || !validDeviceId(row.device_id)) continue
        // CORE-2: `expired` is a device whose only credentials ran out. It is
        // still something to act on - one approval on the device away from
        // working, or one Remove from gone - so it is drawn, not dropped.
        if (["authorized", "revoked", "expired"].indexOf(row.status) < 0) continue
        rows.push({device_id: row.device_id, status: row.status,
            active_credentials: Number.isInteger(row.active_credentials) ? row.active_credentials : 0,
            // CORE-2: when the device's live credential stops working. `null`
            // is "this host has not seen that credential since it started
            // keeping issue times", which is not the same as "never".
            expires_at: Number.isInteger(row.expires_at) && row.expires_at > 0 ? row.expires_at : null,
            device_name: typeof row.device_name === "string" ? row.device_name : "",
            role: deviceRole(row.role),
            // PAIR-3 / core §2.3: "companion yes, streaming no" is the state
            // that made Remote look unpaired, so it is carried onto the row.
            // `undefined` means an older core does not report it, which is not
            // the same as `false` and must not be drawn as a missing grant.
            media_authorized: typeof row.media_authorized === "boolean" ? row.media_authorized : undefined,
            // The request the Remote grant can be repaired from. core keeps it
            // past the pairing request's 300 s TTL.
            source_request_id: /^pair_[0-9a-f]{32}$/.test(row.source_request_id) ? row.source_request_id : "",
            // The one row this panel must not offer a button for: revoking it
            // takes away the page the revoke would be undone from, and core
            // answers `plugin_credential` to anything that tries.
            revocable: deviceRole(row.role) !== "plugin" && (row.status === "authorized" || row.status === "expired"),
            // LITE-1b: a web device's push, as core reports it. `null` is an
            // older core, or not a web device: nothing to draw.
            push: deviceRole(row.role) === "web" && isObject(row.push) && typeof row.push.subscribed === "boolean"
                && typeof row.push.enabled === "boolean" ? {subscribed: row.push.subscribed, enabled: row.push.enabled} : null})
    }
    return rows
}
// CORE-2 §1: a device credential lives 30 days and the device renews it by
// itself in the last 7. The row says when it ends; inside those 7 days it is
// drawn in the theme's yellow, because a device that has not come back to
// renew by then is one that will need pairing again.
var EXPIRY_WARNING_SECONDS = 7 * 86400
function isoDay(seconds) {
    // Days since 1970-01-01 to a civil date (H. Hinnant), UTC, with no Date:
    // the panel and the tests read the same answer.
    var z = Math.floor(seconds / 86400) + 719468
    var era = Math.floor(z / 146097)
    var doe = z - era * 146097
    var yoe = Math.floor((doe - Math.floor(doe / 1460) + Math.floor(doe / 36524) - Math.floor(doe / 146096)) / 365)
    var doy = doe - (365 * yoe + Math.floor(yoe / 4) - Math.floor(yoe / 100))
    var mp = Math.floor((5 * doy + 2) / 153)
    var day = doy - Math.floor((153 * mp + 2) / 5) + 1
    var month = mp < 10 ? mp + 3 : mp - 9
    var year = yoe + era * 400 + (month <= 2 ? 1 : 0)
    return year + "-" + (month < 10 ? "0" : "") + month + "-" + (day < 10 ? "0" : "") + day
}
function deviceExpiry(row, now) {
    if (!isObject(row) || row.role === "plugin" || !Number.isInteger(now)) return {text: "", soon: false}
    if (row.status === "expired") {
        return {text: "Credential expired" + (row.expires_at ? " on " + isoDay(row.expires_at) : "")
                      + " - approve the device's next pairing request to bring it back", soon: true}
    }
    if (row.status !== "authorized" || !Number.isInteger(row.expires_at)) return {text: "", soon: false}
    var left = row.expires_at - now
    if (left <= 0) return {text: "Credential expired on " + isoDay(row.expires_at), soon: true}
    var days = Math.ceil(left / 86400)
    var soon = left <= EXPIRY_WARNING_SECONDS
    return {text: "Expires " + isoDay(row.expires_at) + " (UTC)"
                  + (soon ? " - in " + days + (days === 1 ? " day" : " days")
                            + "; the device renews it the next time it opens" : ""),
            soon: soon}
}
// The theme's own yellow, from the colors.toml Omarchy renders for every
// themed application. No hex is hardcoded here; a theme without one gets the
// fallback the caller passes (the accent).
function themeYellow(text, fallback) {
    var match = /^\s*yellow\s*=\s*"(#[0-9a-fA-F]{6})"/m.exec(typeof text === "string" ? text : "")
    return match ? match[1] : fallback
}

// PLUG-4: how many revoked devices core left out of the list it just answered.
// It is a footer offering one cleanup, never a list of rows nobody can act on -
// 32 dead test devices against one real one is what this page used to draw. An
// older core does not report it, which reads as zero: nothing to offer.
function revokedHidden(result) {
    if (!isObject(result)) return 0
    var value = result.revoked_hidden
    return Number.isInteger(value) && value > 0 && value <= 4096 ? value : 0
}

// `SHA256:` plus the first twelve characters of the digest. It is a label for
// the card, not a comparison the user is asked to make character by character.
function shortSshFingerprint(value) {
    if (typeof value !== "string" || !/^SHA256:[A-Za-z0-9+/]{43}$/.test(value)) return ""
    return "SHA256:" + value.slice(7, 19) + "…"
}
// RELEASE-9 (B4). The requester chose this name, and it is about to be a
// notification title and the heading of the card someone approves from. Core
// already cleans it; this does it again for an older core. Control and format
// characters (newlines, bidi overrides, zero-width joiners) go, whitespace runs
// become one space, and it stops at 48 characters. Emoji and accents stay.
var NAME_LIMIT = 48
function cleanName(value) {
    if (typeof value !== "string" || value.length > 256) return ""
    var text = value.replace(/[\t\n\v\f\r\u0085\u2028\u2029]/g, " ")
        .replace(/[\u0000-\u001f\u007f-\u009f\u00ad\u061c\u180e\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u206f\ufeff\ufff9-\ufffb]/g, "")
        .replace(/\s+/g, " ").trim()
    return Array.from(text).slice(0, NAME_LIMIT).join("").trim()
}
// TAIL-2 P1-6. `via` is core's `{kind, peer_name, login}`; an older core sends
// none, and then a 100.64/10 or fd7a:115c:a1e0::/48 source is still read as
// the tailnet so its address is never what the card shows.
function isTailnetAddress(value) {
    if (typeof value !== "string") return false
    var v4 = /^100\.(\d{1,3})\.\d{1,3}\.\d{1,3}$/.exec(value)
    if (v4) return Number(v4[1]) >= 64 && Number(v4[1]) <= 127
    return /^fd7a:115c:a1e0:/i.test(value)
}
function requestVia(value, remoteAddr) {
    var kinds = ["lan", "tailnet", "loopback", "other"]
    var kind = isObject(value) && kinds.indexOf(value.kind) >= 0 ? value.kind
        : isTailnetAddress(remoteAddr) ? "tailnet" : ""
    function text(raw, limit) {
        var clean = cleanName(typeof raw === "string" ? raw : "")
        return Array.from(clean).slice(0, limit).join("")
    }
    return {kind: kind,
            peer_name: isObject(value) ? text(value.peer_name, 64) : "",
            login: isObject(value) ? text(value.login, 128) : ""}
}
// The card's heading: `"iPad" via Tailscale` on the tailnet, otherwise the
// name alone. The login, when Tailscale knows one, is in the detail line.
// LITE-1a: a browser is named by what core calls it ("Web app · Safari on
// iPhone"); NEXT-1: it has the same `via` as the App, so the same suffix.
function requestTitle(row) {
    if (!isObject(row)) return ""
    var name = row.web === true ? (row.client_label || "Web app")
        : "\u201c" + (cleanName(row.device_name) || "Unnamed device") + "\u201d"
    var via = isObject(row.via) && row.via.kind === "tailnet" ? " via Tailscale" : ""
    return name + via + " wants to connect"
}
function pairRequests(result) {
    if (!isObject(result) || !Array.isArray(result.requests)) return null
    var rows = []
    for (var i = 0; i < result.requests.length && i < 256; i++) {
        var row = result.requests[i]
        if (!isObject(row) || !/^pair_[0-9a-f]{32}$/.test(row.request_id)) continue
        if (typeof row.device_name !== "string" || !validDeviceId(row.device_id)) continue
        var via = requestVia(row.via, row.remote_addr)
        var web = isObject(row.client) && row.client.kind === "web"
        rows.push({request_id: row.request_id, device_id: row.device_id,
            device_name: cleanName(row.device_name) || "Unnamed device",
            status: typeof row.status === "string" ? row.status : "",
            // LITE-1a: a browser asking. Core formats the label ("Web app ·
            // Safari on iPhone") and cleans the browser's half like a name;
            // it is cleaned again here for an older core. A web request is
            // never a screen and never SSH, so its card says less.
            web: web,
            client_label: web ? (cleanName(row.client_label) || "Web app") : "",
            // PAIR-2: with no invitation to vouch for it, where the request came
            // from is what tells "the iPad in my hand" from "something else on
            // this network". It is context for the decision, not authorization.
            // TAIL-2 P1-6: over the tailnet the card says who Tailscale says it
            // is, and the raw 100.x is not carried at all.
            remote_addr: via.kind === "tailnet" ? ""
                : typeof row.remote_addr === "string" && row.remote_addr.length <= 45 ? row.remote_addr : "",
            via: via,
            // TAIL-2 P0-2: this device already holds a credential here.
            already_paired: row.already_paired === true,
            ssh_fingerprint: shortSshFingerprint(row.ssh_fingerprint)})
    }
    return rows
}

// One line, the same on the card and in the notification, so what Approve gives
// away is written down before it is pressed rather than after.
//
// RELEASE-9 (B4): all of it. "screen · terminal · agent" left out that the
// device also drives the keyboard and mouse, attaches to every Herdr session,
// runs every Omarchy menu row (shutdown and remove among them) and - when the
// request carries a key - gets an SSH login.
var GRANT_LINE = "Approving grants: screen, keyboard and mouse · agent · Herdr sessions · every menu action, including power and remove"
// LITE-1a: what a web app gets, which is less, and says what it never gets.
var WEB_GRANT_LINE = "Approving grants this browser: every menu action, including power and remove · keybindings · notifications. Never the screen, never SSH."
function grantLine(row) {
    if (isObject(row) && row.web === true) return WEB_GRANT_LINE
    if (isObject(row) && row.ssh_fingerprint)
        return "Approving grants: screen, keyboard and mouse · SSH login (" + row.ssh_fingerprint
            + ") · agent · Herdr sessions · every menu action, including power and remove"
    return GRANT_LINE
}
function requestDetail(row) {
    if (!isObject(row)) return ""
    var parts = [row.device_id]
    var via = isObject(row.via) ? row.via : {kind: ""}
    if (via.kind === "tailnet") {
        // Never the 100.x: who Tailscale on this computer says asked.
        var who = via.peer_name ? "Tailscale device " + via.peer_name : "Tailscale"
        parts.push("via " + who + (via.login ? " (" + via.login + ")" : ""))
    } else if (row.remote_addr) parts.push("from " + row.remote_addr)
    if (row.ssh_fingerprint) parts.push(row.ssh_fingerprint)
    if (row.already_paired === true) parts.push("already paired - approving replaces its credential")
    return parts.join(" · ")
}
// The sentence under the buttons, which used to promise a Remote certificate
// to every request.
function approvalNote(row) {
    if (isObject(row) && row.web === true)
        return "Approving gives this browser its own credential, and nothing else: no Remote certificate, no SSH key."
    return "Approving finishes everything: the companion credential and this host's Remote certificate, in one call. No PIN, no Sunshine page."
}
// LITE-1b: what a device row is called. The name it paired with; for a row
// without one, what kind of device it is - never the raw `odomo-…`/`ios-…` id
// (a long-standing backlog item: the id is for the machine, not the person).
// A web device paired before LITE-1c still has an old `lite-…` id; nothing
// here depends on either prefix.
function deviceTitle(row) {
    if (!isObject(row)) return "Unnamed device"
    if (row.role === "plugin") return "This computer's panel"
    var name = cleanName(row.device_name)
    if (name && name !== row.device_id) return name
    return row.role === "web" ? "Web app" : "Unnamed device"
}
// The device a request or a certificate attempt belongs to, by name, from the
// Devices list the panel already holds.
function deviceLabelFor(devices, deviceId) {
    return deviceDisplayName(devices, deviceId) || "A paired device"
}
// LITE-1b: push to a web device. One line for its row.
function pushLine(row) {
    if (!isObject(row) || row.role !== "web" || !isObject(row.push)) return ""
    if (!row.push.enabled) return "Push: off on this computer"
    return row.push.subscribed ? "Push: on" : "Push: not turned on in this browser"
}
// What Remove takes away, said for the kind of device it is.
function removeNote(row) {
    if (isObject(row) && row.role === "web")
        return "This web app loses its credential and its push subscription. It has to be approved again next time."
    return "This device loses its companion credential and its Remote certificate. It has to be approved again next time."
}

// --- LITE-1b: Odomo's address (`omodachi-host odomo status`) ---------------
//
// Read-only, no daemon: the installer's `tailscale serve` record and whether
// serve still agrees. `on` with the URL to open on a phone, or why not and
// the command that fixes it. An older core has no such command: nothing to say.
var ODOMO_REASONS = {
    tailscale_not_installed: ODOMO_NAME + " needs Tailscale on this computer: it is how a phone reaches it with a real certificate.",
    tailscale_not_running: "Tailscale is not running here, so " + ODOMO_NAME + " has no address.",
    not_enabled: ODOMO_NAME + " has no address on your tailnet yet.",
    operator_required: "Tailscale only lets its operator add the address. Run in a terminal:",
    mapping_missing: ODOMO_NAME + "'s tailscale serve mapping is gone. Run in a terminal:",
    serve_status_unreadable: "Could not read tailscale serve's state."
}
var ODOMO_NO_ADDRESS = ODOMO_NAME + " has no address."
// Overview's section header for it.
var ODOMO_HEADER = ODOMO_NAME.toUpperCase()
function odomoStatus(result) {
    var empty = {known: false, on: false, url: "", text: "", command: ""}
    if (!isObject(result)) return empty
    var url = typeof result.odomo_url === "string" && /^https:\/\/[a-z0-9.-]+\.ts\.net(:[0-9]{1,5})?\/odomo\/$/.test(result.odomo_url)
        ? result.odomo_url : ""
    if (result.enabled === true && url)
        return {known: true, on: true, url: url, text: "Open this on your phone, then Share \u203a Add to Home Screen.",
                command: ""}
    var command = typeof result.command === "string" && /^[a-zA-Z0-9 $=._:/+-]{1,120}$/.test(result.command)
        ? result.command : ""
    var text = ODOMO_REASONS[result.reason] || ODOMO_NO_ADDRESS
    if (!command && (result.reason === "operator_required" || result.reason === "mapping_missing")) text = ODOMO_REASONS.not_enabled
    return {known: true, on: false, url: "", text: text, command: command}
}

// LITE-1d: one line under Odomo's address - how many of the web devices
// paired here get its notifications (subscribed, push on, still authorized).
// The same three things core counts for the native app's `odomo.push_devices`.
// "" when the device list is not read yet or an older core reports no push.
function odomoPushLine(rows, loaded) {
    if (!loaded || !Array.isArray(rows)) return ""
    var web = rows.filter(function(row) { return isObject(row) && row.role === "web" && isObject(row.push) })
    if (!web.length && !rows.some(function(row) { return isObject(row) && row.role === "web" })) return "No phone gets notifications from " + ODOMO_NAME + " yet."
    if (!web.length) return ""
    var count = web.filter(function(row) {
        return row.status === "authorized" && row.push.subscribed === true && row.push.enabled === true
    }).length
    if (count === 0) return "No phone gets notifications from " + ODOMO_NAME + " yet."
    return count === 1 ? "1 phone gets notifications from " + ODOMO_NAME + "."
                       : count + " phones get notifications from " + ODOMO_NAME + "."
}

function deviceKind(row) {
    if (!isObject(row)) return ""
    if (row.role === "plugin") return "This plugin (cannot be revoked)"
    return row.role === "web" ? "Web app (" + ODOMO_NAME + ")" : ""
}
function requestNotification(row) {
    if (!isObject(row) || typeof row.device_name !== "string") return null
    return {title: requestTitle(row),
            body: requestDetail(row) + "\n" + grantLine(row)}
}

// --- TAIL-2: what Tailscale on this computer means for Omodachi -------------
//
// `omodachi-host tailnet` (core 0.2.0+) is read-only. The panel draws its own
// sentences per warning id rather than core's, so an id this build does not
// know is skipped instead of drawn unchecked. An older core has no such
// command: that is "nothing to say", never an error on the page.
var TAILNET_WARNINGS = ["tailscale_ssh", "accept_routes_lan", "tailnet_firewall"]
var ACCEPT_ROUTES_FIX = "tailscale set --accept-routes=false"
// TAIL-3b: `state` is what the pair block says. "" when there is no report at
// all (an older core, or not read yet): that is nothing to say, never "absent".
function tailnetState(result) {
    if (!isObject(result)) return ""
    if (result.installed === false) return "absent"
    return result.running === true ? "running" : "signed_out"   // NeedsLogin / Stopped / NoState / null
}
function tailnetReport(result) {
    var empty = {running: false, dns_name: "", short_name: "", state: "", warnings: []}
    if (!isObject(result)) return empty
    var routes = []
    if (Array.isArray(result.lan_routes_captured))
        for (var i = 0; i < result.lan_routes_captured.length && i < 16; i++) {
            var route = result.lan_routes_captured[i]
            if (typeof route === "string" && /^[0-9a-fA-F:.]+\/\d{1,3}$/.test(route)) routes.push(route)
        }
    var ids = []
    if (Array.isArray(result.warnings))
        for (var j = 0; j < result.warnings.length && j < 8; j++) {
            var id = isObject(result.warnings[j]) ? result.warnings[j].id : ""
            if (TAILNET_WARNINGS.indexOf(id) >= 0 && ids.indexOf(id) < 0) ids.push(id)
        }
    var warnings = []
    // Order is severity, not core's order.
    for (var k = 0; k < TAILNET_WARNINGS.length; k++) {
        var wanted = TAILNET_WARNINGS[k]
        if (ids.indexOf(wanted) < 0) continue
        if (wanted === "tailscale_ssh")
            warnings.push({id: wanted, severe: true,
                text: "Tailscale SSH is on. SSH over Tailscale ignores Omodachi's device approval; "
                      + "revoking a device here does not stop it. Your tailnet's SSH rules decide who gets in."})
        else if (wanted === "accept_routes_lan")
            warnings.push({id: wanted, severe: true, command: ACCEPT_ROUTES_FIX,
                text: "Tailscale is routing this computer's own network"
                      + (routes.length ? " (" + routes.join(", ") + ")" : "")
                      + " through the tailnet, so pairing and connecting on this Wi-Fi may fail. "
                      + "To fix it, run in a terminal: " + ACCEPT_ROUTES_FIX})
        else
            warnings.push({id: wanted, severe: false,
                text: "Over Tailscale, your tailnet's access rules decide who can reach this computer, "
                      + "not ufw: Tailscale accepts tailscale0 before ufw sees it."})
    }
    var name = typeof result.dns_name === "string" && /^[a-z0-9.-]{1,253}\.ts\.net$/.test(result.dns_name)
        ? result.dns_name : ""
    return {running: result.running === true, dns_name: name, short_name: name ? name.split(".")[0] : "",
            state: tailnetState(result), warnings: warnings}
}

// --- TAIL-3b: pairing a phone or tablet, as the panel says it ---------------
//
// Every string the pair block and the Tailscale paragraphs draw lives here, so
// a copy pass touches this one table.
var PAIR_TEXT = {
    header: "PAIR A PHONE OR TABLET",
    nameLabel: "This computer's name on Tailscale",
    copy: "Copy",
    copied: "Copied",
    shortPrefix: "or just ",
    how: "Open Omodachi on your iPhone or iPad and paste this name.",
    signedOut: "Tailscale is installed but not signed in. Sign in from Tailscale in the bar, or run "
               + "tailscale up. Until then phones pair on this Wi-Fi only.",
    absent: "Without Tailscale, phones pair on this Wi-Fi only. To add it: "
            + "Omarchy menu \u203a Install \u203a Service \u203a Tailscale."
}
// The strings for one report: the short-name line filled in, and the one
// paragraph a node that is not running gets (or "").
function pairText(report) {
    var r = isObject(report) ? report : {}
    var shortName = typeof r.short_name === "string" ? r.short_name : ""
    return {header: PAIR_TEXT.header, nameLabel: PAIR_TEXT.nameLabel, copy: PAIR_TEXT.copy,
            copied: PAIR_TEXT.copied, how: PAIR_TEXT.how,
            short: shortName ? PAIR_TEXT.shortPrefix + shortName : "",
            note: r.state === "signed_out" ? PAIR_TEXT.signedOut : r.state === "absent" ? PAIR_TEXT.absent : ""}
}
// Overview: the block whenever Tailscale runs here and has a name to give.
function showPairBlock(report) {
    return isObject(report) && report.state === "running" && typeof report.dns_name === "string"
        && report.dns_name !== ""
}
// Devices: the same block on top, until a phone or tablet is paired. A web app
// (Odomo) and this computer's own panel are not one.
function hasPairedCompanion(devices) {
    return (Array.isArray(devices) ? devices : []).some(function(row) {
        return isObject(row) && row.status === "authorized" && row.role !== "plugin" && row.role !== "web"
    })
}
function showDevicesPairBlock(report, devices, devicesLoaded) {
    return showPairBlock(report) && devicesLoaded === true && !hasPairedCompanion(devices)
}

// RELEASE-9 (B2). A paired device that was never granted a terminal offered an
// SSH key; core holds it for ten minutes until the person here decides. Same
// shape as a pairing request: who, which key, what Approve gives.
function sshRequests(result) {
    if (!isObject(result) || !Array.isArray(result.requests)) return null
    var rows = []
    for (var i = 0; i < result.requests.length && i < 64; i++) {
        var row = result.requests[i]
        if (!isObject(row) || !validDeviceId(row.device_id)) continue
        if (typeof row.fingerprint !== "string" || !/^SHA256:[A-Za-z0-9+/]{43}$/.test(row.fingerprint)) continue
        rows.push({device_id: row.device_id,
            device_name: cleanName(row.device_name) || row.device_id,
            fingerprint: row.fingerprint,
            short_fingerprint: shortSshFingerprint(row.fingerprint),
            expires_at: Number.isInteger(row.expires_at) ? row.expires_at : 0})
    }
    return rows
}
var SSH_GRANT_LINE = "Approving adds this key to ~/.ssh/authorized_keys: a terminal (pty) and nothing else - no forwarding - ending with the device's pairing."
function sshRequestNotification(row) {
    if (!isObject(row)) return null
    return {title: "\u201c" + (cleanName(row.device_name) || row.device_id) + "\u201d wants an SSH login",
            body: row.device_id + " · " + row.short_fingerprint + "\n" + SSH_GRANT_LINE}
}
function sshActionResult(operation, target, result) {
    if (!isObject(result) || result.device_id !== target) return {ok: false}
    if (operation === "ssh_approve")
        return result.authorized === true ? {ok: true, message: "SSH login approved for " + target + "."} : {ok: false}
    if (operation === "ssh_reject")
        return result.authorized === false ? {ok: true, message: "SSH key rejected."} : {ok: false}
    return {ok: false}
}

function connectionHelp(state) {
    if (state === "loading")
        return "Checking the Omodachi host service. Wait for its status, or choose Reconnect if this does not finish."
    if (state === "permission_required")
        return "This panel needs permission from the host service. Complete local Omodachi setup to authorize it, then choose Reconnect."
    if (state === "unsupported")
        return "This host service does not support the panel's contract revision. Update Omodachi on this computer, then choose Reconnect."
    if (state === "setup_required")
        return "Omodachi Host is not running on this computer. Start or install it below, then choose Reconnect."
    if (state === "limited")
        return "Connected, but this computer reports some capabilities unavailable. Overview lists which."
    if (state === "ready")
        return "Open Omodachi on your iPad and approve the request that appears here."
    return "Cannot reach the Omodachi host service. Start omodachid below, then choose Reconnect."
}

// The line under Overview. It used to tell every connected host to go approve a
// request on the iPad - including a host with paired devices and a session
// already on screen, which is advice for a state that ended weeks ago. One
// line, and it says what is true now: what to do when nothing is paired, that
// there is nothing to do when something is, and what is running when a session
// is running.
function summonDevice(summon, sessionId) {
    if (!isObject(summon) || summon.route !== "remote" || !validNonEmptyString(summon.owner_device_id)) return ""
    // A recall from a session that has since been replaced names the wrong iPad.
    if (validNonEmptyString(sessionId) && summon.session_id !== sessionId) return ""
    return summon.owner_device_id
}

function overviewHint(state, snapshot, devices, summon) {
    if (state !== "ready") return connectionHelp(state)
    var remote = isStateSnapshot(snapshot) ? snapshot.remote : null
    if (remote && REMOTE_LIVE_STATES.indexOf(remote.state) >= 0) {
        var parts = [remote.mode === "takeover" ? "Takeover" : "Extended screen", display(remote.backend, "backend unknown")]
        var owner = summonDevice(summon, remote.session_id)
        if (owner) parts.push(owner)
        return parts.join(" · ")
    }
    var paired = (Array.isArray(devices) ? devices : []).some(function(device) {
        return isObject(device) && device.status === "authorized"
    })
    return paired ? "Ready." : connectionHelp("ready")
}

// INSTALL-1. The install runs in its own terminal window, which is the whole
// point - every step stays visible - but the panel that started it should not
// have to say "a terminal is open somewhere" and nothing else. The installer
// rewrites one small JSON file per stage and this reads it. Anything that is
// not an object with a known stage is ignored rather than drawn: the file is
// written and replaced while this is polling it, so a half-written read is an
// ordinary event, not an error to report.
var INSTALL_STAGES = ["starting", "checking", "fetching", "installing", "removing", "done", "failed"]

function parseInstallStatus(text) {
    // Not validNonEmptyString: that caps at 256 characters, and this is a whole
    // JSON document. The cap that matters here is on the fields it yields.
    if (typeof text !== "string" || text.length === 0 || text.length > 8192) return null
    var value
    try { value = JSON.parse(text) } catch (error) { return null }
    if (!isObject(value) || INSTALL_STAGES.indexOf(value.stage) < 0) return null
    return {stage: value.stage,
            message: validNonEmptyString(value.message) ? value.message : "",
            detail: validNonEmptyString(value.detail) ? value.detail : "",
            ok: value.ok === true ? true : (value.ok === false ? false : null)}
}

// One line for the card, whatever the stage. A failure keeps its own sentence
// and adds the detail, because the detail is the part that says what to fix.
function installLine(stage, message, detail) {
    if (!validNonEmptyString(stage)) return ""
    var head = validNonEmptyString(message) ? message : stage
    return validNonEmptyString(detail) ? head + "\n" + detail : head
}
