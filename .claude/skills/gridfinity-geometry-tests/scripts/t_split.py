import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
# Folder that CONTAINS the GridfinityPlus package (scripts -> skill -> skills -> .claude -> add-in -> parent).
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import plateSplit as S, plateLayout as PL
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _box
fails = 0
def check(n, b, p, e):
    global fails
    if b.contains(list(p)) != e:
        fails += 1; print('FAIL', n, p, 'expected', e)
base = dict(baseWidth=4.2, baseLength=4.2, xyClearance=0.025, plateWidth=13, plateLength=8,
            layoutVersion=3, sizeMode='Cells', plateType='Full', extraBottomThickness=0.64,
            splitMode=S.SPLIT_MAX, splitMaxWidth=25.0, splitMaxDepth=25.0)
pl = S.plan(base)
print('plan', pl['tiles'], [round(v, 3) for v in pl['xs']], [round(v, 3) for v in pl['ys']], [round(w, 2) for w in pl['widths']], S.describe(base))
x0, x1, y0, y1, zb = PL.localExtents(base)
plate = _box(x0, x1, y0, y1, zb, 0.0)
t = S.split(plate, base)
s = pl['xs'][0]; m = 1 * 4.2 + 2.1 - 0.025   # middle of cell row 1 edge
check('left of seam', t, (s - 0.05, 3.0, -0.6), True)
check('seam gap', t, (s, 3.0, -0.6), False)
check('right of seam', t, (s + 0.05, 3.0, -0.6), True)
check('tab head in right tile area', t, (s + 0.25, m, -0.6), True)
check('socket gap around tab head', t, (s + 0.3 + 0.007, m, -0.6), False)
check('tab neck', t, (s + 0.02, m, -0.6), True)
check('right tile beside socket', t, (s + 0.05, m + 0.6, -0.6), True)
# dovetail undercut: right tile material at head-corner, behind the neck
check('undercut holds', t, (s + 0.04, m + 0.38, -0.6), True)
ys = pl['ys'][0]; mx = 2 * 4.2 + 2.1 - 0.025
check('y seam gap', t, (3.0, ys, -0.6), False)
check('y tab', t, (mx, ys + 0.25, -0.6), True)
check('cross point gap', t, (s, ys, -0.6), False)
off = dict(base, splitMode=S.SPLIT_OFF)
assert S.split(plate, off) is plate
small = dict(base, plateWidth=4, plateLength=4)
print('small', S.describe(small))
light = dict(base, plateType='Light')
tl = S.split(_box(x0, x1, y0, y1, -0.5, 0.0), light)
check('light tab', tl, (s + 0.17, m, -0.3), True)
tooBig = dict(base, splitMaxWidth=4.0)
print('too big', S.describe(tooBig))
import math
d, neck, head, c = 0.3, 0.5, 0.8, 0.015
flare = (head - neck) / 2; L = math.hypot(flare, d); n = (-flare / L, d / L)
for k in range(1, 10):
    tt = k / 10
    px, py = s + tt * d, m + neck / 2 + tt * flare
    for f, e, nm in ((-0.3, True, 'tab'), (0.3, False, 'gap'), (0.7, False, 'gap'), (1.4, True, 'socket wall')):
        check('flank %s t=%.1f' % (nm, tt), t, (px + n[0] * c * f, py + n[1] * c * f, -0.6), e)
# head end face gap
check('head end gap', t, (s + d + c * 0.5, m, -0.6), False)
check('head end wall', t, (s + d + c * 1.5, m, -0.6), True)
ps = S.pieces(plate, base)
assert len(ps) == 6, len(ps)
# tile 0 = front-left, tile 1 = front-middle, tile 3 = back-left
check('piece0 has front-left', ps[0], (3.0, 3.0, -0.6), True)
check('piece0 not front-middle', ps[0], (s + 3.0, 3.0, -0.6), False)
check('piece1 has front-middle', ps[1], (s + 3.0, 3.0, -0.6), True)
check('piece0 owns its tab', ps[0], (s + 0.25, m, -0.6), True)
check('piece1 not at tab', ps[1], (s + 0.25, m, -0.6), False)
check('piece3 back-left', ps[3], (3.0, ys + 3.0, -0.6), True)
assert len(S.pieces(plate, off)) == 1
print('DONE fails', fails)
