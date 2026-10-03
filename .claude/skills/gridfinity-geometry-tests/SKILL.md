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
| `t_split.py` | baseplate split plan, one body per tile, dovetail gap equal along the flank | 2 s |
| `test_geom.py` | cabinet/insert probes (walls, ledges, grooves, detent, handles, knobs, labels, wire holes, overhang, top grid) + collision scan cabinet vs. insert, closed and pulled out | ~2-3 min |
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
simulated. Anything Fusion-side (edit routing, compute, design intent) needs a test in Fusion
and the log (see `fusion-addin-debugging`).
