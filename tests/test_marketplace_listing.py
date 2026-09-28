"""LISTING-1: what the Omarchy plugin marketplace reads from this repository.

The marketplace's scheduled refresh reads `manifest.json` and the root
`preview.png` from the default branch and builds the listing page from them.
A field over its limit makes the whole manifest invalid there, and the refresh
then fails, so the page says compatibility is unconfirmed. The page escapes
every character: a link or markdown in the description shows up as literal
brackets, never as a link.

The limits below are the marketplace's own (name 120, description 500,
author 120, version 64); the description is held to 480 so a small edit
cannot tip it over. The preview is scaled to a 1280x800 detail image and a
720x450 card, both 16:10.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]

LIMITS = {"name": 120, "description": 500, "author": 120, "version": 64}
DESCRIPTION_CAP = 480
PREVIEW_MAX_BYTES = 5 * 1024 * 1024
PREVIEW_MAX_PIXELS = 40_000_000
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def manifest() -> dict:
    return json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        head = handle.read(24)
    if head[:8] != PNG_SIGNATURE or head[12:16] != b"IHDR":
        raise AssertionError(f"{path.name} is not a PNG")
    return struct.unpack(">II", head[16:24])


class ManifestFieldLimitTests(unittest.TestCase):
    def test_every_projected_field_is_a_non_empty_string_within_its_limit(self):
        data = manifest()
        for field, limit in LIMITS.items():
            with self.subTest(field=field):
                value = data[field]
                self.assertIsInstance(value, str)
                self.assertEqual(value, value.strip())
                self.assertTrue(value)
                self.assertLessEqual(len(value), limit)

    def test_the_description_keeps_a_margin_under_the_limit(self):
        self.assertLessEqual(len(manifest()["description"]), DESCRIPTION_CAP)

    def test_the_version_is_semver(self):
        self.assertRegex(manifest()["version"], r"^\d+\.\d+\.\d+$")


class DescriptionIsPlainTextTests(unittest.TestCase):
    """The page escapes it, so anything but plain sentences shows as noise."""

    def test_no_markup_and_no_link_syntax(self):
        text = manifest()["description"]
        for token in ("<", ">", "](", "[", "]", "**", "__", "`", "://", "\n", "\r", "\t"):
            with self.subTest(token=token):
                self.assertNotIn(token, text)
        self.assertIsNone(re.search(r"^\s*(#|[-*+] |\d+\. )", text), "a markdown block marker")

    def test_it_claims_no_store_and_no_push(self):
        # The App is in review, not on the App Store, and there is no APNs:
        # desktop notifications are listed in the App, never pushed.
        text = manifest()["description"].lower()
        self.assertNotIn("app store", text)
        self.assertNotIn("push", text)


class PreviewTests(unittest.TestCase):
    PREVIEW = ROOT / "preview.png"

    def test_the_preview_is_a_png_at_the_root(self):
        self.assertTrue(self.PREVIEW.is_file())
        self.assertFalse(self.PREVIEW.is_symlink())
        png_size(self.PREVIEW)

    def test_the_preview_is_small_enough(self):
        self.assertLessEqual(self.PREVIEW.stat().st_size, PREVIEW_MAX_BYTES)
        width, height = png_size(self.PREVIEW)
        self.assertLessEqual(width * height, PREVIEW_MAX_PIXELS)

    def test_the_preview_is_sixteen_by_ten(self):
        width, height = png_size(self.PREVIEW)
        self.assertEqual(width * 10, height * 16, f"{width}x{height} is not 16:10")
        self.assertGreaterEqual(width, 1280, "the detail image is 1280 wide; a smaller preview is upscaled")

    def test_no_other_preview_competes_with_it(self):
        # The marketplace reads one root `preview.*`; a second one would be a
        # coin toss.
        others = sorted(p.name for p in ROOT.glob("preview.*") if p.name != "preview.png")
        self.assertEqual(others, [])


if __name__ == "__main__":
    unittest.main()
