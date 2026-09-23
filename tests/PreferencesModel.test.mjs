import assert from 'node:assert/strict';
import {readFileSync,writeFileSync,mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import vm from 'node:vm';
const ctx={JSON,Number,Object,Array};vm.createContext(ctx);
vm.runInContext(readFileSync(new URL('../PreferencesModel.js',import.meta.url),'utf8').replace('.pragma library',''),ctx);
const value={revision:3,scope:'host_remote',applies_to:'next_session',permission_effect:'subsequent_output_change_requests',values:{allow_dynamic_resolution:true,quality:'balanced',host_audio_playback:false},profile_defaults:{quality:{fps:60,bitrate_kbps:12000}},runtime:{profile_defaults:true,host_audio_default:true,remote_available:false}};
const parsed=ctx.parse(JSON.stringify({ok:true,result:value}));
assert.equal(parsed.ok,true);
assert.equal(ctx.command(parsed,'quality','performance').join('|'),'omodachi-host|preferences|set|--revision|3|--quality|performance');
assert.equal(ctx.command(parsed,'host_audio_playback',true).at(-1),'true');
assert.equal(ctx.command(parsed,'allow_dynamic_resolution',false).join('|'),'omodachi-host|preferences|set|--revision|3|--allow-dynamic-resolution|false');
assert.equal(ctx.command({...parsed,runtime:{...parsed.runtime,profile_defaults:false,remote_available:false}},'allow_dynamic_resolution',true).at(-1),'true');
assert.equal(ctx.command(parsed,'resolution','720p'),null);
assert.equal(ctx.command(parsed,'follow_orientation',true),null);
// --- PLUG-2: forward compatibility -----------------------------------------
// Settings reads `revision`, three values and three capability flags. A
// constant it does not branch on, a preference it does not offer and a profile
// core reshapes are all things this page can simply not show; none of them is
// a reason to black the whole page out with preferences_invalid.
assert.equal(ctx.parse(JSON.stringify({ok:true,result:{...value,permission_effect:'next_session'}})).ok,true);
assert.equal(ctx.parse(JSON.stringify({ok:true,result:{...value,scope:'device'}})).ok,true);
const extra=ctx.parse(JSON.stringify({ok:true,result:{...value,values:{...value.values,resolution:'1080p'},served_at:7}}));
assert.equal(extra.ok,true);
assert.equal(extra.values.resolution,undefined,'a key this build does not offer never reaches Settings');
assert.equal(ctx.command(extra,'resolution','720p'),null);
const grown=ctx.parse(JSON.stringify({ok:true,result:{...value,profile_defaults:{quality:{fps:60,bitrate_kbps:12000,max_pixels:1280*720}}}}));
assert.equal(grown.ok,true);
assert.equal(grown.profile.fps,60);
// A runtime flag core adds is ignored; one it stops sending reads as false,
// which disables that row instead of the page.
const runtimeGrown=ctx.parse(JSON.stringify({ok:true,result:{...value,runtime:{profile_defaults:true,host_audio_default:true,adaptive_control_available:true}}}));
assert.equal(runtimeGrown.ok,true);
assert.equal(runtimeGrown.runtime.remote_available,false);
assert.equal(runtimeGrown.runtime.adaptive_control_available,undefined);
assert.equal(ctx.command(runtimeGrown,'quality','balanced').at(-1),'balanced');
// A profile core stops sending is a description with nothing to describe.
const noProfile=ctx.parse(JSON.stringify({ok:true,result:{...value,profile_defaults:undefined}}));
assert.equal(noProfile.ok,true);
assert.equal(noProfile.runtime.profile_defaults,false);
assert.equal(ctx.command(noProfile,'quality','balanced'),null);
// A quality this build has no button for loads and displays; it is never written back.
const novelQuality=ctx.parse(JSON.stringify({ok:true,result:{...value,values:{...value.values,quality:'cinema'}}}));
assert.equal(novelQuality.ok,true);
assert.equal(novelQuality.values.quality,'cinema');
assert.equal(ctx.command(novelQuality,'quality','cinema'),null);
// Still refused: no CAS token, and a values object that cannot be read.
assert.equal(ctx.parse(JSON.stringify({ok:true,result:{...value,revision:'3'}})).ok,false);
assert.equal(ctx.parse(JSON.stringify({ok:true,result:{...value,values:{...value.values,allow_dynamic_resolution:'yes'}}})).ok,false);
assert.equal(ctx.parse(JSON.stringify({ok:true,result:{...value,values:[]}})).ok,false);
assert.equal(ctx.command(parsed,'quality','shell-command'),null);
assert.equal(ctx.command(parsed,'microphone',true),null);
assert.equal(ctx.command({...parsed,runtime:{...parsed.runtime,host_audio_default:false}},'host_audio_playback',true),null);
assert.equal(ctx.parse(JSON.stringify({ok:true,result:{...value,revision:-1}})).ok,false);
assert.equal(ctx.parse(JSON.stringify({ok:false,error:'preferences_revision_conflict'})).code,'preferences_revision_conflict');
assert.match(ctx.errorMessage('preferences_revision_conflict'),/elsewhere/);
assert.equal(ctx.route('{"view":"setup"}','devices').page,'settings');
assert.equal(ctx.route('{"view":"setup"}','devices').setupExpanded,true);
assert.equal(ctx.route('{"view":"settings"}','devices').setupExpanded,false);
assert.equal(ctx.route('{}','devices').page,'devices');
assert.equal(ctx.route('bad','settings').page,'settings');
assert.equal(ctx.uiChange({},'default_page','diagnostics'),null);
assert.equal(ctx.uiChange({},'icon_click','open').icon_click,'open');
// The official scoped API persists this entry; model changes preserve its other
// inline settings and can be re-read in a new plugin instance after reload.
const temp=mkdtempSync(join(tmpdir(),'omodachi-ui-prefs-'));
try {
 const path=join(temp,'shell.json');
 const initial={version:1,bar:{layout:{right:[{id:'com.omodachi.host',existing_option:7},{id:'other',untouched:true}]}}};
 writeFileSync(path,JSON.stringify(initial));
 const next=ctx.uiChange(initial.bar.layout.right[0],'default_page','settings');
 initial.bar.layout.right[0]=JSON.parse(JSON.stringify(next));writeFileSync(path,JSON.stringify(initial));
 const reloaded=JSON.parse(readFileSync(path));
 assert.equal(ctx.ui(reloaded.bar.layout.right[0]).default_page,'settings');
 assert.equal(reloaded.bar.layout.right[0].existing_option,7);assert.equal(reloaded.bar.layout.right[1].untouched,true);
} finally {rmSync(temp,{recursive:true});}

// The Remote settings core does not store are not offered as if it did: a
// backend or a placement is an argument of `remote start`, never a saved key.
assert.equal(ctx.command(parsed,'remote_backend','vnc'),null);
assert.equal(ctx.command(parsed,'placement','left'),null);
assert.equal(ctx.command(parsed,'takeover_bar','top'),null);
assert.equal(Object.keys(ctx.HOST_FLAGS).sort().join(','),'allow_dynamic_resolution,biometric_auth,clipboard_sync,host_audio_playback,quality');
// AUTH-1. The switch is offered only when the host sends it, it is written
// only when the host says it supports it, and a host that predates it still
// loads the page instead of blacking it out.
assert.equal(parsed.values.biometric_auth,false);
assert.equal(parsed.runtime.biometric_auth_supported,false);
assert.equal(ctx.command(parsed,'biometric_auth',true),null);
const withAuth=ctx.parse(JSON.stringify({ok:true,result:{...value,values:{...value.values,biometric_auth:false}}}));
assert.equal(withAuth.ok,true);
assert.equal(withAuth.runtime.biometric_auth_supported,true);
assert.equal(ctx.command(withAuth,'biometric_auth',true).join(' '),
    'omodachi-host preferences set --revision 3 --biometric-auth true');
assert.equal(ctx.command(withAuth,'biometric_auth','yes'),null);
// The host switch says nothing about any device: it is one of AUTH-1's two
// switches and this page owns exactly that one.
const authOn=ctx.parse(JSON.stringify({ok:true,result:{...value,revision:4,values:{...value.values,biometric_auth:true}}}));
assert.equal(authOn.values.biometric_auth,true);
assert.equal(ctx.command(authOn,'biometric_auth',false).join(' '),
    'omodachi-host preferences set --revision 4 --biometric-auth false');
// CLIP-1. The same shape as AUTH-1's switch, with three answers instead of
// two: absent on a host that predates it, off when it is there, and never
// written with a value this build does not know.
assert.equal(parsed.values.clipboard_sync,'off');
assert.equal(parsed.runtime.clipboard_sync_supported,false);
assert.equal(ctx.command(parsed,'clipboard_sync','both'),null);
const withClip=ctx.parse(JSON.stringify({ok:true,result:{...value,values:{...value.values,clipboard_sync:'off'},
    runtime:{...(value.runtime||{}),clipboard_supported:true}}}));
assert.equal(withClip.ok,true);
assert.equal(withClip.runtime.clipboard_sync_supported,true);
assert.equal(withClip.runtime.clipboard_supported,true);
assert.equal(ctx.command(withClip,'clipboard_sync','host_to_device').join(' '),
    'omodachi-host preferences set --revision 3 --clipboard-sync host_to_device');
assert.equal(ctx.command(withClip,'clipboard_sync','both').join(' '),
    'omodachi-host preferences set --revision 3 --clipboard-sync both');
assert.equal(ctx.command(withClip,'clipboard_sync','device_to_host'),null);
assert.equal(ctx.command(withClip,'clipboard_sync',true),null);
// A mode a later host invents still loads - the chooser simply shows nothing
// selected - and it is still never written back by this build.
const future=ctx.parse(JSON.stringify({ok:true,result:{...value,values:{...value.values,clipboard_sync:'images'}}}));
assert.equal(future.ok,true);
assert.equal(future.values.clipboard_sync,'images');
assert.equal(ctx.command(future,'clipboard_sync','images'),null);
// A clipboard the host cannot reach yet is not a reason to refuse the write:
// the preference is stored and takes effect when the session is back.
const noBridge=ctx.parse(JSON.stringify({ok:true,result:{...value,values:{...value.values,clipboard_sync:'off'}}}));
assert.equal(noBridge.runtime.clipboard_supported,false);
assert.equal(noBridge.runtime.clipboard_sync_supported,true);
assert.equal(ctx.command(noBridge,'clipboard_sync','both').join(' '),
    'omodachi-host preferences set --revision 3 --clipboard-sync both');

// A pairing notification routes straight to the request that raised it.
const pairRoute=ctx.route(JSON.stringify({view:'devices',request_id:'pair_'+'c'.repeat(32)}),'overview');
assert.equal(pairRoute.page,'devices');
assert.equal(pairRoute.focusRequestId,'pair_'+'c'.repeat(32));
assert.equal(ctx.route('{"view":"devices","request_id":"nope"}','overview').focusRequestId,'');
console.log('PreferencesModel: PASS (host permission independent of capability; no host size/direction defaults; CAS/UI persistence)');
