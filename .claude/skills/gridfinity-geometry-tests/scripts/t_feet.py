"""Feet never stick out past the walls (cabinet + cover). Uses a fake foot as
large as the real one: cell + xy clearance on every side, like baseGenerator."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import cabinetGeometry as G, cabinetLayout as L, coverGeometry as C
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _box

G._getFoot = lambda des, b, l, cl, *a: _box(-cl, b - cl, -cl, l - cl, -0.5, 0.0)   # real size
G._getCellCutout = lambda des, b, l, cl: _box(-2 * cl + 0.3, b - 0.3, -2 * cl + 0.3, l - 0.3, -0.5, 0.0)
fails = 0


def check(name, body, p, expect):
    global fails
    if body.contains(list(p)) != expect:
        fails += 1
        print('FAIL', name, [round(v, 3) for v in p], 'expected', expect)


for units in ((1, 1), (2, 3)):
    cp = dict(L.CABINET_DEFAULTS, unitsW=units[0], unitsL=units[1])
    cab = L.cabinet(cp)
    body = G.buildCabinet(None, cp)
    aW, aL = cab['aW'], cab['aL']
    z = -0.25
    for name, pt in (('left', (-0.01, aL / 2, z)), ('right', (aW + 0.01, aL / 2, z)),
                     ('front', (aW / 2, -0.01, z)), ('back', (aW / 2, aL + 0.01, z))):
        check(f'cabinet {units} foot not past the {name} wall', body, pt, False)
    check(f'cabinet {units} foot still there', body, (aW / 2, aL / 2, z), True)
    cov = C.buildCover(None, dict(C.COVER_DEFAULTS, unitsW=units[0], unitsL=units[1]))
    check(f'cover {units} foot not past the left edge', cov, (-0.01, aL / 2 if units[1] == 1 else 2.0, z), False)

# partial cell on the left: feet reach into it, but not past the outline
cp = dict(L.CABINET_DEFAULTS, unitsW=2, ovh={'left': 1.0, 'right': 0, 'front': 0, 'back': 0,
                                             'partial': {'left': True}})
body = G.buildCabinet(None, cp)
check('partial: foot under the partial cell', body, (-0.5, 2.0, -0.25), True)
check('partial: not past the outline', body, (-1.01, 2.0, -0.25), False)
check('partial: right side still trimmed', body, (L.cabinet(cp)['aW'] + 0.01, 2.0, -0.25), False)
print('DONE fails', fails)
