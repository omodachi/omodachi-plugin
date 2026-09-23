import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const source = await readFile(new URL('../OmodachiModel.js', import.meta.url), 'utf8');
const context = { console, Number, JSON, Object, Array, Math };
vm.createContext(context);
vm.runInContext(source.replace('.pragma library', ''), context);

const remote = (overrides = {}) => ({session_id: null, state: 'offline', mode: null, backend: null, revision: 0, ...overrides});
const live = {session_id: 'rs_' + '0'.repeat(32), state: 'ready', mode: 'extend', backend: 'vnc', revision: 4};
const snapshot = (overrides = {}) => ({
  instance_id: 'instance-1', revision: 3, event_cursor: 10,
  host: {name: 'fixture', connected: true}, workspace: {active: 2}, focus: {window: null},
  agent: {kind: 'codex', status: 'working'}, herdr: {available: true},
  capabilities: {terminal: true, desktop: true}, catalog: {revision: 'cat-1', entries: []},
  remote: remote(), ...overrides
});

// --- the state machine -----------------------------------------------------
assert.equal(context.asState(null), 'loading');
assert.equal(context.asState(snapshot()), 'ready');
assert.equal(context.asState(snapshot({host: {connected: false}})), 'setup_required');
assert.equal(context.asState(snapshot({capabilities: {terminal: false, desktop: false}})), 'limited');
// A live session is not a reason to call the host busy any more: there are no
// leases, and the panel stays usable while the iPad holds the screen.
assert.equal(context.asState(snapshot({remote: live})), 'ready');

assert.equal(context.isStateSnapshot(snapshot()), true);
assert.equal(context.isStateSnapshot({host: {connected: true}, capabilities: {}}), false);
// remote is required as an object with a named state; the name itself is open.
assert.equal(context.isStateSnapshot({...snapshot(), remote: undefined}), false);
assert.equal(context.isStateSnapshot(snapshot({remote: {...remote(), state: null}})), false);
// `wake` is a live-host projection the demo fixtures do not carry.
assert.equal(context.isStateSnapshot(snapshot({wake: {state: 'awake'}})), true);

// --- PLUG-2: forward compatibility -----------------------------------------
// Twice in one day a field core added took the panel to connection:error while
// the host was healthy. A frame is now checked for what this panel reads, and
// for nothing else.
//
// 1. Unknown top-level fields ride along and are projected away.
assert.equal(context.isStateSnapshot(snapshot({invented: {}})), true);
assert.equal(context.isStateSnapshot(snapshot({stream: {state: 'offline'}, telemetry: {x: 1}})), true);
const future = context.parseFrame(JSON.stringify({ok: true, result: snapshot({invented: {deep: [1, 2]}})}));
assert.equal(future.kind, 'snapshot');
assert.equal(future.snapshot.invented, undefined, 'a field nobody reads never reaches QML');
// 2. Unknown enum values are carried, and simply are not "live".
assert.equal(context.isStateSnapshot(snapshot({remote: remote({state: 'hibernating'})})), true);
assert.equal(context.remoteState(snapshot({remote: remote({state: 'hibernating'})})), 'hibernating');
assert.equal(context.remoteActive(snapshot({remote: remote({state: 'hibernating'})})), false);
assert.equal(context.isStateSnapshot(snapshot({remote: {...live, backend: 'rdp', mode: 'mirror'}})), true);
assert.equal(context.remoteActive(snapshot({remote: {...live, backend: 'rdp', mode: 'mirror'}})), true);
assert.match(context.remoteLabel(snapshot({remote: {...live, backend: 'rdp'}})), /rdp/);
// 3. A cross-field invariant core owns is core's business, not a rejection here.
assert.equal(context.isStateSnapshot(snapshot({remote: remote({session_id: 'rs_x'})})), true);
// 4. An unknown state field inside a known object is merged and ignored.
assert.equal(context.isStateSnapshot(snapshot({capabilities: {terminal: true, desktop: true, tablet: true}})), true);
// 5. Still rejected: genuine malformation.
assert.equal(context.isStateSnapshot({...snapshot(), revision: undefined}), false);
assert.equal(context.isStateSnapshot({...snapshot(), revision: 'three'}), false);
assert.equal(context.isStateSnapshot({...snapshot(), event_cursor: -1}), false);
assert.equal(context.isStateSnapshot({...snapshot(), instance_id: ''}), false);
assert.equal(context.isStateSnapshot(snapshot({host: 'fixture'})), false);
assert.equal(context.isStateSnapshot(snapshot({remote: 'ready'})), false);
assert.equal(context.isStateSnapshot('not an object'), false);

// --- the four bar icon states ---------------------------------------------
assert.equal(context.remoteActive(snapshot()), false);
assert.equal(context.remoteActive(snapshot({remote: live})), true);
assert.equal(context.remoteActive(snapshot({remote: {...live, state: 'resizing'}})), true);
assert.equal(context.remoteActive(snapshot({remote: {...live, state: 'creating'}})), false);
assert.equal(context.remoteActive(snapshot({remote: {...live, state: 'stopping'}})), false);
assert.equal(context.iconState('setup_required', false), 'absent');
assert.equal(context.iconState('loading', false), 'idle');
assert.equal(context.iconState('ready', false), 'linked');
assert.equal(context.iconState('limited', false), 'linked');
assert.equal(context.iconState('ready', true), 'remote');
assert.equal(new Set(['absent', 'idle', 'linked', 'remote']).size, context.ICON_STATES.length);
for (const state of ['loading', 'ready', 'limited', 'setup_required', 'permission_required', 'unsupported', 'error'])
  assert.ok(context.iconTooltip(state, false, null).length > 0, state);
assert.match(context.iconTooltip('ready', true, {mode: 'takeover', backend: 'sunshine'}), /Takeover · sunshine/);

// --- bar roles core actually emits ----------------------------------------
const bar = {source: 'shell.json', source_status: 'available', position: 'left', revision: '0123456789abcdef',
  left: [{id: 'example.other-plugin', role: 'unsupported'}, {id: 'omarchy.workspaces', role: 'workspaces'}],
  center: [{id: 'omarchy.clock', role: 'clock'}],
  right: [{id: 'omarchy.tray', role: 'system_tray'}, {id: 'omarchy.agents', role: 'agent_usage'},
          {id: 'com.omodachi.host', role: 'panel'}, {id: 'omodachi.stream', role: 'stream'}]};
assert.equal(context.isStateSnapshot(snapshot({bar})), true);
// PLUG-2: a role core invents next is a module we draw generically, and an
// extra key on the bar object is a key we do not read. Neither is an error.
assert.equal(context.isStateSnapshot(snapshot({bar: {...bar, right: [{id: 'x', role: 'invented'}]}})), true);
assert.equal(context.isStateSnapshot(snapshot({bar: {...bar, extra: 'carried', source: 'somewhere.json'}})), true);
assert.equal(context.isStateSnapshot(snapshot({bar: {...bar, source_status: 'degraded'}})), true);
assert.equal(context.isStateSnapshot(snapshot({bar: {...bar, revision: 17}})), true);
assert.equal(context.isStateSnapshot(snapshot({bar: {...bar, position: 'north-east'}})), true);
assert.equal(context.barRole('agent_usage'), 'agent_usage');
assert.equal(context.barRole('invented'), 'module');
assert.equal(context.barRole(undefined), 'module');
const entries = context.barEntries({...bar, right: bar.right.concat([{id: 'omarchy.new', role: 'invented'}])});
assert.equal(entries.length, 8);
assert.equal(entries.at(-1).role, 'module');
assert.equal(entries.at(-1).known, false);
assert.equal(entries.find(row => row.id === 'omarchy.clock').region, 'center');
// Still rejected: a bar that is not an object, or an entry that is not one.
assert.equal(context.isStateSnapshot(snapshot({bar: 'top'})), false);
assert.equal(context.isStateSnapshot(snapshot({bar: {...bar, right: ['omarchy.tray']}})), false);

// --- bar.modules: the status rows CORE-1 §5 added --------------------------
const withModules = {...bar,
  right: bar.right.concat([{id: 'omarchy.audio', role: 'audio'}, {id: 'omarchy.power', role: 'power'}]),
  modules: [{id: 'omarchy.audio', role: 'audio', status: {volume: 0.74, muted: false}},
            {id: 'omarchy.power', role: 'power', status: null}]};
assert.equal(context.isStateSnapshot(snapshot({bar: withModules})), true);
assert.equal(context.barModules(withModules).length, 2);
assert.equal(context.barModules(withModules)[0].status.volume, 0.74);
assert.equal(context.barModules(withModules)[1].status, null);
// An empty list and an absent key are both "this host has none of them".
assert.equal(context.isStateSnapshot(snapshot({bar: {...bar, modules: []}})), true);
// PLUG-2: a status role core adds, a row with no status at all, and a reading
// too deep to draw are all accepted; the reading is dropped, the frame is not.
for (const tolerated of [[{id: 'omarchy.bluetooth', role: 'bluetooth', status: {connected: true}}],
                         [{id: 'omarchy.audio', role: 'audio'}],
                         [{id: 'omarchy.audio', role: 'audio', status: {volume: {nested: 1}}}],
                         [{id: 'omarchy.audio', role: 'audio', status: {volume: 0.5, extra: null}}]])
  assert.equal(context.isStateSnapshot(snapshot({bar: {...bar, modules: tolerated}})), true,
               'rejected a tolerable modules value: ' + JSON.stringify(tolerated));
assert.equal(context.barModules({modules: [{id: 'omarchy.bluetooth', role: 'bluetooth', status: {connected: true}}]})[0].role, 'module');
assert.equal(context.barModules({modules: [{id: 'omarchy.bluetooth', role: 'bluetooth', status: {connected: true}}]})[0].known, false);
assert.equal(JSON.stringify(context.barModules({modules: [{id: 'a', role: 'audio', status: {volume: {nested: 1}, muted: false}}]})[0].status), '{"muted":false}');
// Still rejected: modules that are not a list of objects.
for (const bad of [{}, 'audio', [7], [{role: 'audio', status: null}],
                   [{id: 'omarchy.audio', role: 'audio', status: 0.74}]])
  assert.equal(context.isStateSnapshot(snapshot({bar: {...bar, modules: bad}})), false,
               'accepted a malformed modules value: ' + JSON.stringify(bad));

// --- frames ----------------------------------------------------------------
assert.equal(context.parseFrame(JSON.stringify({ok: true, result: snapshot()})).kind, 'snapshot');
assert.equal(context.parseFrame('{"ok":true,"result":{"shell":"rm -rf"}}'), null);
assert.equal(context.parseFrame(JSON.stringify({ok: false, error: 'permission_required', message: 'x'})).kind, 'error');
// PLUG-2: an envelope core decorates is still the envelope it always was.
assert.equal(context.parseFrame(JSON.stringify({ok: true, result: snapshot(), served_at: 12})).kind, 'snapshot');
assert.equal(context.parseFrame(JSON.stringify({ok: false, error: 'setup_required', message: 'x', hint: 'run it'})).kind, 'error');
// An error code with no copy here still reports as an error, and every
// presentation helper answers it with its neutral fallback.
const novel = context.parseFrame(JSON.stringify({ok: false, error: 'quota_exhausted', message: 'later'}));
assert.equal(novel.kind, 'error');
assert.equal(novel.code, 'quota_exhausted');
assert.equal(context.isConnected(novel.code), false);
assert.ok(context.connectionLabel(novel.code).length > 0);
assert.ok(context.connectionHelp(novel.code).length > 20);
assert.equal(context.iconState(novel.code, false), 'absent');
assert.equal(context.parseFrame(JSON.stringify({ok: false, error: 7})).code, 'error');
assert.equal(context.parseFrame(JSON.stringify({ok: true, result: {...snapshot(), huge: '😀'.repeat(1100000)}})), null);

const stateEvent = {seq: 11, event_id: 'evt_11', type: 'state.changed', device_id: null,
  payload: {workspace: {active: 4}, revision: 4}, ts: 1};
const merged = context.consumeLine(JSON.stringify({event: stateEvent, instance_id: 'instance-1'}), snapshot(), 'instance-1');
// PLUG-2: an event envelope that grew a field, and an event type this build
// has never seen, both still move the cursor instead of killing the stream.
const decorated = context.consumeLine(JSON.stringify({event: stateEvent, instance_id: 'instance-1', origin: 'hub'}), snapshot(), 'instance-1');
assert.equal(decorated.kind, 'event');
const unknownType = context.consumeLine(JSON.stringify({instance_id: 'instance-1',
  event: {...stateEvent, type: 'agent.usage.changed', payload: {usage: {tokens: 12}}}}), snapshot(), 'instance-1');
assert.equal(unknownType.kind, 'event');
assert.equal(unknownType.snapshot.event_cursor, 11);
assert.equal(unknownType.snapshot.revision, 3, 'an event this build ignores must not rewrite the revision');
assert.equal(merged.kind, 'event');
assert.equal(merged.snapshot.workspace.active, 4);
assert.equal(merged.snapshot.event_cursor, 11);
assert.equal(context.consumeLine(JSON.stringify({event: {...stateEvent, seq: 13}, instance_id: 'instance-1'}), snapshot(), 'instance-1').kind, 'invalid');
assert.equal(context.consumeLine(JSON.stringify({event: stateEvent, instance_id: 'other'}), snapshot(), 'instance-1').kind, 'invalid');

// after_cursor lets a filtered private event leave a hole in seq numbering.
const jumped = context.consumeLine(JSON.stringify({event: {...stateEvent, seq: 14}, instance_id: 'instance-1', after_cursor: 10}), snapshot(), 'instance-1');
assert.equal(jumped.kind, 'event');
assert.equal(jumped.snapshot.event_cursor, 14);
assert.equal(context.consumeLine(JSON.stringify({event: {...stateEvent, seq: 14}, instance_id: 'instance-1', after_cursor: 11}), snapshot(), 'instance-1').kind, 'invalid');

const resync = {seq: 11, event_id: 'resync_11', type: 'resync.required', device_id: 'plugin', payload: {snapshot_required: true}, ts: 1};
assert.equal(context.consumeLine(JSON.stringify({event: resync, instance_id: 'instance-1'}), snapshot(), 'instance-1').kind, 'resync');

// remote and remote_bar are replaced whole, never deep-merged: releasing a
// session must not leave its id, mode or output behind.
const started = context.consumeLine(JSON.stringify({instance_id: 'instance-1',
  event: {...stateEvent, payload: {remote: live, revision: 4}}}), snapshot(), 'instance-1');
assert.equal(started.snapshot.remote.session_id, live.session_id);
assert.equal(context.remoteActive(started.snapshot), true);
const stopped = context.consumeLine(JSON.stringify({instance_id: 'instance-1',
  event: {...stateEvent, seq: 12, payload: {remote: remote(), revision: 5}}}), started.snapshot, 'instance-1');
assert.equal(stopped.kind, 'event');
assert.equal(stopped.snapshot.remote.session_id, null);
assert.equal(stopped.snapshot.remote.mode, null);
assert.equal(context.remoteActive(stopped.snapshot), false);

// The live shape from omodachi_core/remote/session.py:bar_projection. Note the
// string revision and the {id, monitor, windows, active, remote} rows - an
// earlier model wanted {label, occupied, output_name} and integer revisions,
// and silently rejected every frame a real session produced.
const remoteBar = {active: true, session_id: 'rs_' + '0'.repeat(32), output_name: 'OMODACHI-22597120e66e468f',
  viewport: {width: 1194, height: 834}, orientation: 'landscape', revision: '2',
  logical_size: {width: 1280.0, height: 894.0},
  workspaces: [{id: 4, monitor: 'eDP-1', windows: 1, active: false, remote: false},
               {id: 6, monitor: 'OMODACHI-22597120e66e468f', windows: 1, active: true, remote: true}]};
const withBar = context.parseFrame(JSON.stringify({ok: true, result: snapshot({remote: live, remote_bar: {...remoteBar, future_hint: 42}})}));
assert.equal(withBar.snapshot.remote_bar.workspaces[1].remote, true);
assert.equal(withBar.snapshot.remote_bar.revision, '2');
assert.equal(withBar.snapshot.remote_bar.workspaces[0].monitor, 'eDP-1');
// A row that has no monitor is still a row; a row missing `remote` is not.
assert.equal(context.normalizeRemoteBar({...remoteBar, workspaces: [{id: 1, monitor: null, windows: 0, active: false, remote: false}]}).active, true);
assert.equal(context.normalizeRemoteBar({...remoteBar, workspaces: [{id: 1, monitor: 'eDP-1', windows: 0, active: false}]}).active, false);
assert.equal(context.normalizeRemoteBar({...remoteBar, revision: 2}).revision, '2');
// PLUG-2: an orientation core adds still describes a live screen.
assert.equal(context.normalizeRemoteBar({...remoteBar, orientation: 'square'}).active, true);
assert.equal(context.normalizeRemoteBar({...remoteBar, orientation: 'square'}).orientation, 'square');
// A projection we cannot read at all is inactive, and never a rejected frame.
assert.equal(context.normalizeRemoteBar({...remoteBar, orientation: 7}).orientation, 'landscape');
assert.equal(context.isStateSnapshot(snapshot({remote: live, remote_bar: {active: true, session_id: ''}})), true);
assert.equal(context.parseFrame(JSON.stringify({ok: true, result: snapshot({remote: live, remote_bar: {active: true, session_id: ''}})})).snapshot.remote_bar.active, false);
assert.equal(withBar.snapshot.remote_bar.future_hint, undefined);
const cleared = context.consumeLine(JSON.stringify({instance_id: 'instance-1',
  event: {...stateEvent, payload: {remote_bar: {active: false}, revision: 4}}}), withBar.snapshot, 'instance-1');
assert.equal(JSON.stringify(cleared.snapshot.remote_bar), '{"active":false}');
assert.equal(context.parseFrame(JSON.stringify({ok: true, result: snapshot({remote_bar: null})})).snapshot.remote_bar.active, false);
assert.equal(context.parseFrame(JSON.stringify({ok: true, result: snapshot({remote_bar: {...remoteBar, viewport: {width: 0, height: 1}}})})).snapshot.remote_bar.active, false);

// --- what a real session actually sends ------------------------------------
// Both of these were found on the host: with a session running, every frame
// after the first was rejected and the panel reported connection:error while
// the session it was describing was healthy.

// 1. remote.session.changed is a notification, and its `revision` is the
// session's, not the state's. Reading it as a state revision made 2 <= 3 and
// stalled the cursor forever.
const notification = {seq: 11, event_id: 'evt_11', type: 'remote.session.changed', device_id: null,
  payload: {id: live.session_id, revision: 2, state: 'ready', reason: 'created'}, ts: 1};
const notified = context.consumeLine(JSON.stringify({event: notification, instance_id: 'instance-1', after_cursor: 10}), snapshot(), 'instance-1');
assert.equal(notified.kind, 'event');
assert.equal(notified.snapshot.event_cursor, 11);
assert.equal(notified.snapshot.revision, 3, 'a notification must not rewrite the state revision');
// A real state patch still must move the revision forward.
assert.equal(context.consumeLine(JSON.stringify({event: {...stateEvent, payload: {workspace: {active: 4}, revision: 2}}, instance_id: 'instance-1'}), snapshot(), 'instance-1').kind, 'invalid');

// 2. Opening a Remote screen creates workspaces beyond ten, and those rows
// carry null catalog entries because no keybinding selects them.
const manyWorkspaces = {active: 2, items: Array.from({length: 11}, (_, i) => ({
  id: i + 1, label: 'Workspace ' + (i + 1), active: i === 1, window_count: 0, occupied: false,
  select_entry_id: i < 10 ? 'omodachi.workspace.select.' + (i + 1) : null,
  move_entry_id: i < 10 ? 'omodachi.workspace.move.' + (i + 1) : null}))};
assert.equal(context.isStateSnapshot(snapshot({workspace: manyWorkspaces})), true);
assert.equal(context.isStateSnapshot(snapshot({workspace: {active: 11, items: manyWorkspaces.items}})), true);
// Duplicate or non-positive ids are still refused.
assert.equal(context.isStateSnapshot(snapshot({workspace: {active: 1, items: [manyWorkspaces.items[0], manyWorkspaces.items[0]]}})), false);
assert.equal(context.isStateSnapshot(snapshot({workspace: {active: 1, items: [{...manyWorkspaces.items[0], id: 0}]}})), false);

// --- panel-summon ----------------------------------------------------------
// The icon recalls the panel, so it names the panel's view. An argument core
// does not offer would make argparse exit non-zero, which this plugin reads as
// "the host is unavailable" - so the view is pinned to core's own list.
// --- MENU-2 / A-67: the icon is locked while a takeover is running ---------
// A takeover has this machine's screens blanked and the user's hands on the
// tablet, so neither button has anything it can usefully open here. Extended
// screen is the opposite case and is untouched.
assert.equal(context.takeoverLocked(snapshot({remote: remote()})), false, 'no session, no lock');
assert.equal(context.takeoverLocked(snapshot({remote: live})), false, 'extend is not locked');
assert.equal(context.takeoverLocked(snapshot({remote: {...live, mode: 'takeover'}})), true);
// A takeover that is not on screen yet, or has ended, is not a lock either.
assert.equal(context.takeoverLocked(snapshot({remote: {...live, mode: 'takeover', state: 'creating'}})), false);
assert.equal(context.takeoverLocked(snapshot({remote: {...live, mode: 'takeover', state: 'released'}})), false);
assert.equal(context.takeoverLocked(snapshot({remote: {...live, mode: 'takeover', state: 'resizing'}})), true,
  'a resize is still a live takeover');
assert.equal(context.takeoverLocked(null), false, 'an unknown host locks nothing');
assert.equal(context.remoteMode(snapshot({remote: {...live, mode: 'takeover'}})), 'takeover');
assert.equal(context.remoteMode(snapshot({remote: remote()})), null);
assert.equal(context.remoteMode(null), null);
// One short sentence, one verb, and the tooltip says the same thing.
assert.equal(context.TAKEOVER_LOCK_NOTICE, 'Locked while a takeover session is running');
assert.match(context.iconTooltip('ready', true, {mode: 'takeover', backend: 'sunshine'}),
  /Locked while a takeover session is running/);
assert.match(context.iconTooltip('ready', true, {mode: 'extend', backend: 'vnc'}),
  /bring the panel back to the device/);

assert.equal(context.summonCommand('overview').join('|'), 'omodachi-host|panel-summon|--view|overview');
assert.equal(context.summonCommand('keybindings').join('|'), 'omodachi-host|panel-summon|--view|keybindings');
assert.equal(context.summonCommand('settings').join('|'), 'omodachi-host|panel-summon|--view|settings');
assert.equal(context.summonCommand('setup').join('|'), 'omodachi-host|panel-summon|--view|overview');
assert.equal(context.summonCommand(undefined).join('|'), 'omodachi-host|panel-summon|--view|overview');

// Verbatim from `omodachi-host panel-summon` on alex@omarchy, 2026-09-18,
// with the iPad holding a live VNC takeover. SPEC-E3 §1.5 added `view` after
// SPEC-C wrote this classifier; a model that rejects the field it has not seen
// opens the local panel on top of the session it was told to recall.
const liveSummon = {ok: true, result: {route: 'remote', owner_device_id: 'spec-e2-cli', view: 'overview',
  session_id: 'rs_6c51465e3fd8429fbd7b0c5a8b58e924', revision: 2}};
assert.equal(context.classifySummon(liveSummon, 'overview').ok, true);
assert.equal(context.classifySummon(liveSummon, 'overview').route, 'remote');
assert.equal(context.classifySummon(liveSummon, 'overview').view, 'overview');
// ARCH-1 / A-59: a session left click asks for the app's own settings panel.
assert.equal(context.classifySummon({ok: true, result: {route: 'remote', view: 'settings',
  owner_device_id: 'ipad', session_id: live.session_id, revision: 4}}, 'settings').view, 'settings');
assert.equal(context.classifySummon({ok: true, result: {route: 'local', opened: false}}, 'settings').view, 'settings');
assert.equal(context.classifySummon(liveSummon, 'overview').value.owner_device_id, 'spec-e2-cli');
// Whatever core adds next rides along; it is never a reason to open a view here.
assert.equal(context.classifySummon({ok: true, result: {...liveSummon.result, expires_in_seconds: 60, placement: 'right'}}, 'overview').ok, true);
assert.equal(context.classifySummon({ok: true, result: {route: 'local', view: 'keybindings', opened: false}}, 'keybindings').ok, true);
assert.equal(context.classifySummon({ok: true, result: {route: 'local', view: 'keybindings', opened: false}}, 'keybindings').view, 'keybindings');
// A core that predates the echoed view acted on the view we asked for.
assert.equal(context.classifySummon({ok: true, result: {route: 'local', opened: false}}, 'keybindings').view, 'keybindings');
assert.equal(context.classifySummon({ok: true, result: {route: 'local', view: 'overview', opened: false}}).ok, true);
// What is still a failure: a local route that claims it opened something, a
// remote route with no device to recall, a view that is not a name at all.
assert.equal(context.classifySummon({ok: true, result: {route: 'local', view: 'overview', opened: true}}).ok, false);
assert.equal(context.classifySummon({ok: true, result: {route: 'local', view: 7, opened: false}}).ok, false);
assert.equal(context.classifySummon({ok: true, result: {route: 'remote', owner_device_id: 'ipad', session_id: live.session_id, revision: 4}}).route, 'remote');
assert.equal(context.classifySummon({ok: true, result: {route: 'remote'}}).ok, false);
assert.equal(context.classifySummon({ok: true, result: {route: 'elsewhere'}}).code, 'unsupported');
assert.equal(context.classifySummon(null).ok, false);

// --- presentation ----------------------------------------------------------
const rows = context.overviewRows(snapshot({remote: live, remote_bar: remoteBar}), 'ready');
assert.equal(rows.map(row => row.label).join('|'), 'Machine|Host|Remote|Agent|Herdr|Capabilities');
assert.match(rows[2].value, /Extended screen · vnc · 1194×834/);
assert.equal(context.overviewRows(snapshot(), 'ready')[2].value, 'Not started');
assert.equal(context.remoteLabel(snapshot({remote: {...live, state: 'resizing'}})), 'Extended screen · vnc · resizing');
for (const state of context.STATES) assert.ok(context.connectionHelp(state).length > 20, state);
for (const state of context.STATES) assert.ok(context.connectionLabel(state).length > 0, state);

// The line under Overview. The stale copy told a connected host to go approve a
// request on the iPad whatever was already paired or already running.
const paired = [{device_id: 'spec-e2-cli', status: 'authorized', active_credentials: 1, revoked_credentials: 0}];
const revokedOnly = [{device_id: 'spec-c-ipad', status: 'revoked', active_credentials: 0, revoked_credentials: 1}];
const recall = {ok: true, route: 'remote', view: 'overview', owner_device_id: 'spec-e2-cli', session_id: live.session_id};
assert.equal(context.overviewHint('ready', snapshot(), [], null), context.connectionHelp('ready'));
assert.equal(context.overviewHint('ready', snapshot(), revokedOnly, null), context.connectionHelp('ready'));
assert.equal(context.overviewHint('ready', snapshot(), paired, null), 'Ready.');
assert.equal(context.overviewHint('ready', snapshot({remote: live}), paired, null), 'Extended screen · vnc');
assert.equal(context.overviewHint('ready', snapshot({remote: live}), paired, recall), 'Extended screen · vnc · spec-e2-cli');
assert.equal(context.overviewHint('ready', snapshot({remote: {...live, mode: 'takeover'}}), paired, recall),
             'Takeover · vnc · spec-e2-cli');
// A recall left over from a session that has been replaced names the wrong iPad.
assert.equal(context.overviewHint('ready', snapshot({remote: {...live, session_id: 'rs_' + '1'.repeat(32)}}), paired, recall),
             'Extended screen · vnc');
// Every other connection state still explains itself the way it always did.
assert.equal(context.overviewHint('setup_required', snapshot(), paired, null), context.connectionHelp('setup_required'));
assert.equal(context.overviewHint('limited', snapshot(), paired, null), context.connectionHelp('limited'));
assert.ok(context.overviewHint('ready', snapshot(), [], null).indexOf('Connected.') < 0);
assert.equal(context.sanitizeState(snapshot({remote: live})).remoteBackend, 'vnc');
assert.equal(context.sanitizeState(null).remoteState, 'offline');
assert.equal(JSON.stringify(context.sanitizeState(snapshot())).includes('instance-1'), true);

// --- PLUG-3 / PAIR-2: the devices list and the pairing cards ---------------
const deviceFrame = {devices: [
  {device_id: 'com.omodachi.host', status: 'authorized', active_credentials: 2, device_name: null, role: 'plugin'},
  {device_id: 'ios-pad', status: 'authorized', active_credentials: 1, device_name: "Leo 的 iPad", role: 'companion'},
  {device_id: 'ios-old', status: 'revoked', active_credentials: 0, revoked_credentials: 1, device_name: null, role: 'companion'},
]};
const deviceRows = context.devices(deviceFrame);
assert.equal(deviceRows.map((row) => row.role).join(), 'plugin,companion,companion');
// The one row with no Remove button, and the only one revokeDevice refuses.
assert.equal(deviceRows.map((row) => row.revocable).join(), 'false,true,false');
// A host from before PAIR-2 sends no role at all; everything it lists is a
// companion, which is exactly what it was before the plugin row was labelled.
assert.equal(context.devices({devices: [{device_id: 'ios-pad', status: 'authorized', active_credentials: 1}]})[0].role,
             'companion');
// And a role core invents later is neither a crash nor a hidden Remove button.
assert.equal(context.devices({devices: [{device_id: 'ios-pad', status: 'authorized', active_credentials: 1, role: 'kiosk'}]})[0].role,
             'companion');
// An extra field is carried by being ignored, never by blanking the page.
assert.equal(context.devices({devices: [{device_id: 'ios-pad', status: 'authorized', active_credentials: 1, invented_later: {}}]}).length, 1);
// Genuine malformation is still refused, and one bad row is not a blank list.
assert.equal(context.devices({}), null);
assert.equal(context.devices({devices: 'nope'}), null);
assert.equal(context.devices({devices: [{device_id: 'ios-pad', status: 'authorized'}, {status: 'authorized'}]}).length, 1);

// --- CORE-2 §1: expiry on the Devices page --------------------------------
{
  const now = 1790150400;                 // 2026-09-23T16:00:00Z
  const day = 86400;
  const rows = context.devices({devices: [
    {device_id: 'ios-pad', status: 'authorized', active_credentials: 1, expires_at: now + 26 * day},
    {device_id: 'ios-soon', status: 'authorized', active_credentials: 1, expires_at: now + 3 * day - 60},
    {device_id: 'ios-gone', status: 'expired', active_credentials: 0, expired_credentials: 1, expires_at: now - day},
    {device_id: 'ios-legacy', status: 'authorized', active_credentials: 1, expires_at: null},
    {device_id: 'com.omodachi.host', status: 'authorized', active_credentials: 2, role: 'plugin', expires_at: null},
  ]});
  // An expired device is drawn, with a Remove button; an older plugin dropped it.
  assert.equal(rows.map((row) => row.status).join(), 'authorized,authorized,expired,authorized,authorized');
  assert.equal(rows.map((row) => row.revocable).join(), 'true,true,true,true,false');
  const expiry = rows.map((row) => context.deviceExpiry(row, now));
  assert.equal(JSON.stringify(expiry[0]), JSON.stringify({text: 'Expires 2026-10-19 (UTC)', soon: false}));
  assert.equal(expiry[1].soon, true);
  assert.match(expiry[1].text, /^Expires 2026-09-26 \(UTC\) - in 3 days; the device renews it/);
  assert.equal(expiry[2].soon, true);
  assert.match(expiry[2].text, /^Credential expired on 2026-09-22 - approve the device's next pairing request/);
  assert.equal(JSON.stringify(expiry[3]), '{"text":"","soon":false}');        // not known yet is not "never"
  assert.equal(JSON.stringify(expiry[4]), '{"text":"","soon":false}');        // the panel's own credential
  // Exactly seven days is inside the window, a second more is not.
  assert.equal(context.deviceExpiry({status: 'authorized', expires_at: now + 7 * day}, now).soon, true);
  assert.equal(context.deviceExpiry({status: 'authorized', expires_at: now + 7 * day + 1}, now).soon, false);
  assert.equal(context.deviceExpiry({status: 'authorized', expires_at: now + day}, now).text.includes('in 1 day;'), true);
  assert.equal(context.isoDay(0), '1970-01-01');
  assert.equal(context.isoDay(951782400), '2000-02-29');
  // A garbage expiry is no expiry, never a crash or a 1970 date.
  assert.equal(context.devices({devices: [{device_id: 'x', status: 'authorized', expires_at: 'soon'}]})[0].expires_at, null);
  // The theme's yellow, or the fallback.
  assert.equal(context.themeYellow('[colors]\nred = "#bf616a"\nyellow = "#ebcb8b"\n', '#fff'), '#ebcb8b');
  assert.equal(context.themeYellow('bright_yellow = "#ebcb8b"', '#fff'), '#fff');
  assert.equal(context.themeYellow(null, '#fff'), '#fff');
}

// --- PLUG-4: the revoked devices are a number, not 32 rows -----------------
// core now answers only what a user can act on and says how many revoked rows
// it left out. The footer is drawn off that number, so it has to be read
// strictly - and an older core that does not send it means "nothing to offer",
// never an undefined footer.
assert.equal(context.revokedHidden({devices: [], revoked_hidden: 32}), 32);
assert.equal(context.revokedHidden({devices: []}), 0);
assert.equal(context.revokedHidden({devices: [], revoked_hidden: 0}), 0);
assert.equal(context.revokedHidden({devices: [], revoked_hidden: -1}), 0);
assert.equal(context.revokedHidden({devices: [], revoked_hidden: 1.5}), 0);
assert.equal(context.revokedHidden({devices: [], revoked_hidden: '32'}), 0);
assert.equal(context.revokedHidden({devices: [], revoked_hidden: 99999}), 0);
assert.equal(context.revokedHidden(null), 0);
// The rows themselves are unchanged by the filter: a revoked row that core
// does send (`devices list --all`) still draws without a Remove button.
assert.equal(context.devices({devices: [{device_id: 'ios-old', status: 'revoked', active_credentials: 0}],
                              revoked_hidden: 0})[0].revocable, false);

const requestId = 'pair_' + 'a'.repeat(32);
const requestFrame = {requests: [{request_id: requestId, device_id: 'ios-pad', device_name: "Leo 的 iPad",
  status: 'pending', expires_at: 1789755064, remote_addr: '192.168.1.22',
  ssh_fingerprint: 'SHA256:ujDWcEv6kr0qRWbh5Zu+R/83vdZp3Y9ngfYGcpAEx7g',
  ssh_public_key: 'ssh-ed25519 AAAA', grants: {companion: false, media: false, ssh: false}}]};
const request = context.pairRequests(requestFrame)[0];
assert.equal(request.remote_addr, '192.168.1.22');
// Twelve characters of the digest, and the panel never draws the whole key.
assert.equal(request.ssh_fingerprint, 'SHA256:ujDWcEv6kr0q…');
assert.equal(JSON.stringify(request).includes('ssh-ed25519'), false);
assert.equal(context.requestDetail(request), 'ios-pad · from 192.168.1.22 · SHA256:ujDWcEv6kr0q…');
const announcement = context.requestNotification(request);
assert.equal(announcement.title, '\u201cLeo 的 iPad\u201d wants to connect');
assert.ok(announcement.body.includes('192.168.1.22'));
assert.ok(announcement.body.includes('SHA256:ujDWcEv6kr0q…'));
// The desktop notification says what one Approve gives away, before it is hit.
assert.ok(announcement.body.includes('screen · terminal · agent'));
assert.equal(context.GRANT_LINE, 'Approving grants: screen · terminal · agent');
// PAIR-2 hosts that could not read a peer address, and pre-PAIR-2 hosts that
// never sent one, both leave the line shorter rather than printing "undefined".
const bare = context.pairRequests({requests: [{request_id: requestId, device_id: 'ios-pad', device_name: 'iPad', status: 'pending'}]})[0];
assert.equal(bare.remote_addr, '');
assert.equal(bare.ssh_fingerprint, '');
assert.equal(context.requestDetail(bare), 'ios-pad');
assert.equal(context.pairRequests({}), null);
assert.equal(context.pairRequests({requests: [{request_id: 'nope', device_id: 'x', device_name: 'x'}]}).length, 0);

console.log('OmodachiModel: PASS (forward-compatible frames; PLUG-3 device roles and PAIR-2 request cards: the plugin row has no Remove, the card names its source and key; PLUG-4 revoked-device count)');

// --- INSTALL-1: the install status the panel polls --------------------------

// The first version of this read the file with validNonEmptyString, whose
// 256-character cap is right for one field and wrong for a document: every
// status the installer ever wrote came back null and the panel stayed blank.
const longStatus = JSON.stringify({stage: 'fetching', label: 'Fetching...',
  message: 'Fetching Omodachi Host from https://github.com/omodachi/omodachi-core.git (main)',
  detail: 'x'.repeat(200), ok: null, pid: 4242, updated: 1.5});
assert.ok(longStatus.length > 256);
assert.equal(context.parseInstallStatus(longStatus).stage, 'fetching');
assert.equal(context.parseInstallStatus(longStatus).ok, null);

// The installer replaces the file while the panel polls it, so a torn read is
// an ordinary event on this path and not something to report to the user.
assert.equal(context.parseInstallStatus('{"stage": "fetch'), null);
assert.equal(context.parseInstallStatus(''), null);
assert.equal(context.parseInstallStatus('[]'), null);
assert.equal(context.parseInstallStatus(JSON.stringify({stage: 'rm -rf /'})), null);
for (const stage of ['starting', 'checking', 'fetching', 'installing', 'removing', 'done', 'failed']) {
  assert.equal(context.parseInstallStatus(JSON.stringify({stage})).stage, stage);
}

// Only the two terminal stages carry a verdict; everything else is "running".
assert.equal(context.parseInstallStatus(JSON.stringify({stage: 'done', ok: true})).ok, true);
assert.equal(context.parseInstallStatus(JSON.stringify({stage: 'failed', ok: false})).ok, false);
assert.equal(context.parseInstallStatus(JSON.stringify({stage: 'installing', ok: null})).ok, null);

// A failure keeps the detail, because the detail is the part that says what to fix.
assert.equal(context.installLine('failed', 'Could not fetch the source.', 'host unreachable'),
  'Could not fetch the source.\nhost unreachable');
assert.equal(context.installLine('installing', 'Installing Omodachi Host', ''),
  'Installing Omodachi Host');
assert.equal(context.installLine('', 'x', 'y'), '');

console.log('OmodachiModel: PASS (INSTALL-1 install status: whole documents parse, torn reads and unknown stages are ignored, failures keep their detail)');

// --- PLUG-5: a patch for a field the snapshot has not got yet ---------------

// The clean VM produced this at the first event after `omarchy plugin add`:
// OmodachiModel.js:384 TypeError: Value is null and could not be converted to
// an object. mergeObject cloned a base of null and then assigned into it.
assert.deepEqual(context.mergeObject(null, {a: 1}), {a: 1});
assert.deepEqual(context.mergeObject(undefined, {a: 1}), {a: 1});
assert.deepEqual(context.mergeObject(7, {a: 1}), {a: 1});
assert.deepEqual(context.mergeObject([], {a: 1}), {a: 1});
// A real base still merges, and still merges deeply.
assert.deepEqual(context.mergeObject({a: 1, b: {c: 1, d: 2}}, {b: {c: 9}}),
  {a: 1, b: {c: 9, d: 2}});

// And the frame that carried it now survives. `wake` is one of the optional
// state fields, so a snapshot can legitimately not have it - and then the
// first `wake.changed` event is a patch for a key whose base is undefined.
// That is the shape the clean VM hit.
const plug5Snapshot = snapshot({revision: 3, event_cursor: 10});
assert.ok(!('wake' in plug5Snapshot));
const plug5Event = {instance_id: 'instance-1', seq: 11, type: 'wake.changed',
  event_id: 'ev_plug5', ts: 1789935000.0,
  payload: {wake: {supported: true, armed: false}, revision: 4}};
const plug5 = context.mergePatch(plug5Snapshot, plug5Event, 'instance-1');
assert.equal(plug5.kind, 'event');
assert.deepEqual(plug5.snapshot.wake, {supported: true, armed: false});
assert.equal(plug5.snapshot.event_cursor, 11);
assert.equal(plug5.snapshot.revision, 4);

console.log('OmodachiModel: PASS (PLUG-5: a patch for a state field the snapshot has not got yet replaces it instead of throwing)');
