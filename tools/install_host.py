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
owner, one repository, one ref and the full 40-character commit that ref names.
RELEASE-9: nothing else, unless this script is started with `--staging`: only
then do $OMODACHI_CORE_SOURCE / $OMODACHI_CORE_REF / $OMODACHI_CORE_COMMIT (or
--source / --ref / --commit) replace the pin - which is how a developer or a
staging host installs its own core, through the same fetch and the same check -
and a banner says, before anything is fetched and again at the end, that what
is being installed is NOT the pinned core. The panel never passes --staging, so
nothing in the session environment can change what its Install button runs.

RELEASE-9: of core's installer options, this script passes on only
--no-sunshine, --no-vnc and --no-firewall, each of which installs less; any
other option is refused. Root steps (--pam) and unverified builds
(--sunshine-build, --sunshine-package) are core's own options, run from core's
checkout by a person who reads its README, never through this entry point.

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
import re  # noqa: E402
import secrets  # noqa: E402
import shlex  # noqa: E402
from pathlib import Path  # noqa: E402
import shutil  # noqa: E402
import stat  # noqa: E402
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


def fail(message: str, detail: str = "", *, code: int = 1) -> int:
    status("failed", message, detail=detail)
    if code == 1:
        print("\nNothing was left half-installed by this step. "
              "Close this window, fix the above and press Install again.", flush=True)
    return code


def source_pin(*, staging: bool = False) -> dict:
    """Where core comes from: the pinned file; with --staging, then the environment."""
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
    if staging:
        value["url"] = os.environ.get(SOURCE_ENV) or value["url"]
        value["ref"] = os.environ.get(REF_ENV) or value["ref"]
        value["commit"] = os.environ.get(COMMIT_ENV) or value["commit"]
    return value


def staging_banner(pin: dict, pinned: dict) -> str:
    rule = "!" * 72
    return (f"{rule}\n!! STAGING: this installs {pin['url']} at {pin.get('commit') or '?'},\n"
            f"!! which is NOT the omodachi-core this plugin pins "
            f"({pinned['url']} at {pinned.get('commit') or '?'}).\n{rule}")


def is_full_commit(value) -> bool:
    return (isinstance(value, str) and len(value) == 40
            and all(character in "0123456789abcdef" for character in value))


def run(argv, **kwargs):
    print("+ " + " ".join(str(part) for part in argv), flush=True)
    return subprocess.run(argv, **kwargs)


# What `--purge` takes when core's installer is already gone - the same rule
# core's own --purge follows (RELEASE-9, core scripts/install_host.py
# PURGE_RULES, which tests/test_install_host.py compares with this copy): in
# ~/.config/omodachi, ~/.cache/omodachi and ~/.local/state/omodachi exactly the
# files and directories Omodachi creates - each by its name or the exact
# pattern of a name it generates (tempfile's random part is eight of
# [a-z0-9_]) - and nothing else. Anything a person put there is kept and
# printed. None is a file (or socket, or link - never followed); a dict is a
# directory of ours, judged the same way inside and removed only if that
# leaves it empty; a string is a directory removed whole only when that marker
# file of ours is in it. In ~/.local/share/omodachi: a venv only when core's
# record shows core made it (VENV_RECORD), the hook directories only when
# empty, src only when it is ours; agent-workspace and everything else stay.
SUNSHINE_BUILD_MARKER = ".git/omodachi-sunshine-build-cache"
_TMP = "[a-z0-9_]{8}"
PURGE_RULES = {
    ".config/omodachi": {
        r"device\.secret": None,
        r"device\.credentials\.json": None,
        r"device\.credentials\.json\.lock": None,
        r"\.device\.credentials\.json\." + _TMP: None,
        r"pairing\.json": None,
        r"pairing\.json\.lock": None,
        r"\.pairing-" + _TMP: None,
        r"host-id": None,
        r"herdr-sessions\.json": None,
        r"herdr-sessions\.json\.lock": None,
        r"\.herdr-sessions" + _TMP: None,
        r"biometric-keys\.json": None,
        r"biometric-keys\.json\.lock": None,
        r"\.biometric-" + _TMP: None,
        r"plugin\.token": None,
        r"plugin\.token\.new": None,
        r"owned-herdr-pane\.json": None,
        r"agent-requests\.json": None,
        r"agent-lifecycle\.lock": None,
        r"\.agent-" + _TMP: None,
        r"sunshine-web-credentials\.json": None,
        r"media-pairing": {r"state\.json": None, r"state\.lock": None,
                           r"\.media-pairing-" + _TMP: None},
        r"preferences": {r"state\.json": None, r"state\.json\.lock": None,
                         r"\.preferences-" + _TMP: None},
        r"tls": {r"server\.pem": None, r"server\.key": None,
                 r"\.server-" + _TMP + r"\.(pem|key)": None},
        r"structured-default": {r"owner\.json": None, r"owner-" + _TMP: None,
                                r"owner-before-empty-recovery-\d+\.json": None,
                                r"delivery\.json": None, r"sequence\.json": None,
                                r"\.agent-" + _TMP: None},
        r"agent-handoff": {r"handoff_[0-9a-f]{32}\.json": None, r"\.agent-" + _TMP: None},
        r"agent": {r"ws-token": None, r"ws-token-" + _TMP: None,
                   r"endpoint\.json": None, r"endpoint-" + _TMP: None},
    },
    ".cache/omodachi": {
        r"install-status\.json": None,
        r"\.install-status\.json\.\d+\.tmp": None,
        r"omodachid\.sock": None,
        r"omodachid\.sock\.omodachi-new": None,
        r"voice": {r"transcript-[0-9a-f]{16}\.txt(\.done)?": None},
        r"sunshine": {r"omodachi-sunshine-[0-9a-f]{7,40}(-dirty)?-x86_64\.tar\.zst": None,
                      r"omodachi-sunshine-x86_64\.tar\.zst": None, r"sunshine\.tar\.zst": None},
        r"sunshine-src": SUNSHINE_BUILD_MARKER,
    },
    ".local/state/omodachi": {
        r"remote": {
            r"OMODACHI-[0-9a-f]{16}\.json": None,
            r"\.remote-session-" + _TMP: None,
            # rfb.sock: RELEASE-9 B3's private RFB listener, left behind only
            # if the daemon died with a VNC session open.
            r"vnc": {r"rs_[0-9a-f]{32}": {r"instance\.json": None, r"control\.sock": None,
                                          r"rfb\.sock": None, r"last-error\.txt": None}},
        },
        r"desktop": {},
        r"core-source\.json": None,
        r"\.core-source\.json\.\d+\.tmp": None,
        r"venv-ids\.json": None,
        r"\.venv-ids\.json\.\d+\.tmp": None,
        r"sunshine-unit\.json": None,
        r"\.sunshine-unit\.json\." + _TMP: None,
    },
}
VENV_RECORD = ".local/state/omodachi/venv-ids.json"
VENV_ID_FILE = "omodachi-venv-id"


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


def purge_directory(directory: Path, rules: dict, kept: list, *, spare=()) -> None:
    """Delete what `rules` names under `directory`; list everything else in `kept`."""
    if not _real_dir(directory):
        if os.path.lexists(directory):
            kept.append(directory)
        return
    for child in sorted(directory.iterdir()):
        rule, known = None, False
        for pattern, value in rules.items():
            if re.fullmatch(pattern, child.name):
                rule, known = value, True
                break
        if not known or child in spare:
            kept.append(child)
        elif rule is None:
            if _real_dir(child):
                kept.append(child)
            else:
                child.unlink(missing_ok=True)
        elif isinstance(rule, str):
            marker = child / rule
            if _real_dir(child) and not marker.is_symlink() and marker.is_file():
                shutil.rmtree(child, ignore_errors=True)
            else:
                kept.append(child)
        elif _real_dir(child):
            purge_directory(child, rule, kept, spare=spare)
            _remove_empty(child)
        else:
            kept.append(child)


def _core_made_venv(path: Path) -> bool:
    """Core's record (RELEASE-9) names the id inside this venv."""
    if not _real_dir(path):
        return False
    found = _head_of(path / VENV_ID_FILE, 64)
    try:
        ids = json.loads((HOME / VENV_RECORD).read_text()).get("ids") or []
    except (OSError, ValueError, AttributeError):
        return False
    return _is_id(found) and found in ids


# RELEASE-9. What shows core's opt-in PAM integration is on this computer (the
# same files core's install_host.pam_present reads; all readable without root).
PAM_FILES = ("/etc/omodachi/pam.conf", "/usr/local/bin/omodachi-pam", "/etc/tmpfiles.d/omodachi.conf",
             "/etc/systemd/system/polkit-agent-helper@.service.d/60-omodachi.conf")
PAM_SERVICES = ("sudo", "polkit-1", "hyprlock", "omarchy-lock-password", "su")


def pam_present() -> list[str]:
    found = [path for path in PAM_FILES if os.path.lexists(path)]
    for service in PAM_SERVICES:
        try:
            text = Path("/etc/pam.d", service).read_text(errors="replace")
        except OSError:
            continue
        if "omodachi-auth" in text or "omodachi-pam" in text:
            found.append(f"/etc/pam.d/{service}")
    return found


# RELEASE-9. The authorized_keys lines Omodachi wrote - `<key> # omodachi:<device>`,
# possibly behind options - and only those, the same rule as core's
# ssh_keys.AuthorizedKeys._owner. Used when core's own uninstaller is gone
# (it removes them itself otherwise), so that no removal of Omodachi leaves a
# paired device able to log in.
SSH_MARKER = "# omodachi:"
SSH_DEVICE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")


def _ssh_owner(line: str) -> str | None:
    index = line.find(SSH_MARKER)
    if index < 0 or line.lstrip().startswith("#"):
        return None
    owner = line[index + len(SSH_MARKER):].strip()
    return owner if SSH_DEVICE.fullmatch(owner) else None


def remove_ssh_lines() -> tuple[list[str], str]:
    """(devices whose lines were removed, error or "")."""
    path = HOME / ".ssh/authorized_keys"
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return [], ""
    except OSError as error:
        return [], f"{path} could not be read safely ({error})"
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            return [], f"{path} is not a regular file of this user"
        raw = handle.read(1048577)
    if len(raw) > 1048576:
        return [], f"{path} is larger than 1 MiB"
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError:
        return [], f"{path} is not UTF-8"
    removed = [owner for owner in map(_ssh_owner, lines) if owner is not None]
    if removed:
        write_file(path, "".join(line + "\n" for line in lines if _ssh_owner(line) is None), 0o600)
    return removed, ""


def purge_only() -> int:
    share = SOURCE_DIR.parent
    kept = []
    for name in ("venv.previous", "venv"):
        path = share / name
        if _core_made_venv(path):
            _delete(path)
        elif os.path.lexists(path):
            kept.append(path)
    for directory in sorted((share / "hooks").glob("*"), reverse=True) + [share / "hooks"]:
        _remove_empty(directory)
    # main() has refused a src that is not ours before it gets here.
    if os.path.lexists(SOURCE_DIR) and ownership()[0] == "ours":
        _delete(SOURCE_DIR)
    # The lock this run holds goes after it is released (main); the record
    # stays while a checkout it names is still there.
    spare = [LOCK_PATH] + ([RECORD_PATH] if os.path.lexists(SOURCE_DIR) else [])
    # The status file lives in ~/.cache/omodachi; it is written first and then
    # purged with the rest, so the last act of a purge does not recreate it.
    status("done", "Removed the files Omodachi Host left behind.")
    for relative, rules in PURGE_RULES.items():
        before = len(kept)
        purge_directory(HOME / relative, rules, kept, spare=spare)
        _remove_empty(HOME / relative)
        kept[before:] = [path for path in kept[before:] if path not in spare]
    kept += [child for child in _children(share) if child != SOURCE_DIR and child not in kept]
    _remove_empty(share)
    if kept:
        print("kept, because they are yours rather than the installer's:\n  "
              + "\n  ".join(str(path) for path in kept), flush=True)
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
# core's scripts/install_host.py exits with this when it could not take back
# something that grants access to this computer.
PARTIAL = 3
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
                       f"(got {commit or 'nothing'}); a staging source needs --staging and ${COMMIT_ENV}")
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


# RELEASE-9: core's installer also reads these two (a Sunshine archive other
# than the pinned one, and its sha256). Like OMODACHI_CORE_*, they reach it
# from this script only with --staging.
SUNSHINE_OVERRIDES = ("OMODACHI_SUNSHINE_PACKAGE", "OMODACHI_SUNSHINE_SHA256")


def core_environment(bytecode: Path, *, staging: bool = False) -> dict:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("PYTHON")
                   and (staging or key not in SUNSHINE_OVERRIDES)}
    environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPYCACHEPREFIX=str(bytecode),
                       PYTHONNOUSERSITE="1")
    return environment


def run_core(installer: Path, arguments, *, staging: bool = False) -> int:
    scratch = Path(tempfile.mkdtemp(prefix="omodachi-core-"))  # 0700
    try:
        bytecode, work = scratch / "bytecode", scratch / "cwd"
        bytecode.mkdir(mode=0o700)
        work.mkdir(mode=0o700)
        return run(core_command(installer, bytecode, arguments),
                   env=core_environment(bytecode, staging=staging),
                   cwd=str(work)).returncode
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


# RELEASE-9. The only core installer options this script passes on: each of
# them installs less. Everything else core's installer takes - the root PAM
# step, a Sunshine archive or build of the caller's choosing - is refused here.
FORWARDED = ("--no-sunshine", "--no-vnc", "--no-firewall")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--remove", action="store_true",
                        help="uninstall Omodachi Host: what core's installer made, including "
                             "the authorized_keys lines Omodachi wrote and, if it was "
                             "installed, the PAM entry (asks for your password)")
    parser.add_argument("--purge", action="store_true",
                        help="with --remove, also delete the device secret, the host "
                             "certificate, every pairing and the rest of the host's state - "
                             "only the files Omodachi creates; anything else in "
                             "~/.config/omodachi, ~/.cache/omodachi and ~/.local/state/omodachi, "
                             "and agent-workspace, is kept and listed")
    parser.add_argument("--staging", action="store_true",
                        help=f"install a core other than the pinned one: honour ${SOURCE_ENV}, "
                             f"${REF_ENV}, ${COMMIT_ENV} and --source/--ref/--commit (same fetch "
                             f"and check, with a NOT-the-pinned-core banner)")
    parser.add_argument("--source", help=f"with --staging: the core repository (or ${SOURCE_ENV})")
    parser.add_argument("--ref", help=f"with --staging: the core ref (or ${REF_ENV})")
    parser.add_argument("--commit", help=f"with --staging: the full core commit (or ${COMMIT_ENV})")
    for flag in FORWARDED:
        parser.add_argument(flag, action="store_true", help=f"passed to core's installer: {flag}")
    # Accepted and ignored: released plugins before INSTALL-1 ran this script
    # with `--local`, and an old panel must not hit an argparse error it cannot
    # show anybody. (Their `--source <url>` is refused since RELEASE-9: it would
    # replace the pinned core, which only --staging may do.)
    parser.add_argument("--local", action="store_true", help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    extra = [flag for flag in FORWARDED if getattr(arguments, flag[2:].replace("-", "_"))]

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
        code = _locked_main(arguments, extra)
    finally:
        os.close(lock)
    if arguments.remove and arguments.purge and code == 0:
        # The lock is this script's own file; a purge takes it last, once it
        # is no longer held, and the directory with it if nothing else is there.
        LOCK_PATH.unlink(missing_ok=True)
        _remove_empty(LOCK_PATH.parent)
    return code


def _locked_main(arguments, extra) -> int:
    status("checking")
    for tool in ("git", "python3"):
        if shutil.which(tool) is None:
            return fail(f"{tool} is not installed on this computer.",
                        f"install it first: sudo pacman -S --needed {tool}")

    pinned = source_pin()
    pin = source_pin(staging=arguments.staging)
    overrides = [name for name in (SOURCE_ENV, REF_ENV, COMMIT_ENV, *SUNSHINE_OVERRIDES)
                 if os.environ.get(name)]
    if not arguments.staging:
        if arguments.source or arguments.ref or arguments.commit:
            return fail("--source, --ref and --commit only go with --staging.",
                        "Without --staging this installs the core omodachi.json pins, and nothing else.")
        if overrides:
            print(f"ignoring ${', $'.join(overrides)}: without --staging this installs the core "
                  f"{SOURCE_PIN.name} pins ({pinned['url']} at {pinned.get('commit')})", flush=True)
    else:
        if arguments.source:
            pin["url"] = arguments.source
        if arguments.ref:
            pin["ref"] = arguments.ref
        if arguments.commit:
            pin["commit"] = arguments.commit
        print(staging_banner(pin, pinned), flush=True)

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
            # Core's uninstaller is gone (a --remove before this one took it).
            # An older one did not take back the SSH lines, so they go here -
            # and did not take back the PAM entry either, which needs core's
            # root step: then the removal is partial, and says how to finish.
            pam = pam_present()
            if pam:
                return fail("Omodachi Host was only partly removed: its device-approval PAM entry "
                            "is still installed (" + ", ".join(pam) + ").",
                            "Press Install (it fetches the pinned core again), then run this "
                            "script with --remove in a terminal: it takes the PAM entry back, "
                            "asking for your password.", code=PARTIAL)
            devices, error = remove_ssh_lines()
            if error:
                return fail("Omodachi Host was only partly removed.",
                            f"{error}; delete every line ending in '# omodachi:<device>' from it "
                            f"yourself.", code=PARTIAL)
            if devices:
                print(f"removed {len(devices)} Omodachi line(s) from "
                      f"{HOME / '.ssh/authorized_keys'} ({', '.join(devices)})", flush=True)
            if arguments.purge:
                # `--remove` deletes the sources, so a user who decides
                # afterwards that they also want their pairings gone has no
                # installer left to ask; this is the same purge core does.
                return purge_only()
            if devices:
                status("done", "Removed the SSH access Omodachi Host had left behind.")
                return 0
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
        code = run_core(installer, ["--remove", *(["--purge"] if arguments.purge else [])],
                        staging=arguments.staging)
        if not os.path.lexists(SOURCE_DIR):
            # core's uninstaller took the checkout with it: nothing is ours now.
            record = read_record()
            if record:
                write_record({**record, "id": None, "commit": None, "url": None})
        if code == PARTIAL:
            # RELEASE-9: something that grants access (the PAM entry, an
            # authorized_keys line) is still there; core printed what and how.
            return fail("Omodachi Host was only partly removed.",
                        "The lines above say what is still installed and the command that "
                        "removes it.", code=PARTIAL)
        if code != 0:
            return fail("The uninstaller reported an error.", f"exit {code}")
        status("done", "Omodachi Host removed.")
        if arguments.purge:
            # Nothing of ours is left behind by a purge, this status file included.
            STATUS_PATH.unlink(missing_ok=True)
            _remove_empty(STATUS_PATH.parent)
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
    code = run_core(installer, extra, staging=arguments.staging)
    if code == PARTIAL:
        # RELEASE-9: core installed, but something it found needs a root step
        # (an outdated PAM helper); core printed what and the command.
        return fail("Omodachi Host was only partly installed.",
                    "The lines above say what is left to do and the command for it.", code=PARTIAL)
    if code != 0:
        return fail("The installer reported an error.",
                    f"exit {code}. The lines above say which step failed.")
    if arguments.staging:
        print(staging_banner(pin, pinned), flush=True)
    status("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
