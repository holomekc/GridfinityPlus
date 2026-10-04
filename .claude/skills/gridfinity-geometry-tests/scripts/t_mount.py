import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import cabinetGeometry as G, cabinetLayout as L
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _box

G._getFoot = lambda des, b, l, cl, *a: _box(0.05, b - 2 * cl - 0.05, 0.05, l - 2 * cl - 0.05, -0.5, 0.0)
G._getCellCutout = lambda des, b, l, cl: _box(-2 * cl + 0.3, b - 0.3, -2 * cl + 0.3, l - 0.3, -0.5, 0.0)
fails = 0
def check(name, body, p, expect):
    global fails
    if body.contains(list(p)) != expect:
        fails += 1
        print('FAIL', name, [round(v, 3) for v in p], 'expected', expect)

for screw in L.MOUNT_SCREW_NAMES:
    for head in L.MOUNT_HEADS:
        cp = dict(L.CABINET_DEFAULTS, unitsW=3, wallMount=True, mountScrew=screw, mountHead=head,
                  mountRows=2, mountPerRow=3)
        cab = L.cabinet(cp)
        sc = L.mountScrew(cab['p'])
        assert not cab['errors'], (screw, head, cab['errors'])
        assert cab['backWall'] >= sc['depth'] + L.MOUNT_MIN_MATERIAL - 1e-9
        body = G.buildCabinet(None, cp)
        yIn = cab['innerBack']
        holes = L.mountHoles(cab)
        assert len(holes) == 6, holes
        for x, z in holes:
            check(f'{screw} hole through', body, (x, cab['back'] - 0.01, z), False)
            check(f'{screw} head flush inside', body, (x, yIn + 0.005, z + sc['headR'] - 0.02), False)
            check(f'{screw} material beside head', body, (x, yIn + 0.005, z + sc['headR'] + 0.03), True)
            check(f'{screw} material behind head', body, (x, cab['back'] - 0.02, z + sc['holeR'] + 0.03), True)
            check(f'{screw} nothing sticks into the drawer', body, (x, yIn - 0.01, z), False)
        print(screw, head, 'back wall', round(cab['backWall'] * 10, 2), 'mm')

# holes move off a divider
cp = dict(L.CABINET_DEFAULTS, unitsW=3, columns=2, wallMount=True, mountPerRow=1)
cab = L.cabinet(cp)
(x, z), = L.mountHoles(cab)
d0, d1 = cab['columns'][0][1], cab['columns'][1][0]
r = L.mountScrew(cab['p'])['headR']
assert not (d0 - r < x < d1 + r), ('hole on divider', x, d0, d1)
print('single hole moved from divider to x =', round(x, 2))
# hole outside the wall is reported
bad = L.cabinet(dict(L.CABINET_DEFAULTS, wallMount=True, mountTop=20.0))
assert bad['errors'], bad
print(bad['errors'])
# drawers get shorter by the thicker back wall
thin = L.insert(L.cabinet(dict(L.CABINET_DEFAULTS)), dict(L.INSERT_DEFAULTS))
thick = L.insert(L.cabinet(dict(L.CABINET_DEFAULTS, wallMount=True, mountScrew='M6', mountHead=L.HEAD_PAN)), dict(L.INSERT_DEFAULTS))
print('drawer depth', round((thin['y1'] - thin['y0']) * 10, 1), '->', round((thick['y1'] - thick['y0']) * 10, 1), 'mm with M6 pan head')
print('DONE fails', fails)
