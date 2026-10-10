.pragma library

// PLUG-2: the statuses this panel has copy and buttons for. It is a
// vocabulary, not a filter - a status core adds later still describes a real
// request, and dropping the whole list because one row used a new name is how
// Devices went blank. An unknown status gets a neutral label, no Approve and
// no Cancel; it is never a reason to reject the row or the list.
var STATUSES = ["pending", "awaiting_local_approval", "submitting", "awaiting_client_proof", "paired", "failed", "cancelled", "expired", "cancellation_pending", "revocation_pending", "revoked"]
var APPROVABLE = ["awaiting_local_approval"]
var CANCELLABLE = ["pending", "awaiting_local_approval", "submitting", "awaiting_client_proof", "cancellation_pending"]
// PAIR-3: what already finished and can only be cleaned up. The fork has no
// persistent certificate revocation, so a revoked device leaves a
// `revocation_pending` record on the host forever. Those records are history:
// they are shown as history, they are never to-do items, and - the actual
// 2026-09-19 outage - they must never decide whether the Devices page loads.
// PLUG-4 adds `revoked`: a revoke the fork really completed. core does not
// keep such a record at all, so it only ever arrives as the answer to the
// revoke itself - it is history the moment it is read.
var HISTORICAL = ["revocation_pending", "cancellation_pending", "failed", "cancelled", "expired", "revoked"]
function validStatus(value) { return typeof value === "string" && /^[a-z][a-z0-9_]{0,63}$/.test(value) }
// The managed Sunshine fork emits its pairing request IDs in UPPERCASE
// (`A7E9C135-7326-E027-0108-4EEDBF0190C1`, measured on the real host), and core
// accepts both cases deliberately (`media_pairing._UUID`). This validator was
// lowercase-only, so every real `media-pairing pending` row failed it, the
// whole list came back `media_api_invalid`, `mediaApiReady` went false and
// Approve silently dropped `--remote`. Case is accepted, never normalized: the
// ID is handed back to the fork exactly as it arrived.
function validUuid(value) { return typeof value === "string" && /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(value) }
function validFingerprint(value) { return typeof value === "string" && /^[0-9a-f]{64}$/.test(value) }
function validDeviceId(value) { return typeof value === "string" && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(value) }
function validCompanionRequestId(value) { return typeof value === "string" && /^pair_[0-9a-f]{32}$/.test(value) }
// Presence and type, bounded and printable - PLUG-2's rule. A field whose
// exact spelling is core's business is checked for being a usable string, not
// for matching this build's idea of the format.
function printable(value, max) {
    return typeof value === "string" && value.length >= 1 && value.length <= max && !/[\x00-\x1f\x7f]/.test(value)
}
// The one thing that is still a hard stop. A row carrying a PIN or a
// credential means this is not the surface the panel thinks it is, and no part
// of it may reach a QML property.
function carriesSecret(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return false
    return Object.prototype.hasOwnProperty.call(value, "pin") || Object.prototype.hasOwnProperty.call(value, "credential")
}
function summary(value, nowMs) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return null
    if (carriesSecret(value)) return null
    // Readable is enough to draw a row. Whether the row can be acted on is a
    // separate, stricter question answered by `bindable` below.
    if (!printable(value.attempt_id, 128) || !printable(value.request_id, 128) || !printable(value.client_cert_sha256, 128)) return null
    if (!validDeviceId(value.device_id)) return null
    if (!validStatus(value.status) || typeof value.paired !== "boolean" || typeof value.media_authorized !== "boolean") return null
    if (!Number.isInteger(value.expires_in_ms) || value.expires_in_ms < 0) return null
    var remaining = value.expires_in_ms
    if (typeof nowMs === "number" && Number.isFinite(nowMs) && typeof value.received_at_ms === "number" && Number.isFinite(value.received_at_ms))
        remaining = Math.max(0, remaining - Math.max(0, nowMs - value.received_at_ms))
    // Only a row core could act on is offered a button: the three identifiers
    // are what `media-pairing approve|cancel` is called with, so anything the
    // host would refuse is drawn as information instead of as an action.
    var bindable = validUuid(value.attempt_id) && validUuid(value.request_id) && validFingerprint(value.client_cert_sha256)
    var historical = HISTORICAL.indexOf(value.status) >= 0
    return {attemptId: value.attempt_id, requestId: value.request_id, fingerprint: value.client_cert_sha256,
        deviceId: value.device_id, status: value.status, paired: value.paired,
        mediaAuthorized: value.media_authorized, secondsLeft: Math.ceil(remaining / 1000),
        known: STATUSES.indexOf(value.status) >= 0,
        bindable: bindable,
        historical: historical,
        canApprove: bindable && !historical && APPROVABLE.indexOf(value.status) >= 0 && remaining > 0 && value.reason !== "pin_resubmission_required",
        needsPinResubmission: value.reason === "pin_resubmission_required",
        canCancel: bindable && CANCELLABLE.indexOf(value.status) >= 0}
}
function localBinding(value) {
    var row = summary(value)
    return row && row.bindable ? {attempt_id: row.attemptId, request_id: row.requestId, client_cert_sha256: row.fingerprint} : null
}
function label(value, nowMs) {
    var row = summary(value, nowMs)
    if (!row) return "Pairing unavailable"
    if (row.paired) return "Paired for Remote"
    if (row.needsPinResubmission) return "Waiting for the companion to resume pairing"
    // A status this build has no copy for still gets a sentence, not undefined.
    return ({pending: "Pairing request ready", awaiting_local_approval: "Remote approval required",
        submitting: "Submitting pairing", awaiting_client_proof: "Waiting for the device's pairing proof",
        failed: "Pairing failed", cancelled: "Pairing cancelled", expired: "Pairing expired",
        cancellation_pending: "Cancellation pending", revocation_pending: "Media certificate removal pending",
        revoked: "Remote certificate revoked",
        paired: "Remote permission is no longer active"})[row.status] || "Remote pairing reported by the host"
}

function safeError(raw) {
    var frame
    try { frame = typeof raw === "string" ? JSON.parse(raw) : raw } catch (_) { return "media_api_unavailable" }
    var code = frame && typeof frame.error === "string" ? frame.error : frame && frame.error && frame.error.code
    return typeof code === "string" && /^[a-z0-9_:-]{1,128}$/.test(code) ? code : "media_api_unavailable"
}
function errorMessage(code) {
    if (["media_pairing_binding_mismatch", "media_pairing_not_found", "pairing_request_not_pending", "media_pairing_request_not_pending"].indexOf(code) >= 0)
        return "This pairing request changed. Refresh Remote status before approving it."
    if (code === "media_pairing_auth_revoked" || code === "permission_denied" || code === "media_permission_required")
        return "Host permission is required to manage this Remote connection."
    if (code === "pairing_approval_required")
        return "This device has no approved pairing on record. Approve it again from this page."
    if (code === "media_pairing_capacity") return "The host has too many pairing requests. Finish or cancel an existing request first."
    return "Remote pairing is not ready. Update or reconnect the Omodachi host service."
}
// PAIR-3 core answers `{requests, history}`; an older core puts everything in
// `requests`. Both are read, and `historical` is decided by the status either
// way, so the panel does not depend on which core is installed.
function parseLocalList(raw, receivedAtMs) {
    var frame
    try {
        if (typeof raw !== "string" || raw.length > 1048576) return {ok: false, code: "media_api_unavailable"}
        frame = JSON.parse(raw)
    } catch (_) { return {ok: false, code: "media_api_unavailable"} }
    var result = frame && frame.ok === true ? frame.result : null
    // Only `requests` is read as a list. `certificate_revocation_supported` is
    // a capability flag: absent means "this host does not offer it", which is
    // exactly what an older or newer core omitting it should mean.
    if (!result || typeof result !== "object" || Array.isArray(result)
            || !Array.isArray(result.requests) || result.requests.length > 256)
        return {ok: false, code: safeError(frame)}
    var history = Array.isArray(result.history) && result.history.length <= 256 ? result.history : []
    var incoming = result.requests.concat(history)
    var rows = [], seen = ({})
    for (var index = 0; index < incoming.length; index++) {
        var value = incoming[index]
        if (carriesSecret(value)) return {ok: false, code: "media_api_invalid"}
        var row = summary(value)
        // PLUG-2, the lesson this file already had and did not apply: a row
        // this build cannot read is dropped, never a veto on the whole list.
        // One unreadable row used to blank Devices and turn Remote approval
        // off without saying so.
        if (!row || seen[row.attemptId]) continue
        seen[row.attemptId] = true
        // Project only the UI contract. PIN, token and arbitrary extra state
        // never cross into QML properties or diagnostics.
        rows.push({attempt_id: row.attemptId, request_id: row.requestId,
            client_cert_sha256: row.fingerprint, device_id: row.deviceId,
            status: row.status, paired: row.paired, media_authorized: row.mediaAuthorized,
            expires_in_ms: value.expires_in_ms, reason: value.reason === "pin_resubmission_required" ? value.reason : "",
            historical: row.historical || index >= result.requests.length,
            received_at_ms: receivedAtMs})
    }
    return {ok: true, requests: rows, certificateRevocationSupported: result.certificate_revocation_supported === true}
}
// The to-do half of the list: Sunshine certificate attempts that are stopped
// on this host waiting for a local Approve. core has had `approve_local` since
// SPEC-B2; until PAIR-3 nothing in the panel ever drew it, so an app that
// asked for a streaming certificate spun for 120 s and was cancelled.
function localApprovals(rows, nowMs) {
    if (!Array.isArray(rows)) return []
    var cards = []
    for (var index = 0; index < rows.length; index++) {
        var row = summary(rows[index], nowMs)
        if (!row || row.historical || row.status !== "awaiting_local_approval") continue
        if (!row.canApprove && !row.needsPinResubmission) continue
        cards.push({attempt_id: row.attemptId, request_id: row.requestId,
            client_cert_sha256: row.fingerprint, device_id: row.deviceId,
            seconds_left: row.secondsLeft, can_approve: row.canApprove,
            needs_pin_resubmission: row.needsPinResubmission})
    }
    return cards
}
function currentBinding(rows, binding, operation, nowMs) {
    if (!binding || !validUuid(binding.attempt_id) || !validUuid(binding.request_id) || !validFingerprint(binding.client_cert_sha256)) return null
    var current = rows.filter(function(row) { return row.attempt_id === binding.attempt_id && row.request_id === binding.request_id && row.client_cert_sha256 === binding.client_cert_sha256 })
    if (current.length !== 1) return null
    var row = summary(current[0], nowMs)
    if (!row || (operation === "approve" ? !row.canApprove : operation === "cancel" ? !row.canCancel : true)) return null
    return {attempt_id: row.attemptId, request_id: row.requestId, client_cert_sha256: row.fingerprint}
}
function deviceStatus(rows, deviceId) {
    var owned = rows.filter(function(row) { return row.device_id === deviceId }), paired = 0, pending = 0, removal = 0
    owned.forEach(function(value) {
        var row = summary(value)
        if (!row) return
        if (row.paired) paired++
        else if (row.status === "revocation_pending") removal++
        else if (row.canApprove || row.canCancel) pending++
    })
    var parts = []
    if (paired) parts.push(paired + " Remote certificate(s) paired")
    if (pending) parts.push(pending + " Remote pairing request(s)")
    if (removal) parts.push(removal + " media certificate removal(s) pending")
    return parts.length ? parts.join(" · ") : "No completed Remote pairing reported"
}

function mediaCommand(rows, binding, operation, nowMs) {
    var current = currentBinding(rows, binding, operation, nowMs)
    return current ? ["omodachi-host", "media-pairing", operation, current.attempt_id, current.request_id, current.client_cert_sha256] : null
}
// PAIR-3 §1.2: the manual repair for a half-paired device - companion granted,
// streaming not. It is the same grant an Approve would have landed, addressed
// by the request that approved the device in the first place.
function grantRemoteCommand(deviceId, sourceRequestId) {
    if (!validDeviceId(deviceId) || !validCompanionRequestId(sourceRequestId)) return null
    return ["omodachi-host", "media-pairing", "grant-remote", deviceId, sourceRequestId]
}
// Study 02 N-12, one-step confirm: a single Approve issues one command that
// core runs as one transaction - the Companion credential and, when the media
// bridge is up, the Sunshine certificate grant. There is no PIN to copy, no
// Sunshine web page, and no second approval anywhere.
function companionCommand(rows, requestId, allowRemote) {
    if (typeof allowRemote !== "boolean" || !validCompanionRequestId(requestId)) return null
    if (rows.filter(function(row) { return row.request_id === requestId && row.status === "pending" }).length !== 1) return null
    var command = ["omodachi-host", "pair", "approve", requestId]
    if (allowRemote) command.push("--remote")
    return command
}
// PAIR-3: Approve never quietly becomes a smaller Approve. `--remote` is
// unconditional - it is core's default since PAIR-3 and a no-op flag there,
// and it is still passed explicitly so an older core grants Remote too. When
// the panel could not read `media-pairing pending` it used to drop the flag
// without telling anyone, which is how a device paired for the terminal and
// not for the screen. Whether the grant landed is now read off the reply.
function approveCommand(rows, requestId) {
    return companionCommand(rows, requestId, true)
}
function rejectCommand(rows, requestId) {
    if (!validCompanionRequestId(requestId)) return null
    if (rows.filter(function(row) { return row.request_id === requestId && row.status === "pending" }).length !== 1) return null
    return ["omodachi-host", "pair", "reject", requestId]
}
// What core said the grant actually did. `grant_remote` answers
// `{device_id, media_authorized}`; anything else it adds (an epoch, a reason)
// is read when present and never required.
function remoteGrant(result, binding) {
    var remote = result && result.remote
    if (!remote || typeof remote !== "object" || Array.isArray(remote)) return null
    if (!binding || remote.device_id !== binding.device_id) return null
    if (typeof remote.media_authorized !== "boolean") return null
    if (remote.epoch !== undefined && (!Number.isInteger(remote.epoch) || remote.epoch < 1)) return null
    var reason = typeof remote.reason === "string" && /^[a-z0-9_:-]{1,128}$/.test(remote.reason) ? remote.reason : ""
    return {deviceId: remote.device_id, mediaAuthorized: remote.media_authorized === true, reason: reason}
}
function actionResult(operation, target, binding, result) {
    if (!result || typeof result !== "object" || Array.isArray(result)) return {ok: false}
    if (operation === "approve" || operation === "approve_remote" || operation === "reject") {
        var validStatus = operation === "approve_remote" ? ["approved", "claimed"].indexOf(result.status) >= 0 : result.status === (operation === "reject" ? "rejected" : "approved")
        if (result.request_id !== target || !validStatus) return {ok: false}
        if (operation === "approve_remote") {
            if (!binding || result.device_id !== binding.device_id) return {ok: false}
            // LITE-1a: a browser gets its credential and nothing else, so no
            // Remote grant is a success here, not a half-paired device.
            if (result.client && typeof result.client === "object" && result.client.kind === "web" && result.remote === undefined)
                return {ok: true, message: "Web app approved: the menu, keybindings and notifications. No screen, no SSH."}
            var grant = remoteGrant(result, binding)
            if (!grant) return {ok: false}
            // PAIR-3 §1.2: a grant that did not land is reported on the card,
            // with the device's repair action, instead of being reported as a
            // success the user would only discover on the iPad.
            if (!grant.mediaAuthorized)
                return {ok: true, warning: true, grantRemote: true, deviceId: grant.deviceId, sourceRequestId: target,
                    message: "Remote streaming was not granted: " + (grant.reason || "the host did not say why")
                        + ". Use Grant Remote on this device's row."}
            return {ok: true, message: "Companion and Remote approved. The companion will finish media pairing in the background."}
        }
        if (operation === "approve" && result.remote !== undefined) return {ok: false}
        return {ok: true, message: operation === "reject" ? "Companion request rejected." : "Companion approved. Remote permission was not added."}
    }
    if (operation === "grant_remote") {
        if (result.device_id !== target || result.media_authorized !== true) return {ok: false}
        return {ok: true, message: "Remote streaming granted. Open Remote on the device again."}
    }
    if (operation === "revoke" || operation === "media_revoke") {
        if (result.device_id !== target) return {ok: false}
        if (operation === "revoke" && (!Number.isInteger(result.revoked) || result.revoked < 0)) return {ok: false}
        var media = operation === "revoke" ? result.media : result
        if (!media || media.device_id !== target || media.media_authorized !== false
            || !Number.isInteger(media.pending_media_revocations) || media.pending_media_revocations < 0
            || typeof media.media_revocation_complete !== "boolean")
            return operation === "revoke" ? {ok: true, warning: true, message: "Companion access revoked. Remote cleanup could not be confirmed."} : {ok: false}
        if (result.desktop_cleanup && (result.desktop_cleanup.released !== true || result.desktop_cleanup.recovery_required === true))
            return {ok: true, warning: true, message: "Authorization is revoked, but the active Remote session cleanup needs attention."}
        if (!media.media_revocation_complete && media.pending_media_revocations === 0)
            return {ok: true, warning: true, message: "Remote authorization is blocked. External media certificate removal could not be confirmed."}
        if (!media.media_revocation_complete || media.pending_media_revocations > 0)
            return {ok: true, warning: true, message: "Access is blocked in Omodachi. " + media.pending_media_revocations + " media certificate cleanup(s) remain pending."}
        return {ok: true, message: operation === "revoke" ? "Device access revoked." : "Remote authorization revoked."}
    }
    // PLUG-4 §3: the footer's one cleanup. core answers which devices it
    // removed and which it kept, and a device it kept is the honest half of
    // the answer - its certificate revocation is not finished yet.
    if (operation === "purge") {
        if (!Array.isArray(result.purged) || !Array.isArray(result.kept)) return {ok: false}
        if (result.purged.length === 0 && result.kept.length === 0)
            return {ok: true, message: "There was nothing to clear."}
        if (result.kept.length > 0)
            return {ok: true, warning: true,
                message: "Cleared " + result.purged.length + " revoked device(s). " + result.kept.length
                    + " could not be cleared yet: their streaming certificate has not been taken back."}
        return {ok: true, message: "Cleared " + result.purged.length + " revoked device(s)."}
    }
    if (operation === "media_approve" || operation === "media_cancel") {
        var row = summary(result)
        if (!row || !binding || row.attemptId !== binding.attempt_id || row.requestId !== binding.request_id || row.fingerprint !== binding.client_cert_sha256) return {ok: false}
        return {ok: true, warning: row.status === "revocation_pending" || row.status === "cancellation_pending", message: label(result)}
    }
    return {ok: false}
}
