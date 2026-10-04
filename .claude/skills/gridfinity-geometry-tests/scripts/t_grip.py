"""Notch / finger hole with compartments: dividers in the way get the round
grip profile - along the front row, a set depth, or not at all."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import cabinetGeometry as G, cabinetLayout as L

fails = 0


def check(name, body, p, expect):
    global fails
    if body.contains(list(p)) != expect:
        fails += 1
        print('FAIL', name, [round(v, 3) for v in p], 'expected', expect)


cp = dict(L.CABINET_DEFAULTS, unitsW=2, unitsL=3, rows=2)
cab = L.cabinet(cp)
for handle in (L.HANDLE_NOTCH, L.HANDLE_SLOT):
    base = dict(L.INSERT_DEFAULTS, column=1, row=1, interior=L.INTERIOR_COMPARTMENTS, divX=3, divY=2,
                handle=handle, label=L.LABEL_NONE, frontStyle=L.FRONT_FLUSH)
    ins = L.insert(cab, base)
    tw, tf = float(ins['p']['wall']), float(ins['p']['floor'])
    yB = ins['y0'] + float(ins['p']['front'])
    px0, px1, py1 = ins['x0'] + tw, ins['x1'] - tw, ins['y1'] - tw
    uW = (px1 - px0 - 2 * tw) / 3
    uL = (py1 - yB - tw) / 2
    xd = px0 + uW + tw / 2                       # first lengthwise divider (in the notch's way)
    xc = (ins['x0'] + ins['x1']) / 2
    if handle == L.HANDLE_NOTCH:
        z = ins['z1'] - 0.3
    else:
        _, band, _ = G.frontLayout(ins['p'], ins['x0'], ins['x1'], ins['z0'], ins['z1'])
        z = (band[2] + band[3]) / 2
    body = G.buildInsertParts(None, cp, base)[0]           # default: front row
    check(f'{handle} front row: divider cut near the front', body, (xd, yB + 0.5, z), False)
    check(f'{handle} front row: divider cut to the cross divider', body, (xd, yB + uL - 0.3, z), False)
    check(f'{handle} front row: back row divider kept', body, (xd, yB + uL + tw + 0.5, z), True)
    check(f'{handle} front row: cross divider kept', body, (xc + uW / 2 + tw + 0.3, yB + uL + tw / 2, z), True)
    check(f'{handle} front row: floor kept', body, (xd, yB + 1.0, ins['z0'] + tf / 2), True)
    body = G.buildInsertParts(None, cp, dict(base, gripDividers=L.GRIP_DEPTH, gripDepth=1.0))[0]
    check(f'{handle} depth 10 mm: cut', body, (xd, yB + 0.5, z), False)
    check(f'{handle} depth 10 mm: kept behind', body, (xd, yB + 1.5, z), True)
    body = G.buildInsertParts(None, cp, dict(base, gripDividers=L.GRIP_OFF))[0]
    check(f'{handle} off: divider full', body, (xd, yB + 0.5, z), True)
print('DONE fails', fails)
