"""REL2-VM-1: a purge after core is gone (purge_only) leaves nothing of ours.

On the clean VM gate a `--remove --purge` that ran after core's own
uninstaller had gone printed two of core's paths as the user's: the daemon's
~/.config/omodachi/seen.json and the empty agent-workspace Install makes. The
purge rule now names seen.json (and its temp file) as core's does, and an
agent-workspace goes when it is empty and stays, listed, otherwise.
"""
from __future__ import annotations

import unittest

from tests import test_install_host as base


class PurgeOnlyLeavesNothingOfOursTests(base.OwnershipTests):
    def state(self):
        home, share = self.module.HOME, self.source_dir.parent
        seen = home / ".config/omodachi/seen.json"
        temporary = home / ".config/omodachi/.seen-ab12cd34"
        for path in (seen, temporary, home / ".config/omodachi/device.secret"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x\n")
        (share / "agent-workspace").mkdir(parents=True, exist_ok=True)
        return home, share, seen, temporary

    def test_a_purge_takes_seen_json_and_an_empty_agent_workspace(self):
        home, share, seen, temporary = self.state()
        code, out = self.main("--remove", "--purge")      # no installer left: purge_only
        self.assertEqual(code, 0, out)
        self.assertFalse(seen.exists() or temporary.exists())
        self.assertFalse((share / "agent-workspace").exists())
        self.assertNotIn("kept, because they are yours", out)
        self.assertFalse((home / ".config/omodachi").exists())

    def test_an_agent_workspace_with_a_file_in_it_stays(self):
        home, share, seen, _ = self.state()
        (share / "agent-workspace/plan.md").write_text("mine\n")
        code, out = self.main("--remove", "--purge")
        self.assertEqual(code, 0, out)
        self.assertEqual((share / "agent-workspace/plan.md").read_text(), "mine\n")
        self.assertIn(str(share / "agent-workspace"), out)
        self.assertFalse(seen.exists())


for _name in dir(base.OwnershipTests):
    if _name.startswith("test_") and _name not in vars(PurgeOnlyLeavesNothingOfOursTests):
        setattr(PurgeOnlyLeavesNothingOfOursTests, _name, None)


if __name__ == "__main__":
    unittest.main()
