"""Slide-on feet: the cabinet has a flat bottom with a dovetail head under
each cell, running front to back (printed on its back the profile just rises;
both ends chamfered 45 deg); each foot is a part with a lipped channel (stop
at the far end), an entry pocket and a click dimple. Set on from below beside
the head, push along y (chessboard directions) - then it cannot drop off,
slide on or slide back without clicking out. Printed on the back nothing of
the head starts in the air."""
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


def expect(name, ok, info=''):
    global fails
    if not ok:
        fails += 1
        print('FAIL', name, info)


def check(name, body, p, want):
    expect(name, body.contains(list(p)) == want, [round(v, 3) for v in p])


def overlaps(a, b, cx, cy, wx=1.0, wy=2.0):
    for i in range(25):
        for j in range(51):
            for k in range(13):
                pt = [cx - wx + 2 * wx * i / 24, cy - wy + 2 * wy * j / 50, -0.35 + 0.34 * k / 12]  # not the contact plane z 0
                if a.contains(pt) and b.contains(pt):
                    return True
    return False


big = L.footHead(L.cabinet(dict(L.CABINET_DEFAULTS, unitsL=1, footHeadLen=9.0, footHeadWidth=9.0)))
multi = L.footHead(L.cabinet(dict(L.CABINET_DEFAULTS, unitsL=3, footHeadLen=9.0)))
expect('several rows: at most ~17 mm (set on inside its cell)', 1.6 < multi['len'] < 1.75, multi)
expect('dovetail up to ~33 mm long, ~27 mm wide', 3.2 < big['len'] < 3.45 and 2.6 < big['root'] < 2.8, big)
expect('built in: no foot parts', len(G.buildCabinetParts(None, dict(L.CABINET_DEFAULTS, topMount=L.TOP_MOUNT_FIXED))) == 1)
cp = dict(L.CABINET_DEFAULTS, unitsW=2, unitsL=2, topMount=L.TOP_MOUNT_FIXED, footMount=L.FOOT_SLIDE)
cab = L.cabinet(cp)
parts = G.buildCabinetParts(None, cp)
names = G.cabinetPartNames(cp)
expect('four feet as parts', len(parts) == 5 and names == ['foot 1,1', 'foot 1,2', 'foot 2,1', 'foot 2,2'], names)
body, feet = parts[0], parts[1:]
fh = L.footHead(cab)
t, half, Lh = fh['depth'], fh['root'] / 2, fh['len']
cells = L.footCells(cab)
expect('alternating per column, first column backwards', [c[4] for c in cells] == [1, 1, -1, -1],
       [c[4] for c in cells])
one = L.footCells(L.cabinet(dict(cp, unitsW=1)))
expect('single column: pushed backwards', all(c[4] == 1 for c in one))
# Single column: the stop is at the front - the cabinet cannot move forward
# off its feet (drawers pulled), only backwards (toward the wall).
i, j, cx, hy, push = cells[0]
fh0 = L.footHead(cab)
front = hy - fh0['len'] / 2                              # head's front end
check('stop at the front of the head', feet[0], (cx, front - L.FOOT_PLAY - 0.05, -0.1), True)
check('channel open behind the head (entry)', feet[0], (cx, hy + fh0['len'] / 2 + 0.1, -0.1), False)
for (i, j, cx, cy, push), foot in zip(cells, feet):
    n = f'cell {i + 1},{j + 1}'
    check(f'{n}: head under the cell', body, (cx, cy, -0.1), True)
    check(f'{n}: head widens 45 deg', body, (cx + half + 0.12, cy, -0.15), True)
    check(f'{n}: ... narrow at the root', body, (cx + half + 0.12, cy, -0.05), False)
    # Printed on its back (+y = down): the head's lower (+y) end rises 45 deg
    # away from the bottom, so it never starts in the air.
    yEnd = cy + Lh / 2
    check(f'{n}: +y end full at the root', body, (cx, yEnd - 0.01, -0.005), True)
    check(f'{n}: +y end chamfered below', body, (cx, yEnd - 0.05, -0.15), False)
    check(f'{n}: no built-in foot', body, (cx + 1.6, cy + 1.2, -0.3), False)
    check(f'{n}: foot there', foot, (cx + 1.6, cy + 1.2, -0.3), True)
    # Channel + entry pocket stay inside the foot (its ends keep a rim).
    cc = j * cab['p']['baseL'] + cab['p']['baseL'] / 2 - cab['p']['cl']     # cell centre
    ext = Lh + 2 * L.FOOT_PLAY                                               # both centred in the cell
    for yr in (cc - ext - 0.06, cc + ext + 0.06):
        check(f'{n}: rim beyond channel + pocket y {round(yr, 2)}', foot, (cx, yr, -0.3), True)
    expect(f'{n}: channel + pocket inside the foot at their depth', ext <= fh['half'] - 0.05)
    check(f'{n}: foot lip over the head', foot, (cx + half + 0.12, cy, -0.03), True)
    expect(f'{n}: foot and cabinet apart', not overlaps(body, foot, cx, cy))
    m = _tmgr().copy(foot); _translate(m, 0, 0, -0.05)
    expect(f'{n}: foot cannot drop off', overlaps(body, m, cx, cy))
    for dx in (0.05, -0.05):
        m = _tmgr().copy(foot); _translate(m, dx, 0, 0)
        expect(f'{n}: foot cannot slide sideways ({dx})', overlaps(body, m, cx, cy))
    sp = (cx, cy - push * (Lh / 2 - 0.01), -0.005)          # head's leading end
    check(f'{n}: head reaches the stop', body, sp, True)
    check(f'{n}: channel clear of it', foot, sp, False)
    m = _tmgr().copy(foot); _translate(m, 0, push * 0.05, 0)
    check(f'{n}: pushed further, the stop wall meets the head', m, sp, True)
    h = L.FOOT_CLICK + L.FOOT_PLAY
    end = G._clickEnd(fh, cy, push)                          # bump's trailing end
    bp = (cx, end - push * 0.04, -t - h + 0.004)             # bottom of the bump
    check(f'{n}: click bump under the head', body, bp, True)
    check(f'{n}: dimple in the foot under it', foot, bp, False)
    m = _tmgr().copy(foot); _translate(m, 0, -push * 0.06, 0)
    check(f'{n}: pushed back, the floor ridge meets the bump (click)', m, bp, True)
    # Set on: foot shifted back by the push distance, coming up from below.
    D = Lh + 2 * L.FOOT_PLAY + 0.01
    for dz in (-0.6, -0.3, 0.0):
        m = _tmgr().copy(foot); _translate(m, 0, -push * D, dz)
        expect(f'{n}: set on from below (dz {dz})', not overlaps(body, m, cx, cy))

# Printed on the back (up = -y): every layer of a head must rest on the layer
# below it (no part of the head may start in the air): material at (x, y, z)
# needs material at (x, y + 0.005, z') with |z' - z| <= 0.006 (45 deg + grid).
i, j, cx, cy, push = cells[0]
bad = []
for xi in range(15):
    x = cx - 0.9 + 1.8 * xi / 14
    for yi in range(81):
        y = cy - 0.9 + 1.8 * yi / 80
        for zi in range(1, 31):
            z = -0.3 * zi / 30
            if body.contains([x, y, z]) and not any(body.contains([x, y + 0.005, z + dz])
                                                    for dz in (-0.006, -0.003, 0.0, 0.003, 0.006)):
                bad.append((round(x, 3), round(y, 3), round(z, 3)))
expect('head prints on the back (nothing starts in the air)', not bad, bad[:5])

# A long dovetail: the channel runs from the stop rim on, the entry pocket
# out of the foot's end (the foot slides on from beyond it).
cp2 = dict(cp, unitsW=1, unitsL=1, footHeadLen=3.0, footHeadWidth=2.5)
cab2 = L.cabinet(cp2)
fh2 = L.footHead(cab2)
body2, foot2 = G.buildCabinetParts(None, cp2)
i, j, cx, hy, push = L.footCells(cab2)[0]
cc = cab2['p']['baseL'] / 2 - cab2['p']['cl']
check('long: head there', body2, (cx, hy, -0.1), True)
check('long: stop rim', foot2, (cx, cc - push * (fh2['half'] - L.FOOT_RIM / 2), -0.3), True)
check('long: channel clear', foot2, (cx, hy, -0.1), False)
expect('long: foot and cabinet apart', not overlaps(body2, foot2, cx, hy, 1.8, 2.1))
m = _tmgr().copy(foot2); _translate(m, 0, 0, -0.05)
expect('long: foot cannot drop off', overlaps(body2, m, cx, hy, 1.8, 2.1))
D = fh2['len'] + 2 * L.FOOT_PLAY + 0.01
m = _tmgr().copy(foot2); _translate(m, 0, -push * D, -0.3)
expect('long: set on beyond the end, from below', not overlaps(body2, m, cx, hy, 1.8, 2.1))

# Mounting a column of three, back row first: each foot is set on (shifted
# forward by the push distance, from below) without hitting a head; the
# longest dovetail allowed.
cp3 = dict(cp, unitsW=1, unitsL=3, footHeadLen=9.0)
cab3 = L.cabinet(cp3)
parts3 = G.buildCabinetParts(None, cp3)
body3, feet3 = parts3[0], parts3[1:]
fh3 = L.footHead(cab3)
D = fh3['len'] + 2 * L.FOOT_PLAY + 0.01
for (i, j, cx, hy, push), foot in sorted(zip(L.footCells(cab3), feet3), key=lambda c: -c[0][1]):
    for dz in (-0.6, -0.3, 0.0):
        m = _tmgr().copy(foot); _translate(m, 0, -push * D, dz)
        expect(f'1x3 row {j + 1}: set on (dz {dz})', not overlaps(body3, m, cx, hy, 1.0, 4.0))
print('DONE fails', fails)
