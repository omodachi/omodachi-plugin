import assert from 'node:assert/strict';
import { readFile, readdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import vm from 'node:vm';

// SPEC-C §5: the canonical fixtures in ../omodachi-core/contracts/fixtures are
// generated from core's own serializers, so driving the plugin's models from
// them is the only check that says something about the real wire. If core
// changes a shape, this fails here rather than on the host.

const FIXTURES = new URL('../../omodachi-core/contracts/fixtures/', import.meta.url);
if (!existsSync(FIXTURES)) {
  console.log('contracts: SKIPPED (../omodachi-core/contracts/fixtures is not checked out)');
  process.exit(0);
}

const load = async (name) => JSON.parse(await readFile(new URL(name, FIXTURES), 'utf8'));
const evaluate = async (file) => {
  const context = { console, Number, JSON, Object, Array, Date };
  vm.createContext(context);
  vm.runInContext((await readFile(new URL('../' + file, import.meta.url), 'utf8'))
    .replace('.pragma library', ''), context);
  return context;
};

const model = await evaluate('OmodachiModel.js');
const media = await evaluate('MediaPairingModel.js');
const preferences = await evaluate('PreferencesModel.js');

// --- state -----------------------------------------------------------------
const state = await load('state.json');
const envelope = {ok: true, result: state};
const parsed = model.parseFrame(JSON.stringify(envelope));
assert.equal(parsed && parsed.kind, 'snapshot', 'core state.json must parse as a plugin snapshot');
assert.equal(model.isStateSnapshot(parsed.snapshot), true);
assert.equal(model.asState(parsed.snapshot), 'ready');
assert.equal(model.remoteState(parsed.snapshot), state.remote.state);
assert.equal(model.remoteActive(parsed.snapshot), false);
assert.equal(model.iconState(model.asState(parsed.snapshot), false), 'linked');
// The snapshot must survive the round trip with its declared envelope fields.
assert.equal(parsed.snapshot.instance_id, state.instance_id);
assert.equal(parsed.snapshot.revision, state.revision);
assert.equal(parsed.snapshot.event_cursor, state.event_cursor);
assert.equal(parsed.snapshot.contract_revision, 'omodachi.v1');

// --- bar, including the roles this fixture set introduced -------------------
const bar = await load('bar.json');
assert.equal(model.isStateSnapshot({...parsed.snapshot, bar}), true);
const roles = ['left', 'center', 'right'].flatMap(region => bar[region].map(entry => entry.role));
assert.ok(roles.includes('agent_usage'), 'bar.json carries the agent_usage role');
for (const role of roles) assert.ok(model.BAR_ROLES.includes(role), 'unknown bar role ' + role);
assert.equal(model.isStateSnapshot({...parsed.snapshot, bar: await load('bar-unavailable.json')}), true);

// --- remote_bar ------------------------------------------------------------
assert.equal(model.isStateSnapshot({...parsed.snapshot, remote_bar: state.remote_bar}), true);
assert.equal(model.normalizeRemoteBar(state.remote_bar).active, false);
// The fixtures only carry the idle projection, so the live one is pinned here
// verbatim as read back from `omodachi-host state` on the Omarchy host during
// a real extend/vnc session (SPEC-C §6.6). An earlier model rejected it whole,
// which took the plugin to connection:error while a session was running.
const liveRemoteBar = {active: true, session_id: 'rs_105590ac6ed248a8ad4f090b9562c3db',
  output_name: 'OMODACHI-22597120e66e468f', viewport: {width: 1194, height: 834},
  orientation: 'landscape', logical_size: {width: 1280.0, height: 894.0}, revision: '2',
  workspaces: [{id: 1, monitor: 'eDP-1', windows: 0, active: false, remote: false},
               {id: 2, monitor: 'eDP-1', windows: 0, active: true, remote: false},
               {id: 6, monitor: 'OMODACHI-22597120e66e468f', windows: 1, active: false, remote: true},
               {id: 11, monitor: 'OMODACHI-22597120e66e468f', windows: 0, active: false, remote: true}]};
assert.equal(model.normalizeRemoteBar(liveRemoteBar).active, true);
const liveRemote = {session_id: 'rs_105590ac6ed248a8ad4f090b9562c3db', state: 'ready',
  mode: 'extend', backend: 'vnc', revision: 2};
const liveSnapshot = {...parsed.snapshot, remote: liveRemote, remote_bar: liveRemoteBar};
assert.equal(model.isStateSnapshot(liveSnapshot), true, 'a live session frame must not be rejected');
assert.equal(model.remoteActive(liveSnapshot), true);
assert.equal(model.iconState(model.asState(liveSnapshot), true), 'remote');

// --- WSS frames the plugin must accept -------------------------------------
const wssSnapshot = await load('wss-snapshot.json');
assert.equal(wssSnapshot.type, 'snapshot');
const fromWss = model.parseFrame(JSON.stringify({ok: true, result: wssSnapshot.state}));
assert.equal(fromWss && fromWss.kind, 'snapshot', 'the WSS snapshot body is the same state shape');
const ready = await load('wss-ready.json');
assert.equal(ready.instance_id, state.instance_id);
assert.equal(ready.cursor, state.event_cursor);

// --- events ----------------------------------------------------------------
const ipcEvent = await load('ipc-event.json');
const event = ipcEvent.event;
// The fixture set is generated at an earlier revision than state.json, so the
// event is rebased onto the snapshot's cursor and revision; its body is untouched.
const rebased = {...event, seq: fromWss.snapshot.event_cursor + 1,
                 payload: {...event.payload, revision: fromWss.snapshot.revision + 1}};
const applied = model.consumeLine(JSON.stringify({event: rebased, instance_id: state.instance_id}),
                                  fromWss.snapshot, state.instance_id);
assert.equal(applied.kind, 'event', 'a catalog.changed event must merge into the fixture snapshot');
assert.equal(applied.snapshot.event_cursor, rebased.seq);
assert.equal(applied.snapshot.catalog.revision, event.payload.catalog.revision);

const wssEvent = await load('wss-event.json');
assert.equal(wssEvent.event.type, event.type);

const resync = await load('event-resync-required.json');
assert.equal(model.consumeLine(JSON.stringify({event: {...resync, seq: state.event_cursor + 1}, instance_id: state.instance_id}),
                               parsed.snapshot, state.instance_id).kind, 'resync');

// An event from another daemon identity is never merged.
assert.equal(model.consumeLine(JSON.stringify({event: rebased, instance_id: 'someone-else'}),
                               parsed.snapshot, state.instance_id).kind, 'invalid');

// --- errors ----------------------------------------------------------------
const error = await load('ipc-response-error.json');
const errorFrame = model.parseFrame(JSON.stringify(error));
assert.ok(errorFrame === null || errorFrame.kind === 'error', 'an error envelope is never read as state');

// --- media pairing and preferences -----------------------------------------
assert.equal(media.parseLocalList(JSON.stringify({ok: true, result: {requests: [], certificate_revocation_supported: false}}), 0).ok, true);
assert.equal(media.parseLocalList(JSON.stringify(error), 0).ok, false);

// The live host's own preferences payload shape, which is what the panel reads.
const prefs = {ok: true, result: {revision: 3, values: {allow_dynamic_resolution: true, quality: 'performance', host_audio_playback: false},
  scope: 'host_remote', applies_to: 'next_session', permission_effect: 'subsequent_output_change_requests',
  profile_defaults: {quality: {fps: 30, bitrate_kbps: 8000}},
  runtime: {profile_defaults: true, host_audio_default: true, remote_available: true}}};
assert.equal(preferences.parse(JSON.stringify(prefs)).ok, true);

const names = (await readdir(new URL('.', FIXTURES))).filter(name => name.endsWith('.json'));
console.log('contracts: PASS (' + names.length + ' core fixtures available; state/bar/remote_bar/wss/event/error/preferences all accepted)');
