#!/usr/bin/env python3
"""Linux-only QML lifecycle probe: the real Service.qml, a synthetic helper.

Runs the unchanged `Service.qml` at this repository root in an offscreen
Quickshell with a fake `omodachi-host` on PATH. It proves the three things that
have actually broken on a host - FailedToStart with no binary installed, the
no-Host route, and recovery after the helper exits - plus that a live
state.remote turns the icon to its fourth state and sends the left click to the
device instead of the local panel.

It never touches the live daemon, a credential, or the user's shell.

    python3 tests/runtime_watch_probe.py     # on the Omarchy host only
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
# This repository is the plugin: `manifest.json` is at its root.
PLUGIN = ROOT
qa = ROOT / ".runtime-qa" / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%f")
qa.mkdir(parents=True)
(qa / "bin").mkdir()
for name in ["Service.qml", "OmodachiModel.js", "MediaPairingModel.js", "PreferencesModel.js"]:
    shutil.copyfile(PLUGIN / name, qa / name)

(qa / "shell.qml").write_text('''import QtQuick
import Quickshell
import Quickshell.Io
ShellRoot {
    Service { id: bridge; shell: localShell }
    QtObject {
        id: localShell
        property string lastPayload: ""
        function summon(id, payload) { lastPayload = payload; return true }
        function hide(id) { return true }
        function isPluginOpen(id) { return false }
    }
    IpcHandler {
        target: "qa"
        function activate(): void { bridge.activate() }
        function payload(): string { return localShell.lastPayload }
        function devices(): void { bridge.refreshDevices() }
        function approve(): void { bridge.approve("pair_" + "a".repeat(32)) }
        function message(): string { return JSON.stringify({message: bridge.adminMessage, error: bridge.adminError}) }
    }
}
''')

env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
           PATH=str(qa / "bin") + ":/usr/bin")
logfile = (qa / "quickshell.log").open("w")
process = subprocess.Popen(["/usr/bin/quickshell", "-n", "-p", str(qa)], env=env,
                           stdout=logfile, stderr=subprocess.STDOUT)
checks = []


def ipc(target, method):
    run = subprocess.run(["/usr/bin/quickshell", "ipc", "--pid", str(process.pid), "call", target, method],
                         env=env, capture_output=True, text=True)
    if run.returncode:
        raise RuntimeError(run.stderr.strip())
    return json.loads(run.stdout)


def call(target, method):
    subprocess.run(["/usr/bin/quickshell", "ipc", "--pid", str(process.pid), "call", target, method],
                   env=env, check=True, capture_output=True)


def wait_for(predicate, limit=15):
    deadline = time.monotonic() + limit
    last_error = ""
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("probe shell exited: " + (qa / "quickshell.log").read_text())
        try:
            value = ipc("omodachi", "status")
            if predicate(value):
                return value
        except (RuntimeError, json.JSONDecodeError) as error:
            last_error = str(error)
        time.sleep(.1)
    raise RuntimeError("probe timed out: " + last_error + "\n" + (qa / "quickshell.log").read_text())


def helper(frame):
    # Only plugin-watch is long-lived. Every other subcommand answers and exits,
    # or the panel's own device/preferences polls would sit on a sleeping child.
    path = qa / "bin" / "omodachi-host"
    path.write_text("#!/usr/bin/python3\nimport json,sys,time\n"
                    "if sys.argv[1:] != ['plugin-watch']:\n"
                    " print(json.dumps({'ok':False,'error':'setup_required','message':'qa'}));sys.exit(1)\n"
                    "print(" + repr(json.dumps(frame)) + ",flush=True)\ntime.sleep(60)\n")
    path.chmod(0o700)


def snapshot(remote):
    return {"instance_id": "runtime-qa", "revision": 1, "event_cursor": 0,
            "host": {"name": "qa", "connected": True}, "workspace": {"active": 1},
            "focus": {"window": None}, "agent": {"kind": "codex", "status": "idle"},
            "herdr": {"available": True}, "remote": remote,
            "capabilities": {"desktop": True, "terminal": True},
            "catalog": {"revision": None, "entries": []}}


OFFLINE = {"session_id": None, "state": "offline", "mode": None, "backend": None, "revision": 0}
LIVE = {"session_id": "rs_" + "0" * 32, "state": "ready", "mode": "extend", "backend": "vnc", "revision": 4}

try:
    first = wait_for(lambda state: state["connection"] == "setup_required" and not state["helperRunning"])
    checks.append({"test": "missing_executable_is_setup_required_not_a_crash", "state": first})

    helper({"ok": False, "error": "setup_required", "message": "qa_daemon_absent"})
    absent = wait_for(lambda state: state["connection"] == "setup_required" and state["helperRunning"])
    checks.append({"test": "failed_start_retries_and_recovers_once_the_binary_exists", "state": absent})

    call("qa", "activate")
    payload = ipc("qa", "payload")
    assert payload == {"view": "overview"}, payload
    checks.append({"test": "no_host_click_opens_the_local_panel", "payload": payload})

    helper({"ok": True, "result": snapshot(OFFLINE)})
    os.kill(absent["helperPid"], signal.SIGTERM)
    recovered = wait_for(lambda state: state["connection"] == "ready" and state["helperRunning"]
                         and state["helperPid"] != absent["helperPid"])
    assert recovered["iconState"] == "linked", recovered
    checks.append({"test": "helper_exit_recovers_and_the_icon_reaches_its_connected_state", "state": recovered})

    # A live session: the fourth icon state, and a left click that does not
    # open anything here. panel-summon answers route=remote, so no local view.
    live_helper = """#!/usr/bin/python3
import json,sys,time
argv=sys.argv[1:]
if argv == ['plugin-watch']:
 print(json.dumps({'ok':True,'result':json.loads(""" + repr(json.dumps(snapshot(LIVE))) + """)}),flush=True);time.sleep(60)
elif argv == ['panel-summon','--view','overview']:
 print(json.dumps({'ok':True,'result':{'route':'remote','owner_device_id':'qa-ipad','view':'overview','session_id':'rs_'+'0'*32,'revision':4}}))
elif argv == ['devices','list']:
 print(json.dumps({'ok':True,'result':{'devices':[{'device_id':'qa-device','status':'authorized','active_credentials':1,'revoked_credentials':0}]}}))
elif argv == ['pair','pending']:
 print(json.dumps({'ok':True,'result':{'requests':[{'request_id':'pair_'+'a'*32,'device_id':'qa-device','device_name':'QA companion','status':'pending'}]}}))
elif argv[:3] == ['pair','approve','pair_'+'a'*32]:
 out={'request_id':'pair_'+'a'*32,'device_id':'qa-device','status':'approved'}
 if '--remote' in argv: out['remote']={'device_id':'qa-device','media_authorized':True,'epoch':1}
 print(json.dumps({'ok':True,'result':out}))
elif argv[:1] == ['media-pairing']:
 print(json.dumps({'ok':True,'result':{'requests':[],'certificate_revocation_supported':False}}))
elif argv[:1] == ['preferences']:
 print(json.dumps({'ok':False,'error':'setup_required','message':'qa'}))
else:
 print(json.dumps({'ok':False,'error':'error','message':'qa_invalid_argv'}));sys.exit(1)
"""
    path = qa / "bin" / "omodachi-host"
    path.write_text(live_helper)
    path.chmod(0o700)
    os.kill(recovered["helperPid"], signal.SIGTERM)
    streaming = wait_for(lambda state: state["remoteState"] == "ready" and state["iconState"] == "remote")
    checks.append({"test": "state_remote_reaches_the_fourth_icon_state", "state": streaming})

    before = ipc("qa", "payload")
    call("qa", "activate")
    time.sleep(1.5)
    assert ipc("qa", "payload") == before, "a click during a live session must not open a local view"
    activated = wait_for(lambda state: state["widgetActivations"] >= 1 and state["lastSummon"])
    # The recall answers with the view it acted on. SPEC-E3 §1.5 added that
    # field after SPEC-C froze the classifier, and the frozen classifier read
    # it as a failure and opened the local panel over the live session.
    assert activated["lastSummon"] == {"ok": True, "route": "remote", "view": "overview",
                                       "owner_device_id": "qa-ipad",
                                       "session_id": "rs_" + "0" * 32}, activated["lastSummon"]
    assert activated["error"] == "", activated
    checks.append({"test": "click_during_a_session_recalls_the_device_and_opens_nothing_here",
                   "widgetActivations": activated["widgetActivations"],
                   "lastSummon": activated["lastSummon"]})

    call("qa", "devices")
    listed = wait_for(lambda state: state["devicesLoaded"] and state["requestsLoaded"]
                      and state["deviceCount"] == 1 and state["pendingPairRequests"] == 1)
    checks.append({"test": "devices_and_pending_requests_load_from_fixed_argv", "state": listed})

    call("qa", "approve")
    wait_for(lambda state: not state["adminBusy"] and state["adminOperation"] == "")
    message = ipc("qa", "message")
    assert message["error"] == "", message
    checks.append({"test": "one_step_approve_consumes_the_hosts_answer", "result": message})

    print(json.dumps({"utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      "fixture": "isolated synthetic helper; no live daemon, credential or shell change",
                      "checks": checks}, indent=2))
finally:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    logfile.close()
