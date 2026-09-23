import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../MediaPairingModel.js',import.meta.url),'utf8');
const context={JSON,Number,Object,Array};vm.createContext(context);vm.runInContext(source.replace('.pragma library',''),context);
const item={attempt_id:'11111111-1111-1111-1111-111111111111',request_id:'22222222-2222-2222-2222-222222222222',
    client_cert_sha256:'a'.repeat(64),device_id:'fixture-ipad',status:'awaiting_local_approval',paired:false,media_authorized:false,expires_in_ms:90000};
assert.equal(context.summary(item).canApprove,true);
assert.deepEqual(Object.keys(context.localBinding(item)).sort(),['attempt_id','client_cert_sha256','request_id']);
assert.equal(context.summary({...item,status:'awaiting_client_proof',media_authorized:true}).paired,false);
// PLUG-2: a combination core owns is core's invariant, not a row we delete.
assert.equal(context.summary({...item,status:'awaiting_client_proof',paired:true,media_authorized:true}).paired,true);
assert.equal(context.label({...item,status:'paired',paired:true,media_authorized:true}),'Paired for Remote');
assert.equal(context.summary({...item,pin:'4826'}),null);
assert.equal(context.summary({...item,credential:'SECRET'}),null);
// PAIR-3: presence+type. An identifier whose exact spelling is core's business
// draws its row; only a row core could act on is offered a button, so an
// uppercase fingerprint is readable but not `bindable`.
assert.equal(context.summary({...item,client_cert_sha256:'A'.repeat(64)}).bindable,false);
assert.equal(context.summary({...item,client_cert_sha256:'A'.repeat(64)}).canApprove,false);
assert.equal(context.localBinding({...item,client_cert_sha256:'A'.repeat(64)}),null);
assert.equal(context.summary(item).bindable,true);
assert.equal(context.summary({...item,expires_in_ms:0}).canApprove,false);
assert.equal(context.summary({...item,status:'revocation_pending'}).paired,false);

// --- PLUG-2: forward-compatible pairing rows -------------------------------
// A status this build has never seen still describes a real request: it keeps
// its row, gets a neutral sentence, and offers neither Approve nor Cancel.
const novel={...item,status:'awaiting_attestation'};
assert.equal(context.summary(novel).status,'awaiting_attestation');
assert.equal(context.summary(novel).known,false);
assert.equal(context.summary(novel).canApprove,false);
assert.equal(context.summary(novel).canCancel,false);
assert.equal(context.label(novel),'Remote pairing reported by the host');
assert.equal(context.summary(item).known,true);
// Extra fields ride along and are projected away; the row is not rejected.
assert.equal(context.summary({...item,attestation:{level:2},expires_in_ms:600000}).canApprove,true);
const forward=context.parseLocalList(JSON.stringify({ok:true,result:{requests:[novel,{...item,attempt_id:'33333333-3333-3333-3333-333333333333'}],
    certificate_revocation_supported:true,served_at:12}}),1000);
assert.equal(forward.ok,true);
assert.equal(forward.requests.length,2);
assert.equal(forward.requests[0].status,'awaiting_attestation');
assert.equal(forward.certificateRevocationSupported,true);
// A host that does not report the capability flag at all simply does not have it.
const noFlag=context.parseLocalList(JSON.stringify({ok:true,result:{requests:[item]}}),1000);
assert.equal(noFlag.ok,true);
assert.equal(noFlag.certificateRevocationSupported,false);
// Still refused: secrets in a row, and a body that is not a list of requests.
assert.equal(context.summary({...item,status:'Not A Status'}),null);
assert.equal(context.parseLocalList(JSON.stringify({ok:true,result:{requests:'none'}}),1000).ok,false);


const received=context.parseLocalList(JSON.stringify({ok:true,result:{requests:[item],certificate_revocation_supported:false}}),1000);
assert.equal(received.ok,true);assert.equal(received.requests.length,1);
assert.equal(context.currentBinding(received.requests,context.localBinding(item),'approve',2000).attempt_id,item.attempt_id);
assert.equal(context.currentBinding(received.requests,context.localBinding(item),'approve',100000),null);
assert.equal(context.mediaCommand(received.requests,context.localBinding(item),'approve',2000).join('|'),
    ['omodachi-host','media-pairing','approve',item.attempt_id,item.request_id,item.client_cert_sha256].join('|'));
assert.equal(context.parseLocalList(JSON.stringify({ok:false,error:'unknown_operation'}),1000).ok,false);
assert.equal(context.parseLocalList(JSON.stringify({ok:true,result:{requests:[{...item,pin:'4826'}],certificate_revocation_supported:false}}),1000).ok,false);
const companionId='pair_'+'a'.repeat(32);
const pending=[{request_id:companionId,status:'pending',device_id:'fixture-ipad'}];
assert.equal(context.companionCommand(pending,companionId,false).includes('--remote'),false);
assert.equal(context.companionCommand(pending,companionId,true).at(-1),'--remote');
// PAIR-3: Approve never becomes a smaller Approve. `--remote` does not depend
// on whether the panel could read the media list - that dependency is exactly
// what paired a device for the terminal and not for the screen.
assert.equal(context.approveCommand(pending,companionId).join('|'),['omodachi-host','pair','approve',companionId,'--remote'].join('|'));
assert.equal(context.approveCommand(pending,'pair_'+'b'.repeat(32)),null);
assert.equal(context.approveCommand([{request_id:companionId,status:'approved'}],companionId),null);
// The repair for a device that only got the companion half.
assert.equal(context.grantRemoteCommand('fixture-ipad',companionId).join('|'),
    ['omodachi-host','media-pairing','grant-remote','fixture-ipad',companionId].join('|'));
assert.equal(context.grantRemoteCommand('fixture-ipad','not-a-request'),null);
assert.equal(context.grantRemoteCommand('bad id',companionId),null);
assert.equal(context.rejectCommand(pending,companionId).join('|'),['omodachi-host','pair','reject',companionId].join('|'));
assert.equal(context.rejectCommand(pending,'not-a-request-id'),null);
const approved={request_id:companionId,device_id:'fixture-ipad',status:'approved'};
assert.equal(context.actionResult('approve',companionId,null,approved).ok,true);
assert.equal(context.actionResult('approve_remote',companionId,{device_id:'fixture-ipad'},approved).ok,false);
// core's `grant_remote` answers {device_id, media_authorized}; an epoch is read
// when present and never required, which the previous fixture wrongly demanded.
const remoteApproved={...approved,remote:{device_id:'fixture-ipad',media_authorized:true}};
assert.equal(context.actionResult('approve_remote',companionId,{device_id:'fixture-ipad'},{...approved,remote:{device_id:'fixture-ipad',media_authorized:true,epoch:1}}).ok,true);
// PAIR-3 §1.2: a grant that did not land is a warning with a repair, not a
// success and not a mismatch.
const notGranted=context.actionResult('approve_remote',companionId,{device_id:'fixture-ipad'},
    {...approved,remote:{device_id:'fixture-ipad',media_authorized:false,reason:'media_pairing_unavailable'}});
assert.equal(notGranted.ok,true);
assert.equal(notGranted.warning,true);
assert.equal(notGranted.grantRemote,true);
assert.equal(notGranted.deviceId,'fixture-ipad');
assert.equal(notGranted.sourceRequestId,companionId);
assert.match(notGranted.message,/media_pairing_unavailable/);
assert.equal(context.actionResult('grant_remote','fixture-ipad',null,{device_id:'fixture-ipad',media_authorized:true}).ok,true);
assert.equal(context.actionResult('grant_remote','fixture-ipad',null,{device_id:'fixture-ipad',media_authorized:false}).ok,false);
assert.equal(context.actionResult('approve_remote',companionId,{device_id:'fixture-ipad'},remoteApproved).ok,true);
assert.equal(context.actionResult('approve_remote',companionId,{device_id:'fixture-ipad'},{...remoteApproved,status:'claimed'}).ok,true);
assert.equal(context.actionResult('approve_remote',companionId,{device_id:'fixture-ipad'},{...remoteApproved,status:'rejected'}).ok,false);
assert.equal(context.actionResult('approve',companionId,null,remoteApproved).ok,false);
assert.equal(context.actionResult('media_approve',item.attempt_id,context.localBinding(item),{...item,status:'awaiting_client_proof',media_authorized:true}).message,
    "Waiting for the device's pairing proof");
assert.equal(context.actionResult('media_approve',item.attempt_id,context.localBinding(item),{accepted:true,request_id:item.request_id,status:'awaiting_client_proof'}).ok,false);
const revoked={device_id:'fixture-ipad',revoked:1,media:{device_id:'fixture-ipad',media_authorized:false,pending_media_revocations:1,media_revocation_complete:false}};
assert.equal(context.actionResult('revoke','fixture-ipad',null,revoked).warning,true);
assert.equal(context.actionResult('revoke','fixture-ipad',null,{device_id:'fixture-ipad',revoked:1}).warning,true);
assert.equal(context.actionResult('revoke','other-device',null,revoked).ok,false);
assert.match(context.actionResult('revoke','fixture-ipad',null,{...revoked,media:{...revoked.media,pending_media_revocations:0}}).message,/could not be confirmed/);
assert.match(context.actionResult('revoke','fixture-ipad',null,{...revoked,desktop_cleanup:{released:false,recovery_required:true}}).message,/session cleanup/);

// --- PAIR-3 regression: the real host, with its permanent revocation records -
// Three `revocation_pending` rows the fork can never clean up. Their
// `request_id` is the fork's own UPPERCASE uniqueid, which the lowercase-only
// validator refused; the list came back `media_api_invalid`, `mediaApiReady`
// went false and Approve dropped `--remote` without saying so.
const hostFixture=await readFile(new URL('./fixtures/media-pending-with-revocations.json',import.meta.url),'utf8');
const hostList=context.parseLocalList(hostFixture,1000);
assert.equal(hostList.ok,true,'the host fixture must not fail the whole list');
assert.equal(hostList.requests.length,3);
assert.equal(hostList.certificateRevocationSupported,false);
// They are history, so they are not to-do items and offer no buttons.
assert.equal(hostList.requests.map(r=>r.status).join(','),'revocation_pending,revocation_pending,revocation_pending');
assert.equal(hostList.requests.every(r=>r.historical===true),true);
assert.equal(context.localApprovals(hostList.requests,1000).length,0);
// The uppercase uniqueid is carried back verbatim, never normalized.
assert.equal(hostList.requests[0].request_id,'A7E9C135-7326-E027-0108-4EEDBF0190C1');
assert.equal(context.summary(hostList.requests[0]).bindable,true);
// PAIR-3 §1.1: one unreadable row is dropped, not a veto on the list.
const mixed=context.parseLocalList(JSON.stringify({ok:true,result:{requests:[
    {...item,attempt_id:'44444444-4444-4444-4444-444444444444'},{nonsense:true},{...item,status:'Not A Status'}]}}),1000);
assert.equal(mixed.ok,true);
assert.equal(mixed.requests.length,1);
// ...but a row carrying a secret still fails the whole list.
assert.equal(context.parseLocalList(JSON.stringify({ok:true,result:{requests:[item,{...item,attempt_id:'55555555-5555-5555-5555-555555555555',credential:'X'}]}}),1000).ok,false);
// PAIR-3 core §2.2 splits history out; both shapes read the same.
const split=context.parseLocalList(JSON.stringify({ok:true,result:{requests:[item],
    history:[{...item,attempt_id:'66666666-6666-6666-6666-666666666666',status:'revocation_pending'}],
    certificate_revocation_supported:false}}),1000);
assert.equal(split.ok,true);
assert.equal(split.requests.length,2);
assert.equal(split.requests[0].historical,false);
assert.equal(split.requests[1].historical,true);
// PAIR-3 §1.3: the awaiting_local_approval to-do card nothing ever drew.
const todo=context.localApprovals(split.requests,1000);
assert.equal(todo.length,1);
assert.equal(todo[0].attempt_id,item.attempt_id);
assert.equal(todo[0].can_approve,true);
assert.equal(todo[0].needs_pin_resubmission,false);
const resubmit=context.parseLocalList(JSON.stringify({ok:true,result:{requests:[{...item,reason:'pin_resubmission_required'}]}}),1000);
assert.equal(context.localApprovals(resubmit.requests,1000)[0].needs_pin_resubmission,true);
assert.equal(context.localApprovals(resubmit.requests,1000)[0].can_approve,false);

// --- PLUG-4 -----------------------------------------------------------------
// The capability is read off the list, and a fork that can revoke leaves no
// history at all - which is what the page has to be able to draw.
const clean=context.parseLocalList(JSON.stringify({ok:true,result:{requests:[],history:[],
    certificate_revocation_supported:true}}),1000);
assert.equal(clean.ok,true);
assert.equal(clean.requests.length,0);
assert.equal(clean.certificateRevocationSupported,true);
assert.equal(context.deviceStatus(clean.requests,'ipad'),'No completed Remote pairing reported');
// `revoked` only ever arrives as the answer to a revoke; it is history, it has
// no buttons, and it has a sentence rather than `undefined`.
const revokedRow={...item,status:'revoked',paired:false};
assert.equal(context.summary(revokedRow).historical,true);
assert.equal(context.summary(revokedRow).canApprove,false);
assert.equal(context.summary(revokedRow).canCancel,false);
assert.equal(context.summary(revokedRow).known,true);
assert.equal(context.label(revokedRow),'Remote certificate revoked');
// The footer's one action, and the honest half of its answer.
const cleared=context.actionResult('purge','',null,{purged:['a','b'],kept:[]});
assert.equal(cleared.ok,true);
assert.equal(cleared.warning,undefined);
assert.equal(cleared.message,'Cleared 2 revoked device(s).');
assert.equal(context.actionResult('purge','',null,{purged:[],kept:[]}).message,'There was nothing to clear.');
const partial=context.actionResult('purge','',null,{purged:['a'],kept:[{device_id:'b',reason:'media_revocation_pending'}]});
assert.equal(partial.ok,true);
assert.equal(partial.warning,true);
assert.ok(partial.message.includes('1 could not be cleared yet'));
assert.equal(context.actionResult('purge','',null,{purged:'all'}).ok,false);
assert.equal(context.actionResult('purge','',null,{}).ok,false);
// A revoke that core completed still has to match the device it was asked for.
assert.equal(context.actionResult('revoke','ipad',null,{device_id:'ipad',revoked:1,
    media:{device_id:'ipad',media_authorized:false,pending_media_revocations:0,
           media_revocation_complete:true,certificate_revocation_supported:true},
    purged:{device_id:'ipad',purged:true}}).message,'Device access revoked.');
assert.equal(context.actionResult('revoke','ipad',null,{device_id:'other',revoked:1}).ok,false);

console.log('MediaPairingModel: PASS (one-step approve, real-host revocation fixture, local-approval cards, grant-remote repair, PLUG-4 revoke and clear)');
