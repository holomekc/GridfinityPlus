"""Slide-in top: cabinet ends at the ceiling with undercut rails on the side
walls, the plate has matching slots (open at the front, closed at the back),
the two never overlap; old cabinets (no topMount) stay one piece."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import cabinetGeometry as G, cabinetLayout as L
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _box

G._getFoot = lambda des, b, l, cl, *a: _box(-cl, b - cl, -cl, l - cl, -0.5, 0.0)
G._getCellCutout = lambda des, b, l, cl: _box(-2 * cl + 0.3, b - 0.3, -2 * cl + 0.3, l - 0.3, -0.5, 0.0)
fails = 0


def check(name, body, p, expect):
    global fails
    if body.contains(list(p)) != expect:
        fails += 1
        print('FAIL', name, [round(v, 3) for v in p], 'expected', expect)


def expect(name, ok):
    global fails
    if not ok:
        fails += 1
        print('FAIL', name)


expect('legacy cabinet: one piece', len(G.buildCabinetParts(None, {k: v for k, v in L.CABINET_DEFAULTS.items()
                                                                  if k != 'topMount'})) == 1)
expect('fixed: one piece', len(G.buildCabinetParts(None, dict(L.CABINET_DEFAULTS, topMount=L.TOP_MOUNT_FIXED))) == 1)
for guide in (L.GUIDE_LEDGE, L.GUIDE_GROOVE):
    for top in (L.TOP_GRID, L.TOP_FLAT):
        cp = dict(L.CABINET_DEFAULTS, guide=guide, topType=top)
        cab = L.cabinet(cp)
        parts = G.buildCabinetParts(None, cp)
        expect(f'{guide}/{top}: two parts', len(parts) == 2)
        body, plate = parts
        rl = cab['rail']
        w, h, z, x0 = rl['w'], rl['h'], cab['ceil'], cab['x0']
        ym = (cab['front'] + cab['back']) / 2
        xc = (cab['x0'] + cab['x1']) / 2
        n = f'{guide}/{top}'
        check(f'{n}: no ceiling on the cabinet', body, (xc, ym, z + 0.05), False)
        check(f'{n}: rail on the wall', body, (x0 + 0.05, ym, z + 0.05), True)
        check(f'{n}: rail undercut holds', body, (x0 + w + 0.5 * h, ym, z + 0.9 * h), True)
        check(f'{n}: rail undercut open below', body, (x0 + w + 0.5 * h, ym, z + 0.2 * h), False)
        check(f'{n}: rail right side', body, (cab['x1'] - 0.05, ym, z + 0.05), True)
        check(f'{n}: rail ends before the back', body, (x0 + 0.05, rl['y1'] + 0.1, z + 0.05), False)
        check(f'{n}: plate covers the middle', plate, (xc, ym, z + 0.05), True)
        check(f'{n}: plate slot over the rail', plate, (x0 + 0.05, ym, z + 0.05), False)
        check(f'{n}: plate slot open at the front', plate, (x0 + 0.05, cab['front'] + 0.01, z + 0.05), False)
        check(f'{n}: plate slot closed at the back (stop)', plate, (x0 + 0.15, cab['back'] - 0.12, z + 0.05), True)
        steps = 12
        for i in range(steps + 1):
            for k in range(steps + 1):
                pt = (x0 + (w + h + 0.05) * i / steps, ym, z + (w + 2 * h + 0.06) * k / steps)
                if body.contains(list(pt)) and plate.contains(list(pt)):
                    fails += 1
                    print('FAIL', n, 'rail and plate overlap', [round(v, 3) for v in pt])
# Grid top like a baseplate: the top is cut down by the bin height clearance
# (flat ridges between the pockets), fixed top and slide-in plate alike.
from GridfinityPlus.lib.gridfinityUtils import const
clr = const.BASEPLATE_BIN_Z_CLEARANCE
for mount in (L.TOP_MOUNT_FIXED, L.TOP_MOUNT_SLIDE):
    cp = dict(L.CABINET_DEFAULTS, topType=L.TOP_GRID, topMount=mount)
    cab = L.cabinet(cp)
    parts = G.buildCabinetParts(None, cp)
    top = parts[-1]
    xr = cab['p']['baseW'] - cab['p']['cl']            # ridge between the first two pockets
    ym = (cab['front'] + cab['back']) / 2
    check(f'{mount}: ridge cut down by the clearance', top, (xr, ym, cab['zTop'] - clr / 2), False)
    check(f'{mount}: ridge below the cut', top, (xr, ym, cab['zTop'] - clr - 0.02), True)

# Slide-in: flat and grid cabinets of the same height match outside and inside.
flat = L.cabinet(dict(L.CABINET_DEFAULTS, topType=L.TOP_FLAT, topMount=L.TOP_MOUNT_SLIDE))
grid = L.cabinet(dict(L.CABINET_DEFAULTS, topType=L.TOP_GRID, topMount=L.TOP_MOUNT_SLIDE))
expect('flat / grid: same outside height', abs(flat['zTop'] - grid['zTop']) < 1e-9)
expect('flat / grid: same inside', abs(flat['ceil'] - grid['ceil']) < 1e-9 and
       [r['height'] for r in flat['rows']] == [r['height'] for r in grid['rows']])
fixedGrid = L.cabinet(dict(L.CABINET_DEFAULTS, topType=L.TOP_GRID, topMount=L.TOP_MOUNT_FIXED))
expect('grid: slide-in costs nothing', abs(fixedGrid['ceil'] - grid['ceil']) < 1e-9 and
       abs(fixedGrid['zTop'] - grid['zTop']) < 1e-9)
print('DONE fails', fails)
