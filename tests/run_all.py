#!/usr/bin/env python3
"""Every check that runs without a host, in one command.

    python3 tests/run_all.py

`tests/runtime_watch_probe.py` and `omarchy plugin validate .` need the
Omarchy host and are deliberately not in here; README says how to run those.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = [
    ["node", "tests/OmodachiModel.test.mjs"],
    ["node", "tests/MediaPairingModel.test.mjs"],
    ["node", "tests/PreferencesModel.test.mjs"],
    ["node", "tests/contracts.test.mjs"],
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", ".", "-p", "test_*.py"],
]


def main() -> int:
    failed = []
    for command in SUITES:
        finished = subprocess.run(command, cwd=ROOT)
        if finished.returncode != 0:
            failed.append(" ".join(command))
    if failed:
        print("\nFAILED: " + ", ".join(failed))
        return 1
    print("\nall suites passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
