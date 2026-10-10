"""LITE-1b C7: removing Omodachi after core is gone still takes back Odomo's
`tailscale serve` mapping - and only that one.

Core's Install adds one mapping and records it; core's own `--remove` takes it
back. When core's uninstaller is already gone, `tools/install_host.py` applies
the same rule itself. These tests drive it against a fake `tailscale` on a
temporary PATH (the shape `tailscale serve status --json` prints), and, when a
core checkout is at hand, run core's `odomo_serve.remove` on the same scenarios
and compare the answers.
"""
from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
NAME = "omodachi-lab.example-tailnet.ts.net"
OURS = "https+insecure://127.0.0.1:8099"

FAKE = r'''#!/usr/bin/env python3
import json, os, sys
state_path, log_path = os.environ["FAKE_TS_STATE"], os.environ["FAKE_TS_LOG"]
state = json.load(open(state_path))
args = sys.argv[1:]
open(log_path, "a").write(json.dumps(args) + "\n")
if args == ["status", "--json"]:
    print(json.dumps({"BackendState": "Running", "Self": {"DNSName": state["name"] + "."}}))
elif args == ["serve", "status", "--json"]:
    print(json.dumps(state["serve"]))
elif args[:1] == ["serve"] and args[-1] == "off":
    port = args[1].split("=")[1]
    state["serve"].get("TCP", {}).pop(port, None)
    state["serve"].get("Web", {}).pop(state["name"] + ":" + port, None)
    for key in ("TCP", "Web"):
        if not state["serve"].get(key):
            state["serve"].pop(key, None)
    json.dump(state, open(state_path, "w"))
else:
    sys.exit(2)
'''


def web(port, proxy):
    return {"TCP": {str(port): {"HTTPS": True}}, "Web": {f"{NAME}:{port}": {"Handlers": {"/": {"Proxy": proxy}}}}}


def merged(*configs):
    out = {"TCP": {}, "Web": {}}
    for config in configs:
        out["TCP"].update(config["TCP"])
        out["Web"].update(config["Web"])
    return out


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCENARIOS = {
    # name: (live serve config, record) -> what must be left in serve
    "ours, unchanged, beside a user's": (merged(web(443, "http://127.0.0.1:3000"), web(8443, OURS)),
                                         {"port": 8443, "owner": "omodachi"},
                                         web(443, "http://127.0.0.1:3000")),
    "ours, changed since": (web(443, "http://127.0.0.1:5000"), {"port": 443, "owner": "omodachi"},
                            web(443, "http://127.0.0.1:5000")),
    "already there, not ours": (web(443, OURS), {"port": 443, "owner": "user"}, web(443, OURS)),
    "no record": (web(443, OURS), None, web(443, OURS)),
    "already gone": ({}, {"port": 443, "owner": "omodachi"}, {}),
}


class RemovalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        (base / "bin").mkdir()
        tool = base / "bin/tailscale"
        tool.write_text(FAKE)
        tool.chmod(0o755)
        self.state, self.log = base / "ts.json", base / "ts.jsonl"
        patcher = mock.patch.dict(os.environ, {"FAKE_TS_STATE": str(self.state), "FAKE_TS_LOG": str(self.log),
                                               "PATH": str(base / "bin") + os.pathsep + os.environ["PATH"]})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.module = load(ROOT / "tools/install_host.py", "plugin_install_host_odomo")

    def scenario(self, home: Path, serve, record):
        self.state.write_text(json.dumps({"name": NAME, "serve": serve}))
        path = home / ".local/state/omodachi/tailscale-serve.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
        if record:
            path.write_text(json.dumps({"version": 1, "target": OURS, "dns_name": NAME, "created_at": 1, **record}))
        return path

    def served(self):
        return json.loads(self.state.read_text())["serve"]

    def test_only_a_mapping_the_record_says_is_ours_and_unchanged_is_turned_off(self):
        for name, (serve, record, left) in SCENARIOS.items():
            with self.subTest(name):
                home = Path(self.temp.name) / "home"
                self.module.HOME = home
                record_path = self.scenario(home, serve, record)
                with contextlib.redirect_stdout(io.StringIO()):
                    result = self.module.remove_tailscale_serve()
                self.assertEqual(self.served(), left)
                self.assertEqual(result["removed"], name.startswith("ours, unchanged"))
                self.assertFalse(record_path.exists())
                calls = [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []
                self.assertFalse([argv for argv in calls if "reset" in argv])

    def test_it_is_cores_rule(self):
        core = Path(os.environ.get("OMODACHI_CORE_TREE") or ROOT.parent / "omodachi-core")
        if not (core / "src/omodachi_core/odomo_serve.py").is_file():
            self.skipTest("no omodachi-core checkout with odomo_serve.py beside this one (set OMODACHI_CORE_TREE)")
        odomo_serve = load(core / "src/omodachi_core/odomo_serve.py", "core_odomo_serve")
        for name, (serve, record, _) in SCENARIOS.items():
            with self.subTest(name):
                home = Path(self.temp.name) / "plugin-home"
                self.module.HOME = home
                self.scenario(home, serve, record)
                with contextlib.redirect_stdout(io.StringIO()):
                    ours = self.module.remove_tailscale_serve()
                after_plugin = self.served()
                core_home = Path(self.temp.name) / "core-home"
                self.scenario(core_home, serve, record)
                theirs = odomo_serve.remove(core_home, log=lambda line: None)
                self.assertEqual(ours, theirs)
                self.assertEqual(after_plugin, self.served())
        self.assertEqual(self.module.SERVE_RECORD, odomo_serve.STATE)

    def test_the_removal_after_core_is_gone_runs_it(self):
        tree = ast.parse((ROOT / "tools/install_host.py").read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_locked_main")
        text = ast.unparse(main)
        self.assertIn("remove_tailscale_serve()", text)
        self.assertLess(text.index("remove_tailscale_serve()"), text.index("purge_only()"))


if __name__ == "__main__":
    unittest.main()
