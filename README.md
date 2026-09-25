# omodachi-plugin

The Omarchy plugin of Omodachi: the bar icon, the panel and one-step device
pairing that a desktop running [Omarchy](https://omarchy.org) draws for itself.

This repository **is** the plugin. `manifest.json` is at its root, which is
what `omarchy plugin add` clones, validates and installs.

<p>
  <img src="https://omodachi.app/img/shots/vm-03-panel-ready.webp" width="400" alt="The Omodachi panel on a fresh Omarchy install, Overview, host connected and ready">
  <img src="https://omodachi.app/img/shots/vm-05-devices-paired.webp" width="400" alt="The Devices page of the panel after one iPad was let in">
</p>

<sub>A fresh Omarchy VM, installed from this repository. More at <a href="https://omodachi.app">omodachi.app</a>.</sub>

## Where this sits

Omodachi turns an iPhone or iPad into an extension of an Omarchy desktop. It
ships as four repositories, plus the site.

| Repository | What it is |
| --- | --- |
| **`omodachi-plugin`** | **this repository: the Omarchy plugin, a thin front end on the desktop** |
| [`omodachi-core`](https://github.com/omodachi/omodachi-core) | the host daemon, where the weight of the system sits |
| [`omodachi-ios`](https://github.com/omodachi/omodachi-ios) | the native iPhone and iPad app |
| [`omodachi-sunshine`](https://github.com/omodachi/omodachi-sunshine) | the Sunshine fork that drives the remote screen |
| the site | **omodachi.app**. Its source is not published |

This plugin is thin. Everything it knows comes from `omodachi-core`;
everything it draws comes from Omarchy's own `qs.Ui` kit. There is no state
here, no configuration file of our own, and no second copy of anything Omarchy
already ships.

`panel` · `service` · `bar-widget`. The bar icon, the Overview / Devices /
Settings panel, one-step pairing, and starting or installing Host.

## Install

```sh
omarchy plugin add https://github.com/omodachi/omodachi-plugin.git --enable
```

Then open the Omodachi panel from the bar and press **Install** to put the host
daemon on the computer.

This is version **0.1.0** of the plugin, and it installs the `v0.1.2` tag of
the host daemon.

**Where the host comes from.** Install fetches
[`omodachi-core`](https://github.com/omodachi/omodachi-core) into
`~/.local/share/omodachi/src` and runs that checkout's own installer in a
visible terminal. Core is pinned by commit, not only by tag: `omodachi.json`
carries the full 40-character commit that `v0.1.2` names, the checkout is that
commit, detached, and any other commit is refused. Every Install fetches into a
new directory, so nothing left in the old checkout is used. Right before it
runs anything from that checkout, Install deletes every ignored and untracked
file in it (bytecode caches included) and checks again that it is exactly the
pinned commit, with no modified, extra or ignored file; `--remove` does the
same before it runs the checkout's uninstaller. Core's installer then runs as
`python3 -I -B` with a new, empty bytecode cache directory, so no interpreter
in the install reads a `.pyc` from beside a source file. If
`~/.local/share/omodachi/src` already holds something that is not that
checkout, Install stops and says so; it never runs it and never deletes it.
The Install button itself runs `python3 -I -B tools/install_host.py`.
**Where Sunshine comes from.** That
installer downloads the prebuilt managed Sunshine fork from the Releases of
[`omodachi-sunshine`](https://github.com/omodachi/omodachi-sunshine) and checks
it against the sha256 pinned in core's `data/versions.json` before unpacking it.

To remove it, take the host daemon back first, then the plugin:

```sh
python3 ~/.config/omarchy/plugins/com.omodachi.host/tools/install_host.py --remove
omarchy plugin remove com.omodachi.host
```

`--remove` keeps this computer's pairings in `~/.config/omodachi`; add
`--purge` to delete those too. Removing only the plugin leaves the host daemon
running.

**External dependencies.**

- Omarchy 4.x with its Quickshell shell
- `jq`
- `python3` and `git`, for the Install button
- [`omodachi-core`](https://github.com/omodachi/omodachi-core), the host
  daemon, which Install fetches
- the managed Sunshine fork package from
  [`omodachi-sunshine`](https://github.com/omodachi/omodachi-sunshine), which
  core's installer fetches

Everything the plugin displays comes from `omodachi-core` over a user-owned
Unix socket; with no host daemon the panel is one sentence and one button.

A plugin runs unsandboxed inside the long-lived `omarchy-shell` process. Read
the source before you enable it.

## Screenshots

None here. The site draws the interface: **omodachi.app**.

## How it works

`Service.qml` runs `omodachi-host plugin-watch` as a shell-owned child and turns
its JSONL frames into QML properties through `OmodachiModel.js`. No credential
ever reaches QML — the helper holds it and the frames arrive authenticated.
Every other call is fixed argv: `devices list`, `devices revoke`, `pair
pending|approve|reject`, `media-pairing pending`, `preferences get|set`,
`panel-summon --view overview`, and `systemctl --user {is-active,start,stop,restart}
omodachid.service`.

**The bar icon has four states**, drawn only with opacity, the theme's
`bar.active` colour and one indicator:

| state | what it means | how it is drawn |
| --- | --- | --- |
| `absent` | no Host answering | `dimmed` → the kit's 0.45 |
| `idle` | still checking | plain bar foreground |
| `linked` | connected | `active` → `Color.bar.active` |
| `remote` | a session is running | `active` + a small square marker |

The marker lives inside our own slot. The design sketch put it in a second bar
slot; that would mean editing the user's `shell.json` layout, which no plugin
should do to itself.

**Left click** opens the local panel — unless `state.remote.state` is `ready`
or `resizing`, in which case the user's hands are on the iPad, so it calls
`panel-summon --view overview` and core recalls the native panel there while
nothing opens here. **Right click** always opens local Settings. The classifier
reads only the fields it acts on: core's `panel.summon` result has grown since
this plugin was written, and a plugin that refuses a shape it has not seen
answers a recall by opening the local panel over the live session — the one
outcome this path exists to prevent.

**Pairing is one confirm.** A request from the iPad appears as a card on
Devices *and* as an ordinary clickable Omarchy notification, which reopens the
panel on that card. One **Approve** issues one command; core grants the
companion credential and, when the media bridge is up, the Sunshine certificate
inside the same call. No PIN to copy, no Sunshine web page, no second approval.
Removing a device is two inline clicks, not a modal.

**Settings holds only what something consumes.** Core's preference store has
exactly three keys, so Settings offers exactly three: dynamic-resolution
permission, quality, host speaker. Remote's backend, placement and takeover bar
edge are arguments of a single `omodachi-host remote start` call rather than
stored defaults, so they are not shown here as if saving them did something.
The two panel preferences, default page and click-while-open, are written to
this widget's own entry in `shell.json` through `bar.shell.updateEntryInline`,
and declared in `barWidget.schema` so the official settings UI can edit them
too.

**With no Host**, the panel is one sentence and one button. Install opens a
terminal and runs `tools/install_host.py`, a small tracked bootstrap inside this
plugin directory that fetches `omodachi-core` and hands over to its installer,
so the argv is fixed and the file is one a reader can open before pressing
anything.

## Layout

| Path | What it is |
| --- | --- |
| `manifest.json`, `*.qml`, `*.js`, `assets/`, `components/`, `tools/` | the plugin itself, the part a host receives |
| `scripts/` | packaging and deployment, which never run on a user's machine |
| `tests/` | the models, the contracts, the manifest invariants |
| `docs/` | what a running host taught us |

`scripts/deploy_plugin.py` and `scripts/package.py` share one list of what
belongs on a host, and `tests/test_manifests.py` fails if a new top-level entry
is in neither that list nor the furniture beside it.

## Working on it

```sh
python3 tests/run_all.py                       # models, contracts, manifests
python3 scripts/package.py                     # build/<plugin-id>.tar.gz + PACKAGE.json
python3 scripts/deploy_plugin.py <host>        # content-addressed, no shell restart
```

To install your own core on a development host, commit it and point the
installer at that repository and commit. It goes through the same fetch and the
same check as a release; there is no way to run a copied tree, so do not rsync
into `~/.local/share/omodachi/src` (Install refuses anything there that is not
its own checkout, and deletes every untracked or ignored file inside its own
checkout before running it):

```sh
OMODACHI_CORE_SOURCE=file:///path/to/omodachi-core \
OMODACHI_CORE_COMMIT=$(git -C /path/to/omodachi-core rev-parse HEAD) \
  python3 tools/install_host.py              # or --source … --commit …
```

On the computer:

```sh
omarchy plugin validate .
omarchy plugin enable com.omodachi.host
OMARCHY_PATH=/usr/share/omarchy omarchy-shell omodachi status
python3 tests/runtime_watch_probe.py           # offscreen Quickshell, synthetic helper
```

`tests/contracts.test.mjs` drives the models straight from
`../omodachi-core/contracts/fixtures/*.json`, so a change to core's wire shape
fails here rather than on the computer. Core's
`tests/test_bridge_model_integration.py` drives the model the other way, from a
real Unix bridge through `tests/model_frame_driver.mjs`.

[`docs/host-runtime-validation.md`](docs/host-runtime-validation.md) is the ten
things a running host taught us: implicit sizing, `bar.shell`, anchor
registration, `FailedToStart`, the component cache, `keepLoaded`, the frame
validation policy, and the rest. Read it before changing anything about
loading, deployment or what the models accept.

**Validation is forward-compatible on purpose.** The models check only the
fields they read, by presence and type, and ignore unknown fields and unknown
enum values rather than rejecting the frame that carried them. Adding a
whitelist here is how this plugin has twice reported `connection: error`
against a healthy host.

## Contributing

Issues and pull requests are welcome. Run `python3 tests/run_all.py` before you
open one, and say which Omarchy and Quickshell versions you ran against.

## Licence

**MIT.** See [LICENSE](LICENSE), and `manifest.json`, which declares the same.
`omodachi-core` is MIT too. The iPhone and iPad app is GPL-3.0, which two
vendored streaming components decide for it, and the managed Sunshine fork
keeps upstream's GPL-3.0-only.

---

Omodachi is an independent project with no tie to Omarchy upstream.
