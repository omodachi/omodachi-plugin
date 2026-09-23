#!/usr/bin/env node
// Feed canonical plugin-watch frames through OmodachiModel without exposing
// their payloads. Input is a JSON array, or {snapshot,frames:[...]}.
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
const source = await readFile(new URL('../OmodachiModel.js', import.meta.url), 'utf8');
const context = { console, Number, JSON, Object, Array, Buffer };
vm.createContext(context);
vm.runInContext(source.replace('.pragma library', ''), context);
const chunks = []; for await (const chunk of process.stdin) chunks.push(chunk);
const input = JSON.parse(Buffer.concat(chunks).toString('utf8'));
const frames = Array.isArray(input) ? input : (input.frames || []);
let snapshot = Array.isArray(input) ? null : (input.snapshot || null);
let instanceId = snapshot?.instance_id || '';
const results = [];
for (const raw of frames) {
  const line = typeof raw === 'string' ? raw : JSON.stringify(raw);
  const result = context.consumeLine(line, snapshot, instanceId);
  results.push({kind: result?.kind || 'invalid', code: result?.code,
    seq: result?.event?.seq, revision: result?.snapshot?.revision});
  if (result?.kind === 'snapshot' || result?.kind === 'event') {
    snapshot = result.snapshot;
    instanceId = snapshot.instance_id;
  } else if (result?.kind === 'resync') {
    snapshot = null;
    instanceId = '';
  }
}
const output = {results, state: context.asState(snapshot), instance_id: snapshot?.instance_id || null,
  revision: snapshot?.revision ?? null, event_cursor: snapshot?.event_cursor ?? null,
  snapshot: snapshot || null};
process.stdout.write(JSON.stringify(output) + '\n');
