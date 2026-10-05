"""Front / back corners: ledges / grooves never poke through the rounded outer corner,
the wall keeps its thickness there, and the drawer does not collide with the
rounded interior back corner."""
import sys, os, math
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


def check(name, ok, p):
    global fails
    if not ok:
        fails += 1
        print('FAIL', name, [round(v, 3) for v in p])


for guide in (L.GUIDE_LEDGE, L.GUIDE_GROOVE):
    cp = dict(L.CABINET_DEFAULTS, unitsW=2, unitsL=3, rows=2, guide=guide)
    cab = L.cabinet(cp)
    body = G.buildCabinet(None, cp)
    R, wall = cab['radius'], min(cab['wall'], cab['backWall'])
    zs = [cab['rows'][1]['bottom'] - k * 0.05 for k in range(8)]
    if cab['grooved']:
        zs += [L.grooveCenter(row) for row in cab['rows']]
    for sx, cx in ((1, cab['x0'] + R), (-1, cab['x1'] - R)):
        cy = cab['back'] - R
        for deg in range(0, 91, 5):
            a = math.radians(deg)
            dx, dy = -sx * math.cos(a), math.sin(a)          # outward from the arc centre
            for z in zs:
                out = (cx + dx * (R + 0.005), cy + dy * (R + 0.005), z)
                check(f'{guide}: nothing outside the corner', not body.contains(list(out)), out)
                inner = (cx + dx * (R - wall * 0.9), cy + dy * (R - wall * 0.9), z)
                check(f'{guide}: wall thick enough in the corner', body.contains(list(inner)), inner)

    # Front corners: as round as the feet and the top (Gridfinity radius).
    rf = cab['radius']
    for sx, cx in ((1, cab['x0'] + rf), (-1, cab['x1'] - rf)):
        cy = cab['front'] + rf
        for deg in range(0, 91, 5):
            a = math.radians(deg)
            dx, dy = -sx * math.cos(a), -math.sin(a)
            for z in zs:
                out = (cx + dx * (rf + 0.003), cy + dy * (rf + 0.003), z)
                check(f'{guide}: nothing outside the front corner', not body.contains(list(out)), out)

    # Grid on top: front corners of the grid layer as round as the pockets.
    cpg = dict(cp, topType=L.TOP_GRID)
    cg = L.cabinet(cpg)
    top = G.buildCabinet(None, cpg)
    R = cg['radius']
    zt = cg['zTop'] - 0.05
    for sx, cx in ((1, cg['x0'] + R), (-1, cg['x1'] - R)):
        corner = (cx - sx * R * 0.85, cg['front'] + R * 0.15, zt)     # outside the radius
        check(f'{guide}: grid top front corner rounded', not top.contains(list(corner)), corner)
        low = (cx - sx * (R - 0.03), cg['front'] + R, cg['ceil'] - 0.2)  # below: wall still there
        check(f'{guide}: wall below the grid layer kept', top.contains(list(low)), low)

    # Insert in the outer column: its front corner follows the cabinet's
    # rounding and touches it in the front plane (nothing sticks out).
    ipo = dict(L.INSERT_DEFAULTS, column=1, row=2)
    inso = L.insert(cab, ipo)
    dr = G.buildInsertParts(None, cp, ipo)[0]
    zc = (inso['z0'] + inso['z1']) / 2
    Rr = cab['radius']
    for deg in range(0, 91, 10):
        a = math.radians(deg)
        p = (cab['x0'] + Rr - (Rr + 0.003) * math.cos(a), cab['front'] + Rr - (Rr + 0.003) * math.sin(a), zc)
        check(f'{guide}: insert inside the rounded front corner', not dr.contains(list(p)), p)
    check(f'{guide}: insert front flush at the corner end', dr.contains([cab['x0'] + Rr, cab['front'] + 0.01, zc]),
          (cab['x0'] + Rr, cab['front'] + 0.01, zc))

    ip = dict(L.INSERT_DEFAULTS, column=1, row=1)
    drawer = G.buildInsertParts(None, cp, ip)[0]
    ins = L.insert(cab, ip)
    z = (ins['z0'] + ins['z1']) / 2
    steps = 30
    for i in range(steps + 1):
        for j in range(steps + 1):
            p = (ins['colX0'] - 0.2 + 0.6 * i / steps, cab['innerBack'] - 0.5 + 0.55 * j / steps, z)
            check(f'{guide}: drawer clear of the cabinet', not (body.contains(list(p)) and drawer.contains(list(p))), p)
print('DONE fails', fails)
