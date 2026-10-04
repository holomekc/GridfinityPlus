---
name: gridfinity-geometry-tests
description: Test GridfinityPlus geometry and dialog code without Fusion, using a mock adsk with a CSG point-membership kernel. Use after changing cabinet/drawer/handle/baseplate-split geometry (cabinetGeometry, cabinetLayout, plateSplit), when a Fusion API error must be reproduced, or to check that a dialog's command_created survives being opened several times.
---

# Geometry & dialog tests without Fusion

Fusion cannot run here. `scripts/mockadsk.py` installs a fake `adsk` package:

- `TemporaryBRepManager` builds **implicit solids**: box (oriented), cylinder/cone, torus,
  union/difference/intersection, transform. `body.contains([x, y, z])` answers point membership.
- Boxes assert positive size, like Fusion's "3 : invalid argument box".
- Unknown `adsk` names resolve to permissive dummies, so modules import.
- `quietLog(root)` redirects `gplog` to a temp file (keeps the real `gridfinityplus.log` clean).

Parametric pieces (Gridfinity foot, baseplate cell cutout) are replaced by simple boxes in the tests
(`fakeFoot`, `fakeCell`), so only our own TBM geometry is checked exactly.

## Scripts (run from `scripts/`, plain `python`)

| Script | Checks | Runtime |
|---|---|---|
| `t_import.py` | all command modules import | 1 s |
| `t_feet.py` | feet never stick out past the walls (real-size fake foot: cell + clearance), partial cells reach the outline | 3 s |
| `t_backcorner.py` | ledges / grooves never poke through the rounded outer back corner, wall keeps its thickness there, drawer clears the rounded interior corner | 20 s |
| `t_cover.py` | grid cover: slab, feet, fill to edge (border / partial cell) | 1 s |
| `t_spool.py` | spool drawer: cradles, open U slot, eyelets, outlets, separate axle that never touches the drawer, size errors | 5 s |
| `t_spool2.py` | spool slot width (width + 2 x play), divider / end thickness, snap-in lips, outlet heights + offset; label positions with / without handle, offsets clamped | 10 s |
| `t_bayonet.py` | two-half axle: halves never touch inserted or turned, locked after a quarter turn, free before it, chamfered lugs | 60 s |
| `t_spoolcheck.py` | spool fit check (collision of each spool with the finished drawer, sampled), spool preview body + names | 20 s |
| `t_mount.py` | cabinet wall mount: every screw size and head type, head flush inside, back wall thickness, holes off dividers | 5 s |
| `t_split.py` | baseplate split plan, one body per tile, dovetail gap equal along the flank | 2 s |
| `t_platecorner.py` | baseplate outline: corners next to a partial cell stay square, clean ends rounded (final cut + preview) | 2 s |
| `t_stackpick.py` | click picking: front-most baseplate / cabinet top under the cursor wins (stacking), outside every outline -> None | 1 s |
| `test_geom.py` | cabinet/insert probes (walls, ledges, grooves, detent, handles, knobs, labels, wire holes, overhang, top grid) + collision scan cabinet vs. insert, closed and pulled out | ~2-3 min |
| `t_dialogs.py` | builds the bin, cabinet, drawer and cover dialogs against fake inputs that reject non-ASCII / duplicate input ids (Fusion: "invalid argument id") | 3 s |
| `t_bin2.py` | builds the bin dialog 3x in a row; each run must reach the handler attach line (~874, `add_handler` KeyError is the mock's limit, not a bug) | 2 s |

Expected: `DONE fails=0`. A failing probe prints the point; check whether the probe or the
geometry is wrong (several "failures" were wrong probe points, e.g. inside a rounded corner or on
a contact face — membership is boundary-inclusive, offset scan grids by ~0.001).

## Writing new checks

- Probe points in cabinet local cm: x width, y depth (front = `cab['front']`), z up.
- Layout numbers come from `cabinetLayout.cabinet(params)` / `insert(cab, params)`; build bodies
  with `cabinetGeometry.buildCabinet(None, params)` / `buildInsert(None, cabParams, insertParams)`.
- Test fixtures `CAB0` / `INS0` keep the older wall sizes (2 mm walls, 1.6 mm floor) that the
  probe coordinates were written for; new defaults are 1.2 / 1.2 / 1.5 mm.
- Collision scan: `collisions(cab, ins, cabBody, insBody, shift)` samples the column-wall zones.
- For dialog bugs: extend `t_bin2.py`'s fake inputs (`FI` registers every `add*` input by id).

## Limits

No real B-rep: fillets, mesh, custom features, timeline, selection, mouse events are not
simulated. The spool cradles' floor fillet is a real Fusion fillet feature (scratch component,
`cabinetGeometry.filletPostFeet`); without a design (mock) it is skipped, so check it in Fusion. Anything Fusion-side (edit routing, compute, design intent) needs a test in Fusion
and the log (see `fusion-addin-debugging`).
