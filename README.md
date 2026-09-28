# omodachi-plugin

**Use your iPhone or iPad with your Omarchy desktop:** an extra screen, or the
whole desktop to drive by touch; the Omarchy menu and keybindings; your coding
agent and herdr; an SSH terminal; your desktop notifications. This repository
is the Omarchy plugin that sets it up on the computer.

<p align="center">
  <img src="https://omodachi.app/img/shots/listing-preview.webp" width="800" alt="An Omarchy desktop with the Omodachi panel open, an iPad in landscape that has taken over the same desktop, and an iPhone showing the Omarchy menu">
</p>

[omodachi.app](https://omodachi.app) ·
[Omarchy marketplace listing](https://plugins.omarchy.org/plugin.html?id=com.omodachi.host) ·
iPhone and iPad app: in App Store review; build it yourself from
[omodachi-ios](https://github.com/omodachi/omodachi-ios) ·
[omodachi-core](https://github.com/omodachi/omodachi-core) (the host daemon) ·
[omodachi-sunshine](https://github.com/omodachi/omodachi-sunshine) (the streaming server) ·
[Security model](#security-model) ·
[Report a vulnerability](SECURITY.md)

## Install

1. Add the plugin and enable it:

   ```sh
   omarchy plugin add https://github.com/omodachi/omodachi-plugin.git --enable
   ```

2. Click the Omodachi icon in the bar and press **Install…**. A terminal opens
   and runs the installer, so every step is on screen. It asks for your
   password only for `sudo`: to add firewall rules when ufw is installed, and
   to install any of Sunshine's libraries or `wayvnc` that are missing, with
   pacman. The panel says **Ready** when it is done.
3. Open the Omodachi app on your iPhone or iPad, on the same network. Pick this
   computer from the list, or add it by name or address, then press
   **Approve** on the card that appears on the panel's **Devices** page and as
   an Omarchy notification.

**Requirements.** Omarchy 4 with its Quickshell shell (tested on the `omarchy`
4.0.4 package), `python3` 3.11 or newer, `git` and `jq`; `sshd` running if you
want the terminal, which Omodachi does not turn on. An iPhone or iPad on iOS 17
or later. Remote streams through Sunshine when the computer has a working
VA-API video encoder, and through WayVNC otherwise.

**Updating.** Run `omarchy plugin update com.omodachi.host`, then
`omarchy-restart-shell`: the running shell keeps the plugin version it loaded
until it restarts.

This is version **0.2.0** of the plugin, and it installs the `v0.1.5` tag of
the host daemon, at the full commit `omodachi.json` pins. What Install changes,
and how to take it all back, is under [Security model](#security-model) and
[Remove](#remove).

## What you get

### Remote: Extra screen or Take over

<p>
  <img src="https://omodachi.app/img/shots/vm-08-takeover-ipad.webp" width="560" alt="An iPad in landscape that has taken over an Omarchy desktop: a terminal with fastfetch and btop, the Omodachi mark on the Omarchy logo at the top left">
  <img src="https://omodachi.app/img/shots/vm-11-remote-iphone.webp" width="200" alt="An iPhone showing an extra Omarchy screen whose bar starts and ends clear of the phone's rounded corners">
</p>

**Extra screen** adds a new display to the desktop, beside the computer's own,
and windows drag across. **Take over** moves every workspace to the device and
turns the computer's own screen off until you end the session; everything is
put back then. You can also lock the computer's keyboard and mouse for the
session. It works on an iPhone as well as an iPad.

Over Sunshine, touch drives the desktop: direct touch or a touchpad mode,
two-finger scroll, a three-finger tap for the keyboard, and three-finger
swipes that run the computer's own workspace keybindings. The picture is H.264,
or HEVC when the computer's encoder and the device's hardware decoder both do
it. When Sunshine cannot stream, for example on a computer without a VA-API
encoder, Remote uses WayVNC instead, with a one-finger pointer and the
keyboard.

While a session runs, the Omarchy bar on the device's screen moves its two ends
in, clear of the device's rounded corners, and the Omodachi mark drawn over the
Omarchy logo brings the app's panel down over the picture.

### The Omarchy menu and keybindings

<img src="https://omodachi.app/img/shots/vm-09-takeover-panel-ipad.webp" width="560" alt="The app's panel over a Take over on an iPad: the computer's Omarchy menu on the left, its keybindings on the right">

The app shows this computer's own Omarchy menu, with your additions from
`~/.config/omarchy/extensions/omarchy-menu.jsonc`, its submenus, a search and
the rows you pin, and the keybindings Omarchy defines, searchable. Tapping a row
runs it on the computer. Rows that power off, remove, update or need root ask
for a second tap before they run.

### Your coding agent and herdr

<img src="https://omodachi.app/img/shots/vm-13-herdr-ipad.webp" width="560" alt="The app's herdr panel on an iPad: the session's workspace and its three panes on the left, the selected pane on the right">

The Agent panel talks to the coding agent that `omarchy-default-agent` names,
running in the host's own herdr session: start it, send it a prompt, open its
terminal. With Codex it is also a chat: the transcript, steer or interrupt,
model and effort, slash commands, and Accept or Decline for what it asks to run.
The herdr panel shows your herdr sessions, workspaces and panes. Watch any pane
live, take control of one to type into it, split, zoom or close panes, and
switch sessions.

### SSH terminal

<img src="https://omodachi.app/img/shots/vm-14-ssh-ipad.webp" width="560" alt="The app's SSH terminal on an iPad, running fastfetch on the computer">

A terminal on the computer, with Esc, Ctrl, Alt, Tab and the arrows above the
keyboard. The app makes its own Ed25519 key on the device and sends the public
half with the pairing request. Approve adds it to `~/.ssh/authorized_keys` as
one line limited to a terminal, which expires with the device's credential and
goes when you remove the device.

### Notifications

<img src="https://omodachi.app/img/shots/vm-15-notifications-iphone.webp" width="220" alt="The app's notifications on an iPhone: three desktop notifications and two earlier pairing requests">

What the Omarchy shell shows as a notification appears in the app while it is
connected: in a list you can dismiss or clear, and as a toast inside the app.
Do Not Disturb is one switch. There is no push service, so nothing arrives
while the app is closed.

### Pairing, and what a device may do

<img src="https://omodachi.app/img/shots/vm-04-devices-request.webp" width="560" alt="The Devices page of the panel: a pairing request that lists everything Approve grants, above a paired iPad and its expiry date">

The app finds the computer on the local network, or you add it by name or
address. The request shows up on the panel's Devices page and as an Omarchy
notification, with the device's name, where it connects from and its SSH key
fingerprint, and it says what Approve grants: the screen, keyboard and mouse;
an SSH login; the agent; herdr sessions; and every menu action, including power
and remove. One Approve grants all of it, the Remote (Sunshine) certificate
included, with no PIN and no Sunshine page. A device's credential lasts 30 days
and the app renews it in its last week. **Remove** on the Devices page takes
back the credential, the Sunshine certificate and the SSH line together.
Pairing can also require an invitation:
`omodachi-host preferences set --revision <n> --pairing-mode invite`, where
`<n>` is the `revision` that `omodachi-host preferences get` prints.

## Security model

### Who can do what

- **A paired device** can do what its pairing card listed, and that is a
  lot: with the SSH login and every menu row it reaches about as far as you
  do at the keyboard, as your user. It cannot answer a password prompt unless
  you opt in (next point). **Remove** revokes all of it in one step.
- **Password prompts** stay yours unless you opt in: only if core's installer
  is run with `--pam` can a paired device approve a `sudo` or polkit prompt,
  and then only with a device key kept in a root-owned store and checked by a
  root helper. Typing the password keeps working. The plugin offers the switch
  only where that helper is installed and current.
- **SSH** lines Omodachi writes are `restrict,pty` (no forwarding of any kind)
  with an `expiry-time`, and marked `# omodachi:<device>`; your own lines are
  copied through untouched. A device without the SSH grant can only ask: its
  key waits for a new Approve on the computer.
- **The remote screen over VNC** is a WayVNC that listens only on a Unix socket
  in a directory only you can open, reached through the host's authenticated
  TLS connection; no VNC port is open.
- **Rows that change the computer** (power, remove, update, anything run with
  root) are refused on the first request and run only on a second one for the
  same row from the same device within 30 seconds, and the app asks you to tap
  twice.

### What Install does

**Where the host comes from.** Install fetches
[`omodachi-core`](https://github.com/omodachi/omodachi-core) into
`~/.local/share/omodachi/src` and runs that checkout's own installer in a
visible terminal. Core is pinned by commit, not only by tag: `omodachi.json`
carries the full 40-character commit that `v0.1.5` names, the checkout is that
commit, detached, and any other commit is refused. Every Install fetches into a
new directory, so nothing left in the old checkout is used. Right before it
runs anything from that checkout, Install deletes the build output core's
`.gitignore` names (bytecode caches included) and checks again that it is
exactly the pinned commit, with no modified, extra or ignored file; `--remove`
does the same before it runs the checkout's uninstaller. Core's installer then
runs as `python3 -I -B` with a new, empty bytecode cache directory, so no
interpreter in the install reads a `.pyc` from beside a source file.
The Install button itself runs `python3 -I -B tools/install_host.py`.

**What Install will and will not touch.** It only ever replaces, cleans or
deletes a `~/.local/share/omodachi/src` it made itself, which it knows by a
random id written into that checkout's `.git` and into
`~/.local/state/omodachi/core-source.json`. Anything else at that path - your
own repository, a clone of `omodachi-core`, a file, a link - is left exactly
as it is: Install and `--remove` stop, say what they found, and tell you to
move it aside. A checkout made by an earlier version of the plugin is
recognised as one only if it is still exactly what that version made. If
Install's own checkout holds a file that is not part of its commit or a
changed file, it is moved to `~/.local/share/omodachi-kept/` rather than
deleted.
**Where Sunshine comes from.** That
installer downloads the prebuilt managed Sunshine fork from the Releases of
[`omodachi-sunshine`](https://github.com/omodachi/omodachi-sunshine) and checks
it against the sha256 pinned in core's `data/versions.json` before unpacking it.
It does not take over a Sunshine that something else set up on this computer:
then Remote uses WayVNC and that Sunshine is left as it is.

**Nothing else steers it.** The panel runs the bootstrap with no options. The
bootstrap passes core's installer at most `--no-sunshine`, `--no-vnc` or
`--no-firewall` (each installs less) and refuses every other option. The
`OMODACHI_CORE_*` and `OMODACHI_SUNSHINE_*` variables and
`--source`/`--ref`/`--commit` are honoured only with an explicit `--staging`, which prints that what it installs is not the
pinned core (see Working on it).

**What Install changes on this computer.**

| Where | What |
| --- | --- |
| `~/.local/share/omodachi/` | `src/` (the checked core checkout), `venv/` built from it with hash-locked dependencies, `sunshine/<commit>/` (the managed Sunshine fork), `hooks/`, `agent-workspace/` (the agent's working directory) |
| `~/.config/omodachi/` | the device secret, a self-signed certificate (`tls/`), the panel's own device credential `plugin.token` (0600), and a random login for Sunshine's web page that nobody knows (`sunshine-web-credentials.json`, 0600, never printed); the daemon keeps pairings and settings here |
| `~/.config/systemd/user/` | `omodachid.service`, `omodachi-herdr.service` and the managed Sunshine's `app-dev.lizardbyte.app.Sunshine.service`, enabled and started |
| `~/.local/bin/`, `~/.local/share/applications/` | the `omodachid`, `omodachi-host` and `omodachi-panel` commands and a desktop entry with its icon |
| `~/.config/omarchy/` | the theme template `themed/omodachi-theme.json.tpl` and the `theme-set`/`font-set` hooks, installed with `omarchy hook install`; the current theme is re-applied headless so Omarchy renders the template |
| `~/.config/sunshine/apps.json` | one app entry, only for a Sunshine it manages (the original kept as `apps.json.omodachi-bak`) |
| ufw, with `sudo` | allow rules for `8099/tcp` and the Sunshine ports from `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` and `tailscale0`; the installer then says whether ufw is active and actually filtering, or that those ports are reachable from every network |
| pacman | Sunshine's runtime libraries and `wayvnc`, only those missing |
| `~/.local/state/omodachi/`, `~/.cache/omodachi/` | the installers' records of what they made, Remote's session journals, the downloaded archive, this Install's status |

Sunshine's web admin page (port 47990) answers this computer only and has that
random login from the start, so no one can claim it by setting the first
password. Once running, the daemon also writes one line per device you grant
SSH to `~/.ssh/authorized_keys` (marked `# omodachi:<device>`, limited to a
terminal with `restrict,pty` and expiring with the device's credential), points Voxtype at
its own audio source while a device dictates and puts the original back after,
and moves the Omarchy bar during a Remote session and back after it. Only if you
run core's own installer with `--pam` does anything go into `/etc` (the opt-in
device approval for password prompts, with a root-owned store of the device keys
it accepts; see core's README).

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

## Remove

Take the host daemon back first, then the plugin:

```sh
python3 -I -B ~/.config/omarchy/plugins/com.omodachi.host/tools/install_host.py --remove
omarchy plugin remove com.omodachi.host
```

`--remove` takes back what Install made: the units, commands, desktop entry,
venv, the managed Sunshine (disabling its unit only if Install enabled it, and
deleting the clients it paired only if `~/.config/sunshine` was created for it),
the `apps.json` entry, the Omarchy template and hooks, the ufw rules, every
`authorized_keys` line marked as Omodachi's, and, if `--pam` was used, the PAM
entry (it asks for your password in the terminal). If something that grants
access cannot be removed it says the host was only partly removed and what to
run, and exits 3. It keeps this computer's pairings in `~/.config/omodachi`;
add `--purge` to delete those too, with the rest of the host's state - only the
files Omodachi creates. Neither ever deletes your own files: anything you put
in `~/.config/omodachi`, `~/.cache/omodachi` or `~/.local/state/omodachi`
(such as `omodachi-menu.jsonc` or `desktop-runtime.json`),
`~/.local/share/omodachi/agent-workspace` and anything else under
`~/.local/share/omodachi` are kept, and the uninstaller prints where they are.
A venv or Sunshine install it cannot show it made is kept too, and so is a
checkout it made - `src`, or core's Sunshine build cache
`~/.cache/omodachi/sunshine-src` - that holds anything besides the commit it
was made for (a changed file, a file of yours, a commit of yours). Removing only
the plugin leaves the host daemon running.

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

**Settings holds only what something consumes.** Settings shows the host
preferences a person decides here: under Remote, dynamic-resolution permission,
default quality and host speaker; under Security, whether a paired device may
approve password prompts (it does nothing unless core's `--pam` step was run);
under Clipboard, whether and which way the clipboard is shared. Core's store
also keeps a few values the devices set (the voice uplink, the Remote backend,
the pairing mode), which are not repeated here. Remote's placement and takeover
bar edge are arguments of a single `omodachi-host remote start` call rather
than stored defaults, so they are not shown here as if saving them did something.
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
installer at that repository and commit, with `--staging`. It goes through the
same fetch and the same check as a release; there is no way to run a copied
tree, so do not rsync into `~/.local/share/omodachi/src` (Install refuses
anything there that is not its own checkout, deletes the build output inside
its own checkout before running it, and refuses a file there that is not build
output). Without `--staging` these variables are ignored, and the panel never
passes it:

```sh
OMODACHI_CORE_SOURCE=file:///path/to/omodachi-core \
OMODACHI_CORE_COMMIT=$(git -C /path/to/omodachi-core rev-parse HEAD) \
  python3 -I -B tools/install_host.py --staging   # or --staging --source … --commit …
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
