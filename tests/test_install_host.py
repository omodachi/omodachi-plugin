"""RELEASE-3b: the Install bootstrap runs a pinned commit, never a bare tag.

The marketplace baseline (`remote-git-execution-unpinned`) wants a full commit
and a detached checkout for anything fetched and then executed. These tests
drive `tools/install_host.py`'s fetch against real local git repositories
(`file://`, so `--depth 1` behaves as it does over https) with every path the
script writes moved into a temporary directory.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load_bootstrap():
    spec = importlib.util.spec_from_file_location("plugin_install_host", ROOT / "tools/install_host.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(*arguments, cwd):
    environment = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
                       GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    return subprocess.run(["git", *arguments], cwd=cwd, env=environment, check=True,
                          capture_output=True, text=True).stdout.strip()


class PinnedCommitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        # An upstream with two commits: v0.1.0 on the first, main on the second.
        self.upstream = base / "omodachi-core"
        self.upstream.mkdir()
        git("init", "--quiet", cwd=self.upstream)
        (self.upstream / "pyproject.toml").write_text("[project]\nname='x'\n")
        git("add", ".", cwd=self.upstream)
        git("commit", "--quiet", "-m", "first", cwd=self.upstream)
        self.first = git("rev-parse", "HEAD", cwd=self.upstream)
        git("tag", "-a", "v0.1.0", "-m", "v0.1.0", cwd=self.upstream)
        (self.upstream / "second").write_text("2\n")
        git("add", ".", cwd=self.upstream)
        git("commit", "--quiet", "-m", "second", cwd=self.upstream)
        self.second = git("rev-parse", "HEAD", cwd=self.upstream)
        self.url = "file://" + str(self.upstream)

        self.module = load_bootstrap()
        self.source_dir = base / "home/.local/share/omodachi/src"
        self.pin_file = base / "omodachi.json"
        for name, value in (("SOURCE_DIR", self.source_dir), ("SOURCE_PIN", self.pin_file),
                            ("STATUS_PATH", base / "home/.cache/omodachi/install-status.json")):
            patcher = mock.patch.object(self.module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("OMODACHI_CORE_SOURCE", "OMODACHI_CORE_REF", "OMODACHI_CORE_COMMIT"):
            os.environ.pop(name, None)

    def write_pin(self, **fields):
        body = {"owner": "omodachi", "repository": "omodachi-core", "ref": "v0.1.0", "url": self.url}
        body.update(fields)
        self.pin_file.write_text(json.dumps({"core_source": body}))

    def fetch(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ok, detail = self.module.fetch_source(self.module.source_pin())
        return ok, detail, out.getvalue()

    def head(self):
        return git("rev-parse", "HEAD", cwd=self.source_dir)

    def assert_detached(self):
        result = subprocess.run(["git", "-C", str(self.source_dir), "symbolic-ref", "-q", "HEAD"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0, "HEAD must be detached")

    def test_the_pinned_commit_is_fetched_by_sha_and_checked_out_detached(self):
        self.write_pin(commit=self.first)
        ok, detail, out = self.fetch()
        self.assertTrue(ok, detail)
        self.assertEqual(self.head(), self.first)
        self.assert_detached()
        self.assertIn(f"fetch --depth 1 {self.url} {self.first}", out)
        self.assertNotIn("clone", out)
        self.assertNotIn("--branch", out)

    def test_an_existing_checkout_moves_to_the_pinned_commit(self):
        self.write_pin(commit=self.first)
        self.assertTrue(self.fetch()[0])
        self.write_pin(commit=self.second, ref="main")
        ok, detail, _ = self.fetch()
        self.assertTrue(ok, detail)
        self.assertEqual(self.head(), self.second)
        self.assert_detached()

    def test_a_server_that_refuses_a_sha_falls_back_to_the_tag_and_checks_it(self):
        self.write_pin(commit=self.first)
        real_run = self.module.run

        def refuse_sha(argv, **kwargs):
            if argv[-1] == self.first and "fetch" in argv:
                return subprocess.CompletedProcess(argv, 128, "", "error: Server does not allow request")
            return real_run(argv, **kwargs)

        with mock.patch.object(self.module, "run", refuse_sha):
            ok, detail, out = self.fetch()
        self.assertTrue(ok, detail)
        self.assertEqual(self.head(), self.first)
        self.assert_detached()
        self.assertIn(f"fetch --depth 1 --tags {self.url} v0.1.0", out)

    def test_a_tag_that_does_not_name_the_pinned_commit_is_refused(self):
        # The tag says `first`; the pin says `second`. Nothing may be checked out.
        self.write_pin(commit=self.second, ref="v0.1.0")
        real_run = self.module.run

        def refuse_sha(argv, **kwargs):
            if argv[-1] == self.second and "fetch" in argv:
                return subprocess.CompletedProcess(argv, 128, "", "error: Server does not allow request")
            return real_run(argv, **kwargs)

        with mock.patch.object(self.module, "run", refuse_sha):
            ok, detail, _ = self.fetch()
        self.assertFalse(ok)
        self.assertIn(self.first, detail)
        self.assertIn(self.second, detail)
        self.assertFalse(self.source_dir.exists(), "a refused fresh checkout is removed")

    def test_a_refused_update_leaves_the_existing_checkout_where_it_was(self):
        self.write_pin(commit=self.first)
        self.assertTrue(self.fetch()[0])
        self.write_pin(commit="f" * 40, ref="main")
        ok, detail, _ = self.fetch()
        self.assertFalse(ok)
        self.assertEqual(self.head(), self.first)

    def test_the_environment_overrides_the_pinned_commit(self):
        self.write_pin(commit=self.first)
        os.environ["OMODACHI_CORE_COMMIT"] = self.second
        os.environ["OMODACHI_CORE_REF"] = "main"
        pin = self.module.source_pin()
        self.assertEqual((pin["commit"], pin["ref"]), (self.second, "main"))
        ok, detail, _ = self.fetch()
        self.assertTrue(ok, detail)
        self.assertEqual(self.head(), self.second)

    def test_no_full_commit_means_no_install(self):
        for commit in (None, "v0.1.0", self.first[:12]):
            with self.subTest(commit=commit):
                self.write_pin(**({} if commit is None else {"commit": commit}))
                ok, detail, out = self.fetch()
                self.assertFalse(ok)
                self.assertIn("40-character commit", detail)
                self.assertNotIn("+ git", out)

    def test_the_shipped_pin_carries_a_full_commit_beside_the_tag(self):
        pin = json.loads((ROOT / "omodachi.json").read_text())["core_source"]
        self.assertEqual(pin["ref"], "v0.1.0")
        self.assertTrue(self.module.is_full_commit(pin.get("commit")), pin.get("commit"))


if __name__ == "__main__":
    unittest.main()
