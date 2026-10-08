"""Pull-out stops: side bump (bump behind the cabinet front, nose at the back
of the insert's side walls) and top catch (tooth under the ledge above, nose
on the rim) - they stop the insert pulled out, clear while it moves."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import cabinetGeometry as G, cabinetLayout as L
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _box

G._getCellCutout = lambda des, b, l, cl: _box(-2 * cl + 0.3, b - 0.3, -2 * cl + 0.3, l - 0.3, -0.5, 0.0)
G._getFoot = lambda des, b, l, cl, *a: _box(-cl, b - cl, -cl, l - cl, -0.5, 0.0)
fails = 0


def expect(name, ok, info=''):
    global fails
    if not ok:
        fails += 1
        print('FAIL', name, info)


def overlap(a, b, pts):
    return [p for p in pts if a.contains(list(p)) and b.contains(list(p))]


kL, kH = G._kAngle(L.SIDE_LEAD_ANGLE), G._kAngle(L.SIDE_HOLD_ANGLE)
for guide in (L.GUIDE_LEDGE, L.GUIDE_GROOVE):
    cp = dict(L.CABINET_DEFAULTS, unitsW=2, unitsL=3, rows=2, guide=guide, topMount=L.TOP_MOUNT_FIXED, heightUnits=14)
    cab = L.cabinet(cp)
    cabinet = G.buildCabinet(None, cp)
    ip = dict(L.INSERT_DEFAULTS, column=1, row=1, interior=L.INTERIOR_EMPTY)
    expect(f'{guide}: auto = side bump', L.stopMode(cab, ip) == L.STOP_SIDE)
    ins = L.insert(cab, ip)
    zs, zt = L.sideBand(cab, 0)
    zm = (zs + zt) / 2
    x0, lat = ins['x0'], float(cp['fitLateral'])
    bumpY1 = G.sideStopY(cab)
    bumpY0 = bumpY1 - G.sideReach(cab) * (kL + kH)
    yn0 = ins['y1'] - L.STOP_LAND
    yn1 = yn0 + G.sideReach(cab) * (kL + kH)
    body = G.buildInsertParts(None, cp, ip)[0]
    expect(f'{guide}: bump on the wall', cabinet.contains([ins['colX0'] + 0.01, bumpY0 + G.sideReach(cab) * kL, zm]))
    expect(f'{guide}: nose on the insert', body.contains([x0 - 0.01, yn0 + G.sideReach(cab) * kH, zm]))
    yb = bumpY0 + G.sideReach(cab) * kL
    expect(f'{guide}: bump underside 45 deg', not cabinet.contains([ins['colX0'] + 0.015, yb, zs + 0.005]) and
           cabinet.contains([ins['colX0'] + 0.015, yb, zs + 0.03]))
    expect(f'{guide}: nose underside 45 deg', not body.contains([x0 - 0.015, yn0 + G.sideReach(cab) * kH, zs + 0.01]))
    pts = [(ins['colX0'] + f * lat, bumpY0 - 0.05 + i * 0.005, zm) for f in (0.2, 0.5, 0.8)
           for i in range(int((bumpY1 - bumpY0 + 0.1) / 0.005) + 1)]
    expect(f'{guide}: closed insert clear of the bumps', not overlap(cabinet, body, pts))
    tr = G.sideTrack(cab)
    expect(f'{guide}: track in the cabinet wall behind the bump', tr > 0.01 and
           not cabinet.contains([ins['colX0'] - tr / 2, (bumpY1 + ins['y1']) / 2, zm]))
    expect(f'{guide}: track in the insert wall in front of the nose',
           not body.contains([x0 + tr / 2, (ins['y0'] + yn0) / 2, zm]))
    # Whole travel: nothing rubs anywhere in the band (gap and tracks).
    full = [(ins['colX0'] + dx, y / 20.0, zm) for dx in (-0.015, -0.005, 0.005, 0.015, 0.025, 0.035)
            for y in range(int(ins['y0'] * 20) + 1, int(ins['y1'] * 20))]
    for pull in (0.0, 2.0, 4.0):
        moved = G.buildInsertParts(None, cp, dict(ip, pullOut=pull))[0]
        expect(f'{guide}: clear while moving (pull {pull})', not overlap(cabinet, moved, full))
    expect(f'{guide}: overlap at the stop >= 0.5 mm', 2 * G.sideReach(cab) - lat >= 0.05 - 1e-9)
    # Pulled out until just before the stop: clear; a bit further: nose hits the bump.
    before = yn0 - bumpY1 - 0.05
    out = G.buildInsertParts(None, cp, dict(ip, pullOut=before))[0]
    expect(f'{guide}: pulled out, still clear', not overlap(cabinet, out, pts))
    out = G.buildInsertParts(None, cp, dict(ip, pullOut=before + 0.06))[0]
    expect(f'{guide}: further out the nose hits the bump', bool(overlap(cabinet, out, pts)))

# Top catch (ledges): level the nose passes under the tooth, lifted by the play it hits it.
cp = dict(L.CABINET_DEFAULTS, unitsW=2, unitsL=3, rows=2, guide=L.GUIDE_LEDGE, topMount=L.TOP_MOUNT_FIXED, heightUnits=14)
cab = L.cabinet(cp)
cabinet = G.buildCabinet(None, cp)
ip = dict(L.INSERT_DEFAULTS, column=1, row=1, interior=L.INTERIOR_EMPTY, stop=L.STOP_TOP)
ins = L.insert(cab, ip)
expect('top catch kept on ledges', L.stopMode(cab, ip) == L.STOP_TOP)
xn = ins['x0'] + 0.01
yt = cab['front'] + L.TOP_Y + L.TOP_LEN / 2
z1 = ins['z1']
expect('tooth above the rim', cabinet.contains([xn, yt, z1 + L.TOP_NOSE + L.TOP_CLEAR + 0.02]))
expect('level: nose passes under the tooth', not cabinet.contains([xn, yt, z1 + L.TOP_NOSE]))
expect('lifted by the play: nose in the tooth', cabinet.contains([xn, yt, z1 + L.TOP_NOSE + L.insertVert(cab) - 0.005]))
body = G.buildInsertParts(None, cp, ip)[0]
expect('rim nose on the insert', body.contains([xn, ins['y1'] - 0.45, z1 + L.TOP_NOSE * 0.5]))
expect('grooves: top catch falls back to side bump',
       L.stopMode(L.cabinet(dict(cp, guide=L.GUIDE_GROOVE)), ip) == L.STOP_SIDE)
old = L.cabinet({k: v for k, v in L.CABINET_DEFAULTS.items() if k != 'stopParts'})
expect('old cabinets: no stop parts', not old['stopParts'] and not G.sideBumps(old) and not G.topTeeth(old))
# Auto: side bump and the stop in the groove / at the bottom catch at the same pull.
for guide, want in ((L.GUIDE_GROOVE, L.STOP_SOFT), (L.GUIDE_LEDGE, L.STOP_HARD)):
    c2 = L.cabinet(dict(L.CABINET_DEFAULTS, guide=guide))
    expect(f'{guide}: auto adds the {want} stop', L.bottomStop(c2, {'stop': L.STOP_AUTO}) == want)
    expect(f'{guide}: explicit side bump only', L.bottomStop(c2, {'stop': L.STOP_SIDE}) is None)
c2 = L.cabinet(dict(L.CABINET_DEFAULTS))
ins2 = L.insert(c2, dict(L.INSERT_DEFAULTS, column=1, row=1))
landY = ins2['y1'] - L.STOP_LAND                     # land face in the groove / floor
toothBack = c2['detentY'] + G._kAngle(L.BUMP_BACK_ANGLE) * c2['detentR']
expect('side bump and groove stop at the same pull', abs((landY - toothBack) - (landY - G.sideStopY(c2))) < 1e-9)
print('DONE fails', fails)
