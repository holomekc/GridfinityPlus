"""Baseplate outline: only clean ends are rounded; corners next to a partial
cell stay square (final plate via cutToSize and the fast preview)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import plateLayout as PL, plateSplit as S
from GridfinityPlus.lib.gridfinityUtils import baseplateFastPreview as P
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _box

P._getCellCutout = lambda des, b, l, cl: _box(1.0, 3.0, 1.0, 3.0, -0.3, 0.1)   # keep corners solid
fails = 0


def check(name, body, p, expect):
    global fails
    if body.contains(list(p)) != expect:
        fails += 1
        print('FAIL', name, [round(v, 3) for v in p], 'expected', expect)


base = dict(baseWidth=4.2, baseLength=4.2, xyClearance=0.025, plateWidth=3, plateLength=2,
            layoutVersion=3, sizeMode=PL.SIZE_CELLS, plateType='Light', extraBottomThickness=0.0,
            hasMagnetSockets=False, hasScrewHoles=False, splitMode=S.SPLIT_OFF,
            edgeLeft=PL.EDGE_PARTIAL, borderLeft=0.9, edgeRight=PL.EDGE_FLUSH,
            edgeFront=PL.EDGE_FLUSH, edgeBack=PL.EDGE_FLUSH)
x0, x1, y0, y1, zb = PL.localExtents(base)
z, d = zb / 2, 0.03
final = PL.cutToSize(_box(x0 - 5, x1 + 5, y0 - 5, y1 + 5, zb - 1, 0.0), base)
preview = P.buildPreviewPlate(None, base)
for name, body in (('final', final), ('preview', preview)):
    check(f'{name}: front-left (partial) square', body, (x0 + d, y0 + d, z), True)
    check(f'{name}: back-left (partial) square', body, (x0 + d, y1 - d, z), True)
    check(f'{name}: front-right rounded', body, (x1 - d, y0 + d, z), False)
    check(f'{name}: back-right rounded', body, (x1 - d, y1 - d, z), False)
print('DONE fails', fails)
