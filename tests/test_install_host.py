"""RELEASE-3b: the Install bootstrap runs a pinned commit, never a bare tag.

The marketplace baseline (`remote-git-execution-unpinned`) wants a full commit
and a detached checkout for anything fetched and then executed. These tests
drive `tools/install_host.py`'s fetch against real local git repositories
(`file://`, so `--depth 1` behaves as it does over https) with every path the
script writes moved into a temporary directory.

RELEASE-5: nothing from ~/.local/share/omodachi/src runs unless it is exactly
the pinned commit (`verify_checkout`), and a tree there that is not a git
checkout is refused and left alone. `ExecutionBindingTests` drive `main()`
itself, with an upstream whose `scripts/install_host.py` only records that it
ran.
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


# The fake core installer: records its arguments, so a test can tell whether
# (and how) the bootstrap ran it.
FAKE_INSTALLER = """import os, sys
with open(os.environ["OMODACHI_TEST_MARKER"], "a") as marker:
    marker.write(" ".join(sys.argv[1:]) + "\\n")
"""


class UpstreamCase(unittest.TestCase):
    """A real local upstream, and every path the bootstrap writes moved under a temp dir."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        # An upstream with two commits: v0.1.0 on the first, main on the second.
        self.upstream = base / "omodachi-core"
        self.upstream.mkdir()
        git("init", "--quiet", cwd=self.upstream)
        (self.upstream / "pyproject.toml").write_text("[project]\nname='x'\n")
        (self.upstream / "scripts").mkdir()
        (self.upstream / "scripts/install_host.py").write_text(FAKE_INSTALLER)
        (self.upstream / ".gitignore").write_text("build/\n")
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


class PinnedCommitTests(UpstreamCase):
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


class ExecutionBindingTests(UpstreamCase):
    """RELEASE-5: `main()` runs a checkout only after `verify_checkout` says it is the pin."""

    def setUp(self):
        super().setUp()
        self.marker = Path(self.temporary.name) / "ran"
        os.environ["OMODACHI_TEST_MARKER"] = str(self.marker)
        patcher = mock.patch.object(self.module.sys, "platform", "linux")
        patcher.start()
        self.addCleanup(patcher.stop)

    def main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.module.main(list(argv))
        return code, out.getvalue()

    def ran(self):
        return self.marker.read_text().splitlines() if self.marker.exists() else []

    def snapshot(self, directory):
        return sorted((str(path.relative_to(directory)), path.read_bytes() if path.is_file() else None)
                      for path in directory.rglob("*"))

    def install_first(self):
        self.write_pin(commit=self.first)
        code, out = self.main()
        self.assertEqual(code, 0, out)
        self.marker.unlink()

    def test_a_clean_checkout_of_the_pin_is_installed(self):
        self.write_pin(commit=self.first)
        code, out = self.main()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.ran(), ["--local"])
        self.assertEqual(self.head(), self.first)

    def test_an_existing_tree_that_is_not_a_git_checkout_is_refused_and_kept(self):
        # The old rsynced developer tree: a perfectly plausible core, even a
        # runnable installer - and exactly what the review said must not run.
        self.source_dir.mkdir(parents=True)
        (self.source_dir / "pyproject.toml").write_text("[project]\nname='x'\n")
        (self.source_dir / "scripts").mkdir()
        (self.source_dir / "scripts/install_host.py").write_text(FAKE_INSTALLER)
        before = self.snapshot(self.source_dir)
        self.write_pin(commit=self.first)
        for argv in ((), ("--remove",), ("--remove", "--purge")):
            with self.subTest(argv=argv):
                code, out = self.main(*argv)
                self.assertEqual(code, 1, out)
                self.assertEqual(self.ran(), [])
                self.assertEqual(self.snapshot(self.source_dir), before)
        code, out = self.main()
        self.assertIn("is not the checkout this installer makes", out)
        self.assertIn("OMODACHI_CORE_SOURCE", out)
        self.assertNotIn("+ git", out)
        self.assertNotIn("existing_sources", self.module.fetch_source(self.module.source_pin())[1])

    def test_a_non_directory_or_a_link_in_the_way_is_refused_and_kept(self):
        self.source_dir.parent.mkdir(parents=True)
        self.source_dir.write_text("mine\n")
        self.write_pin(commit=self.first)
        code, out = self.main()
        self.assertEqual(code, 1, out)
        self.assertEqual(self.source_dir.read_text(), "mine\n")
        self.source_dir.unlink()
        self.source_dir.symlink_to(self.upstream)
        code, out = self.main()
        self.assertEqual(code, 1, out)
        self.assertTrue(self.source_dir.is_symlink())
        self.assertEqual(self.ran(), [])

    def test_an_untracked_file_in_the_checkout_is_refused(self):
        self.install_first()
        (self.source_dir / "scripts/json.py").write_text("raise SystemExit('planted')\n")
        code, out = self.main()
        self.assertEqual(code, 1, out)
        self.assertEqual(self.ran(), [])
        self.assertIn("scripts/json.py", out)
        self.assertTrue((self.source_dir / "scripts/json.py").exists(), "refused, not cleaned")

    def test_an_untracked_file_hidden_by_the_checkouts_own_excludes_is_still_refused(self):
        self.install_first()
        (self.source_dir / ".git/info").mkdir(exist_ok=True)
        (self.source_dir / ".git/info/exclude").write_text("json.py\n")
        (self.source_dir / "scripts/json.py").write_text("raise SystemExit('planted')\n")
        code, out = self.main()
        self.assertEqual(code, 1, out)
        self.assertEqual(self.ran(), [])
        self.assertIn("scripts/json.py", out)

    def test_files_the_pinned_gitignore_ignores_do_not_block_a_reinstall(self):
        # core's own installer leaves build/ behind; that is not tampering.
        self.install_first()
        (self.source_dir / "build").mkdir()
        (self.source_dir / "build/cache").write_text("x\n")
        code, out = self.main()
        self.assertEqual(code, 0, out)

    def test_a_modified_checkout_fails_the_check(self):
        self.install_first()
        (self.source_dir / "scripts/install_host.py").write_text("print('replaced')\n")
        with contextlib.redirect_stdout(io.StringIO()):
            ok, detail = self.module.verify_checkout(self.first)
        self.assertFalse(ok)
        self.assertIn("scripts/install_host.py", detail)

    def test_a_checkout_at_another_commit_is_not_run(self):
        # Even if the fetch said yes, the check right before exec says no.
        self.install_first()
        git("fetch", "--quiet", "--depth", "1", self.url, self.second, cwd=self.source_dir)
        git("checkout", "--quiet", "--detach", "FETCH_HEAD", cwd=self.source_dir)
        with mock.patch.object(self.module, "fetch_source", return_value=(True, "")):
            code, out = self.main()
        self.assertEqual(code, 1, out)
        self.assertEqual(self.ran(), [])
        self.assertIn(f"is at {self.second}, but the pin is {self.first}", out)

    def test_remove_runs_the_uninstaller_of_a_matching_checkout(self):
        self.install_first()
        code, out = self.main("--remove")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.ran(), ["--local --remove"])

    def test_remove_refuses_a_checkout_that_is_not_the_pin(self):
        self.install_first()
        self.write_pin(commit=self.second, ref="main")
        for argv in (("--remove",), ("--remove", "--purge")):
            with self.subTest(argv=argv):
                code, out = self.main(*argv)
                self.assertEqual(code, 1, out)
                self.assertEqual(self.ran(), [])
                self.assertIn("uninstaller was not run", out)
                self.assertTrue((self.source_dir / "scripts/install_host.py").is_file())
        (self.source_dir / "scripts/extra.py").write_text("x\n")
        self.write_pin(commit=self.first)
        code, out = self.main("--remove")
        self.assertEqual(code, 1, out)
        self.assertEqual(self.ran(), [])

    def test_a_pre_existing_checkouts_hooks_never_run(self):
        self.install_first()
        hook = self.source_dir / ".git/hooks/post-checkout"
        hook.parent.mkdir(exist_ok=True)
        hook.write_text(f"#!/bin/sh\necho hook >> {self.marker}\n")
        hook.chmod(0o755)
        code, out = self.main()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.ran(), ["--local"])

    def test_a_failed_fetch_keeps_an_empty_directory_the_user_made(self):
        self.source_dir.mkdir(parents=True)
        self.write_pin(commit="f" * 40, ref="main")
        code, out = self.main()
        self.assertEqual(code, 1, out)
        self.assertTrue(self.source_dir.is_dir())
        self.assertEqual(list(self.source_dir.iterdir()), [])

    def test_a_developer_source_goes_through_the_same_fetch_and_check(self):
        self.write_pin(commit=self.first)
        os.environ["OMODACHI_CORE_SOURCE"] = self.url
        os.environ["OMODACHI_CORE_COMMIT"] = self.second
        code, out = self.main()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.head(), self.second)
        self.assertIn(f"fetch --depth 1 {self.url} {self.second}", out)
        self.assertEqual(self.ran(), ["--local"])


if __name__ == "__main__":
    unittest.main()
