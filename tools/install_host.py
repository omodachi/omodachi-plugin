#!/usr/bin/env python3
"""Get omodachi-core onto this computer, then hand over to its own installer.

This is the whole of the panel's "Install…" button, and the only file in this
repository that runs as a program. It is deliberately small and deliberately
tracked: until INSTALL-1 the plugin shipped a *copy* of core's installer that
`scripts/package.py` wrote at package time into a gitignored `tools/`
directory, which meant a public clone of this repository had no Install at all
and every developer host had a copy that could silently go stale.

    python3 tools/install_host.py               # fetch core, then install it
    python3 tools/install_host.py --remove      # uninstall, keeping pairings
    python3 tools/install_host.py --remove --purge

What it does, in order:

  1. check that git and python3 are here, and say which is missing if not;
  2. fetch the pinned core commit into a new directory, check it out
     detached, refusing anything whose sha is not the pinned one, and put it
     at ~/.local/share/omodachi/src;
  3. immediately before running anything from it, delete every ignored and
     untracked file in the checkout and check that it is exactly the pinned
     commit: HEAD, its tree, and not one modified, extra or ignored file;
  4. run that checkout's own scripts/install_host.py --local under
     `python3 -I -B`, which owns every decision about units, the virtualenv,
     the firewall, the Omarchy surfaces and the managed Sunshine fork.

It writes one more thing: ~/.cache/omodachi/install-status.json, rewritten at
each stage. The panel reads it, so a user watching the panel sees the same
stage as the user watching the terminal, and a failure names itself in both
places instead of scrolling past.

Where core comes from is `omodachi.json` beside this plugin's manifest - one
owner, one repository, one ref and the full 40-character commit that ref names
- and $OMODACHI_CORE_SOURCE / $OMODACHI_CORE_REF / $OMODACHI_CORE_COMMIT
override it, which is how a staging host installs from a private mirror
without editing a pinned file.

RELEASE-3b. What runs is the commit, not the tag: a tag can be moved after the
plugin was reviewed, a commit cannot. The ref is kept for the one case a git
server will not hand out a bare sha (old servers without
`uploadpack.allowReachableSHA1InWant`): the tag is fetched instead and its
commit has to equal the pinned one, or nothing is checked out.

RELEASE-5. There is no other way in. A ~/.local/share/omodachi/src that is not
a git checkout (the rsynced tree developers used before this button could
fetch) is refused and left exactly where it is, never run and never deleted;
and `--remove` runs a checkout's uninstaller only when that checkout passes
the same check. A developer installs their own core by pointing
$OMODACHI_CORE_SOURCE at a git repository and $OMODACHI_CORE_COMMIT at a
commit in it, which goes through the same fetch and the same check.

RELEASE-7. Nothing that is not in the verified tree gets to run, bytecode
included. Install fetches into a brand-new directory every time, so nothing
that was in src before - ignored files, __pycache__, the old .git and its
config - is used. Right before the check, install and `--remove` alike, every
ignored and untracked file is deleted (`git clean -ffdx`), and the check itself
counts ignored files too, so whatever could not be deleted fails it. The check
never reads the checkout's own .git/config: it runs in a scratch repository
that takes the pinned commit's objects from the checkout by hash. And core's
installer runs as `python3 -I -B -X pycache_prefix=<empty private dir>`, with
the same prefix and no PYTHON* variables from the caller in its children's
environment, so no interpreter in the install reads a bytecode cache from the
checkout, a user site-packages .pth, PYTHONPATH or PYTHONSTARTUP. This file
re-runs itself the same way (-I -B) when it was started without them.
"""
from __future__ import annotations

import os
import sys

# RELEASE-7. Before any other import: an interpreter started without -I puts
# this file's directory and $PYTHONPATH in front of the standard library, so
# the modules imported below could come from there. `sys` is built in and `os`
# was already loaded by the interpreter's own startup before this line runs.
# The panel already passes -I -B; a hand-typed `python3 install_host.py` gets
# the same interpreter from here on.
if __name__ == "__main__" and sys.executable and not (sys.flags.isolated and sys.flags.dont_write_bytecode):
    os.execv(sys.executable, [sys.executable, "-I", "-B", os.path.realpath(__file__), *sys.argv[1:]])

import argparse  # noqa: E402 - after the re-exec above, on purpose
import json  # noqa: E402
from pathlib import Path  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PIN = ROOT / "omodachi.json"
HOME = Path.home()
SOURCE_DIR = HOME / ".local/share/omodachi/src"
STATUS_PATH = HOME / ".cache/omodachi/install-status.json"
SOURCE_ENV, REF_ENV, COMMIT_ENV = "OMODACHI_CORE_SOURCE", "OMODACHI_CORE_REF", "OMODACHI_CORE_COMMIT"
# Kept in step with the same constant in core's sunshine_package.py. Moving the
# project to another GitHub account is an edit to omodachi.json and to that.
DEFAULT_OWNER = "omodachi"

STAGES = {
    "starting": "Starting…",
    "checking": "Checking this computer has git and python3…",
    "fetching": "Fetching the Omodachi Host source…",
    "installing": "Installing Omodachi Host…",
    "removing": "Removing Omodachi Host…",
    "done": "Done. The panel reconnects on its own.",
    "failed": "Install failed.",
}


def status(stage: str, message: str = "", *, detail: str = "") -> None:
    """One small JSON file the panel polls. Never fails the install."""
    try:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        body = {"stage": stage, "label": STAGES.get(stage, stage),
                "message": message or STAGES.get(stage, stage), "detail": detail,
                "ok": None if stage not in ("done", "failed") else (stage == "done"),
                "pid": os.getpid(), "updated": time.time()}
        temporary = STATUS_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(body))
        temporary.replace(STATUS_PATH)
    except OSError:
        pass
    print(f"[{stage}] {message or STAGES.get(stage, stage)}"
          + (f"\n    {detail}" if detail else ""), flush=True)


def fail(message: str, detail: str = "") -> int:
    status("failed", message, detail=detail)
    print("\nNothing was left half-installed by this step. "
          "Close this window, fix the above and press Install again.", flush=True)
    return 1


def source_pin() -> dict:
    """Where core comes from: the pinned file, then the environment."""
    value = {"owner": DEFAULT_OWNER, "repository": "omodachi-core", "ref": "main", "url": None,
             "commit": None}
    try:
        stored = json.loads(SOURCE_PIN.read_text()).get("core_source") or {}
        if isinstance(stored, dict):
            value.update({key: stored[key] for key in ("owner", "repository", "ref", "url", "commit")
                          if key in stored and isinstance(stored[key], str)})
    except (OSError, ValueError):
        pass
    if not value["url"]:
        value["url"] = f"https://github.com/{value['owner']}/{value['repository']}.git"
    value["url"] = os.environ.get(SOURCE_ENV) or value["url"]
    value["ref"] = os.environ.get(REF_ENV) or value["ref"]
    value["commit"] = os.environ.get(COMMIT_ENV) or value["commit"]
    return value


def is_full_commit(value) -> bool:
    return (isinstance(value, str) and len(value) == 40
            and all(character in "0123456789abcdef" for character in value))


def run(argv, **kwargs):
    print("+ " + " ".join(str(part) for part in argv), flush=True)
    return subprocess.run(argv, **kwargs)


# What `--purge` takes when core's installer is already gone. Every one of
# these is a directory this project made under the user's own home; nothing
# here is shared with Omarchy or with any other program.
PURGE_DIRECTORIES = (".config/omodachi", ".cache/omodachi",
                     ".local/state/omodachi", ".local/share/omodachi")


def purge_only() -> int:
    present = [relative for relative in PURGE_DIRECTORIES if (HOME / relative).is_dir()]
    # The status file lives in one of these directories, so it is written
    # before they go - otherwise the last act of a purge is to recreate
    # ~/.cache/omodachi and leave it behind.
    status("done", "Removed the files Omodachi Host left behind.",
           detail=", ".join(present) if present else "there was nothing left to remove")
    for relative in present:
        shutil.rmtree(HOME / relative, ignore_errors=True)
    return 0


# Every git call here. A checkout's .git/config and the user's global config
# can name programs git runs on its own - hooks, fsmonitor, filter drivers
# through an attributes file, the `ext::` transport - and replace refs can
# make a sha name other bytes; none of them get a say in anything this script
# asks git. (Filter drivers need a gitattributes line to fire: the global
# attributes file is switched off here, the pinned tree carries none, and the
# only other place is $GIT_DIR/info/attributes, which is never a directory
# this script did not just create.)
GIT_SAFE = ("-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
            "-c", "core.attributesFile=/dev/null", "-c", "protocol.ext.allow=never",
            "--no-replace-objects")

# Environment variables that would point git at another repository, work
# tree, index, object store, attributes source, template or set of git
# programs than the ones named on its command line, or inject config. The
# user's transport settings (ssh command, askpass, proxies, CA bundle) stay:
# they decide how bytes arrive, never which bytes are accepted.
GIT_REDIRECTS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                 "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_COMMON_DIR", "GIT_NAMESPACE",
                 "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM",
                 "GIT_REPLACE_REF_BASE", "GIT_GRAFT_FILE", "GIT_SHALLOW_FILE", "GIT_ATTR_SOURCE",
                 "GIT_TEMPLATE_DIR", "GIT_EXEC_PATH", "GIT_QUARANTINE_PATH", "GIT_CONFIG",
                 "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT")


def git_environment() -> dict:
    return {key: value for key, value in os.environ.items()
            if key not in GIT_REDIRECTS and not key.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}


def _git(*arguments, repo: Path | None = None):
    return run(["git", *GIT_SAFE, "-C", str(repo or SOURCE_DIR), *arguments],
               capture_output=True, text=True, env=git_environment())


def _error(result) -> str:
    return (result.stderr or "").strip()[:300]


def _fetch_pinned(url: str, ref: str, commit: str, repo: Path) -> tuple[bool, str]:
    """Put the pinned commit in FETCH_HEAD, and nothing else.

    By sha first. A server that will not serve a bare sha gets asked for the
    tag instead, and then the tag has to name the pinned commit.
    """
    result = _git("fetch", "--depth", "1", url, commit, repo=repo)
    if result.returncode != 0:
        print(f"this server would not fetch {commit} by sha; fetching {ref} and checking it", flush=True)
        result = _git("fetch", "--depth", "1", "--tags", url, ref, repo=repo)
        if result.returncode != 0:
            return False, _error(result)
    fetched = _git("rev-parse", "FETCH_HEAD^{commit}", repo=repo)
    got = (fetched.stdout or "").strip()
    if fetched.returncode != 0 or got != commit:
        return False, (f"{ref} is {got or 'unknown'}, but omodachi.json pins {commit}; "
                       f"refusing to install a commit nobody pinned")
    return True, ""


def _checkout_pinned(commit: str, repo: Path) -> tuple[bool, str]:
    result = _git("checkout", "--force", "--detach", "FETCH_HEAD", repo=repo)
    if result.returncode != 0:
        return False, _error(result)
    head = (_git("rev-parse", "HEAD", repo=repo).stdout or "").strip()
    if head != commit:
        return False, f"HEAD is {head or 'unknown'}, but omodachi.json pins {commit}"
    return True, ""


def pinned_commit(pin: dict) -> str:
    return (pin.get("commit") or "").strip().lower()


def foreign_source() -> str:
    """Why SOURCE_DIR is not ours to fetch into, or "" when it is.

    Ours means absent, an empty directory, or a git checkout that is a real
    directory. Anything else - above all a developer's rsynced tree from
    before this button could fetch one, or a link to their own clone, which a
    forced checkout would rewrite - is somebody's files: never run, never
    deleted, only named.
    """
    ours = not SOURCE_DIR.is_symlink() and (
        not SOURCE_DIR.exists()
        or (SOURCE_DIR.is_dir() and ((SOURCE_DIR / ".git").is_dir() or not any(SOURCE_DIR.iterdir()))))
    if ours:
        return ""
    return (f"{SOURCE_DIR} exists but is not the checkout this installer makes. "
            f"Move it away (or delete it) and press Install again. "
            f"Developers: point ${SOURCE_ENV} at a git repository and ${COMMIT_ENV} "
            f"at the commit to install.")


# RELEASE-7. Install never reuses what is in SOURCE_DIR: the pinned commit is
# fetched into a new directory beside it, and only a complete checkout
# replaces the old one. These are the names of those two transient
# directories; one a killed run left behind is removed by the next run.
FRESH_PREFIX, OLD_PREFIX = ".src-new-", ".src-old-"


def _remove_tree(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path, ignore_errors=True)


def fetch_source(pin: dict) -> tuple[bool, str]:
    """Fetch the pinned commit into a new checkout and put it at SOURCE_DIR.

    Nothing that was in SOURCE_DIR before is used - not its files, not its
    bytecode, not its .git or that .git's config. A failure leaves SOURCE_DIR
    exactly as it was (including an empty directory the user made).
    """
    url, ref, commit = pin["url"], pin["ref"], pinned_commit(pin)
    if not is_full_commit(commit):
        return False, (f"{SOURCE_PIN.name} pins no full 40-character commit for core "
                       f"(got {commit or 'nothing'}); set ${COMMIT_ENV} for a staging source")
    refusal = foreign_source()
    if refusal:
        return False, refusal
    parent = SOURCE_DIR.parent
    parent.mkdir(parents=True, exist_ok=True)
    for leftover in (*parent.glob(FRESH_PREFIX + "*"), *parent.glob(OLD_PREFIX + "*")):
        _remove_tree(leftover)
    fresh = Path(tempfile.mkdtemp(prefix=FRESH_PREFIX, dir=parent))
    try:
        # --template= : no hooks, excludes or config copied in from a template
        # directory; this .git holds only what git itself writes.
        result = run(["git", "init", "--quiet", "--template=", str(fresh)],
                     capture_output=True, text=True, env=git_environment())
        ok, detail = (result.returncode == 0, _error(result))
        if ok:
            # `origin` for whoever looks at the checkout later; every fetch
            # names the URL itself, so a changed pin never reads a stale remote.
            _git("remote", "add", "origin", url, repo=fresh)
            ok, detail = _fetch_pinned(url, ref, commit, fresh)
        if ok:
            ok, detail = _checkout_pinned(commit, fresh)
        if not ok:
            return False, detail
        old = parent / f"{OLD_PREFIX}{os.getpid()}-{time.time_ns()}"
        if SOURCE_DIR.exists():
            SOURCE_DIR.rename(old)
        try:
            fresh.rename(SOURCE_DIR)
        except OSError as error:
            if old.exists():
                old.rename(SOURCE_DIR)
            return False, f"could not move the new checkout into place: {error}"
        _remove_tree(old)
        return True, ""
    finally:
        if fresh.exists():
            _remove_tree(fresh)


def verify_checkout(commit: str, *, clean: bool = True) -> tuple[bool, str]:
    """The bytes about to run are the pinned commit's, and nothing else.

    Called immediately before this script executes anything from SOURCE_DIR,
    install and uninstall alike. RELEASE-7: first every ignored and untracked
    file goes (`git clean -ffdx`: __pycache__, *.pyc, build/, anything else),
    then the work tree must equal the pinned commit's tree exactly, ignored
    files included - so a file that could not be deleted fails the check.

    All of it runs in a scratch repository made for this call, with SOURCE_DIR
    as its work tree. The checkout's own .git is only a place the pinned
    commit's objects are fetched from (by `git upload-pack`, which git runs
    safely in repositories it does not trust, and every object arrives checked
    against its hash); its config, hooks, attributes, excludes and index are
    never read.
    """
    commit = (commit or "").strip().lower()
    if not is_full_commit(commit):
        return False, f"no full 40-character commit is pinned (got {commit or 'nothing'})"
    # Nothing is cleaned in a directory that is not this installer's checkout.
    if foreign_source() or SOURCE_DIR.is_symlink() or not (SOURCE_DIR / ".git").is_dir():
        return False, f"{SOURCE_DIR} is not a git checkout this installer made"
    with tempfile.TemporaryDirectory(prefix="omodachi-verify-") as scratch:
        repository = Path(scratch) / "git"
        environment = git_environment()
        created = run(["git", "init", "--quiet", "--bare", "--template=", str(repository)],
                      capture_output=True, text=True, env=environment)
        if created.returncode != 0:
            return False, f"could not make a scratch repository to check with: {_error(created)}"

        def git(*arguments):
            return run(["git", *GIT_SAFE, f"--git-dir={repository}", f"--work-tree={SOURCE_DIR}",
                        *arguments], capture_output=True, text=True, env=environment)

        fetched = git("fetch", "--quiet", "--no-tags", "--depth", "1", str(SOURCE_DIR / ".git"), "HEAD")
        got = (git("rev-parse", "--verify", "FETCH_HEAD^{commit}").stdout or "").strip() \
            if fetched.returncode == 0 else ""
        if got != commit:
            return False, f"{SOURCE_DIR} is at {got or 'no commit'}, but the pin is {commit}"
        for step in (("update-ref", "--no-deref", "HEAD", commit), ("read-tree", commit)):
            result = git(*step)
            if result.returncode != 0:
                return False, f"could not load {commit} to check against: {_error(result)}"
        if clean:
            git("clean", "-ffdxq")
        state = git("status", "--porcelain", "--ignored=matching", "--untracked-files=all")
        lines = (state.stdout or "").splitlines()
        if state.returncode != 0 or lines:
            shown = "; ".join(line.strip() for line in lines[:5]) or _error(state) or "git failed"
            more = f" (and {len(lines) - 5} more)" if len(lines) > 5 else ""
            return False, f"{SOURCE_DIR} has modified, extra or undeletable files: {shown}{more}"
    return True, ""


# RELEASE-7. How core's installer is run. -I: no user site-packages (and so no
# .pth file there), no PYTHON* variable, and neither the script's directory
# nor the current directory on sys.path - core's installer puts its own src/
# there itself, and loads install_wayvnc.py by path. -B and -X pycache_prefix:
# it neither writes nor reads a bytecode cache beside any source; the prefix is
# a new empty directory only this user can open, deleted afterwards. Its
# children (python3 -m venv, pip and the build backend, omodachi-host) are not
# started with -I, so their environment carries the same prefix,
# PYTHONDONTWRITEBYTECODE and PYTHONNOUSERSITE, none of the caller's PYTHON*
# variables, and an empty working directory for `python -m` to put on sys.path.
def core_command(installer: Path, bytecode: Path, arguments) -> list[str]:
    return [sys.executable, "-I", "-B", "-X", f"pycache_prefix={bytecode}", str(installer),
            "--local", *arguments]


def core_environment(bytecode: Path) -> dict:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON")}
    environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(bytecode),
                       PYTHONNOUSERSITE="1")
    return environment


def run_core(installer: Path, arguments) -> int:
    scratch = Path(tempfile.mkdtemp(prefix="omodachi-core-"))  # 0700
    try:
        bytecode, work = scratch / "bytecode", scratch / "cwd"
        bytecode.mkdir(mode=0o700)
        work.mkdir(mode=0o700)
        return run(core_command(installer, bytecode, arguments), env=core_environment(bytecode),
                   cwd=str(work)).returncode
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--remove", action="store_true",
                        help="uninstall Omodachi Host: units, virtualenv, desktop entry, "
                             "the managed Sunshine fork and the firewall rules")
    parser.add_argument("--purge", action="store_true",
                        help="with --remove, also delete ~/.config/omodachi - the device "
                             "secret, the host certificate and every pairing")
    parser.add_argument("--source", help=f"override the pinned core source (or ${SOURCE_ENV})")
    parser.add_argument("--ref", help=f"override the pinned core ref (or ${REF_ENV})")
    parser.add_argument("--commit", help=f"override the pinned core commit (or ${COMMIT_ENV})")
    # Accepted and ignored: released plugins before INSTALL-1 ran this script
    # with `--local --source <url>`, and an old panel must not hit an argparse
    # error it cannot show anybody.
    parser.add_argument("--local", action="store_true", help=argparse.SUPPRESS)
    arguments, extra = parser.parse_known_args(argv)

    if sys.platform != "linux":
        return fail("Omodachi Host installs on the Omarchy computer itself.",
                    f"this is {sys.platform}")
    status("starting", "Omodachi Host installer")
    status("checking")
    for tool in ("git", "python3"):
        if shutil.which(tool) is None:
            return fail(f"{tool} is not installed on this computer.",
                        f"install it first: sudo pacman -S --needed {tool}")

    pin = source_pin()
    if arguments.source:
        pin["url"] = arguments.source
    if arguments.ref:
        pin["ref"] = arguments.ref
    if arguments.commit:
        pin["commit"] = arguments.commit

    installer = SOURCE_DIR / "scripts/install_host.py"
    if arguments.remove:
        status("removing")
        if not installer.is_file():
            if arguments.purge:
                # `--remove` deletes the sources, so a user who decides
                # afterwards that they also want their pairings gone has no
                # installer left to ask. These four directories are the whole
                # of what a purge takes, and they are this user's own.
                return purge_only()
            return fail("Omodachi Host is not installed here.",
                        f"{installer} does not exist, so there is nothing to remove. "
                        f"Add --purge to delete the device secret, the certificate and the "
                        f"pairings it left behind.")
        ok, detail = verify_checkout(pinned_commit(pin))
        if not ok:
            # Its uninstaller is a program like any other: an unverified
            # one does not run. `--purge` alone never runs it either.
            return fail("The Omodachi Host source here is not the pinned commit, "
                        "so its uninstaller was not run.",
                        f"{detail}. Press Install first to bring it to the pinned commit and "
                        f"remove again, or move {SOURCE_DIR} away (or delete it) and run "
                        f"--remove --purge to delete the files Omodachi Host left behind.")
        code = run_core(installer, ["--remove", *(["--purge"] if arguments.purge else [])])
        if code != 0:
            return fail("The uninstaller reported an error.", f"exit {code}")
        status("done", "Omodachi Host removed.")
        return 0

    refusal = foreign_source()
    if refusal:
        return fail("There is already something at the place Omodachi Host installs from.",
                    refusal)
    status("fetching", f"Fetching Omodachi Host from {pin['url']} "
                       f"({pin['ref']} = {pin.get('commit') or 'no commit pinned'})…")
    ok, detail = fetch_source(pin)
    if not ok:
        return fail(f"Could not fetch {pin['url']} ({pin['ref']}).", detail
                    or "check this computer's network connection and try again")
    if not installer.is_file():
        return fail("The downloaded source is not omodachi-core.",
                    f"{installer} is missing. Check the source URL in {SOURCE_PIN.name}.")
    # Last thing before anything from the checkout runs: clean, then check.
    ok, detail = verify_checkout(pinned_commit(pin))
    if not ok:
        return fail("The Omodachi Host source is not exactly the pinned commit; nothing was run.",
                    detail)

    status("installing")
    code = run_core(installer, extra)
    if code != 0:
        return fail("The installer reported an error.",
                    f"exit {code}. The lines above say which step failed.")
    status("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
