"""REMOTE-SAFE-1: what the corner insets are allowed to touch, read off the source.

`tests/OmodachiModel.test.mjs` proves the decision (`barInsetsFor` answers
null for every screen but the session's own OMODACHI output, and for anything
but a live session, Extend or Take over). This proves the reach: the only things the bar
widget ever changes are the two end sections' anchor margins, through
`Binding`s that give the shell's own binding back, gated on that decision -
and the corner path writes no shell configuration and calls no shell setter.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
QML = sorted(ROOT.glob("*.qml")) + sorted((ROOT / "components").rglob("*.qml"))
SCRIPTS = QML + sorted(ROOT.glob("*.js"))

# shell.qml's IpcHandler: every one of these persists shell.json
# (`mutateShellConfig` -> `persistShellConfig`), research §2.1.
SHELL_SETTERS = ("setBarWidget", "moveBarWidget", "putBarWidget", "removeBarWidget", "enablePlugin",
                 "disablePlugin", "mutateShellConfig", "persistShellConfig", "reloadConfig", "setBarPosition")
ALLOWED_TARGETS = {"anchors.topMargin", "anchors.bottomMargin", "anchors.leftMargin", "anchors.rightMargin"}


def bindings(text: str) -> list[str]:
    """Every `Binding { ... }` block, braces balanced."""
    blocks, start = [], 0
    while (index := text.find("Binding {", start)) >= 0:
        depth, cursor = 0, index
        while cursor < len(text):
            if text[cursor] == "{":
                depth += 1
            elif text[cursor] == "}":
                depth -= 1
                if depth == 0:
                    break
            cursor += 1
        blocks.append(text[index:cursor + 1])
        start = cursor + 1
    return blocks


class BarInsetsScopeTests(unittest.TestCase):
    def setUp(self):
        self.widget = (ROOT / "BarWidget.qml").read_text()

    def test_the_corner_path_never_names_shell_json(self):
        # The panel's own "Click while open" preference is stored in this
        # widget's shell.json entry through the official bar settings API
        # (SettingsPage.qml says so to the user); that predates this and is not
        # the corner path. The corner path is the widget and the model.
        for path in (ROOT / "BarWidget.qml", ROOT / "OmodachiModel.js", ROOT / "Service.qml"):
            with self.subTest(path=path.name):
                self.assertNotIn("shell.json", re.sub(r"//.*", "", path.read_text()),
                                 "shell.json may be named in a comment, never in code")

    def test_nothing_in_the_plugin_calls_a_shell_ipc_setter(self):
        for path in SCRIPTS:
            text = path.read_text()
            with self.subTest(path=path.name):
                for name in SHELL_SETTERS:
                    self.assertIsNone(re.search(r"\b%s\s*\(" % name, text), name)
                    self.assertNotIn('"%s"' % name, text)

    def test_the_bar_window_itself_is_never_assigned(self):
        # Research §2.2 suggested the window's `margins`; the popups break on a
        # shortened window (BarWidget.qml says why). Nothing may assign the
        # window's margins, anchors or exclusion, imperatively or by Binding.
        code = re.sub(r"//.*", "", self.widget)
        self.assertIsNone(re.search(r"\.margins\.\w+\s*=[^=]", code))
        self.assertIsNone(re.search(r"exclusionMode\s*=[^=]", code))
        self.assertIsNone(re.search(r"\.anchors\.\w+\s*=[^=]", code),
                          "an imperative assignment would break the shell's binding for good")
        self.assertNotIn('"margins', code)
        self.assertNotIn("exclusionMode", code)

    def test_every_binding_restores_the_shell_and_waits_for_this_screens_insets(self):
        blocks = bindings(self.widget)
        self.assertEqual(len(blocks), 4)
        targets = set()
        for block in blocks:
            with self.subTest(block=block.splitlines()[2]):
                self.assertIn("restoreMode: Binding.RestoreBindingOrValue", block)
                when = re.search(r"when:\s*(.+)", block).group(1)
                self.assertTrue(when.startswith("widget.applying && "), when)
                target = re.search(r"target:\s*(.+)", block).group(1).strip()
                self.assertIn(target, ("widget.leadingSection", "widget.trailingSection"))
                self.assertIn("!!" + target, when)
                name = re.search(r'property:\s*"([^"]+)"', block).group(1)
                targets.add(name)
                self.assertIn("Model.sectionMargin(widget.shellEndMargin", block)
        self.assertEqual(targets, ALLOWED_TARGETS)

    def test_the_bindings_are_turned_off_before_the_widget_goes(self):
        # A Binding destroyed while active leaves its value behind; one whose
        # `when` goes false gives the shell's binding back.
        self.assertIn("readonly property bool applying: !leaving && !!cornerInsets", self.widget)
        destruction = self.widget[self.widget.index("Component.onDestruction: {"):]
        self.assertLess(destruction.index("widget.leaving = true"), destruction.index("}"))

    def test_the_decision_is_the_models_and_keyed_on_this_widgets_own_screen(self):
        self.assertRegex(self.widget, r"cornerInsets: Model\.barInsetsFor\(scopedService \? scopedService\.snapshot : null,\s*"
                                      r"screenName, barPosition\)")
        self.assertIn("readonly property var hostWindow: widget.QsWindow.window", self.widget)
        self.assertRegex(self.widget, r"screenName: hostWindow && hostWindow\.screen \? String\(hostWindow\.screen\.name")

    def test_the_geometry_report_is_a_getter(self):
        service = (ROOT / "Service.qml").read_text()
        body = service[service.index("function barGeometry()"):]
        body = body[:body.index("\n        }\n") + 10]
        self.assertIn("JSON.stringify(rows)", body)
        self.assertNotRegex(body, r"\bservice\.\w+\s*=[^=]")


if __name__ == "__main__":
    unittest.main()
