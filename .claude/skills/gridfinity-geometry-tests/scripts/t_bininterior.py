"""Bin interior in memory (binInterior): compartments with rounded bottoms,
scoop at the front, label tab on the back wall (top clearance, rounded tip),
dividers lowered by the tab clearance - as binBodyGenerator builds them."""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import binInterior as B, const
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _box

fails = 0


def check(name, body, p, want):
    global fails
    if body.contains(list(p)) != want:
        fails += 1
        print('FAIL', name, [round(v, 3) for v in p], 'expected', want)


cl, wall = 0.025, 0.12
spec = {'x0': 0.0, 'x1': 2 * 4.2 - 2 * cl, 'y0': 0.0, 'y1': 4.2 - 2 * cl, 'bodyH': 3.0, 'wall': wall, 'cl': cl,
        'radius': const.BIN_CORNER_FILLET_RADIUS - cl, 'hasLip': True, 'hasScoop': True, 'scoopR': 1.0,
        'hasTab': True, 'tabLength': 1, 'tabWidth': const.BIN_TAB_WIDTH, 'tabPosition': 0,
        'tabAngle': math.radians(45), 'units': 2, 'unitW': 4.2, 'countX': 2, 'countY': 1,
        'compartments': [(0, 0, 1, 1, 1e9), (1, 0, 1, 1, 1e9)]}
body = _box(spec['x0'], spec['x1'], spec['y0'], spec['y1'], 0.0, spec['bodyH'])
B.applyInterior(body, spec)
pockets, (minX, maxX, minY, maxY) = B.compartments(spec)
expect_n = len(pockets) == 2
if not expect_n:
    fails += 1; print('FAIL two pockets')
x0, x1, y0, y1, zb = pockets[0]
xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
top = spec['bodyH']
check('pocket open', body, (xm, ym, top - 0.5), False)
check('floor under the pocket', body, (xm, ym, zb - 0.02), True)
check('bottom rounded at the side', body, (x0 + 0.02, ym, zb + 0.02), True)
check('... not further up', body, (x0 + 0.02, ym, zb + 0.4), False)
check('scoop at the front', body, (xm, y0 + 0.1, zb + 0.1), True)
check('scoop is a round', body, (xm, y0 + 0.5, zb + 0.5), False)
tz = top - const.BIN_TAB_TOP_CLEARANCE
check('label tab at the back', body, (xm, y1 - 0.3, tz - 0.05), True)
check('tab top clearance', body, (xm, y1 - 0.3, tz + 0.02), False)
check('tab underside 45 deg', body, (xm, y1 - 0.9, tz - 1.0), False)
check('tab tip rounded', body, (xm, y1 - const.BIN_TAB_WIDTH - 0.06, tz - 0.005), False)
check('tab only in its compartment span', body, (pockets[1][0] + 0.5, y1 - 0.3, tz - 0.05), True)
xd = (x1 + pockets[1][0]) / 2
check('divider', body, (xd, ym, top - 0.5), True)
check('divider lowered by the tab clearance', body, (xd, ym, top - 0.02), False)
check('outer wall stays full height', body, (spec['x0'] + 0.05, ym, top - 0.02), True)

# Label types: strip / slot on dividers and front wall, angled face, front sticker.
spec2 = dict(spec, countX=1, countY=2, compartments=[(0, 0, 1, 1, 1e9), (0, 1, 1, 1, 1e9)], hasScoop=False)
(px0, px1, py0, py1, pzb), (qx0, qx1, qy0, qy1, _) = B.compartments(spec2)[0]
xm = (px0 + px1) / 2
yc = py1 + wall / 2                                 # divider between front and back pocket


def build(**kw):
    b = _box(spec2['x0'], spec2['x1'], spec2['y0'], spec2['y1'], 0.0, spec2['bodyH'])
    B.applyInterior(b, dict(spec2, **kw))
    return b


b = build(labelType=B.LABEL_NONE)
check('none: no tab', b, (xm, py1 - 0.3, tz - 0.05), False)
b = build(labelType=B.LABEL_TAB)
check('tab type: original tab', b, (xm, py1 - 0.3, tz - 0.05), True)
for on in B.LABEL_ON:
    b = build(labelType=B.LABEL_STRIP, labelOn=on, stripWidth=0.8, labelDepth=0.02)
    div, front = on != B.ON_FRONT, on != B.ON_DIVIDERS
    check(f'strip {on}: on the divider', b, (xm, yc + 0.3, tz - 0.05), div)
    check(f'strip {on}: along the front wall', b, (xm, py0 + 0.4, tz - 0.05), front)
    check(f'strip {on}: no tab', b, (xm, py1 - 0.5, tz - 0.05), False)
b = build(labelType=B.LABEL_STRIP, labelOn=B.ON_BOTH, stripWidth=0.8, labelDepth=0.02)
check('strip: sticker recess', b, (xm, yc + 0.2, tz - 0.01), False)
check('strip: 45 deg underneath', b, (xm, yc + 0.35, tz - 0.4), False)
check('strip: no strip on the back wall', b, (xm, qy1 - 0.3, tz - 0.05), False)
b = build(labelType=B.LABEL_STRIP, labelOn=B.ON_BOTH, stripWidth=0.8, labelDepth=0.0)
check('strip, depth 0: flat', b, (xm, yc + 0.2, tz - 0.01), True)
b = build(labelType=B.LABEL_SLOT, labelOn=B.ON_DIVIDERS, stripWidth=1.2)
check('slot: window open on top', b, (xm, yc, tz - 0.01), False)
check('slot: channel under the lip', b, (xm, yc - 0.5, tz - B.SLOT_DEPTH + 0.01), False)
check('slot: lip over the channel', b, (xm, yc - 0.5, tz - 0.01), True)
check('slot: floor under the channel', b, (xm, yc, tz - B.SLOT_DEPTH - 0.03), True)
for on in B.WALL_ON:
    b = build(labelType=B.LABEL_WALL, wallOn=on, frontHeight=1.0, labelDepth=0.02)
    out, ins = on != B.WALL_INSIDE, on != B.WALL_FRONT
    check(f'wall {on}: recess in the outer front face', b, (xm, spec2['y0'] + 0.01, tz - 0.5), not out)
    check(f'wall {on}: front wall behind it', b, (xm, spec2['y0'] + 0.05, tz - 0.5), True)
    check(f'wall {on}: recess on the divider (back wall of the front pocket)', b, (xm, py1 + 0.01, tz - 0.5), not ins)
    check(f'wall {on}: divider keeps its back face', b, (xm, py1 + wall - 0.01, tz - 0.5), True)
    check(f'wall {on}: recess on the outer back wall', b, (xm, qy1 + 0.01, tz - 0.5), not ins)
    check(f'wall {on}: outer back face untouched', b, (xm, spec2['y1'] - 0.01, tz - 0.5), True)
# Label length: auto / nearly full = whole width; shorter = centred. Front
# recess stays clear of the rounded outer corners.
X0 = spec2['x0']
R = spec2['radius']
b = build(labelType=B.LABEL_WALL, wallOn=B.WALL_BOTH, frontHeight=1.25, labelDepth=0.02, labelLength=0.0)
rr = max(const.BIN_BODY_CUTOUT_BOTTOM_FILLET_RADIUS, spec2['radius'] - wall)
check('auto: inside recess up to the corner rounding', b, (px0 + rr + 0.05, py1 + 0.01, tz - 0.5), False)
check('auto: not into the corner rounding', b, (px0 + rr - 0.05, py1 + 0.01, tz - 0.5), True)
check('front recess not in the rounded corner', b, (X0 + R - 0.05, spec2['y0'] + 0.01, tz - 0.5), True)
check('front recess starts after the corner', b, (X0 + R + 0.15, spec2['y0'] + 0.01, tz - 0.5), False)
check('label height 12.5 mm', b, (xm, py1 + 0.01, tz - 0.1 - 1.2), False)
b = build(labelType=B.LABEL_WALL, wallOn=B.WALL_INSIDE, labelDepth=0.02, labelLength=2.0)
check('length 20 mm: centred', b, (xm, py1 + 0.01, tz - 0.5), False)
check('length 20 mm: not to the side wall', b, (px0 + 0.3, py1 + 0.01, tz - 0.5), True)
b = build(labelType=B.LABEL_WALL, wallOn=B.WALL_INSIDE, labelDepth=0.02, labelLength=(px1 - px0) - 2 * rr - 0.3)
check('length nearly full: whole width', b, (px0 + rr + 0.05, py1 + 0.01, tz - 0.5), False)

# Divider drop: default 0.5 mm below the rim, 0 = flush; labels follow.
b = build(labelType=B.LABEL_NONE, dividerDrop=0.0)
check('drop 0: divider flush with the rim', b, (xm, yc, spec2['bodyH'] - 0.02), True)
b = build(labelType=B.LABEL_NONE, dividerDrop=0.2)
check('drop 2 mm: divider lower', b, (xm, yc, spec2['bodyH'] - 0.15), False)
check('drop 2 mm: divider below that', b, (xm, yc, spec2['bodyH'] - 0.25), True)
b = build(labelType=B.LABEL_STRIP, labelOn=B.ON_DIVIDERS, stripWidth=0.8, labelDepth=0.0, dividerDrop=0.0)
check('drop 0: strip flush too', b, (xm, yc + 0.3, spec2['bodyH'] - 0.02), True)
print('DONE fails', fails)
