"""RELEASE-4: every tracked text file is plain text, byte for byte.

The marketplace's static scan reads each file of a submission and treats any
file with a 0x00 byte in it as a binary; a binary that is not mode 100755 is
not something it can scan, and the whole submission fails closed. Line 36 of
MediaPairingModel.js once held its character-class regex as the raw bytes
0x00, 0x1F and 0x7F instead of the escapes that spell them, which is exactly
that. So: no byte below 0x20 other than a newline or a tab, and no 0x7F, in
any tracked file that is not an image - and the regex that was rewritten still
means what it meant.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
# The only binaries this repository is meant to carry.
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"}
ALLOWED_CONTROL = {0x09, 0x0A}


def tracked_files() -> list[Path]:
    try:
        listed = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True,
                                capture_output=True).stdout.decode("utf-8").split("\0")
        paths = [ROOT / name for name in listed if name]
    except (OSError, subprocess.CalledProcessError):
        # An export without .git (a tarball of the tree) is checked the same way.
        paths = [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.relative_to(ROOT).parts
                 and "__pycache__" not in p.parts]
    return [p for p in paths if p.is_file() and not p.is_symlink()]


class RepositoryHygieneTests(unittest.TestCase):
    def test_no_control_bytes_in_text_files(self) -> None:
        offenders = []
        checked = 0
        for path in tracked_files():
            if path.suffix.lower() in IMAGE_SUFFIXES:
                continue
            checked += 1
            data = path.read_bytes()
            for offset, byte in enumerate(data):
                if (byte < 0x20 and byte not in ALLOWED_CONTROL) or byte == 0x7F:
                    line = data.count(b"\n", 0, offset) + 1
                    offenders.append(f"{path.relative_to(ROOT)}:{line}: byte 0x{byte:02X}")
        self.assertGreater(checked, 0)
        self.assertEqual(offenders, [], "control bytes in tracked text files:\n" + "\n".join(offenders))

    def test_printable_rejects_control_characters(self) -> None:
        # The behaviour of the rewritten regex, through the shipped function.
        cases = {
            "fixture-ipad": True,
            "Leo's iPad (2)": True,
            "a\u0000b": False,
            "a\u001fb": False,
            "a\u007fb": False,
            "tab\there": False,
            "line\nbreak": False,
            "": False,
        }
        script = (
            "const vm=require('node:vm');const fs=require('node:fs');"
            "const src=fs.readFileSync(process.argv[1],'utf8').replace('.pragma library','');"
            "const ctx={JSON,Number,Object,Array};vm.createContext(ctx);vm.runInContext(src,ctx);"
            "const cases=JSON.parse(process.argv[2]);"
            "process.stdout.write(JSON.stringify(Object.fromEntries(Object.keys(cases).map(k=>[k,ctx.printable(k,128)]))));"
        )
        finished = subprocess.run(["node", "-e", script, str(ROOT / "MediaPairingModel.js"), json.dumps(cases)],
                                  check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(finished.stdout), cases)
        # The escape spelling is what keeps the file text; the raw bytes are what broke the scan.
        source = (ROOT / "MediaPairingModel.js").read_text("utf-8")
        self.assertTrue(r"/[\x00-\x1f\x7f]/" in source, "printable() no longer spells its regex with escapes")


if __name__ == "__main__":
    unittest.main()
