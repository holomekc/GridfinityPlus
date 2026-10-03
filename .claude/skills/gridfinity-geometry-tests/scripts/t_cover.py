import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import cabinetGeometry as G, coverGeometry as C
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _box

G._getFoot = lambda des, b, l, cl, *a: _box(0.05, b - 2 * cl - 0.05, 0.05, l - 2 * cl - 0.05, -0.5, 0.0)
fails = 0
def check(name, body, p, expect):
    global fails
    if body.contains(list(p)) != expect:
        fails += 1
        print('FAIL', name, p, 'expected', expect)

p = dict(C.COVER_DEFAULTS, unitsW=3, unitsL=2)
b = C.buildCover(None, p)
check('slab', b, (6.0, 4.0, 0.05), True)
check('above slab', b, (6.0, 4.0, 0.15), False)
check('foot cell 0', b, (2.0, 2.0, -0.25), True)
check('foot cell 2,1', b, (10.4, 6.2, -0.25), True)
check('between feet', b, (4.175, 2.0, -0.25), False)
check('outside footprint', b, (12.6, 4.0, 0.05), False)
check('rounded corner', b, (0.02, 0.02, 0.05), False)
t = dict(p, thickness=0.5)
check('thicker', C.buildCover(None, t), (6.0, 4.0, 0.45), True)
# fill to edge: border front 0.5, partial cell left 1.0
o = dict(p, ovh={'left': 1.0, 'right': 0.0, 'front': 0.5, 'back': 0.0,
                 'partial': {'left': True, 'right': False, 'front': False, 'back': False}})
ob = C.buildCover(None, o)
check('ovh slab left', ob, (-0.9, 4.0, 0.05), True)
check('ovh slab front', ob, (6.0, -0.45, 0.05), True)
check('partial foot', ob, (-0.5, 2.0, -0.25), True)
check('partial foot clipped', ob, (-1.5, 2.0, -0.25), False)
check('no foot under border', ob, (6.0, -0.3, -0.25), False)
assert C.errors(dict(p, thickness=0.05)) and not C.errors(p)
assert abs(C.COVER_DEFAULTS['thickness'] - 0.1) < 1e-9
print(C.describe(p))
print('DONE fails', fails)
