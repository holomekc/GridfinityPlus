"""Bin stacking: lip top height (where a stacked bin sits) and the move of a
stacked bin when the one below changes (delta = new * old^-1)."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
import adsk.core
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import binFeature as B, const

fails = 0


def expect(name, ok, info=''):
    global fails
    if not ok:
        fails += 1
        print('FAIL', name, info)


geom = lambda lip, body=True: {'with_lip': {'id': 'with_lip', 'value': lip, 'type': 'bool'},
                               'bin_generate_body': {'id': 'bin_generate_body', 'value': body, 'type': 'bool'}}
# 3 units x 7 mm: body top at 2*0.7 + 0.2 = 1.6, stacked bin sits 0.5 above (lip foot cutout top)
z = B.lipTopZ({'binH': 3, 'heightUnit': 0.7, 'geom': geom(True)})
expect('lip top 3u', abs(z - (1.6 + const.BIN_BASE_HEIGHT)) < 1e-9, z)
expect('no lip -> not stackable', B.lipTopZ({'binH': 3, 'heightUnit': 0.7, 'geom': geom(False)}) is None)
expect('no body -> not stackable', B.lipTopZ({'binH': 3, 'heightUnit': 0.7, 'geom': geom(True, False)}) is None)
expect('old flat geom values', B.lipTopZ({'binH': 3, 'heightUnit': 0.7, 'geom': {'with_lip': True}}) is not None)

# delta = new * old^-1 moves a body placed with old onto new
def mat(dx, dy, dz, rot=0):
    m = adsk.core.Matrix3D.create()
    if rot:
        m.setToRotation(math.radians(rot), adsk.core.Vector3D.create(0, 0, 1), adsk.core.Point3D.create(0, 0, 0))
    t = adsk.core.Matrix3D.create()
    t.translation = adsk.core.Vector3D.create(dx, dy, dz)
    m.transformBy(t)
    return m

old, new = mat(4.2, 0, 2.1, 90), mat(8.4, 4.2, 3.5, 0)
delta = adsk.core.Matrix3D.create()
delta.setWithArray(list(old.asArray()))
delta.invert()
delta.transformBy(new)
for p in ((0, 0, 0), (1, 2, 3), (4.1, 0.5, -0.4)):
    a = adsk.core.Point3D.create(*p); a.transformBy(old); a.transformBy(delta)
    b = adsk.core.Point3D.create(*p); b.transformBy(new)
    expect('delta moves old placement onto new', max(abs(u - v) for u, v in zip(a.asArray(), b.asArray())) < 1e-9, p)
print('DONE fails', fails)
