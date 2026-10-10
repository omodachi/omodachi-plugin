"""TAIL-3b: the pair block's wiring, read off the source.

`tests/OmodachiModel.test.mjs` proves the decisions (state, short name, when
each page shows the block, the strings). This proves the pages ask the model,
the block draws no string of its own, and Copy runs only wl-copy with the name.
When `qmlformat` is on PATH every payload QML file is also parsed.
"""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


def code(path: Path) -> str:
    return re.sub(r"//.*", "", path.read_text())


class PairBlockTests(unittest.TestCase):
    def test_the_block_draws_only_the_models_strings(self):
        block = code(ROOT / "components/PairPhoneBlock.qml")
        self.assertIn("Model.pairText(tailnet)", block)
        self.assertNotRegex(block, r'text:\s*"', "every string comes from OmodachiModel.js")
        self.assertIn("root.service.copyTailnetName()", block)
        self.assertIn("Text.WrapAnywhere", block)

    def test_the_pages_ask_the_model_when_to_show_it(self):
        overview = code(ROOT / "components/OverviewPage.qml")
        devices = code(ROOT / "components/DevicesPage.qml")
        self.assertIn("visible: Model.showPairBlock(root.tailnet)", overview)
        self.assertIn("Model.showDevicesPairBlock(", devices)
        for page in (overview, devices):
            self.assertEqual(page.count("PairPhoneBlock {"), 1)
        # Devices: on top, before the pairing requests.
        self.assertLess(devices.index("PairPhoneBlock {"), devices.index('"PAIRING REQUEST"'))
        # The signed-out / absent paragraph comes from the model too.
        self.assertIn("root.pairText.note", overview)

    def test_copy_runs_only_wl_copy_with_the_name(self):
        service = code(ROOT / "Service.qml")
        body = service[service.index("function copyTailnetName("):]
        body = body[:body.index("\n    }\n") + 6]
        self.assertIn("Model.showPairBlock(service.tailnet)", body)
        self.assertIn('copyProcess.command = ["wl-copy", "--", service.tailnet.dns_name]', body)
        self.assertIn("tailnetNameCopiedTimer.restart()", body)
        self.assertIn("interval: 2000; onTriggered: service.tailnetNameCopied = false", service)

    @unittest.skipUnless(shutil.which("qmlformat"), "qmlformat is not on PATH")
    def test_every_payload_qml_file_parses(self):
        files = sorted(ROOT.glob("*.qml")) + sorted((ROOT / "components").rglob("*.qml"))
        for path in files:
            with self.subTest(path=path.name):
                finished = subprocess.run(["qmlformat", str(path)], capture_output=True, text=True)
                self.assertEqual(finished.returncode, 0, finished.stderr[-600:])


if __name__ == "__main__":
    unittest.main()
