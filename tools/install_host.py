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
  2. fetch the pinned core commit into ~/.local/share/omodachi/src and check
     it out detached, refusing anything whose sha is not the pinned one;
  3. exec that checkout's own scripts/install_host.py --local, which owns
     every decision about units, the virtualenv, the firewall, the Omarchy
     surfaces and the managed Sunshine fork.

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
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

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


def _git(*arguments):
    return run(["git", "-C", str(SOURCE_DIR), *arguments], capture_output=True, text=True)


def _error(result) -> str:
    return (result.stderr or "").strip()[:300]


def _fetch_pinned(url: str, ref: str, commit: str) -> tuple[bool, str]:
    """Put the pinned commit in FETCH_HEAD, and nothing else.

    By sha first. A server that will not serve a bare sha gets asked for the
    tag instead, and then the tag has to name the pinned commit.
    """
    result = _git("fetch", "--depth", "1", url, commit)
    if result.returncode != 0:
        print(f"this server would not fetch {commit} by sha; fetching {ref} and checking it", flush=True)
        result = _git("fetch", "--depth", "1", "--tags", url, ref)
        if result.returncode != 0:
            return False, _error(result)
    fetched = _git("rev-parse", "FETCH_HEAD^{commit}")
    got = (fetched.stdout or "").strip()
    if fetched.returncode != 0 or got != commit:
        return False, (f"{ref} is {got or 'unknown'}, but omodachi.json pins {commit}; "
                       f"refusing to install a commit nobody pinned")
    return True, ""


def _checkout_pinned(commit: str) -> tuple[bool, str]:
    result = _git("checkout", "--force", "--detach", "FETCH_HEAD")
    if result.returncode != 0:
        return False, _error(result)
    head = (_git("rev-parse", "HEAD").stdout or "").strip()
    if head != commit:
        return False, f"HEAD is {head or 'unknown'}, but omodachi.json pins {commit}"
    return True, ""


def fetch_source(pin: dict) -> tuple[bool, str]:
    """Fetch the pinned commit and check it out detached. The checkout is ours."""
    url, ref, commit = pin["url"], pin["ref"], (pin.get("commit") or "").strip().lower()
    if not is_full_commit(commit):
        return False, (f"{SOURCE_PIN.name} pins no full 40-character commit for core "
                       f"(got {commit or 'nothing'}); set ${COMMIT_ENV} for a staging source")
    if (SOURCE_DIR / ".git").is_dir():
        ok, detail = _fetch_pinned(url, ref, commit)
        if not ok:
            return False, detail
        return _checkout_pinned(commit)
    if SOURCE_DIR.exists() and any(SOURCE_DIR.iterdir()):
        # A developer's rsynced tree, from before this button could fetch one.
        # It is not ours to delete, and it is a perfectly good source.
        if (SOURCE_DIR / "pyproject.toml").is_file():
            print(f"using the sources already at {SOURCE_DIR} (not a git checkout)", flush=True)
            return True, "existing_sources"
        return False, f"{SOURCE_DIR} exists, is not empty and is not an Omodachi checkout"
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    result = run(["git", "init", "--quiet", str(SOURCE_DIR)], capture_output=True, text=True)
    ok, detail = (result.returncode == 0, _error(result))
    if ok:
        # `origin` for whoever looks at the checkout later; every fetch above
        # names the URL itself, so a changed pin never reads a stale remote.
        _git("remote", "add", "origin", url)
        ok, detail = _fetch_pinned(url, ref, commit)
    if ok:
        ok, detail = _checkout_pinned(commit)
    if not ok:
        shutil.rmtree(SOURCE_DIR, ignore_errors=True)
    return ok, detail


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
        command = [sys.executable, str(installer), "--local", "--remove"]
        if arguments.purge:
            command.append("--purge")
        code = run(command).returncode
        if code != 0:
            return fail("The uninstaller reported an error.", f"exit {code}")
        status("done", "Omodachi Host removed.")
        return 0

    pin = source_pin()
    if arguments.source:
        pin["url"] = arguments.source
    if arguments.ref:
        pin["ref"] = arguments.ref
    if arguments.commit:
        pin["commit"] = arguments.commit
    status("fetching", f"Fetching Omodachi Host from {pin['url']} "
                       f"({pin['ref']} = {pin.get('commit') or 'no commit pinned'})…")
    ok, detail = fetch_source(pin)
    if not ok:
        return fail(f"Could not fetch {pin['url']} ({pin['ref']}).", detail
                    or "check this computer's network connection and try again")
    if not installer.is_file():
        return fail("The downloaded source is not omodachi-core.",
                    f"{installer} is missing. Check the source URL in {SOURCE_PIN.name}.")

    status("installing")
    code = run([sys.executable, str(installer), "--local", *extra]).returncode
    if code != 0:
        return fail("The installer reported an error.",
                    f"exit {code}. The lines above say which step failed.")
    status("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
