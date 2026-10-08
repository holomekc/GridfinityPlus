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
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _box, _tmgr, _translate

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
for guide, top, lock in ((L.GUIDE_LEDGE, L.TOP_GRID, L.TOP_LOCK_OUTSIDE), (L.GUIDE_GROOVE, L.TOP_FLAT, L.TOP_LOCK_OUTSIDE),
                         (L.GUIDE_LEDGE, L.TOP_FLAT, L.TOP_LOCK_INSIDE), (L.GUIDE_GROOVE, L.TOP_GRID, L.TOP_LOCK_INSIDE)):
        cp = dict(L.CABINET_DEFAULTS, guide=guide, topType=top, topLock=lock)
        cab = L.cabinet(cp)
        parts = G.buildCabinetParts(None, cp)
        expect(f'{guide}/{top}: two parts', len(parts) == 2)
        body, plate = parts
        rl = cab['rail']
        w, h, z, x0, t = rl['w'], rl['h'], cab['ceil'], cab['x0'], rl['skin']
        expect(f'{lock}: skin', (t > 0) == (lock == L.TOP_LOCK_OUTSIDE))
        ym = (cab['front'] + cab['back']) / 2
        xc = (cab['x0'] + cab['x1']) / 2
        xr = x0 + t + 0.03                              # inside the rail
        n = f'{guide}/{top}/{lock}'
        check(f'{n}: no ceiling on the cabinet', body, (xc, ym, z + 0.05), False)
        check(f'{n}: rail on the wall', body, (xr, ym, z + 0.02), True)
        check(f'{n}: rail right side', body, (cab['x1'] - t - 0.03, ym, z + 0.02), True)
        check(f'{n}: rail ends before the back', body, (xr, rl['y1'] + 0.1, z + 0.02), False)
        check(f'{n}: plate covers the middle', plate, (xc, ym, z + 0.05), True)
        check(f'{n}: plate slot over the rail', plate, (xr, ym, z + 0.02), False)
        check(f'{n}: plate slot open at the front', plate, (xr, cab['front'] + 0.01, z + 0.02), False)
        check(f'{n}: plate slot closed at the back (stop)', plate, (x0 + 0.15, cab['back'] - 0.12, z + 0.05), True)
        if t > 0:
            k, f = L.RAIL_LEAN, rl['foot']
            check(f'{n}: plate edge outside the rail', plate, (x0 + 0.01, ym, z + 0.01), True)
            check(f'{n}: plate edge up to the top', plate, (x0 + 0.01, ym, z + rl['height'] - 0.01), True)
            check(f'{n}: wall top under the plate edge', body, (x0 + 0.01, ym, z - 0.03), True)
            check(f'{n}: no rail in the plate edge', body, (x0 + 0.01, ym, z + 0.01), False)
            check(f'{n}: plate wedge over the leaning outer side', plate, (x0 + t + 0.02, ym, z + 0.12), True)
            check(f'{n}: ... no rail there', body, (x0 + t + 0.02, ym, z + 0.12), False)
            check(f'{n}: rail leans in over the interior', body, (x0 + f + 0.04, ym, z + 0.06), True)
            check(f'{n}: inner 45 deg (no flat overhang)', body, (x0 + f + 0.05, ym, z + 0.03), False)
            check(f'{n}: plate under the lean', plate, (x0 + f + 0.06, ym, z + 0.01), True)

            def overlaps(a, b):
                for i in range(25):
                    for j in range(25):
                        pt = [x0 + 0.45 * i / 24, ym, z + 0.3 * j / 24]
                        if a.contains(pt) and b.contains(pt):
                            return True
                return False
            out = _tmgr().copy(body)
            _translate(out, -0.04, 0.0, 0.0)
            expect(f'{n}: wall bent outwards hits the plate', overlaps(out, plate))
            up = _tmgr().copy(plate)
            _translate(up, 0.0, 0.0, 0.04)
            expect(f'{n}: lifted plate hits the rail', overlaps(body, up))
            both = _tmgr().copy(up)
            _translate(both, -0.04, 0.0, 0.0)
            expect(f'{n}: wall out + plate up still blocked', overlaps(out, both) or overlaps(out, up))
        else:
            check(f'{n}: rail undercut holds', body, (x0 + w + 0.5 * h, ym, z + 0.9 * h), True)
            check(f'{n}: rail undercut open below', body, (x0 + w + 0.5 * h, ym, z + 0.2 * h), False)
        steps = 12
        for i in range(steps + 1):
            for k in range(steps + 1):
                pt = (x0 + (w + h + 0.2) * i / steps, ym, z + (rl['height'] + 0.06) * k / steps)
                if body.contains(list(pt)) and plate.contains(list(pt)):
                    fails += 1
                    print('FAIL', n, 'rail and plate overlap', [round(v, 3) for v in pt])
# Click: bump on the rail top before its end, hollow in the plate's slot; closed
# the plate sits clear, a few millimetres out it squeezes over the bump.
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _tmgr, _translate
import math
cp = dict(L.CABINET_DEFAULTS, topType=L.TOP_GRID, topMount=L.TOP_MOUNT_SLIDE)
cab = L.cabinet(cp)
body, plate = G.buildCabinetParts(None, cp)
rl = cab['rail']
w, h, z0 = rl['w'], rl['h'], cab['ceil']
uv, (u0, u1) = G._railTop(cab)
top = z0 + uv
yb = rl['y1'] - L.CLICK_FROM_END - L.CLICK_LENGTH / 2
q = rl['clearance'] + rl['click'] * 0.5                 # height above the rail top
xp = 0.5 * (u0 + u1) - q / math.sqrt(2)                 # along the slope, from the outer face
pt = (cab['x0'] + xp + q / math.sqrt(2), yb, top - xp + q / math.sqrt(2))
check('click bump on the rail', body, pt, True)
check('hollow in the plate over the bump', plate, pt, False)
moved = _tmgr().copy(plate)
_translate(moved, 0.0, -0.3, 0.0)
check('plate a bit out: squeezes over the bump', moved, pt, True)
expect('no click when 0', not G._railClicks(L.cabinet(dict(cp, topClick=0.0))))

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
# Rail width: rail foot as set (as far as wall and hook allow), plate edge
# thin; the plate itself never changes.
for top in (L.TOP_GRID, L.TOP_FLAT):
    cp = dict(L.CABINET_DEFAULTS, guide=L.GUIDE_GROOVE, topType=top, railWidth=0.1)
    cab = L.cabinet(cp)
    rl = cab['rail']
    expect(f'rail width {top}: foot 1 mm', abs(rl['foot'] - rl['skin'] - 0.1) < 1e-6)
    expect(f'rail width {top}: plate unchanged', abs(cab['zTop'] - cab['ceil'] - 0.62) < 1e-6)
    body, plate = G.buildCabinetParts(None, cp)
    ym = (cab['front'] + cab['back']) / 2
    x0, z = cab['x0'], cab['ceil']
    check(f'rail width {top}: rail foot', body, (x0 + rl['skin'] + 0.09, ym, z + 0.005), True)
    check(f'rail width {top}: plate edge', plate, (x0 + 0.02, ym, z + 0.005), True)
grid = L.cabinet(dict(L.CABINET_DEFAULTS, topType=L.TOP_GRID, railWidth=0.1))
flat = L.cabinet(dict(L.CABINET_DEFAULTS, topType=L.TOP_FLAT, railWidth=0.1))
expect('rail width: flat / grid same inside', abs(grid['ceil'] - flat['ceil']) < 1e-9)
print('DONE fails', fails)
