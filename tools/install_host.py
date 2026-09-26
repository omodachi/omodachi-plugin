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
  3. immediately before running anything from it, delete the build output
     the pinned .gitignore names and check that the checkout is exactly the
     pinned commit: HEAD, its tree, and not one modified, extra or ignored
     file (an extra file that is not build output fails the check, and stays);
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

RELEASE-8. The only src this installer replaces, cleans or deletes is one it
can show it made: a random id it wrote into that checkout's .git, repeated in
~/.local/state/omodachi/core-source.json (0600). Anything else there - a
user's repository, a clone of omodachi-core at the pinned commit, a file, a
link, an empty directory - is described and left exactly as it is, for Install
and `--remove` (with or without --purge) alike; only a checkout that an
earlier version of this installer made is recognised as one and adopted. Even
our own checkout is deleted only when it holds nothing but its commit and the
build output that commit's .gitignore names; otherwise Install moves it to
~/.local/share/omodachi-kept/, and `--remove` refuses.
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
import fcntl  # noqa: E402
import json  # noqa: E402
import secrets  # noqa: E402
import shlex  # noqa: E402
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


def write_file(path: Path, text: str, mode: int) -> None:
    """Every file this script writes goes through here (RELEASE-8): a new
    temporary beside it, created exclusively and never through a link
    (O_EXCL | O_NOFOLLOW), synced, then renamed over the target - and a rename
    replaces a link at the target instead of writing where it points."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.unlink(missing_ok=True)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                         | os.O_CLOEXEC, mode)
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def status(stage: str, message: str = "", *, detail: str = "") -> None:
    """One small JSON file the panel polls. Never fails the install."""
    try:
        STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
        body = {"stage": stage, "label": STAGES.get(stage, stage),
                "message": message or STAGES.get(stage, stage), "detail": detail,
                "ok": None if stage not in ("done", "failed") else (stage == "done"),
                "pid": os.getpid(), "updated": time.time()}
        write_file(STATUS_PATH, json.dumps(body), 0o644)
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


# What `--purge` takes when core's installer is already gone - the same rule
# core's own --purge follows (RELEASE-8): what the installer and its daemon
# made, never the user's own files. Kept: ~/.local/share/omodachi/agent-workspace
# (the agent's working directory), anything else there nobody here made, and
# the files a person writes in ~/.config/omodachi by hand (the menu layer, its
# set-aside copies, desktop-runtime.json). src goes only if it is ours.
SHARE_MADE = ("venv", "venv.previous")
USER_CONFIG = ("omodachi-menu.jsonc", "desktop-runtime.json")
USER_CONFIG_PREFIXES = ("omodachi-menu.jsonc.codex-bak",)


def _delete(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path, ignore_errors=True)


def _children(directory: Path) -> list[Path]:
    return sorted(directory.iterdir()) if _real_dir(directory) else []


def _remove_empty(directory: Path) -> None:
    try:
        if _real_dir(directory):
            directory.rmdir()
    except OSError:
        pass  # something in it is not ours


def purge_only() -> int:
    share, config = SOURCE_DIR.parent, HOME / ".config/omodachi"
    kept = [child for child in _children(config)
            if child.name in USER_CONFIG or child.name.startswith(USER_CONFIG_PREFIXES)]
    for child in _children(config):
        if child not in kept:
            _delete(child)
    _remove_empty(config)
    for name in SHARE_MADE:
        if os.path.lexists(share / name):
            _delete(share / name)
    for directory in sorted((share / "hooks").glob("*"), reverse=True) + [share / "hooks"]:
        _remove_empty(directory)
    # main() has refused a src that is not ours before it gets here.
    if os.path.lexists(SOURCE_DIR) and ownership()[0] == "ours":
        _delete(SOURCE_DIR)
    kept += _children(share)
    _remove_empty(share)
    for child in _children(RECORD_PATH.parent):
        _delete(child)
    _remove_empty(RECORD_PATH.parent)
    # The status file lives in ~/.cache/omodachi, so it is written before that
    # goes - otherwise the last act of a purge is to recreate it.
    status("done", "Removed the files Omodachi Host left behind.",
           detail=("kept, because they are yours rather than the installer's: "
                   + ", ".join(str(path) for path in kept)) if kept else "")
    shutil.rmtree(HOME / ".cache/omodachi", ignore_errors=True)
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


# RELEASE-8. Which ~/.local/share/omodachi/src this installer may replace,
# clean or delete: only one it can show it made. When it makes a checkout it
# writes a random id into that checkout's .git (ID_FILE) and the same id, with
# the path, into RECORD_PATH, a 0600 file outside the tree. A directory there
# is ours only when both agree. Anything else - a user's own repository, a
# clone of omodachi-core at the very same commit, a copied tree, a file, a
# link, even an empty directory - is described, left exactly as it is, and
# nothing in it is run, renamed, cleaned or deleted.
#
# Why an id and not the directory's inode/device: on btrfs, Omarchy's default
# filesystem, st_dev is an anonymous number handed out at mount time, and on
# ext4 a directory deleted and made again can get the same inode back - so an
# inode can call a user's fresh clone ours. Nothing but this file writes 128
# random bits into a .git/ID_FILE; a checkout that is merely *like* ours never
# has them. A process running as this same user can forge both halves, but it
# could as well delete the directory itself: this is a guard against
# accidents, not a security boundary. The boundary is still `verify_checkout`,
# which decides what runs from the bytes in the tree, not from any record.
RECORD_PATH = HOME / ".local/state/omodachi/core-source.json"
LOCK_PATH = HOME / ".local/state/omodachi/install.lock"
ID_FILE = "omodachi-install-id"
# Where Install puts a checkout of ours that holds something the recorded
# commit does not (a modified or extra file): moved aside, never deleted.
# Outside ~/.local/share/omodachi on purpose, so no `--purge` reaches it.
KEPT_DIR = HOME / ".local/share/omodachi-kept"

# Installs made before RELEASE-8 have no record. Such a checkout is adopted only
# if it is unmistakably what those installers made: a real .git whose HEAD is
# detached at one of the commits they pinned, no branch or remote-tracking ref
# (they only ever fetched a URL into FETCH_HEAD), a shallow list naming only
# those commits (they always fetched --depth 1), one remote, `origin`, at the
# public repository, and no modified tracked file. A clone of omodachi-core
# has branches and full history, so it is never taken for one.
EARLIER_PINS = frozenset({
    "da63f8275d70d1c45ac72fb6b79dde21e529f6bf",  # v0.1.0
    "7b0161953538358be6437c0d5f5f57e6e0eff07a",  # v0.1.1
    "5e1474a7751aa40c235b1149ac42b5b11c08d18c",  # v0.1.2
})
EARLIER_ORIGINS = frozenset({"https://github.com/omodachi/omodachi-core.git",
                             "https://github.com/omodachi/omodachi-core"})

# RELEASE-7. Install never reuses what is in SOURCE_DIR: the pinned commit is
# fetched into a new directory beside it, and only a complete checkout
# replaces the old one. These are the names of those two transient
# directories, each suffixed with an id the record lists under "pending"
# while it exists; a run that was killed leaves one behind, and the next run
# removes it - only a directory with exactly such a recorded name.
FRESH_PREFIX, OLD_PREFIX = ".src-new-", ".src-old-"


def _is_id(value) -> bool:
    return (isinstance(value, str) and len(value) == 32
            and all(character in "0123456789abcdef" for character in value))


def _real_dir(path: Path) -> bool:
    return path.is_dir() and not path.is_symlink()


def read_record() -> dict:
    try:
        record = json.loads(RECORD_PATH.read_text())
    except (OSError, ValueError):
        return {}
    if not isinstance(record, dict) or record.get("path") != str(SOURCE_DIR):
        return {}
    record["pending"] = [value for value in record.get("pending") or [] if _is_id(value)]
    return record


def write_record(record: dict) -> None:
    """Replace the record in one step, 0600 in a 0700 directory."""
    record = {**record, "schema": 1, "path": str(SOURCE_DIR)}
    if not record.get("id") and not record.get("pending"):
        RECORD_PATH.unlink(missing_ok=True)
        return
    RECORD_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    write_file(RECORD_PATH, json.dumps(record, indent=1, sort_keys=True), 0o600)


def _head_of(path: Path, size: int = 200) -> str:
    """The start of a regular file (never a link, FIFO or device), or ""."""
    try:
        if path.is_symlink() or not path.is_file():
            return ""
        with path.open("rb") as handle:
            return handle.read(size).decode("utf-8", "replace").strip()
    except OSError:
        return ""


def _read_id(tree: Path) -> str:
    return _head_of(tree / ".git" / ID_FILE, 64)


def _write_id(tree: Path, value: str) -> None:
    write_file(tree / ".git" / ID_FILE, value + "\n", 0o600)


def _earlier_checkout() -> tuple[str, str]:
    """(commit, "") if SOURCE_DIR is a checkout an installer before
    RELEASE-8 made, else ("", why not). Reads files; runs git only once the
    cheap signs agree, and then never with the checkout's own config."""
    dot_git = SOURCE_DIR / ".git"
    try:
        head = _head_of(dot_git / "HEAD")
        if head not in EARLIER_PINS:
            return "", f"its HEAD is {head[:60] or 'unreadable'}, not one of the commits Omodachi pinned"
        refs = [str(path.relative_to(dot_git)) for kind in ("heads", "remotes")
                for path in (dot_git / "refs" / kind).rglob("*") if path.is_file()]
        packed = dot_git / "packed-refs"
        if packed.is_file() and not packed.is_symlink():
            refs += [line.split()[-1] for line in packed.read_text().splitlines()
                     if line.split() and line.split()[-1].startswith(("refs/heads/", "refs/remotes/"))]
        if refs:
            return "", f"it has branches ({', '.join(sorted(refs)[:3])}), which the installer never made"
        shallow = dot_git / "shallow"
        shallow_commits = (set(shallow.read_text().split())
                           if shallow.is_file() and not shallow.is_symlink() else set())
        if not shallow_commits or not shallow_commits <= EARLIER_PINS:
            return "", "its history is not the single pinned commit the installer fetches"
    except (OSError, ValueError) as error:
        return "", f"it could not be read ({error})"
    remotes = run(["git", *GIT_SAFE, "config", "--file", str(dot_git / "config"), "--no-includes",
                   "--get-regexp", r"^remote\..*\.url$"], capture_output=True, text=True,
                  env=git_environment())
    urls = [line.split(" ", 1) for line in (remotes.stdout or "").splitlines()]
    if len(urls) != 1 or urls[0][0] != "remote.origin.url" or urls[0][-1] not in EARLIER_ORIGINS:
        return "", "its remote is not " + " or ".join(sorted(EARLIER_ORIGINS))
    same, why = _inspect(SOURCE_DIR, head, untracked=False, clean=False)
    if not same:
        return "", why
    return head, ""


def ownership() -> tuple[str, str]:
    """What SOURCE_DIR is: "absent", "ours" (the record's id is in its .git),
    "earlier" (an install from before RELEASE-8, see _earlier_checkout), or
    "foreign" with the reason. Changes nothing."""
    if not os.path.lexists(SOURCE_DIR):
        return "absent", ""
    if not (_real_dir(SOURCE_DIR) and _real_dir(SOURCE_DIR / ".git")):
        return "foreign", "it is not a git checkout"
    record, found = read_record(), _read_id(SOURCE_DIR)
    if found and (found == record.get("id") or found in record.get("pending", [])):
        return "ours", ""
    commit, why = _earlier_checkout()
    if commit:
        return "earlier", commit
    if not found:
        reason = "there is no record of this installer making it"
    else:
        reason = f"its id does not match the record in {RECORD_PATH}"
    return "foreign", f"{reason}, and {why}"


def describe_source() -> str:
    try:
        if SOURCE_DIR.is_symlink():
            return f"a symbolic link to {os.readlink(SOURCE_DIR)}"
        if SOURCE_DIR.is_file():
            return f"a file ({SOURCE_DIR.stat().st_size} bytes)"
        if not SOURCE_DIR.is_dir():
            return "something that is neither a file nor a directory"
        entries = sum(1 for _ in SOURCE_DIR.iterdir())
        if (SOURCE_DIR / ".git").is_dir():
            head = _head_of(SOURCE_DIR / ".git/HEAD", 80) or "unreadable"
            return f"a git repository (HEAD: {head}; {entries} entries at the top)"
        if (SOURCE_DIR / ".git").exists():
            return "a git work tree whose .git is a file (a worktree or submodule)"
        return f"a directory with {entries} entries, not a git checkout" if entries else "an empty directory"
    except OSError as error:
        return f"something that could not be read ({error})"


def foreign_message(why: str) -> str:
    aside = HOME / "omodachi-src-moved-aside"
    return (f"{SOURCE_DIR} is {describe_source()}. It is not the checkout this installer makes: "
            f"{why}. It was left exactly as it is - nothing in it was run, cleaned, moved or deleted. "
            f"If it is yours, move it out of {SOURCE_DIR.parent}, for example\n"
            f"        mv {shlex.quote(str(SOURCE_DIR))} {shlex.quote(str(aside))}\n"
            f"    and press Install again. Developers: point ${SOURCE_ENV} at a git repository and "
            f"${COMMIT_ENV} at the commit to install.")


def claim_source() -> tuple[str, str]:
    """ownership(), with an earlier install adopted: its checkout gets an id
    and a record, and from then on is ours like any other. Returns
    ("absent" | "ours", "") or ("foreign", the message to show)."""
    kind, detail = ownership()
    if kind == "foreign":
        return kind, foreign_message(detail)
    if kind == "earlier":
        record = read_record()
        identifier = secrets.token_hex(16)
        try:
            write_record({**record, "pending": [*record.get("pending", []), identifier]})
            _write_id(SOURCE_DIR, identifier)
            write_record({**record, "id": identifier, "commit": detail, "url": None, "adopted": True})
        except OSError as error:
            return "foreign", f"could not record {SOURCE_DIR} as this installer's: {error}"
        print(f"{SOURCE_DIR} is the checkout an earlier Omodachi installer made at {detail}; "
              f"recorded it as this installer's ({RECORD_PATH})", flush=True)
        kind = "ours"
    return kind, ""


def _remove_tree(path: Path) -> None:
    if path.is_symlink() or not path.is_dir():
        path.unlink(missing_ok=True)
    else:
        shutil.rmtree(path, ignore_errors=True)


def remove_leftovers() -> None:
    """Remove what a killed run left: only `.src-new-<id>` / `.src-old-<id>`
    directories whose id the record lists as pending."""
    record = read_record()
    if not record:
        return
    current, pending = _read_id(SOURCE_DIR), []
    for identifier in record["pending"]:
        paths = [SOURCE_DIR.parent / f"{prefix}{identifier}" for prefix in (FRESH_PREFIX, OLD_PREFIX)]
        for path in paths:
            if _real_dir(path):
                shutil.rmtree(path, ignore_errors=True)
        if identifier == current or any(os.path.lexists(path) for path in paths):
            pending.append(identifier)
    if pending != record["pending"]:
        write_record({**record, "pending": pending})


def fetch_source(pin: dict) -> tuple[bool, str]:
    """Fetch the pinned commit into a new checkout and put it at SOURCE_DIR.

    Nothing that was in SOURCE_DIR before is used - not its files, not its
    bytecode, not its .git or that .git's config. What was there is replaced
    only if it is ours; it is deleted only if it holds nothing but its
    recorded commit and the build output that commit's .gitignore names, and
    otherwise moved to KEPT_DIR. A failure leaves SOURCE_DIR exactly as it was.
    """
    url, ref, commit = pin["url"], pin["ref"], pinned_commit(pin)
    if not is_full_commit(commit):
        return False, (f"{SOURCE_PIN.name} pins no full 40-character commit for core "
                       f"(got {commit or 'nothing'}); set ${COMMIT_ENV} for a staging source")
    kind, refusal = claim_source()
    if kind == "foreign":
        return False, refusal
    parent = SOURCE_DIR.parent
    identifier = secrets.token_hex(16)
    fresh = parent / f"{FRESH_PREFIX}{identifier}"
    try:
        parent.mkdir(parents=True, exist_ok=True)
        remove_leftovers()
        prior = read_record()
        write_record({**prior, "pending": [*prior.get("pending", []), identifier]})
        fresh.mkdir(mode=0o700)
    except OSError as error:
        return False, f"could not prepare {parent}: {error}"
    try:
        # --template= : no hooks, excludes or config copied in from a template
        # directory; this .git holds only what git itself writes, and our id.
        result = run(["git", "init", "--quiet", "--template=", str(fresh)],
                     capture_output=True, text=True, env=git_environment())
        ok, detail = (result.returncode == 0, _error(result))
        if ok:
            _write_id(fresh, identifier)
            # `origin` for whoever looks at the checkout later; every fetch
            # names the URL itself, so a changed pin never reads a stale remote.
            _git("remote", "add", "origin", url, repo=fresh)
            ok, detail = _fetch_pinned(url, ref, commit, fresh)
        if ok:
            ok, detail = _checkout_pinned(commit, fresh)
        if not ok:
            return False, detail
        return _swap_in(fresh, identifier, commit, url)
    except OSError as error:
        return False, f"could not put the new checkout in place: {error}"
    finally:
        if fresh.exists():
            _remove_tree(fresh)
        record = read_record()
        if identifier in record.get("pending", []) and _read_id(SOURCE_DIR) != identifier:
            try:
                write_record({**record, "pending": [value for value in record["pending"]
                                                    if value != identifier]})
            except OSError:
                pass  # a stale pending id names no directory; the next run drops it


def _swap_in(fresh: Path, identifier: str, commit: str, url: str) -> tuple[bool, str]:
    prior = read_record()
    aside, kept = None, None
    if os.path.lexists(SOURCE_DIR):
        # claim_source() said "ours"; ask again right here, where it counts.
        if ownership()[0] != "ours":
            return False, foreign_message(ownership()[1])
        unchanged, why = _inspect(SOURCE_DIR, prior.get("commit") or "", untracked=True, clean=False)
        if unchanged and _is_id(prior.get("id")) and _read_id(SOURCE_DIR) == prior["id"]:
            aside = SOURCE_DIR.parent / f"{OLD_PREFIX}{prior['id']}"
            write_record({**prior, "pending": [*prior["pending"], prior["id"]]})
        else:
            KEPT_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
            aside = kept = KEPT_DIR / f"src-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{identifier[:8]}"
        try:
            SOURCE_DIR.rename(aside)
        except OSError as error:
            return False, f"could not move the old checkout out of the way ({error}); nothing was changed"
    try:
        fresh.rename(SOURCE_DIR)
    except OSError as error:
        if aside is not None:
            aside.rename(SOURCE_DIR)
        return False, f"could not move the new checkout into place: {error}"
    record = {key: value for key, value in read_record().items() if key != "adopted"}
    write_record({**record, "id": identifier, "commit": commit, "url": url,
                  "pending": [value for value in record.get("pending", []) if value != identifier]})
    if kept is not None:
        print(f"the previous {SOURCE_DIR} held something besides {prior.get('commit') or 'its commit'} "
              f"({why}); it was moved to {kept}, not deleted", flush=True)
    elif aside is not None:
        _remove_tree(aside)
        remove_leftovers()
    return True, ""


def _inspect(tree: Path, commit: str, *, untracked: bool, clean: bool) -> tuple[bool, str]:
    """Whether `tree` is `commit`, compared in a scratch repository.

    The scratch repository has `tree` as its work tree; the tree's own .git
    is only a place the commit's objects are fetched from (by `git
    upload-pack`, which git runs safely in repositories it does not trust,
    and every object arrives checked against its hash). Its config, hooks,
    attributes, excludes and index are never read.

    Always: HEAD is `commit` and no tracked file is modified. `untracked`:
    no file outside the commit, except what the commit's own top-level
    .gitignore names (build output) - judged by that file alone, so neither a
    .gitignore added to the tree nor the user's global excludes can hide
    anything. `clean`: then delete those ignored files (`git clean -fdx`; a
    nested repository is never deleted) and require that nothing at all is
    left besides the commit.
    """
    if not is_full_commit(commit):
        return False, "there is no recorded commit to compare it with"
    with tempfile.TemporaryDirectory(prefix="omodachi-verify-") as scratch:
        repository = Path(scratch) / "git"
        environment = git_environment()
        created = run(["git", "init", "--quiet", "--bare", "--template=", str(repository)],
                      capture_output=True, text=True, env=environment)
        if created.returncode != 0:
            return False, f"could not make a scratch repository to check with: {_error(created)}"

        def git(*arguments):
            return run(["git", *GIT_SAFE, f"--git-dir={repository}", f"--work-tree={tree}",
                        *arguments], capture_output=True, text=True, env=environment)

        def listed(lines):
            shown = "; ".join(line.strip() for line in lines[:5])
            return shown + (f" (and {len(lines) - 5} more)" if len(lines) > 5 else "")

        fetched = git("fetch", "--quiet", "--no-tags", "--depth", "1", str(tree / ".git"), "HEAD")
        got = (git("rev-parse", "--verify", "FETCH_HEAD^{commit}").stdout or "").strip() \
            if fetched.returncode == 0 else ""
        if got != commit:
            return False, f"{tree} is at {got or 'no commit'}, but the pin is {commit}"
        for step in (("update-ref", "--no-deref", "HEAD", commit), ("read-tree", commit)):
            result = git(*step)
            if result.returncode != 0:
                return False, f"could not load {commit} to check against: {_error(result)}"
        tracked = git("status", "--porcelain", "--untracked-files=no")
        lines = (tracked.stdout or "").splitlines()
        if tracked.returncode != 0 or lines:
            return False, f"{tree} has modified files: {listed(lines) or _error(tracked) or 'git failed'}"
        if untracked:
            ignore = Path(scratch) / "pinned-gitignore"
            pinned = git("cat-file", "blob", f"{commit}:.gitignore")
            ignore.write_text(pinned.stdout if pinned.returncode == 0 else "")
            others = git("ls-files", "--others", "-z", f"--exclude-from={ignore}")
            names = [name for name in (others.stdout or "").split("\0") if name]
            if others.returncode != 0 or names:
                return False, (f"{tree} has files that are not part of {commit[:12]}: "
                               f"{listed(names) or _error(others) or 'git failed'}")
        if clean:
            git("clean", "-fdxq")
            state = git("status", "--porcelain", "--ignored=matching", "--untracked-files=all")
            lines = (state.stdout or "").splitlines()
            if state.returncode != 0 or lines:
                return False, (f"{tree} has modified, extra or undeletable files: "
                               f"{listed(lines) or _error(state) or 'git failed'}")
    return True, ""


def verify_checkout(commit: str, *, clean: bool = True) -> tuple[bool, str]:
    """The bytes about to run are the pinned commit's, and nothing else.

    Called immediately before this script executes anything from SOURCE_DIR,
    install and uninstall alike. RELEASE-7: the ignored build output goes
    first (__pycache__, *.pyc, build/ - what the pinned .gitignore names),
    then the work tree must equal the pinned commit's tree exactly, ignored
    files included, so a file that could not be deleted fails the check.
    RELEASE-8: only in a checkout that is ours, and a file the pinned
    .gitignore does not name is never deleted - it fails the check instead.
    """
    commit = (commit or "").strip().lower()
    if not is_full_commit(commit):
        return False, f"no full 40-character commit is pinned (got {commit or 'nothing'})"
    if ownership()[0] != "ours":
        return False, f"{SOURCE_DIR} is not a git checkout this installer made"
    return _inspect(SOURCE_DIR, commit, untracked=True, clean=clean)


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
                        help="with --remove, also delete the device secret, the host "
                             "certificate, every pairing and the rest of the host's state; "
                             "agent-workspace and the files you wrote in ~/.config/omodachi "
                             "(omodachi-menu.jsonc, desktop-runtime.json) are kept")
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
    # RELEASE-8: one Install or --remove at a time, so two runs never move
    # the same checkout or rewrite the record under each other.
    lock = -1
    try:
        LOCK_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        lock = os.open(LOCK_PATH, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if lock >= 0:
            os.close(lock)
        return fail("Another Omodachi Host Install or removal is already running.",
                    f"wait for it to finish ({LOCK_PATH}: {error})")
    try:
        return _locked_main(arguments, extra)
    finally:
        os.close(lock)


def _locked_main(arguments, extra) -> int:
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
        # RELEASE-8: before anything else, and --purge included - a
        # directory that is not ours is not cleaned, run or deleted.
        kind, refusal = claim_source()
        if kind == "foreign":
            return fail("Something that is not this installer's checkout is where Omodachi Host "
                        "installs from, so nothing was removed.", refusal)
        remove_leftovers()
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
            return fail("The Omodachi Host source here is not exactly the pinned commit, "
                        "so its uninstaller was not run.",
                        f"{detail}. Press Install first to bring it to "
                        f"the pinned commit (a checkout holding anything else is moved to "
                        f"{KEPT_DIR}, not deleted) and remove again.")
        code = run_core(installer, ["--remove", *(["--purge"] if arguments.purge else [])])
        if not os.path.lexists(SOURCE_DIR):
            # core's uninstaller took the checkout with it: nothing is ours now.
            record = read_record()
            if record:
                write_record({**record, "id": None, "commit": None, "url": None})
        if code != 0:
            return fail("The uninstaller reported an error.", f"exit {code}")
        status("done", "Omodachi Host removed.")
        return 0

    kind, refusal = claim_source()
    if kind == "foreign":
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
