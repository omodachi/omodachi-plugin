# Ten things a running Omarchy host taught us

Every one of these cost a failed deployment to find. They are not opinions
about the plugin API; they are how the installed shell on the Omarchy host
actually behaves, and each is load-bearing in the current code. Keep them.

Verified against Omarchy 4.0.0.alpha, Quickshell 0.3.1, on `alex@omarchy`.

---

**1. A bar slot is laid out by implicit size, and only implicit size.**
`shell/plugins/bar/Bar.qml` reads each item's `implicitWidth`/`implicitHeight`.
A widget root with `width: 24; height: 24` still has implicit size zero, so the
slot is present, `itemVisible: true`, and **0×0 pixels wide** — an invisible
plugin that every diagnostic calls healthy. `BarWidget.qml` must export the
official button's implicit dimensions:

```qml
implicitWidth: button.implicitWidth
implicitHeight: button.implicitHeight
```

**2. The bar injects `bar`, `moduleName` and `settings` — never `shell`.**
The scoped facade is reached as `bar.shell`. `shell.serviceFor(id)` returns
only *this* plugin's own service (`shell.qml:600–602`); anything else needs
`pluginRegistry.resolveEnabledId(...)` first. A direct `shell` property on a
bar widget is never populated and silently stays null.

**3. The panel Loader gets a service and a shell, but no live bar anchor.**
`shell.qml:1339–1349` instantiates the panel independently of the bar. So each
bar widget registers its own live `Item` and scoped bar *on the service*, and
`Panel.qml` follows that reference. There is no visual-parent walk and no
reaching into another plugin's service.

**4. `FailedToStart` emits no `exited` signal.**
A `Process` whose executable does not exist — the whole first-install case —
never reaches `onExited`, so an exit-driven retry never fires and the plugin
sits dead forever. The retry `Timer` must be `running` whenever the process is
stopped, for any reason, not only after an exit.

**5. The component cache serves stale QML after `rescanPlugins`.**
Writing new bytes to the same path is not enough; the running shell keeps the
old component. Deployment therefore writes a content-addressed
`releases/<hash>/` directory and points the manifest's `entryPoints` at it, so
the shell has to load a URL it has never seen. This is why
`scripts/deploy_plugin.py` looks the way it does.

**6. `keepLoaded: true` pins the previous singleton across a rescan.**
A kept service is not replaced by a reload, so a new build mounts beside the
old one. Deploy writes `keepLoaded: false`, rescans **twice** (the first scan
reads the flag, the second releases the instance), then restores `true`. No
whole-shell restart, and no `omarchy-restart-shell`.

**7. `listPlugins.active` is not widget evidence.**
The host sets `active` for `kind: "bar"` alternatives. For an ordinary
bar-widget it says nothing. The evidence is `shell debugBarGeometry` reporting
a non-zero `width`/`height`, and the loaded item.

**8. Saving any file under `~/.config/omarchy/plugins/` hot-reloads plugins.**
The host watches the tree, so writing into a plugin directory while its panel
is open destroys and rebuilds it — a panel closes mid-inspection and a
screenshot catches an empty frame. Finish deploying before looking at pixels.

**9. A third-party plugin may register its own IPC target.**
Third-party QML is loaded by `Qt.createComponent` into the same Quickshell
process (`shell.qml:914,1336,1395`), so `IpcHandler { target: "omodachi" }`
works and gives `omarchy-shell omodachi status`. Two already-installed
third-party plugins on this host do the same. It is undocumented, so treat it
as diagnostics, not as a contract — and never return credential material
through it.

---

## 10. Frame validation is forward-compatible, by policy

**Every frame is checked only for the fields the plugin actually reads, by
presence and type; unknown fields and unknown enum values are ignored, carried
through and drawn with a neutral fallback (an unrecognised bar role is a
generic module, an unrecognised remote state is simply not live, an
unrecognised error code reads as "cannot reach the host service"), and nothing
unrecognised ever rejects a whole frame.** What is still rejected is genuine
malformation — a non-object `state`, a missing or non-numeric
`revision`/`event_cursor`, an absent `instance_id`, a state field that must be
an object and is not — because those are frames the panel could not draw
anyway.

This is not a preference. Core added `bar.modules`, the `agent_usage`, `panel`,
`network`, `audio` and `power` bar roles and the `panel.summon` `view` field
after these models were written, and each time a closed whitelist met one of
them the plugin went to `connection: error` while the host was perfectly
healthy — twice in a single day. The models are the enforcement point
(`OmodachiModel.js`, `MediaPairingModel.js`, `PreferencesModel.js`); the
constant lists that remain (`BAR_ROLES`, `REMOTE_STATES`, `STATUSES`,
`ERROR_CODES`, `RUNTIME_FLAGS`) are the vocabulary this build has drawing for,
never a filter. The one place a closed list is still correct is *outbound*
argv: `panel-summon --view` is pinned to core's `PANEL_VIEWS` because argparse
`choices` exits 2 on anything else.

---

## Reproducing a view without claiming a click

```sh
ssh omarchy 'OMARCHY_PATH=/usr/share/omarchy omarchy-shell omodachi status'
ssh omarchy 'OMARCHY_PATH=/usr/share/omarchy omarchy-shell shell summon com.omodachi.host "{\"view\":\"devices\"}"'
ssh omarchy 'OMARCHY_PATH=/usr/share/omarchy omarchy-shell shell debugBarGeometry'
```

An IPC summon is **not** a bar click. `widgetActivations` in `omodachi status`
counts real presses on the widget and nothing else; it is the only evidence
that the icon itself works.
