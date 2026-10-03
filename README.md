# GridfinityPlus

An [Autodesk Fusion](https://www.autodesk.com/products/fusion-360) add-in for generating [Gridfinity](https://gridfinity.xyz/) baseplates and bins. It is a fork of
[FusionGridfinityGenerator](https://github.com/Le0Michine/FusionGridfinityGenerator) by **Lev Mishin**, extended with a
grid-aware workflow: plates you can place anywhere and cut to exact sizes, bins that snap onto them, and everything
editable after the fact.

> [!WARNING]
> **This fork is vibe-coded.** All changes on top of the original add-in were written by an AI assistant (Claude)
> in a conversational "describe it, try it in Fusion, describe what's wrong" loop. Every feature was tried in Fusion,
> but there are no automated tests, the code has not had a thorough human review, and edge cases will exist.
> Use it at your own risk, double-check the geometry before you print, and keep backups of designs that matter.

## What's different from the original

### Baseplates

- **Editable afterwards.** A baseplate is a single custom feature in the timeline. Double-click it to change any
  setting (size, type, magnets, placement, …) and the plate is rebuilt in place.
- **Two ways to size a plate** (`Size by`):
  - **Cells**: columns × rows. Per edge (left / right / front / back) choose *Flush*, *Border* (solid rim, width you
    set) or *Partial cell* (an extra cell cut to the size you set).
  - **Exact size**: total width × depth in mm. Whole cells are placed first; the leftover goes to the edges you
    marked as *Border* or *Partial cell*, split evenly. Great for filling a drawer edge to edge.
  - A side is always either border or partial cell, never both.
- **Placement**: pick a planar face or construction plane and the plate is centred on it. Optionally pick your own
  anchor point (centre or corner), rotate in 90° steps and offset along X / Y / Z of the chosen plane.
- **Fast live preview** that updates while you type.
- **Works in Part Design documents** (single-component designs), including several plates in one part.

### Bins

- **Snap to a baseplate.** Pick the plate, then click a cell in the viewport. Ctrl + click rotates by 90°. Column and
  row can also be typed in.
- **Fill to edge.** Per bin side: *Auto* / *Yes* / *No*. With *Auto*, a bin sitting at the plate edge grows over the
  plate's border or partial cell. Over a partial cell it also gets a matching cut foot, so it seats in the cut pocket.
- **Height in units or in mm** (`Height by`). Units are whole Gridfinity height units (7 mm by default); *Total
  height* takes any height in mm.
- **Editable afterwards** as a custom feature, like plates.
- **Better preview** for hollow (shows compartments / dividers) and shelled bins. Compartment settings only show up for
  hollow bins, where they actually apply.

### Tool cutout (new command, *Modify* panel)

Select a bin and one or more tool bodies (e.g. a screwdriver model). The add-in cuts a cavity you can insert the
tool into **from the top**: it adds a fit tolerance and clears everything above the tool, so no undercut can trap
it. The cutout is stored with the bin and re-applied when you edit the bin.

Known limitation: openings that point downward (e.g. a hollow nozzle tip) can leave a thin pin in the cavity.

### Other

- **Clearer UI**: dialogs regrouped and renamed (Size, Placement, Grid unit, Style, Advanced; Width/Depth instead of
  X/Y). Bin columns/rows are 1-based.
- **Debug log**: the add-in writes `gridfinityplus.log` into its own folder. Handy for bug reports; safe to delete.

## Installation

1. Download this repository (green **Code** button → *Download ZIP*) and unzip it.
2. Make sure the folder is named exactly **`GridfinityPlus`** (rename it if GitHub added `-main` or similar).
   Fusion requires the folder name to match `GridfinityPlus.py`.
3. In Fusion: **Utilities → Add-Ins → Scripts and Add-Ins** (Shift + S) → **+** → *Script or add-in from device* →
   select the `GridfinityPlus` folder.
4. Select **GridfinityPlus** in the list and click **Run**. Tick *Run on Startup* if you like.

The commands appear in **Solid → Create** (*Gridfinity Baseplate*, *Gridfinity Bin*) and
**Solid → Modify** (*Gridfinity Tool Cutout*).

GridfinityPlus uses its own command IDs, so it can be installed side by side with the original Gridfinity
Generator from the Autodesk App Store.

## Typical workflow

1. **Baseplate**: choose *Size by*, set the edges, pick a face to place it on and click OK.
2. **Bin**: choose the plate under *Placement*, click a cell, set size, height and type, then click OK.
3. Need changes? Double-click the plate or bin in the timeline.
4. Optional: model a tool, then run **Gridfinity Tool Cutout** on a bin.

## Compatibility notes

- Plates and bins made with older versions of this fork open as they were. When you edit them, they are converted
  to the new settings. One exception: an old plate with different border widths on opposite sides keeps them as
  long as you use *Size by → Cells*.
- Bins that were placed before a plate was changed don't move by themselves. Open the bin and click OK to re-snap it.
- Placement is not associative. If the face you placed a plate on moves later, the plate stays where it is.

## Credits & license

- Original add-in: **[FusionGridfinityGenerator](https://github.com/Le0Michine/FusionGridfinityGenerator)** by
  **Lev Mishin**. All the core Gridfinity geometry (bins, lips, magnets, screws, compartments, scoops, label tabs)
  comes from there.
- Gridfinity is a modular storage system by [Zack Freedman](https://www.youtube.com/@ZackFreedman).
- This fork's changes were vibe-coded with Claude (Anthropic).

Licensed under **[CC BY-NC-SA 4.0](LICENSE.md)**, the same as the original: attribution required, **no commercial
use**, share-alike. See [LICENSE.md](LICENSE.md).
