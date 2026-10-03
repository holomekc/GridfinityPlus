---
name: fusion-addin-debugging
description: Triage checklist for GridfinityPlus bugs reported from Fusion 360 ("edit does nothing", "can only place one bin", "dialog dead", "body vanished"). Use before changing code for any bug the user reports from Fusion, and when adding or changing command dialogs, custom features or event handlers.
---

# Debugging GridfinityPlus in Fusion

Claude cannot run Fusion. Evidence comes from `gridfinityplus.log` in the add-in folder (read it
yourself, do not ask the user to send it) and from what the user describes. Read the log BEFORE
changing code; most "regressions" on 2026-10-03 were not caused by the code.

## 1. Rule out the environment first

1. **Which add-in made the object?** The original App Store *GridfinityGenerator* is installed
   (`%APPDATA%\Autodesk\ApplicationPlugins\GridfinityGenerator.bundle`) and auto-starts. Its buttons
   ("Gridfinity bin", "Gridfinity baseplate") look like ours. Its objects are plain bodies: no
   custom feature, no edit, no grid snapping (every bin at the origin). Text Commands output with a
   lowercase "Gridfinity bin Command …" is the store add-in. Ours are named "Gridfinity+ …" and log
   `SESSION:` lines to `gridfinityplus.log`.
2. **Design intent.** Every `SESSION:` logs `document: "<name>" type=… intent=Part|Assembly|Hybrid`.
   In **Part** designs Fusion offers no "Edit Feature" and no timeline double-click for add-in
   custom features; the add-in is never called, so the log shows nothing. Workaround: right-click
   "Edit Gridfinity+ …" (`commands/contextEdit.py`) or select the feature + click its create button.
3. **Nothing in the log at all** for an action = Fusion never called the add-in (wrong button,
   Part design, dialog never opened). Do not "fix" code for that.

## 2. Known code pitfalls (all bit us)

- **Stale dialog inputs.** `CommandUiState` keeps `commandInputs` across dialogs. Writing to an input
  of a closed dialog throws inside `command_created`, which then aborts BEFORE the event handlers
  are attached: dialog opens but preview/clicks/OK are dead, only the first dialog per add-in load
  works. Call `state.forgetInputs()` at the start of `command_created` (bin + baseplate do).
- **Handler exceptions are silent.** `futil` handlers swallow errors into the Text Commands window;
  `event_utils` now also writes them to `gridfinityplus.log` (`event handler "…"`). Look there first.
- **`InputChangedEventArgs.inputs`** only holds the changed input's group. Use
  `args.firingEvent.sender.commandInputs` (same for validateInputs).
- **`IntegerSpinnerCommandInput.maximumValue`** cannot be set after creation; clamp values instead.
- **`entityToken`** strings of the same entity can differ; compare resolved entities
  (`des.findEntityByToken(token)` → `==`), see `boxSystemFeature.refersTo`.
- **Deleted features** stay reachable through their attributes (undo history) and can look valid.
  `gridRegistry.findBaseplates` only accepts features still listed in their component's
  `features.customFeatures`, not rolled back, not suppressed.
- **Custom feature compute:** `baseFeat.bodies.count` reads 0 inside compute even when it worked —
  check the `BODIES [...after]` dump instead. Body swaps only inside compute (pending + `rev` bump).
  `rev` bump "Bad index parameter" is old and harmless (auto recompute takes over).
- **Selected feature + create button = edit mode** (bin, cabinet, drawer). Users read that as
  "new bin moved the old one". Edit mode shows "Update …" on the OK button.
- **Global edit hacks are risky.** Purging command definitions at start or intercepting
  `ui.commandStarting` did not help and was reverted; keep startup identical to upstream.

## 3. Working method

- Compare with a known-good state: `git diff <good-commit> -- <path>` or `git stash` + retest; for a
  copy outside git use `diff -rq --strip-trailing-cr` (line endings may differ).
- Reproduce dialog logic with the mock (`../gridfinity-geometry-tests`): e.g. build a dialog twice
  in a row to catch state bugs.
- Shell: heredocs in the Bash tool turn `\n` inside Python strings into real newlines. For code with
  `\n` in string literals use the Edit/Write tools, or `chr(92) + 'n'`.
- Tell the user plainly what is verified (mock / log) and what is not tested in Fusion yet.
