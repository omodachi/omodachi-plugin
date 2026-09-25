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

RELEASE-7: no bytecode, ignored file or git setting from outside the verified
tree runs. `NothingOutsideTheTreeRunsTests` plant a valid `__pycache__/*.pyc`
for one of the upstream's modules (and prove, on the same interpreter, that
the plant does run when nothing stops it), a sourceless `.pyc`, ignored and
untracked files and a program-running .git/config, and check that none of it
runs through Install or `--remove`, that the check fails closed on a file it
cannot delete, and exactly how core's installer is started.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
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
# (and how) the bootstrap ran it. With $OMODACHI_TEST_PROBE set it also does
# what core's installer does - put its own src/ on sys.path and import a
# module from it - and writes down the interpreter it found itself in.
FAKE_INSTALLER = """import os, sys
with open(os.environ["OMODACHI_TEST_MARKER"], "a") as marker:
    marker.write(" ".join(sys.argv[1:]) + "\\n")
probe = os.environ.get("OMODACHI_TEST_PROBE")
if probe:
    import json
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.join(root, "src"))
    from omodachi_core import probe as core_probe
    try:
        import sneaky
        sneaky = True
    except ImportError:
        sneaky = False
    prefix = sys.pycache_prefix
    with open(probe, "w") as out:
        json.dump({"value": core_probe.VALUE, "sneaky": sneaky,
                   "isolated": sys.flags.isolated, "dont_write_bytecode": sys.flags.dont_write_bytecode,
                   "no_user_site": sys.flags.no_user_site, "ignore_environment": sys.flags.ignore_environment,
                   "prefix": prefix,
                   "prefix_listing": sorted(os.listdir(prefix)) if prefix and os.path.isdir(prefix) else None,
                   "prefix_mode": (os.stat(prefix).st_mode & 0o777) if prefix and os.path.isdir(prefix) else None,
                   "cwd": os.getcwd(), "cwd_listing": sorted(os.listdir(".")),
                   "path": sys.path, "script_dir": os.path.dirname(os.path.abspath(__file__)),
                   "env": {k: v for k, v in os.environ.items() if k.startswith("PYTHON")}}, out)
"""

# What a planted bytecode cache runs: it leaves a mark and changes the value.
PLANTED_SOURCE = """import os
with open(os.environ["OMODACHI_TEST_PLANTED"], "a") as planted:
    planted.write("planted " + __name__ + "\\n")
VALUE = "planted"
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
        (self.upstream / "src/omodachi_core").mkdir(parents=True)
        (self.upstream / "src/omodachi_core/__init__.py").write_text("")
        (self.upstream / "src/omodachi_core/probe.py").write_text('VALUE = "verified"\n')
        # core's own .gitignore ignores exactly these.
        (self.upstream / ".gitignore").write_text("build/\n__pycache__/\n*.py[cod]\n")
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
        self.assertEqual(pin["ref"], "v0.1.2")
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

    def test_an_untracked_file_in_the_checkout_is_gone_before_install_runs(self):
        # RELEASE-7: Install starts from a new directory; the old one, and the
        # planted file in it, are not used and do not survive.
        self.install_first()
        (self.source_dir / "scripts/json.py").write_text("raise SystemExit('planted')\n")
        code, out = self.main()
        self.assertEqual(code, 0, out)
        self.assertEqual(self.ran(), ["--local"])
        self.assertFalse((self.source_dir / "scripts/json.py").exists())

    def test_an_untracked_file_hidden_by_the_checkouts_own_excludes_is_cleaned_before_remove(self):
        # RELEASE-7: `--remove` cleans every untracked and ignored file first;
        # the checkout's own info/exclude hides nothing from that.
        self.install_first()
        (self.source_dir / ".git/info").mkdir(exist_ok=True)
        (self.source_dir / ".git/info/exclude").write_text("json.py\n")
        (self.source_dir / "scripts/json.py").write_text("raise SystemExit('planted')\n")
        code, out = self.main("--remove")
        self.assertEqual(code, 0, out)
        self.assertEqual(self.ran(), ["--local --remove"])
        self.assertFalse((self.source_dir / "scripts/json.py").exists())

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
        # A modified tracked file is not something cleaning takes away.
        (self.source_dir / "scripts/install_host.py").write_text(FAKE_INSTALLER + "# edited\n")
        self.write_pin(commit=self.first)
        code, out = self.main("--remove")
        self.assertEqual(code, 1, out)
        self.assertEqual(self.ran(), [])
        self.assertIn("scripts/install_host.py", out)

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


def plant_bytecode(module: Path, *, legacy: Path | None = None) -> Path:
    """A cache for `module` whose code is PLANTED_SOURCE, and optionally a
    sourceless .pyc. The cache is an *unchecked-hash* pyc (PEP 552): a default
    interpreter uses it without looking at the source at all, so it survives
    any change to the source's mtime or contents - the strongest plant there is."""
    from importlib import _bootstrap_external
    import importlib.util
    code = compile(PLANTED_SOURCE, str(module), "exec")
    # The file a default interpreter looks for beside the source.
    cache = module.parent / "__pycache__" / f"{module.stem}.{sys.implementation.cache_tag}.pyc"
    cache.parent.mkdir(exist_ok=True)
    source_hash = importlib.util.source_hash(module.read_bytes())
    cache.write_bytes(_bootstrap_external._code_to_hash_pyc(code, source_hash, checked=False))
    if legacy is not None:
        legacy.write_bytes(_bootstrap_external._code_to_timestamp_pyc(
            compile(PLANTED_SOURCE, str(legacy), "exec"), 0, 0))
    return cache


class NothingOutsideTheTreeRunsTests(UpstreamCase):
    """RELEASE-7 (marketplace #8330, finding 3)."""

    def setUp(self):
        super().setUp()
        base = Path(self.temporary.name)
        self.marker = base / "ran"
        self.planted = base / "planted"
        self.probe = base / "probe.json"
        os.environ.update(OMODACHI_TEST_MARKER=str(self.marker), OMODACHI_TEST_PLANTED=str(self.planted),
                          OMODACHI_TEST_PROBE=str(self.probe))
        patcher = mock.patch.object(self.module.sys, "platform", "linux")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.write_pin(commit=self.first)

    def main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = self.module.main(list(argv))
        return code, out.getvalue()

    def install(self):
        code, out = self.main()
        self.assertEqual(code, 0, out)
        return out

    def plant(self):
        """Everything the review is about, in the installed checkout."""
        module = self.source_dir / "src/omodachi_core/probe.py"
        cache = plant_bytecode(module, legacy=self.source_dir / "src/sneaky.pyc")
        (self.source_dir / "build").mkdir(exist_ok=True)
        (self.source_dir / "build/lib.pth").write_text("import os\n")
        (self.source_dir / "scripts/untracked.py").write_text("x = 1\n")
        return [cache, self.source_dir / "src/sneaky.pyc", self.source_dir / "build",
                self.source_dir / "scripts/untracked.py"]

    def result(self):
        return json.loads(self.probe.read_text())

    def test_the_planted_bytecode_does_run_when_nothing_stops_it(self):
        # The control: same interpreter, the plain `python3 installer` that
        # ran before RELEASE-7. Without it the other tests prove nothing.
        self.install()
        self.plant()
        subprocess.run([sys.executable, str(self.source_dir / "scripts/install_host.py")],
                       check=True, cwd=self.temporary.name)
        self.assertEqual(self.result()["value"], "planted")
        self.assertTrue(self.result()["sneaky"])
        self.assertIn("planted", self.planted.read_text())

    def test_install_never_runs_bytecode_or_files_planted_in_the_checkout(self):
        self.install()
        planted = self.plant()
        parent = self.source_dir.parent
        (parent / ".src-new-leftover").mkdir()
        (parent / ".src-old-leftover").mkdir()
        self.install()
        self.assertFalse(self.planted.exists(), "planted code ran")
        self.assertEqual(self.result()["value"], "verified")
        self.assertFalse(self.result()["sneaky"])
        for path in planted:
            self.assertFalse(path.exists(), path)
        self.assertEqual(sorted(child.name for child in parent.iterdir()), ["src"])

    def test_remove_cleans_the_checkout_before_it_checks_and_runs_it(self):
        self.install()
        planted = self.plant()
        code, out = self.main("--remove")
        self.assertEqual(code, 0, out)
        self.assertIn("clean -ffdxq", out)
        self.assertIn("status --porcelain --ignored=matching --untracked-files=all", out)
        self.assertFalse(self.planted.exists(), "planted code ran")
        self.assertEqual(self.result()["value"], "verified")
        self.assertFalse(self.result()["sneaky"])
        for path in planted:
            self.assertFalse(path.exists(), path)
        self.assertTrue((self.source_dir / ".git").is_dir(), "cleaning never touches .git")

    def test_the_interpreter_never_reads_a_cache_beside_the_sources(self):
        # The second, independent layer: even with the plant still in place
        # (no cleaning at all), core's interpreter does not read it.
        self.install()
        plant_bytecode(self.source_dir / "src/omodachi_core/probe.py")
        with contextlib.redirect_stdout(io.StringIO()):
            code = self.module.run_core(self.source_dir / "scripts/install_host.py", [])
        self.assertEqual(code, 0)
        self.assertFalse(self.planted.exists(), "planted code ran")
        self.assertEqual(self.result()["value"], "verified")

    def test_a_file_that_cannot_be_deleted_fails_the_check_closed(self):
        if os.geteuid() == 0:
            self.skipTest("root can delete it anyway")
        self.install()
        self.marker.unlink()
        stuck = self.source_dir / "src/omodachi_core/__pycache__"
        stuck.mkdir()
        (stuck / "probe.cpython-399.pyc").write_bytes(b"x")
        stuck.chmod(0o555)
        self.addCleanup(stuck.chmod, 0o755)
        code, out = self.main("--remove")
        self.assertEqual(code, 1, out)
        self.assertEqual(self.ran(), [])
        self.assertIn("uninstaller was not run", out)
        self.assertIn("!! src/omodachi_core/__pycache__/", out)
        with contextlib.redirect_stdout(io.StringIO()):
            ok, detail = self.module.verify_checkout(self.first)
        self.assertFalse(ok)
        self.assertIn("undeletable", detail)

    def ran(self):
        return self.marker.read_text().splitlines() if self.marker.exists() else []

    def test_core_runs_isolated_with_a_new_private_empty_bytecode_prefix(self):
        evil = Path(self.temporary.name) / "evil"
        evil.mkdir()
        (evil / "sitecustomize.py").write_text(PLANTED_SOURCE)
        os.environ.update(PYTHONPATH=str(evil), PYTHONSTARTUP=str(evil / "sitecustomize.py"),
                          PYTHONUSERBASE=str(evil), PYTHONWARNINGS="ignore")
        out = self.install()
        seen = self.result()
        self.assertFalse(self.planted.exists(), "PYTHONPATH's sitecustomize ran")
        self.assertEqual((seen["isolated"], seen["dont_write_bytecode"], seen["no_user_site"],
                          seen["ignore_environment"]), (1, 1, 1, 1))
        prefix = seen["prefix"]
        self.assertTrue(prefix and Path(prefix).name == "bytecode", prefix)
        self.assertEqual(seen["prefix_listing"], [])
        self.assertEqual(seen["prefix_mode"], 0o700)
        self.assertFalse(Path(prefix).exists(), "the prefix is removed afterwards")
        self.assertEqual(seen["cwd_listing"], [])
        self.assertEqual(Path(seen["cwd"]).resolve().parent, Path(prefix).resolve().parent)
        self.assertNotIn(seen["script_dir"], seen["path"])
        self.assertNotIn(str(evil), seen["path"])
        self.assertNotIn("", seen["path"])
        self.assertEqual(seen["env"], {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONPYCACHEPREFIX": prefix,
                                       "PYTHONNOUSERSITE": "1"})
        self.assertIn(f" -I -B -X pycache_prefix={prefix} ", out)
        self.assertEqual([path for path in self.source_dir.rglob("*") if path.suffix == ".pyc"
                          or path.name == "__pycache__"], [])

    def test_git_programs_named_by_the_checkouts_own_config_never_run(self):
        self.install()
        dot_git = self.source_dir / ".git"
        ran = Path(self.temporary.name) / "git-program-ran"
        def program(name, *, passthrough=False):
            # A filter has to pass its input through; the others must not wait on it.
            body = f"echo {name} >> {ran}" + ("; cat" if passthrough else "")
            return f"sh -c '{body}'" + ("" if passthrough else " </dev/null")
        for key, value in (("filter.evil.clean", program("clean", passthrough=True)),
                           ("filter.evil.smudge", program("smudge", passthrough=True)),
                           ("filter.evil.required", "true"), ("core.fsmonitor", program("fsmonitor")),
                           ("core.alternateRefsCommand", program("alternateRefsCommand"))):
            git("config", key, value, cwd=self.source_dir)
        (dot_git / "info").mkdir(exist_ok=True)
        (dot_git / "info/attributes").write_text("* filter=evil\n")
        for hook in ("post-checkout", "post-index-change", "reference-transaction"):
            (dot_git / "hooks").mkdir(exist_ok=True)
            (dot_git / "hooks" / hook).write_text(f"#!/bin/sh\necho {hook} >> {ran}\n")
            (dot_git / "hooks" / hook).chmod(0o755)
        # Control: plain git in that checkout does run them.
        (self.source_dir / "pyproject.toml").touch()
        subprocess.run(["git", "-C", str(self.source_dir), "checkout", "--force", "--detach", "HEAD"],
                       capture_output=True, timeout=60)
        self.assertTrue(ran.exists(), "the control did not fire; the test proves nothing")
        ran.unlink()
        code, out = self.main("--remove")
        self.assertEqual(code, 0, out)
        self.assertFalse(ran.exists(), ran.read_text() if ran.exists() else "")
        self.install_again_with_the_same_plant(ran)

    def install_again_with_the_same_plant(self, ran):
        # --remove took src with it (the fake uninstaller does not, so the
        # planted .git is still here): Install must not use it either.
        self.install()
        self.assertFalse(ran.exists(), ran.read_text() if ran.exists() else "")

    def test_git_variables_cannot_point_the_check_at_another_tree(self):
        self.install()
        (self.source_dir / "scripts/install_host.py").write_text(FAKE_INSTALLER + "# edited\n")
        clean = Path(self.temporary.name) / "clean"
        git("clone", "--quiet", self.url, str(clean), cwd=self.temporary.name)
        git("checkout", "--quiet", "--detach", self.first, cwd=clean)
        os.environ.update(GIT_DIR=str(clean / ".git"), GIT_WORK_TREE=str(clean),
                          GIT_INDEX_FILE=str(clean / ".git/index"))
        self.marker.unlink()
        code, out = self.main("--remove")
        self.assertEqual(code, 1, out)
        self.assertEqual(self.ran(), [])
        self.assertIn("scripts/install_host.py", out)

    def test_the_bootstrap_re_runs_itself_isolated_before_importing_anything(self):
        base = Path(self.temporary.name)
        tools = base / "plugin/tools"
        tools.mkdir(parents=True)
        (tools / "install_host.py").write_bytes((ROOT / "tools/install_host.py").read_bytes())
        # Beside the script, and on PYTHONPATH: modules it imports by name.
        (tools / "argparse.py").write_text(PLANTED_SOURCE)
        evil = base / "evil"
        evil.mkdir()
        (evil / "tempfile.py").write_text(PLANTED_SOURCE)
        environment = dict(os.environ, PYTHONPATH=str(evil))
        # Control: an interpreter started the same way does import them.
        control = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
                                  "import argparse, tempfile", str(tools)],
                                 env=environment, capture_output=True, text=True)
        self.assertEqual(control.returncode, 0, control.stderr)
        self.assertEqual(self.planted.read_text().split(), ["planted", "argparse", "planted", "tempfile"])
        self.planted.unlink()
        for cache in (tools / "__pycache__", evil / "__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)
        result = subprocess.run([sys.executable, str(tools / "install_host.py"), "--help"],
                                env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage", result.stdout)
        self.assertFalse(self.planted.exists(), self.planted.read_text() if self.planted.exists() else "")
        self.assertEqual([path.name for path in tools.iterdir() if path.name == "__pycache__"], [])


if __name__ == "__main__":
    unittest.main()
