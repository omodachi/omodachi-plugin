.pragma library

// Two different stores, deliberately kept apart:
//
//   host preferences  -> `omodachi-host preferences get|set`, owned by core,
//                        applied on the next Remote connection.
//   panel preferences -> the plugin's own inline entry in shell.json, written
//                        through bar.shell.updateEntryInline (the official
//                        persistence, see shell/services/PluginShellApi.qml).
//
// Anything the host does not actually consume does not appear here. Backend
// and placement are per-session arguments of `omodachi-host remote start`,
// not stored defaults, so Settings does not pretend to save them.

var PAGES = ["overview", "devices", "settings"]
var CLICK_ACTIONS = ["toggle", "open", "summon"]
var UI_DEFAULTS = {default_page: "overview", icon_click: "toggle"}
var HOST_DEFAULTS = {allow_dynamic_resolution: true, quality: "balanced", host_audio_playback: false,
    biometric_auth: false, clipboard_sync: "off"}
var HOST_FLAGS = {allow_dynamic_resolution: "--allow-dynamic-resolution", quality: "--quality", host_audio_playback: "--host-audio-playback",
    biometric_auth: "--biometric-auth", clipboard_sync: "--clipboard-sync"}
// AUTH-1's switch arrived after this page shipped, and a host that predates it
// is not a broken host. The three original keys must be readable or the page
// is not showing the truth; `biometric_auth` is offered only when the host
// actually sends it, and its absence is reported as "not supported" rather
// than blacking out Settings.
var REQUIRED_HOST_KEYS = ["allow_dynamic_resolution", "quality", "host_audio_playback"]
var OPTIONAL_HOST_KEYS = ["biometric_auth", "clipboard_sync"]
var QUALITIES = ["balanced", "quality", "performance"]
// CLIP-1's three answers. `off` is what a host ships with, and an answer this
// build does not know reads as off rather than as permission.
var CLIPBOARD_MODES = ["off", "host_to_device", "both"]
// omodachi_core/service.py:_preferences_runtime. These are the capability
// flags Settings draws; a flag core adds later is ignored, and one core stops
// sending reads as false (the row is simply not offered) rather than taking
// the whole Settings page down with `preferences_invalid`.
var RUNTIME_FLAGS = ["profile_defaults", "host_audio_default", "remote_available", "clipboard_supported"]
var PROFILE_FALLBACK = {fps: 0, bitrate_kbps: 0}

function ui(value) {
    value = value || {}
    return {default_page: PAGES.indexOf(value.default_page) >= 0 ? value.default_page : UI_DEFAULTS.default_page,
        icon_click: CLICK_ACTIONS.indexOf(value.icon_click) >= 0 ? value.icon_click : UI_DEFAULTS.icon_click}
}

function uiChange(current, key, value) {
    var valid = key === "default_page" ? PAGES.indexOf(value) >= 0
        : key === "icon_click" ? CLICK_ACTIONS.indexOf(value) >= 0 : false
    if (!valid) return null
    var next = Object.assign({}, current || {})
    next[key] = value
    return next
}

// `omarchy-shell shell summon com.omodachi.host '{"view":"devices"}'`, and the
// legacy view=setup route that host scripts and older notifications still use.
function route(payload, defaultPage) {
    var decoded = {}
    try { decoded = typeof payload === "string" ? JSON.parse(payload || "{}") : (payload || {}) } catch (error) { decoded = {} }
    var requested = decoded.page || decoded.view
    if (requested === "setup") return {page: "settings", setupExpanded: true, focusRequestId: ""}
    var focus = typeof decoded.request_id === "string" && /^pair_[0-9a-f]{32}$/.test(decoded.request_id) ? decoded.request_id : ""
    if (focus) return {page: "devices", setupExpanded: false, focusRequestId: focus}
    return {page: PAGES.indexOf(requested) >= 0 ? requested : ui({default_page: defaultPage}).default_page,
        setupExpanded: false, focusRequestId: ""}
}

// Reading and writing are deliberately not the same test. A `quality` core
// invents later must still load (the chooser simply shows nothing selected);
// only a value this build knows may be written back.
function readableValue(key, value) {
    if (key === "allow_dynamic_resolution" || key === "host_audio_playback" || key === "biometric_auth")
        return typeof value === "boolean"
    if (key === "quality" || key === "clipboard_sync")
        return typeof value === "string" && value.length > 0 && value.length <= 64
    return false
}
function validValue(key, value) {
    if (key === "allow_dynamic_resolution" || key === "host_audio_playback" || key === "biometric_auth")
        return typeof value === "boolean"
    if (key === "quality") return QUALITIES.indexOf(value) >= 0
    if (key === "clipboard_sync") return CLIPBOARD_MODES.indexOf(value) >= 0
    return false
}

function parse(raw) {
    var frame
    try {
        if (typeof raw !== "string" || raw.length > 65536) return {ok: false, code: "preferences_unavailable"}
        frame = JSON.parse(raw)
    } catch (error) { return {ok: false, code: "preferences_unavailable"} }
    if (!frame || frame.ok !== true || !frame.result) {
        var code = frame && typeof frame.error === "string" ? frame.error : frame && frame.error && frame.error.code
        return {ok: false, code: typeof code === "string" && /^[a-z0-9_:-]{1,128}$/.test(code) ? code : "preferences_unavailable"}
    }
    // PLUG-2: check only what Settings reads. `revision` is load-bearing (it
    // is the CAS token of the next write) and the three keys this page offers
    // must be readable. `scope`, `applies_to` and `permission_effect` are
    // core's own constants that nothing here branches on, an extra preference
    // key is a key this build does not offer yet, and a profile core reshapes
    // is a description that is simply not shown - none of them is a reason to
    // black out the whole page.
    var result = frame.result, values = result.values, runtime = result.runtime, profile = result.profile_defaults
    if (!Number.isInteger(result.revision) || result.revision < 0
        || !values || typeof values !== "object" || Array.isArray(values)) return {ok: false, code: "preferences_invalid"}
    var clean = {}
    for (var r = 0; r < REQUIRED_HOST_KEYS.length; r++) {
        var required = REQUIRED_HOST_KEYS[r]
        if (!readableValue(required, values[required])) return {ok: false, code: "preferences_invalid"}
        clean[required] = values[required]
    }
    var runtimeClean = {}, source = runtime && typeof runtime === "object" && !Array.isArray(runtime) ? runtime : {}
    for (var i = 0; i < RUNTIME_FLAGS.length; i++)
        runtimeClean[RUNTIME_FLAGS[i]] = source[RUNTIME_FLAGS[i]] === true
    for (var o = 0; o < OPTIONAL_HOST_KEYS.length; o++) {
        var optional = OPTIONAL_HOST_KEYS[o]
        var present = readableValue(optional, values[optional])
        clean[optional] = present ? values[optional] : HOST_DEFAULTS[optional]
        runtimeClean[optional + "_supported"] = present
    }
    var quality = profile && typeof profile === "object" ? profile.quality : null
    var readable = quality && typeof quality === "object"
        && Number.isInteger(quality.fps) && quality.fps > 0
        && Number.isInteger(quality.bitrate_kbps) && quality.bitrate_kbps > 0
    // Without a readable profile there is nothing to describe, so the row that
    // describes it is not offered either.
    if (!readable) runtimeClean.profile_defaults = false
    return {ok: true, revision: result.revision, values: clean, runtime: runtimeClean,
        profile: readable ? {fps: quality.fps, bitrate_kbps: quality.bitrate_kbps} : {fps: PROFILE_FALLBACK.fps, bitrate_kbps: PROFILE_FALLBACK.bitrate_kbps}}
}

function command(snapshot, key, value) {
    if (!snapshot || snapshot.ok !== true || !validValue(key, value)) return null
    if (key === "host_audio_playback" && snapshot.runtime.host_audio_default !== true) return null
    if (key === "quality" && snapshot.runtime.profile_defaults !== true) return null
    // AUTH-1: never write a switch this host has not told us it has. Turning
    // something on that does not exist is the one failure mode a security
    // toggle cannot have.
    if (key === "biometric_auth" && snapshot.runtime.biometric_auth_supported !== true) return null
    // CLIP-1: same rule. A host that has never heard of the clipboard switch
    // must not be sent one — and `clipboard_supported` is deliberately *not*
    // checked here: a daemon outside a graphical session still stores the
    // preference, and it takes effect when the session comes back.
    if (key === "clipboard_sync" && snapshot.runtime.clipboard_sync_supported !== true) return null
    // The permission stays writable even when no Remote backend is ready.
    // Saving On is never evidence that the capability exists.
    return ["omodachi-host", "preferences", "set", "--revision", String(snapshot.revision), HOST_FLAGS[key], String(value)]
}

function errorMessage(code) {
    if (typeof code === "string" && (code.indexOf("conflict") >= 0 || code.indexOf("revision") >= 0))
        return "Settings changed elsewhere. The latest values are loaded; choose your change again."
    return "Host settings are unavailable. Reconnect or update the Omodachi host service."
}
