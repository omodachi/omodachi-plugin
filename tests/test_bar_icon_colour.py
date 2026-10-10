"""PLUGIN-COLOR-1: the bar icon is not red just because a phone is linked.

`tests/OmodachiModel.test.mjs` proves the decision (`iconLook`: only the
"remote" state wears the active colour; linked is the plain foreground). This
proves the wiring: the bar widget takes dimmed / active / the square from
`Model.iconLook` and from nowhere else, and no other place in the plugin's
QML hands a non-failure state the shell's urgent / active colour.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
QML = sorted(ROOT.glob("*.qml")) + sorted((ROOT / "components").rglob("*.qml"))


def code(path: Path) -> str:
    """The file without its `//` comments."""
    return re.sub(r"//.*", "", path.read_text())


class BarIconColourTests(unittest.TestCase):
    def setUp(self):
        self.widget = code(ROOT / "BarWidget.qml")

    def test_the_widget_reads_the_look_from_the_model(self):
        self.assertIn("Model.iconLook(iconState, takeoverLocked)", self.widget)
        self.assertRegex(self.widget, r"\n\s*dimmed: widget\.iconLook\.dimmed\n")
        self.assertRegex(self.widget, r"\n\s*active: widget\.iconLook\.active\n")
        self.assertIn("visible: widget.iconLook.indicator", self.widget)

    def test_linked_is_never_named_next_to_the_active_colour(self):
        # The old binding was `active: iconState === "linked" || ...`.
        for line in self.widget.splitlines():
            if re.match(r"\s*(active|useActiveColor)\s*:", line):
                self.assertNotIn('"linked"', line, line)

    def test_the_urgent_colour_is_only_for_a_failure(self):
        # Color.urgent / Color.error / bar.active are allowed only where the
        # line itself says why: an install that failed, or a Tailscale
        # warning marked severe. Anything new has to be argued in here.
        allowed = ("installFailed", "severe")
        for path in QML:
            for line in code(path).splitlines():
                if re.search(r"Color\.(urgent|error)\b|bar\.active\b|\burgent\b", line):
                    with self.subTest(path=path.name, line=line.strip()):
                        self.assertTrue(any(word in line for word in allowed), line)


if __name__ == "__main__":
    unittest.main()
