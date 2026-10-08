"""Detent: the cabinet's tooth (flat ramp in front, steep edge behind) and the
insert's notch (steep hold flank), push-in ramp, lead-in at the insert's back
end, pull-out stop hard / like the detent / off. The tooth fits the notch."""
import sys, os, math
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


def check(name, body, p, expect):
    global fails
    if body.contains(list(p)) != expect:
        fails += 1
        print('FAIL', name, [round(v, 3) for v in p], 'expected', expect)


k = lambda deg: 1 / math.tan(math.radians(deg))
kH, kR = k(L.DETENT_HOLD_ANGLE), k(L.DETENT_RAMP_ANGLE)
kF, kB = k(L.BUMP_FRONT_ANGLE), k(L.BUMP_BACK_ANGLE)
c = L.DETENT_CLEARANCE

for guide in (L.GUIDE_LEDGE, L.GUIDE_GROOVE):
    cp = dict(L.CABINET_DEFAULTS, unitsW=2, unitsL=3, rows=2, guide=guide, topMount=L.TOP_MOUNT_FIXED,
              stopParts=False)          # bottom stops (side bump / top catch: t_stops)
    cab = L.cabinet(cp)
    R = cab['detentR']
    assert abs(R - L.DETENT_HEIGHT) < 1e-9, R
    yd = cab['detentY']
    cabinet = G.buildCabinet(None, cp)
    xa, xb, z = L.contactStrips(cab, 0, 1)[0]
    x = (xa + xb) / 2
    h = R * 0.5
    # Tooth on the cabinet: flat ramp in front, steep edge behind.
    check(f'{guide}: tooth tip', cabinet, (x, yd, z + R * 0.9), True)
    check(f'{guide}: tooth ramp (front), inside', cabinet, (x, yd - kF * (R - h) + 0.015, z + h), True)
    check(f'{guide}: tooth ramp (front), outside', cabinet, (x, yd - kF * (R - h) - 0.015, z + h), False)
    check(f'{guide}: tooth edge (back), inside', cabinet, (x, yd + kB * (R - h) - 0.005, z + h), True)
    check(f'{guide}: tooth edge (back), outside', cabinet, (x, yd + kB * (R - h) + 0.015, z + h), False)

    dB = max(kH, kB) * R + c * math.sqrt(1 + kH * kH)
    for stop in (L.STOP_AUTO, L.STOP_HARD, L.STOP_SOFT, L.STOP_OFF):
        ip = dict(L.INSERT_DEFAULTS, column=1, row=2, stop=stop, interior=L.INTERIOR_EMPTY)
        ins = L.insert(cab, ip)
        body = G.buildInsertParts(None, cp, ip)[0]
        n = f'{guide}/{stop}'
        check(f'{n}: notch open', body, (x, yd, z + h), False)
        check(f'{n}: hold flank, inside', body, (x, yd + dB - kH * h - 0.015, z + h), False)
        if not cab['grooved']:
            check(f'{n}: hold flank, material', body, (x, yd + dB - kH * h + 0.015, z + h), True)
            check(f'{n}: ridge', body, (x, yd + dB + L.DETENT_RIDGE / 2, z + 0.01), True)
            cs = yd + dB + L.DETENT_RIDGE
            check(f'{n}: ramp, material', body, (x, cs + kR * h - 0.015, z + h), True)
        cs = yd + dB + L.DETENT_RIDGE
        check(f'{n}: ramp, channel', body, (x, cs + kR * h + 0.015, z + h), False)
        y1 = ins['y1']
        chEnd = y1 - L.STOP_LAND
        resolved = L.stopMode(cab, ip)
        if resolved == L.STOP_HARD and not cab['grooved']:
            check(f'{n}: hard land', body, (x, chEnd + 0.015, z + h), True)
            check(f'{n}: hard face low', body, (x, chEnd + 0.015, z + 0.01), True)
            check(f'{n}: channel before the land', body, (x, chEnd - 0.015, z + h), False)
        if resolved == L.STOP_SOFT and not cab['grooved']:
            check(f'{n}: soft flank, channel', body, (x, chEnd - kH * h - 0.015, z + h), False)
            check(f'{n}: soft flank, material', body, (x, chEnd - kH * h + 0.015, z + h), True)
        if resolved != L.STOP_OFF:
            # Lead-in: the back end is ramped (the insert goes in over the tooth).
            r = R + c
            check(f'{n}: lead-in cut at the back end', body, (x, y1 - kR * (r - h) * 0.5 - 0.005, z + h), False)
            if not cab['grooved']:
                check(f'{n}: land in front of the lead-in', body, (x, y1 - kR * r - 0.03, z + 0.01), True)
        else:
            check(f'{n}: channel to the back', body, (x, y1 - 0.05, z + h), False)
        # The cabinet's tooth (closed position) stays clear of the insert.
        for f in [i / 10 for i in range(11)]:
            for hh in (0.1 * R, 0.5 * R, 0.9 * R):
                yy = yd - kF * (R - hh) + f * (kF + kB) * (R - hh)
                check(f'{n}: tooth clear of the notch', body, (x, yy, z + hh), False)
# Grooves: notch roof and tooth follow the 45 deg flank across the whole strip.
cp = dict(L.CABINET_DEFAULTS, unitsW=2, unitsL=3, rows=2, guide=L.GUIDE_GROOVE, topMount=L.TOP_MOUNT_FIXED,
          stopParts=False)
cab = L.cabinet(cp)
R = cab['detentR']
yd = cab['detentY']
cabinet = G.buildCabinet(None, cp)
ip = dict(L.INSERT_DEFAULTS, column=1, row=2, stop=L.STOP_OFF, interior=L.INTERIOR_EMPTY)
body = G.buildInsertParts(None, cp, ip)[0]
for (xa, xb, z), slope in zip(L.contactStrips(cab, 0, 1), (1.0, -1.0)):
    xm = (xa + xb) / 2
    for f in (0.1, 0.3, 0.5, 0.7, 0.9):
        x = xa + f * (xb - xa)
        zf = z - slope * (x - xm)                       # flank height here
        check(f'groove: tooth tip follows the flank (f={f})', cabinet, (x, yd, zf + 0.85 * R), True)
        check(f'groove: notch open over the tooth (f={f})', body, (x, yd, zf + 0.95 * R), False)
        if 0.2 < f < 0.8:                               # the runner ends short of the groove tip
            check(f'groove: notch roof parallel to the flank (f={f})', body, (x, yd, zf + R + c + 0.03), True)
if L.withDefaults({'stop': True}, L.INSERT_DEFAULTS)['stop'] != L.STOP_AUTO or \
        L.withDefaults({'stop': False}, L.INSERT_DEFAULTS)['stop'] != L.STOP_OFF:
    fails += 1; print('FAIL legacy stop checkbox mapping')
print('DONE fails', fails)
