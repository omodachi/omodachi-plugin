#!/usr/bin/env python3
"""Install these plugins on a host without restarting its shell.

The hard-won part: Omarchy's QML component cache can keep serving the old
source even after `rescanPlugins`, so a payload is never written back over the
same path. Each deploy writes a content-addressed `releases/<hash>/` directory
and switches the manifest's entryPoints to it; the running shell then has no
choice but to load a URL it has never seen. `keepLoaded` is dropped for the two
scans that release the previous singleton and restored afterwards.

Nothing else on the host is touched: not the shell process, not shell.json, not
another plugin, not display, input or firewall configuration. The plugin's own
directory is backed up first.

This repository is one plugin: `manifest.json` is at its root, which is what
`omarchy plugin add` clones and what this deploys.

    python3 scripts/deploy_plugin.py omarchy
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]
# What belongs on a host. Everything else in this tree is repository
# furniture: the tests, the scripts, the README, the licence, the preview.
PAYLOAD = ("omodachi.json", "BarWidget.qml", "Panel.qml", "Service.qml", "OmodachiModel.js",
           "MediaPairingModel.js", "PreferencesModel.js",
           "assets", "components", "tools")
# `omarchy-shell` talks to the running compositor, so it needs the instance
# signature a login shell would have had. A non-interactive ssh does not, and
# without it every `shell` call exits 1 — which read as "the deploy failed"
# when the payload had already landed.
SHELL = ('export HYPRLAND_INSTANCE_SIGNATURE=$(ls -t /run/user/$(id -u)/hypr | head -1); '
         "OMARCHY_PATH=/usr/share/omarchy omarchy-shell ")

# Runs on the host. Backs the owned plugin directory up, then extracts only
# releases/* plus the manifest, refusing any other member or a path escape.
REMOTE = r'''
from pathlib import Path
import datetime, io, json, sys, tarfile
plugin = sys.argv[1]
root = Path.home()/".config/omarchy/plugins"/plugin
root.mkdir(parents=True, exist_ok=True)
backups = root/".runtime-backups"
backups.mkdir(exist_ok=True)
backup = backups/(datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")+".tar.gz")
with tarfile.open(backup, "w:gz") as archive:
    for path in sorted(root.iterdir()):
        if path.name != ".runtime-backups":
            archive.add(path, arcname=path.name)
with tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()), mode="r:") as archive:
    manifest = None
    for member in archive:
        name = member.name
        if not member.isfile() or name.startswith("/") or ".." in Path(name).parts:
            raise SystemExit("invalid package path")
        payload = archive.extractfile(member).read()
        if name == "manifest.json":
            manifest = payload
        elif name.startswith("releases/") and all(not part.startswith("._") for part in Path(name).parts):
            destination = root/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(payload)
        else:
            raise SystemExit("unexpected package member " + name)
    if manifest is None:
        raise SystemExit("missing manifest")
    (root/"manifest.json").write_bytes(manifest)
print(json.dumps({"plugin": plugin, "backup": str(backup), "root": str(root)}))
'''

FINAL = r'''
from pathlib import Path
import json, sys
path = Path.home()/".config/omarchy/plugins"/sys.argv[1]/"manifest.json"
manifest = json.loads(path.read_text())
manifest["keepLoaded"] = True
path.write_text(json.dumps(manifest, indent=2)+"\n")
print(json.dumps({"keepLoaded": True}))
'''


def payload_files(directory: Path) -> dict[str, bytes]:
    found = []
    for name in PAYLOAD:
        entry = directory / name
        if entry.is_file():
            found.append(entry)
        elif entry.is_dir():
            found.extend(path for path in entry.rglob("*") if path.is_file())
    files = {}
    for path in sorted(found):
        parts = path.relative_to(directory).parts
        if any(part.startswith(".") or part.startswith("._") or part == "__pycache__" for part in parts):
            continue
        files["/".join(parts)] = path.read_bytes()
    if not files:
        raise SystemExit("no payload files under " + str(directory))
    return files


def build_package(directory: Path) -> tuple[bytes, str, dict[str, str]]:
    content = payload_files(directory)
    digest = hashlib.sha256()
    for name in sorted(content):
        digest.update(name.encode() + b"\0" + content[name] + b"\0")
    release = "releases/" + digest.hexdigest()[:16]
    manifest = json.loads((directory / "manifest.json").read_text())
    manifest["entryPoints"] = {kind: release + "/" + name for kind, name in manifest["entryPoints"].items()}
    # Two rescans with keepLoaded off release the previously mounted singleton.
    manifest["keepLoaded"] = False
    package = io.BytesIO()
    with tarfile.open(fileobj=package, mode="w") as archive:
        members = {release + "/" + name: data for name, data in content.items()}
        members["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
    return package.getvalue(), release, {name: hashlib.sha256(data).hexdigest() for name, data in content.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("host")
    parser.add_argument("--control-socket")
    arguments = parser.parse_args()

    ids = [json.loads((ROOT / "manifest.json").read_text())["id"]]
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5"]
    if arguments.control_socket:
        ssh += ["-S", arguments.control_socket]
    ssh += [arguments.host]

    def run(command: str, *, data: bytes | None = None) -> str:
        return subprocess.run(ssh + [command], input=data, capture_output=True, check=True).stdout.decode().strip()

    receipts = {}
    for plugin in ids:
        directory = ROOT
        if not (directory / "manifest.json").is_file():
            raise SystemExit("no manifest for " + plugin)
        package, release, hashes = build_package(directory)
        receipt = json.loads(run("python3 -c " + shlex.quote(REMOTE) + " " + shlex.quote(plugin), data=package))
        receipt.update(release=release, source_hashes=hashes)
        receipts[plugin] = receipt

    for _ in range(2):
        run(SHELL + "shell rescanPlugins")
        time.sleep(1)

    host_plugin = "com.omodachi.host"
    if host_plugin in receipts:
        expected = "/" + receipts[host_plugin]["release"] + "/Service.qml"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                current = json.loads(run(SHELL + "omodachi status"))
                if expected in current.get("runtimeSource", ""):
                    break
            except (subprocess.CalledProcessError, json.JSONDecodeError):
                pass
            time.sleep(0.5)
        else:
            raise SystemExit("the new service did not load; backups retained: "
                             + json.dumps({k: v["backup"] for k, v in receipts.items()}))

    for plugin in receipts:
        run("python3 -c " + shlex.quote(FINAL) + " " + shlex.quote(plugin))
    run(SHELL + "shell rescanPlugins")
    time.sleep(1)

    if host_plugin in receipts:
        # The final `rescanPlugins` reloads the singleton, and for a second or
        # two after it the shell answers `omarchy-shell is not responding`.
        # That is the deploy working, not failing — the loop above already
        # proved the new Service.qml is the one loaded — so the receipt waits
        # for it rather than the whole deploy exiting non-zero on a race.
        deadline = time.monotonic() + 20
        while True:
            try:
                receipts[host_plugin]["runtime"] = json.loads(run(SHELL + "omodachi status"))
                break
            except (subprocess.CalledProcessError, json.JSONDecodeError):
                if time.monotonic() >= deadline:
                    receipts[host_plugin]["runtime"] = {"error": "status did not answer within 20s"}
                    break
                time.sleep(0.5)
    print(json.dumps(receipts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
