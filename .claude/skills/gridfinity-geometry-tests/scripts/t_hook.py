"""Hooked grooves: the runner's barb sits behind a lip of the wall, so an insert
cannot leave its groove sideways (a wall bending outwards drags it along);
plain V grooves let it go. Runner and groove never overlap."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import cabinetGeometry as G, cabinetLayout as L
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _box, _tmgr, _translate

G._getCellCutout = lambda des, b, l, cl: _box(-2 * cl + 0.3, b - 0.3, -2 * cl + 0.3, l - 0.3, -0.5, 0.0)
G._getFoot = lambda des, b, l, cl, *a: _box(-cl, b - cl, -cl, l - cl, -0.5, 0.0)
fails = 0


def expect(name, ok, info=''):
    global fails
    if not ok:
        fails += 1
        print('FAIL', name, info)


def overlaps(a, b, pts):
    return any(a.contains(list(p)) and b.contains(list(p)) for p in pts)


for guide in (L.GUIDE_HOOK, L.GUIDE_GROOVE):
    cp = dict(L.CABINET_DEFAULTS, unitsW=2, unitsL=3, rows=2, guide=guide, topMount=L.TOP_MOUNT_FIXED,
              heightUnits=14)
    cab = L.cabinet(cp)
    expect(f'{guide}: no errors', not cab['errors'], cab['errors'])
    expect(f'{guide}: grooved', cab['grooved'] and cab['hooked'] == (guide == L.GUIDE_HOOK))
    cabinet = G.buildCabinet(None, cp)
    ip = dict(L.INSERT_DEFAULTS, column=1, row=1, interior=L.INTERIOR_EMPTY)
    ins = L.insert(cab, ip)
    insert = G.buildInsert(None, cp, ip)
    d = cab['grooveDepth']
    gc = L.grooveCenter(cab['rows'][0])
    xf = cab['columns'][0][0]                     # left column face, the wall is at x < xf
    ym = ins['y1'] - 1.0
    X = lambda u: xf - u                           # u: depth into the left wall
    n = guide
    expect(f'{n}: groove open in the wall', not cabinet.contains([X(0.5 * d), ym, gc]))
    expect(f'{n}: runner in the groove', insert.contains([X(0.5 * d), ym, gc]))
    if guide == L.GUIDE_HOOK:
        expect(f'{n}: lip of the wall', cabinet.contains([X(0.3 * d), ym, gc + 0.45 * d]))
        expect(f'{n}: barb behind the lip', insert.contains([X(0.8 * d), ym, gc + 0.45 * d]))
        expect(f'{n}: runner not in the lip', not insert.contains([X(0.3 * d), ym, gc + 0.45 * d]))
        expect(f'{n}: wall behind the barb', cabinet.contains([X(d + 0.03), ym, gc + 0.45 * d]))
        expect(f'{n}: 45 deg under the arm (prints on the insert)',
               not insert.contains([X(0.5 * d), ym, gc - L.HOOK_LOW * d + 0.5 * d - 0.03]))
    pts = [(X(-0.05 + (d + 0.1) * i / 30), ym, gc - d + 2 * d * j / 30) for i in range(31) for j in range(31)]
    expect(f'{n}: runner and groove apart', not overlaps(cabinet, insert, pts))
    # The left wall bends outwards = the insert moves in, off that wall.
    moved = _tmgr().copy(insert)
    _translate(moved, 0.08, 0.0, 0.0)
    hooked = overlaps(cabinet, moved, pts)
    expect(f'{n}: insert pulled off the wall sideways ' + ('is held' if guide == L.GUIDE_HOOK else 'goes'),
           hooked == (guide == L.GUIDE_HOOK))
    lifted = _tmgr().copy(insert)
    _translate(lifted, 0.0, 0.0, 0.06)
    expect(f'{n}: insert cannot lift out', overlaps(cabinet, lifted, pts))
print('DONE fails', fails)
