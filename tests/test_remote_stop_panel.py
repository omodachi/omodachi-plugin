"""REMOTE-STOP-1: Overview's End Remote session, read off the source.

`tests/OmodachiModel.test.mjs` proves the decisions (when the button is offered,
the exact argv, what the answer means). This proves the wiring: the page acts
only on the second click, the service runs nothing but the model's fixed argv
for the session the page showed, no credential is involved anywhere, and the
plugin touches no Hyprland bindings file - the spec allows a keybinding only
where an installer already manages a bindings file of ours, and none does.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD_SOURCES = (sorted(ROOT.glob("*.qml")) + sorted((ROOT / "components").rglob("*.qml"))
                   + sorted(ROOT.glob("*.js")) + sorted((ROOT / "tools").rglob("*.py")))


def code(path: Path) -> str:
    """The file without its `//` and `#` comments."""
    text = path.read_text()
    if path.suffix == ".py":
        return re.sub(r"#.*", "", text)
    return re.sub(r"//.*", "", text)


class EndRemoteSessionTests(unittest.TestCase):
    def setUp(self):
        self.page = code(ROOT / "components/OverviewPage.qml")
        self.service = code(ROOT / "Service.qml")

    def test_the_page_offers_it_only_for_a_live_session_and_acts_on_the_second_click(self):
        self.assertIn("Model.liveSessionId(snapshot)", self.page)
        self.assertIn('visible: root.sessionId !== ""', self.page)
        calls = [match.start() for match in re.finditer(r"root\.service\.endRemote\(root\.sessionId\)", self.page)]
        self.assertEqual(len(calls), 1, "one call site")
        armed = self.page.rfind("if (root.endArmed)", 0, calls[0])
        self.assertGreaterEqual(armed, 0, "the call sits behind the armed check")
        self.assertIn("root.endArmed = true", self.page)
        self.assertIn('"End Remote session"', self.page)
        self.assertIn("onSessionIdChanged: endArmed = false", self.page,
                      "a Confirm left armed must not carry over to the next session")

    def test_the_service_runs_only_the_models_argv(self):
        body = self.service[self.service.index("function endRemote("):]
        body = body[:body.index("\n    }\n") + 6]
        self.assertIn("Model.remoteStopCommand(service.snapshot, sessionId)", body)
        self.assertIn('service.startAdmin("remote_stop", sessionId, command, null)', body)
        self.assertNotRegex(body, r'\[\s*"omodachi-host"', "no argv assembled here")
        self.assertIn('operation === "remote_stop"', self.service)
        # The holding device is named from the Devices list the panel holds.
        self.assertIn("Model.remoteStopOutcome(raw, target, service.devices)", self.service)

    def test_no_credential_is_involved(self):
        for path in PAYLOAD_SOURCES:
            if path.name == "install_host.py":
                continue  # the bootstrap installs core; it never runs `remote stop`
            with self.subTest(path=path.name):
                text = code(path)
                self.assertNotIn("OMODACHI_TOKEN", text)
                self.assertNotIn("plugin.token", text)

    def test_the_plugin_touches_no_hyprland_bindings_file(self):
        forbidden = re.compile(r"bindings\.(conf|lua)|hypr/hyprland\.(conf|lua)|hl\.bind\b|\bbindd?\s*=")
        for path in PAYLOAD_SOURCES:
            with self.subTest(path=path.name):
                self.assertIsNone(forbidden.search(code(path)), path.name)


if __name__ == "__main__":
    unittest.main()
