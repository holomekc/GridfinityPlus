"""
GridfinityPlus - bin interior (compartments, scoop, label tabs) in memory.

Mirrors binBodyGenerator's compartment logic with TemporaryBRep booleans, so
the bin dialog's preview shows the same interior as the result, and the
result no longer costs a few parametric features (extrude, three fillets, a
tab sketch...) per compartment. The solid outside (feet, walls, lip) still
comes from the parametric generator, built once per outside configuration.

All lengths in cm, bin local frame (body from x0..x1, y0..y1, top at bodyH).
"""

import math

import adsk.core, adsk.fusion

from . import const
from .baseplateFastPreview import _box, _roundedSlab, _tmgr, _union, _subtract, _unionAll

_EPS = 0.001

# Label types (one per bin, on every compartment). The label tab is the
# original Gridfinity one; the others are narrow, so they hardly get in the
# way when taking things out.
LABEL_NONE = 'None'
LABEL_TAB = 'Label tab'
LABEL_STRIP = 'Sticker strip'
LABEL_WALL = 'Wall sticker'
LABEL_SLOT = 'Paper slot'
LABEL_TYPES = (LABEL_NONE, LABEL_TAB, LABEL_STRIP, LABEL_WALL, LABEL_SLOT)
# Where strips sit: on the front-to-back dividers and / or
# along the bin's front wall.
ON_BOTH = 'Dividers + front wall'
ON_DIVIDERS = 'Dividers'
ON_FRONT = 'Front wall'
LABEL_ON = (ON_BOTH, ON_DIVIDERS, ON_FRONT)
# Where wall stickers sit: the bin's outside front face and / or inside each
# compartment on its back wall (the face you look at).
WALL_BOTH = 'Front face + compartments'
WALL_FRONT = 'Front face'
WALL_INSIDE = 'Compartments'
WALL_ON = (WALL_BOTH, WALL_FRONT, WALL_INSIDE)
STICKER_MARGIN = 0.1        # rim left around a recess
LABEL_SNAP = 0.5            # a label length leaving less than this free runs the full width
TAPE_HEIGHT = 1.25          # recess height: 12 mm label tape (Brother / Dymo) + play
STRIP_THICKNESS = 0.1       # strip: flat top this thick, 45 deg below
SLOT_STRIP_THICKNESS = 0.18
SLOT_DEPTH = 0.08           # paper slot: channel this deep, lips at 45 deg
SLOT_RIM = 0.06             # strip left beside the channel at its bottom


def _cutHalf(body, point, normal, size=200.0):
    """Remove everything on the `normal` side of the plane through `point`."""
    n = adsk.core.Vector3D.create(*normal)
    n.normalize()
    ref = adsk.core.Vector3D.create(0, 0, 1) if abs(n.z) < 0.9 else adsk.core.Vector3D.create(1, 0, 0)
    w = n.crossProduct(ref)
    w.normalize()
    center = adsk.core.Point3D.create(point[0] + n.x * size / 2, point[1] + n.y * size / 2,
                                      point[2] + n.z * size / 2)
    obb = adsk.core.OrientedBoundingBox3D.create(center, n, w, size, size, size)
    _subtract(body, _tmgr().createBox(obb))


def _cyl(p0, p1, r):
    return _tmgr().createCylinderOrCone(adsk.core.Point3D.create(*p0), r, adsk.core.Point3D.create(*p1), r)


def _sphere(c, r):
    return _tmgr().createSphere(adsk.core.Point3D.create(*c), r)


def tray(x0, x1, y0, y1, zb, zt, r):
    """Pocket with vertical corners and bottom edges rounded by r (the
    generator's inner cutout: vertical fillets + bottom fillet chain)."""
    r = max(0.0, min(r, (x1 - x0) / 2 - _EPS, (y1 - y0) / 2 - _EPS, zt - zb - _EPS))
    if r <= 0:
        return _box(x0, x1, y0, y1, zb, zt)
    a0, a1, b0, b1, zr = x0 + r, x1 - r, y0 + r, y1 - r, zb + r
    parts = [_roundedSlab(x0, x1, y0, y1, zr, zt, r), _box(a0, a1, b0, b1, zb, zr + _EPS)]
    for y in (b0, b1):
        parts.append(_cyl((a0, y, zr), (a1, y, zr), r))
    for x in (a0, a1):
        parts.append(_cyl((x, b0, zr), (x, b1, zr), r))
    for x in (a0, a1):
        for y in (b0, b1):
            parts.append(_sphere((x, y, zr), r))
    return _unionAll(parts)


def scoopFill(x0, x1, y0, zb, s):
    """Material the scoop leaves at the front (min y) of a pocket: a quarter
    round of radius s along the front bottom edge."""
    fill = _box(x0 - _EPS, x1 + _EPS, y0 - _EPS, y0 + s, zb - _EPS, zb + s)
    _subtract(fill, _cyl((x0 - 0.1, y0 + s, zb + s), (x1 + 0.1, y0 + s, zb + s), s))
    return fill


def labelTab(x0, x1, yBack, zTop, width, angle):
    """The generator's label tab: a wedge on the compartment's back wall, top
    face flat at zTop, `width` deep (plus the tip rounding), underside at
    `angle` from vertical, tip rounded by BIN_TAB_EDGE_FILLET_RADIUS."""
    f = const.BIN_TAB_EDGE_FILLET_RADIUS
    theta = math.radians(90) - angle                      # angle at the tip
    w = width + f / math.tan(theta / 2)
    h = w / math.tan(angle)
    yTip = yBack - w
    body = _box(x0, x1, yTip, yBack, zTop - h, zTop)
    # Underside: from (yBack, zTop - h) up to the tip (yTip, zTop).
    _cutHalf(body, (0, yBack, zTop - h), (0, -h, -w))
    # Tip rounding: replace the tip beyond its tangent points by the arc.
    t = f / math.tan(theta / 2)
    d = f / math.sin(theta / 2)
    # bisector of the tip: between +y (top edge) and down the underside
    uy, uz = 1.0, 0.0
    sy, sz = w / math.hypot(w, h), -h / math.hypot(w, h)
    by, bz = uy + sy, uz + sz
    bl = math.hypot(by, bz)
    cy, cz = yTip + d * by / bl, zTop + d * bz / bl
    p1 = (yTip + t, zTop)                                 # tangent on the top
    p2 = (yTip + t * sy, zTop + t * sz)                   # tangent on the underside
    tip = _box(x0, x1, yTip, yBack, zTop - h, zTop)
    # keep the side of the chord p1-p2 that holds the tip
    ny, nz = -(p2[1] - p1[1]), (p2[0] - p1[0])
    if ny * (yTip - p1[0]) + nz * (zTop - p1[1]) > 0:
        ny, nz = -ny, -nz
    _cutHalf(tip, (0, p1[0], p1[1]), (0, ny, nz))
    _subtract(body, tip)
    arc = _cyl((x0, cy, cz), (x1, cy, cz), f)
    wedge = _box(x0, x1, yTip, yBack, zTop - h, zTop)
    _cutHalf(wedge, (0, yBack, zTop - h), (0, -h, -w))
    _tmgr().booleanOperation(arc, wedge, adsk.fusion.BooleanTypes.IntersectionBooleanType)
    _union(body, arc)
    return body


def strip(x0, x1, ya, yb, zTop, thickness, sideA=True, sideB=True):
    """Flat label strip ya..yb, top at zTop, `thickness` thick, 45 deg below
    on the open sides (sideA: the ya side, sideB: the yb side)."""
    drop = thickness + (yb - ya)
    body = _box(x0, x1, ya, yb, zTop - drop, zTop)
    if sideA:
        _cutHalf(body, (0, ya, zTop - thickness), (0, -1, -1))
    if sideB:
        _cutHalf(body, (0, yb, zTop - thickness), (0, 1, -1))
    return body


def slotChannel(x0, x1, y0, y1, zTop, depth):
    """Paper slot: channel y0..y1 at its bottom (depth below zTop), sides at
    45 deg to a narrower opening on top - the lips hold a paper strip that
    is bowed in."""
    ch = _box(x0, x1, y0, y1, zTop - depth, zTop + 0.01)
    _cutHalf(ch, (0, y0, zTop - depth), (0, -1, 1))
    _cutHalf(ch, (0, y1, zTop - depth), (0, 1, 1))
    return ch


def _span(a, b, length):
    """x range of a label `length` long centred in a..b; 0 (auto) or nearly
    the whole space: all of a..b."""
    if length <= 0 or length >= (b - a) - LABEL_SNAP:
        return a, b
    c = (a + b) / 2
    return c - length / 2, c + length / 2


def compartments(spec):
    """[(x0, x1, y0, y1, zBottom)] pockets, as binBodyGenerator lays them out."""
    wall, cl = spec['wall'], spec['cl']
    minX, maxX = spec['x0'] + wall, spec['x1'] - wall
    minY = spec['y0'] + ((const.BIN_LIP_WALL_THICKNESS - cl) if spec['hasLip'] and spec['hasScoop'] else wall)
    maxY = spec['y1'] - wall
    cx, cy = max(1, int(spec['countX'])), max(1, int(spec['countY']))
    uW = (maxX - minX - (cx - 1) * wall) / cx
    uL = (maxY - minY - (cy - 1) * wall) / cy
    out = []
    for px, py, w, l, depth in spec['compartments']:
        ox = minX + px * (uW + wall)
        oy = minY + py * (uL + wall)
        cw = uW * w + (w - 1) * wall
        cL = uL * l + (l - 1) * wall
        d = min(spec['bodyH'] - const.BIN_COMPARTMENT_BOTTOM_THICKNESS, depth)
        out.append((ox, ox + cw, oy, oy + cL, spec['bodyH'] - d))
    return out, (minX, maxX, minY, maxY)


def applyInterior(body, spec):
    """Cut the compartments into the solid bin `body` and add the label tabs
    (binBodyGenerator order: all cuts first, then the tabs)."""
    top = spec['bodyH']
    r = max(const.BIN_BODY_CUTOUT_BOTTOM_FILLET_RADIUS, spec['radius'] - spec['wall'])
    pockets, (minX, maxX, minY, maxY) = compartments(spec)
    cuts, adds, marks = [], [], []
    kind = spec.get('labelType', LABEL_TAB if spec.get('hasTab') else LABEL_NONE)
    on = spec.get('labelOn', ON_BOTH)
    depth = spec.get('labelDepth', 0.02)
    # Dividers (and the labels on them) sit this far below the rim; 0 = flush.
    drop = max(0.0, spec.get('dividerDrop', const.BIN_TAB_TOP_CLEARANCE))
    tabTop = top - drop
    m = STICKER_MARGIN
    length = spec.get('labelLength', 0.0)
    R = spec['radius']                                    # outer corner rounding
    for x0, x1, y0, y1, zb in pockets:
        pocket = tray(x0, x1, y0, y1, zb, top, r)
        if spec['hasScoop']:
            s = min(spec['scoopR'], top - zb)
            if s > r:
                _subtract(pocket, scoopFill(x0, x1, y0, zb, s))
        cuts.append(pocket)
        atFront = y0 < minY + 0.01
        hasDivider = y1 < maxY - 0.01                     # a divider behind (not the back wall)
        if kind == LABEL_TAB:
            span = max(0.0, min(spec['tabLength'], spec['units'])) * spec['unitW']
            tx0 = x0 + max(0.0, min(spec['tabPosition'], spec['units'] - spec['tabLength'])) * spec['unitW']
            if span > 0:
                tab = labelTab(tx0, tx0 + span, y1, tabTop, spec['tabWidth'], spec['tabAngle'])
                _tmgr().booleanOperation(tab, _tmgr().copy(pocket), adsk.fusion.BooleanTypes.IntersectionBooleanType)
                adds.append(tab)
        elif kind in (LABEL_STRIP, LABEL_SLOT):
            w = spec.get('stripWidth', 0.8)
            t = SLOT_STRIP_THICKNESS if kind == LABEL_SLOT else STRIP_THICKNESS
            spans = []
            if hasDivider and on in (ON_BOTH, ON_DIVIDERS):
                yc = y1 + spec['wall'] / 2                # centred on the divider
                spans.append((yc - w / 2, yc + w / 2, True, True))
            if atFront and on in (ON_BOTH, ON_FRONT):
                spans.append((y0 - 0.01, y0 + w - spec['wall'] / 2, False, True))   # on the front wall
            for ya, yb, sa, sb in spans:
                adds.append(strip(x0, x1, ya, yb, tabTop, t, sa, sb))
                lo, hi = (ya + m if sa else y0 + m / 2), yb - m
                if kind == LABEL_STRIP and depth > 0:
                    la, lb = _span(x0 + m, x1 - m, length)
                    marks.append(_box(la, lb, lo, hi, tabTop - depth, tabTop + 0.01))
                elif kind == LABEL_SLOT:
                    marks.append(slotChannel(x0 - 0.1, x1 + 0.1, lo - m + SLOT_RIM, hi + m - SLOT_RIM,
                                             tabTop, SLOT_DEPTH))
        elif kind == LABEL_WALL and depth > 0:
            h = spec.get('frontHeight', TAPE_HEIGHT)
            where = spec.get('wallOn', WALL_BOTH)
            if atFront and where in (WALL_BOTH, WALL_FRONT):
                # Outside front face, under the rim, clear of the rounded corners.
                zt = top - m
                la, lb = _span(max(x0, spec['x0'] + R + m), min(x1, spec['x1'] - R - m), length)
                if lb - la > 0.2:
                    marks.append(_box(la, lb, spec['y0'] - 0.01, spec['y0'] + depth, max(zb, zt - h), zt))
            if where in (WALL_BOTH, WALL_INSIDE):
                # Inside: the compartment's back wall (divider or outer wall),
                # the face you look at, under its top.
                zt = tabTop - m
                la, lb = _span(x0 + r, x1 - r, length)       # the flat part, not the corner roundings
                marks.append(_box(la, lb, y1 - 0.01, y1 + depth, max(zb + r, zt - h), zt))
    if len(pockets) > 1 and drop > 0:
        cuts.append(_roundedSlab(minX, maxX, minY, maxY, top - drop, top, r))
    if cuts:
        _subtract(body, _unionAll(cuts))
    if adds:
        _union(body, _unionAll(adds))
    if marks:
        _subtract(body, _unionAll(marks))
    return body
