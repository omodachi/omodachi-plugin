#!/usr/bin/env python3
"""Assemble the release payload: this plugin, exactly as it is tracked.

The panel's "Install / Update" button runs `tools/install_host.py` inside the
plugin directory. Until INSTALL-1 this script *wrote* that file, copying core's
own installer in at package time into a gitignored directory - so a clone made
by `omarchy plugin add` had no Install button that worked, and no release could
be reproduced from the repository alone. It is a tracked file of this
repository now: a small bootstrap that fetches core and hands over to core's
installer. This script only packages it, and refuses to package a tree that
does not have it.

    python3 scripts/package.py
    python3 scripts/package.py --source https://github.com/omodachi/omodachi-core

The result is build/<plugin-id>.tar.gz plus build/PACKAGE.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
# The bootstrap the Install button runs. Tracked, not generated.
BOOTSTRAP = "tools/install_host.py"
# Where the Install button says it gets core from. The owner half of it lives
# in omodachi.json, which the bootstrap actually reads; this is the sentence
# the panel shows, and packaging checks the two agree.
DEFAULT_SOURCE = "https://github.com/omodachi/omodachi-core"
# This repository is the plugin: `manifest.json` is at the root, which is what
# `omarchy plugin add` clones. PAYLOAD is what belongs on a host; everything
# else in the tree is repository furniture.
PAYLOAD = ("manifest.json", "omodachi.json", "BarWidget.qml", "Panel.qml", "Service.qml",
           "OmodachiModel.js", "MediaPairingModel.js", "PreferencesModel.js",
           "assets", "components", "tools")


def payload_paths(root: Path) -> list[Path]:
    """Every regular file of the plugin itself, sorted, relative to `root`."""
    found = []
    for name in PAYLOAD:
        entry = root / name
        if entry.is_file():
            found.append(entry)
        elif entry.is_dir():
            found.extend(path for path in entry.rglob("*") if path.is_file())
    return sorted(
        path for path in found
        if not any(part.startswith(".") or part == "__pycache__"
                   for part in path.relative_to(root).parts)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=DEFAULT_SOURCE,
                        help="the source the Install button names in the panel")
    arguments = parser.parse_args()

    bootstrap = ROOT / BOOTSTRAP
    if not bootstrap.is_file():
        raise SystemExit(BOOTSTRAP + " is missing; it is a tracked file of this repository "
                         "and the Install button does nothing without it")

    # The install source is a literal in Service.qml so the argv stays fixed
    # and reviewable; packaging only checks that it is the one asked for, and
    # that omodachi.json - the file the bootstrap really reads - agrees.
    service = (ROOT / "Service.qml").read_text()
    declared = service.split('property string installSource: "', 1)[1].split('"', 1)[0]
    if declared != arguments.source:
        raise SystemExit("Service.qml installSource is " + declared + ", not " + arguments.source)
    pin = json.loads((ROOT / "omodachi.json").read_text())["core_source"]
    expected = "https://github.com/" + pin["owner"] + "/" + pin["repository"]
    if declared != expected:
        raise SystemExit("Service.qml names " + declared + " but omodachi.json pins " + expected)

    BUILD.mkdir(exist_ok=True)
    manifest = {"install_source": declared, "core_source": pin,
                "bootstrap": {BOOTSTRAP: hashlib.sha256(bootstrap.read_bytes()).hexdigest()},
                "plugins": {}}
    plugin = json.loads((ROOT / "manifest.json").read_text())["id"]
    archive_path = BUILD / (plugin + ".tar.gz")
    files = {}
    with tarfile.open(archive_path, "w:gz") as archive:
        for path in payload_paths(ROOT):
            name = "/".join(path.relative_to(ROOT).parts)
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            archive.add(path, arcname=plugin + "/" + name)
    manifest["plugins"][plugin] = {"archive": archive_path.name, "files": files}

    (BUILD / "PACKAGE.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
