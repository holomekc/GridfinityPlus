"""Snap tongue: spring tongue in both side walls of an insert (45 deg slots,
free front end, joined at the back), hook outside, room inside to bend in;
the cabinet's catch takes the hook when closed; left high / right low so a
divider keeps material; old cabinets have no catches and no tongues."""
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


g, gg = L.SNAP_GAP, L.SNAP_GAP * math.sqrt(2)
for guide in (L.GUIDE_LEDGE, L.GUIDE_GROOVE):
    cp = dict(L.CABINET_DEFAULTS, unitsW=3, unitsL=3, rows=2, columns=3, guide=guide, snapCatch=True,
              topMount=L.TOP_MOUNT_FIXED, heightUnits=16)
    cab = L.cabinet(cp)
    cabinet = G.buildCabinet(None, cp)
    ip = dict(L.INSERT_DEFAULTS, column=2, row=1, interior=L.INTERIOR_COMPARTMENTS, divX=1, divY=2, snapTongue=True)
    ins = L.insert(cab, ip)
    body = G.buildInsertParts(None, cp, ip)[0]
    tw = float(ins['p']['wall'])
    hy0, hookLen, p, kH, kL, lat = G._snapHook(cab, ip)
    ty0 = cab['front'] + L.SNAP_Y0
    ty1 = ty0 + L.SNAP_LEN
    ym = (ty0 + ty1) / 2
    bands = L.snapBands(cab, 0)
    for side, xo, sx, face, d in (('left', ins['x0'], 1, ins['colX0'], -1), ('right', ins['x1'], -1, ins['colX1'], 1)):
        band = bands[side]
        n = f'{guide}/{side}'
        if band is None:
            fails += 1; print('FAIL', n, 'no tongue band'); continue
        zs, zt = band
        zm = (zs + zt) / 2
        check(f'{n}: tongue', body, (xo + sx * tw / 2, ym, zm), True)
        check(f'{n}: slot below', body, (xo + sx * 0.01, ym, zs - gg / 2), False)
        check(f'{n}: slot above', body, (xo + sx * 0.01, ym, zt + gg / 2), False)
        check(f'{n}: slot below runs down inwards (45 deg)', body, (xo + sx * (tw - 0.01), ym, zs - tw + 0.01 - gg / 2), False)
        check(f'{n}: free front end', body, (xo + sx * tw / 2, ty0 - g / 2, zm), False)
        check(f'{n}: joined at the back', body, (xo + sx * tw / 2, ty1 + 0.05, zm), True)
        check(f'{n}: room inside to bend', body, (xo + sx * (tw + 0.05), ym, zm), False)
        check(f'{n}: hook', body, (xo - sx * p * 0.3, hy0 + hookLen * 0.4, zm), True)
        check(f'{n}: nothing past the hook', body, (xo - sx * (p + 0.01), hy0 + hookLen * 0.4, zm), False)
        # Cabinet catch: the closed hook sits in it, the wall is kept around it.
        dc = L.SNAP_ENGAGE + L.SNAP_CLEARANCE
        check(f'{n}: catch open', cabinet, (face + d * dc * 0.5, hy0 + hookLen * 0.4, zm), False)
        check(f'{n}: wall in front of the catch', cabinet, (face + d * dc * 0.5, hy0 - 0.15, zm), True)
        check(f'{n}: wall behind the catch', cabinet, (face + d * (dc + 0.02), hy0 + hookLen * 0.4, zm), True)
        for f in [i / 8 for i in range(9)]:
            for v in (0.2, 0.5, 0.8):
                vv = v * p
                yy = hy0 + kH * vv + f * (hookLen - (kH + kL) * vv)
                check(f'{n}: closed hook clear of the cabinet', cabinet, (xo - sx * vv, yy, zm), False)
    # Divider between columns: catches from both sides at different heights.
    xd = (cab['columns'][0][1] + cab['columns'][1][0]) / 2
    for side in ('left', 'right'):
        zs, zt = bands[side]
        check(f'{guide}: divider keeps material at the {side} catch', cabinet, (xd, hy0 + hookLen * 0.4, (zs + zt) / 2), True)

old = {k: v for k, v in L.CABINET_DEFAULTS.items() if k != 'snapCatch'}
ocab = L.cabinet(dict(old, topMount=L.TOP_MOUNT_FIXED))
if ocab['snap'] or G.snapCatches(ocab):
    fails += 1; print('FAIL old cabinet has catches')
# Small cabinet (1 x 1 x 6 units, one row): the tongue still fits, also with grooves.
for guide in (L.GUIDE_LEDGE, L.GUIDE_GROOVE):
    small = L.cabinet(dict(L.CABINET_DEFAULTS, unitsW=1, unitsL=1, rows=1, heightUnits=6, guide=guide))
    b = L.snapBands(small, 0)
    if b['left'] is None or b['right'] is None:
        fails += 1; print('FAIL', guide, '1x1x6: no room for the snap tongue', b)
print('DONE fails', fails)
