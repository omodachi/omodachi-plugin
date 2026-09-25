"""Manifest and payload checks that do not need a host.

`omarchy plugin validate .` is the real gate; this is the part that can run in
a plain checkout, plus the two invariants a validator has no opinion about:
every fixed argv in the QML is the `omodachi-host` CLI this plugin is written
against, and no file still carries an old spelling of the name.

This repository is the plugin: `manifest.json` is at its root, which is what
`omarchy plugin add` clones and validates.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
# omodachi_core/cli.py:host_main
CLI_SUBCOMMANDS = {
    "health", "state", "capabilities", "herdr", "catalog", "panel-summon", "plugin-watch",
    "plugin-action", "desktop-entry", "devices", "pair", "media-pairing", "preferences",
    "remote", "workspace", "events",
}
# What a deploy or a package puts on a host, mirroring scripts/deploy_plugin.py
# and scripts/package.py. Everything else in this tree is repository
# furniture: the tests, the scripts, the docs, the README, the licence, the
# marketplace preview.
PAYLOAD = ("manifest.json", "omodachi.json", "BarWidget.qml", "Panel.qml", "Service.qml",
           "OmodachiModel.js", "MediaPairingModel.js", "PreferencesModel.js",
           "assets", "components", "tools")
FURNITURE = {"scripts", "tests", "docs", "build", "README.md", "LICENSE",
             "preview.png", ".gitignore", ".git"}


def payload_files() -> list[Path]:
    found = []
    for name in PAYLOAD:
        entry = ROOT / name
        if entry.is_file():
            found.append(entry)
        elif entry.is_dir():
            found.extend(path for path in entry.rglob("*") if path.is_file())
    return sorted(path for path in found
                  if not any(part.startswith(".") or part == "__pycache__"
                             for part in path.relative_to(ROOT).parts))


class ManifestTests(unittest.TestCase):
    def test_the_manifest_is_at_the_repository_root_with_real_entry_points(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["id"], "com.omodachi.host")
        self.assertRegex(manifest["id"], r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
        self.assertFalse(manifest["id"].startswith("omarchy."))
        self.assertNotIn("..", manifest["id"])
        self.assertEqual(set(manifest["kinds"]), {"panel", "service", "bar-widget"})
        self.assertEqual(manifest["license"], "MIT")
        for kind, relative in manifest["entryPoints"].items():
            candidate = ROOT / relative
            self.assertFalse(Path(relative).is_absolute(), relative)
            self.assertNotIn("..", Path(relative).parts)
            self.assertTrue(candidate.is_file(), relative)
            self.assertFalse(candidate.is_symlink(), relative)
            self.assertIn(candidate, payload_files(), relative)

    def test_every_top_level_entry_is_either_payload_or_declared_furniture(self):
        # A file that is neither would be shipped to a host by accident, or
        # silently left out of one.
        for entry in ROOT.iterdir():
            name = entry.name
            if name.startswith(".") and name != ".gitignore":
                continue
            self.assertIn(name, set(PAYLOAD) | FURNITURE, name)

    def test_the_repository_root_carries_a_readme_and_a_licence(self):
        for name in ("README.md", "LICENSE"):
            self.assertTrue((ROOT / name).is_file(), name)
        self.assertIn("MIT License", (ROOT / "LICENSE").read_text())

    def test_nothing_in_the_tree_is_a_symlink(self):
        # `omarchy-plugin-validate` refuses a plugin folder containing one.
        for path in ROOT.rglob("*"):
            if ".git" in path.parts:
                continue
            self.assertFalse(path.is_symlink(), str(path.relative_to(ROOT)))

    def test_host_manifest_declares_its_panel_preferences_for_the_official_settings_ui(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        widget = manifest["barWidget"]
        self.assertIn(widget["defaultSection"], {"left", "center", "right"})
        keys = {row["key"] for row in widget["schema"]}
        self.assertEqual(keys, set(widget["defaults"]))
        for row in widget["schema"]:
            self.assertIn(row["defaultValue"], row["options"])
            self.assertEqual(widget["defaults"][row["key"]], row["defaultValue"])

    def test_every_fixed_argv_names_a_real_core_subcommand(self):
        pattern = re.compile(r'"omodachi-host"\s*,\s*"([a-z-]+)"')
        seen = set()
        for path in payload_files():
            if path.suffix not in {".qml", ".js"}:
                continue
            for match in pattern.finditer(path.read_text()):
                seen.add(match.group(1))
        self.assertTrue(seen)
        self.assertLessEqual(seen, CLI_SUBCOMMANDS, "argv names a subcommand core does not have")

    def test_nothing_carries_an_old_spelling_of_the_name(self):
        stale = re.compile("oma" + "dochi|oma" + "dachi", re.IGNORECASE)
        offenders = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if path == Path(__file__) or path.suffix == ".png":
                continue
            try:
                text = path.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            if stale.search(text):
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])


class InstallBootstrapTests(unittest.TestCase):
    """INSTALL-1. The Install button's program has to be *in* the repository.

    `omarchy plugin add` clones this repository and runs it as it arrives. The
    button used to run a file that only existed on a developer machine,
    written by scripts/package.py and hidden by .gitignore, so the one path a
    real user takes was the one path nobody had.
    """

    BOOTSTRAP = "tools/install_host.py"

    def _tracked(self) -> set[str]:
        result = subprocess.run(["git", "-C", str(ROOT), "ls-files"],
                                capture_output=True, text=True, check=False)
        if result.returncode != 0:
            self.skipTest("not a git checkout")
        return set(result.stdout.split())

    def test_the_install_bootstrap_is_a_tracked_file_of_this_repository(self):
        tracked = self._tracked()
        self.assertIn(self.BOOTSTRAP, tracked)
        self.assertIn("omodachi.json", tracked)

    def test_nothing_in_the_payload_is_ignored_by_git(self):
        # A payload file that git ignores is a file a clone does not get, and
        # `omarchy plugin add` ships exactly what the clone has.
        relative = ["/".join(path.relative_to(ROOT).parts) for path in payload_files()]
        result = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "--stdin"],
                                input="\n".join(relative), capture_output=True, text=True,
                                check=False)
        self.assertEqual(result.stdout.strip(), "", "these payload files are gitignored")

    def test_the_bootstrap_runs_the_installer_out_of_the_fetched_sources(self):
        body = (ROOT / self.BOOTSTRAP).read_text()
        # It must never carry its own copy of core's installer logic: this file
        # fetches core and hands over, and that hand-over is the whole design.
        self.assertIn('SOURCE_DIR / "scripts/install_host.py"', body)
        self.assertIn("--local", body)
        self.assertNotIn("DAEMON_UNIT", body)

    def test_the_panel_and_the_pin_name_the_same_repository(self):
        pin = json.loads((ROOT / "omodachi.json").read_text())["core_source"]
        declared = (ROOT / "Service.qml").read_text().split(
            'property string installSource: "', 1)[1].split('"', 1)[0]
        self.assertEqual(declared, f"https://github.com/{pin['owner']}/{pin['repository']}")

    def test_the_install_argv_is_literals_and_one_path_inside_this_plugin(self):
        # The marketplace security baseline looks for a shell command built at
        # runtime. This one is a fixed list plus Qt.resolvedUrl of a file that
        # travels with the plugin.
        body = (ROOT / "Service.qml").read_text()
        argv = body.split("terminalProcess.command = [", 1)[1].split("]", 1)[0]
        self.assertIn('"omarchy-launch-terminal", "python3", "-I", "-B",', argv)
        self.assertIn('Qt.resolvedUrl("tools/install_host.py")', argv)
        self.assertNotIn("service.installSource", argv)


if __name__ == "__main__":
    unittest.main()
