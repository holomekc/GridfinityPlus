"""
GridfinityPlus — box system geometry (cabinet + inserts).

Built entirely from TemporaryBRepManager primitives and booleans, so the dialog
ghost IS the final geometry and costs milliseconds. Only the Gridfinity foot and
the baseplate cell cutout are parametric (built once per configuration and
cached by binFastPreview / baseplateFastPreview).

Printability: every overhang is 45° (ledge undersides, groove/runner flanks,
handle undersides, teardrop knob); the only horizontal spans are bridges
(bar handle top, slot top). Print the cabinet upright or on its back, inserts
bottom down.

Dimensions come from cabinetLayout. All lengths in cm, cabinet local frame.
"""

import adsk.core, adsk.fusion
import math

from . import const
from . import gplog
from . import cabinetLayout as L
from .baseplateFastPreview import (_tmgr, _box, _union, _subtract, _translate,
                                   _unionAll, _roundedSlab, _getCellCutout)
from .binFastPreview import _getFoot

_EPS = 0.02
# How far a notch / finger hole continues through dividers behind the front.
GRIP_REACH = 2.5
_SQRT2 = math.sqrt(2.0)


# ------------------------------------------------------------------ primitives

def _cylinderAxis(p0, p1, radius):
    return _tmgr().createCylinderOrCone(
        adsk.core.Point3D.create(*p0), radius, adsk.core.Point3D.create(*p1), radius)


def _cone(p0, r0, p1, r1):
    return _tmgr().createCylinderOrCone(
        adsk.core.Point3D.create(*p0), r0, adsk.core.Point3D.create(*p1), r1)


def _cutHalfSpace(body, point, normal, size=200.0):
    """Remove everything on the `normal` side of the plane through `point`."""
    n = adsk.core.Vector3D.create(*normal)
    n.normalize()
    ref = adsk.core.Vector3D.create(0, 0, 1) if abs(n.z) < 0.9 else adsk.core.Vector3D.create(1, 0, 0)
    w = n.crossProduct(ref)
    w.normalize()
    center = adsk.core.Point3D.create(point[0] + n.x * size / 2,
                                      point[1] + n.y * size / 2,
                                      point[2] + n.z * size / 2)
    obb = adsk.core.OrientedBoundingBox3D.create(center, n, w, size, size, size)
    _subtract(body, _tmgr().createBox(obb))


def _prismXZ(xa, xb, y0, y1, za, zb, cuts):
    """Box x[xa,xb] y[y0,y1] z[za,zb] trimmed by half-spaces [(point, normal)]
    — a prism along y with a convex XZ profile."""
    body = _box(min(xa, xb), max(xa, xb), y0, y1, min(za, zb), max(za, zb))
    for point, normal in cuts:
        _cutHalfSpace(body, point, normal)
    return body


def _prismYZ(x0, x1, ya, yb, za, zb, cuts):
    """Same, as a prism along x with a convex YZ profile."""
    body = _box(x0, x1, min(ya, yb), max(ya, yb), min(za, zb), max(za, zb))
    for point, normal in cuts:
        _cutHalfSpace(body, point, normal)
    return body


def _slab(x0, x1, y0, y1, z0, z1, rFront, rBack):
    """Box with vertical corner fillets, separate radius front (y0) / back."""
    return _slabCorners(x0, x1, y0, y1, z0, z1, rFront, rFront, rBack, rBack)


def _slabCorners(x0, x1, y0, y1, z0, z1, rFL, rFR, rBL, rBR):
    """Box with vertical corner fillets, one radius per corner (front = y0)."""
    body = _box(x0, x1, y0, y1, z0, z1)
    for cx, cy, r, sx, sy in ((x0, y0, rFL, 1, 1), (x1, y0, rFR, -1, 1),
                              (x0, y1, rBL, 1, -1), (x1, y1, rBR, -1, -1)):
        if r <= 0:
            continue
        _subtract(body, _box(min(cx, cx + sx * r), max(cx, cx + sx * r),
                             min(cy, cy + sy * r), max(cy, cy + sy * r), z0 - 1, z1 + 1))
        _union(body, _cylinderAxis((cx + sx * r, cy + sy * r, z0), (cx + sx * r, cy + sy * r, z1), r))
    return body


# ------------------------------------------------------------- cabinet parts

def _ledge(xFace, side, y0, y1, zTop, thickness, depth):
    """Shelf strip on a wall face. side=+1: protrudes +x, -1: protrudes -x.
    Flat top, 45° chamfer underneath (prints upright without support)."""
    zLow = zTop - thickness - depth
    xa = xFace - side * _EPS
    xb = xFace + side * depth
    return _prismXZ(xa, xb, y0, y1, zLow, zTop,
                    [((xFace, 0, zLow), (side, 0, -1))])


def _grooveTool(xFace, side, y0, y1, center, depth):
    """V-groove cutter into a wall face. side=+1: the wall is at -x of the face
    (groove goes -x), -1: wall at +x. 45° flanks, flat tip."""
    tip = L.GROOVE_TIP
    xTip = xFace - side * depth
    half = tip / 2 + depth
    return _prismXZ(xTip, xFace + side * _EPS, y0 - 0.1, y1, center - half - _EPS, center + half + _EPS,
                    [((xTip, 0, center + tip / 2), (-side, 0, 1)),
                     ((xTip, 0, center - tip / 2), (-side, 0, -1))])


def _runner(xFace, side, y0, y1, center, depth, fit, xEmbed):
    """Insert runner that rides in a groove (same profile, offset by `fit`)."""
    tip = L.GROOVE_TIP
    xTip = xFace - side * depth
    shift = fit * _SQRT2
    half = tip / 2 + depth + 0.3
    return _prismXZ(xTip + side * fit, xEmbed, y0, y1, center - half, center + half,
                    [((xTip, 0, center + tip / 2 - shift), (-side, 0, 1)),
                     ((xTip, 0, center - tip / 2 + shift), (-side, 0, -1))])


def _detentCylinder(strip, y, radius):
    xa, xb, z = strip
    return _cylinderAxis((xa, y, z), (xb, y, z), radius)


def _prismXY(x0, x1, y0, y1, za, zb, cuts):
    """Same as _prismXZ, as a prism along z with a convex XY profile."""
    body = _box(min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1), za, zb)
    for point, normal in cuts:
        _cutHalfSpace(body, point, normal)
    return body


def _snapHook(cab, ip):
    """Hook geometry shared by the insert and the cabinet catch:
    (y of the hook's front at the outer face, its length, reach p)."""
    lat = float(cab['p']['fitLateral'])
    p = lat + L.SNAP_ENGAGE
    kH, kL = _kAngle(L.SNAP_HOLD_ANGLE), _kAngle(L.SNAP_LEAD_ANGLE)
    y0 = cab['front'] + L.SNAP_Y0 + 0.02
    return y0, p * (kH + kL), p, kH, kL, lat


def snapCatches(cab):
    """Catches cut into the cabinet walls, one per slot side: the hook of
    an insert's snap tongue clicks in here when it is closed."""
    if not cab['snap']:
        return []
    hy0, hookLen, p, kH, kL, lat = _snapHook(cab, None)
    fb = float(cab['p']['fitBack'])
    c = L.SNAP_CLEARANCE
    dc = L.SNAP_ENGAGE + c                          # depth into the wall
    yb = hy0 + hookLen
    tools = []
    for x0, x1 in cab['columns']:
        for r in range(len(cab['rows'])):
            bands = L.snapBands(cab, r)
            for face, d, band in ((x0, -1, bands['left']), (x1, 1, bands['right'])):
                if band is None:
                    continue
                zs, zt = band
                yF = hy0 + kH * lat - c * math.sqrt(1 + kH * kH)      # flank parallel to the hook
                yB = yb - kL * lat + fb + c * math.sqrt(1 + kL * kL)
                tools.append(_prismXY(face - 0.01 * d, face + dc * d, yF - kH * dc - 0.05,
                                      yB + 0.05, zs - c, zt + c,
                                      [((face, yF, 0), (kH * d, -1, 0)),
                                       ((face, yB, 0), (kL * d, 1, 0))]))
    return tools


def _snapTongues(cab, ins, tw, cuts, adds, keepOut):
    """Spring tongue + hook in both side walls of the insert (see
    cabinetLayout SNAP_*). Slots above and below run at 45 deg through the
    wall, so nothing hangs in the air when printing and the tongue can still
    bend inwards freely."""
    hy0, hookLen, p, kH, kL, lat = _snapHook(cab, ins['p'])
    ty0 = cab['front'] + L.SNAP_Y0
    ty1 = ty0 + L.SNAP_LEN
    if ins['y1'] - ins['y0'] < L.SNAP_Y0 + L.SNAP_LEN + 0.3:
        return
    bands = L.snapBands(cab, ins['slot']['row'] - 1)
    g = L.SNAP_GAP
    gg = g * _SQRT2
    for xo, sx, band in ((ins['x0'], 1, bands['left']), (ins['x1'], -1, bands['right'])):
        if band is None:
            continue
        zs, zt = band
        xa, xb = sorted((xo - sx * 0.01, xo + sx * (tw + 0.01)))
        # u = depth into the wall from the outside: sx * (x - xo).
        cuts.append(_prismXZ(xa, xb, ty0 - g, ty1, zs - tw - gg - 0.02, zs + 0.02,
                             [((xo, 0, zs), (sx, 0, 1)), ((xo, 0, zs - gg), (-sx, 0, -1))]))
        cuts.append(_prismXZ(xa, xb, ty0 - g, ty1, zt - 0.02, zt + tw + gg + 0.02,
                             [((xo, 0, zt + gg), (-sx, 0, 1)), ((xo, 0, zt), (sx, 0, -1))]))
        cuts.append(_box(xa, xb, ty0 - g, ty0, zs - tw - gg - 0.02, zt + tw + gg + 0.02))
        # Room inside so the tongue can bend in (cuts dividers / solid back).
        keepOut.append(_box(*sorted((xo + sx * tw, xo + sx * (tw + L.SNAP_ENGAGE + 0.1))),
                            ty0 - g, ty1, zs - tw - gg, zt + tw + gg))
        # Hook on the outside near the free end: 60 deg holding face in
        # front, 30 deg lead-in behind, 45 deg underneath.
        zb = zs + 0.03
        yb = hy0 + hookLen
        hx0, hx1 = sorted((xo - sx * p, xo + sx * 0.02))
        adds.append(_prismXY(hx0, hx1, hy0, yb + 0.01, zb, zt - 0.03,
                             [((xo, hy0, 0), (-kH * sx, -1, 0)),
                              ((xo, yb, 0), (-kL * sx, 1, 0)),
                              ((xo, 0, zb), (-sx, 0, -1))]))


def _kAngle(deg):
    """Run per rise of a flank at `deg` degrees from the floor."""
    return 1.0 / math.tan(math.radians(deg))


def _detentTooth(strip, y, height):
    """Cabinet bump: a tooth across the strip, tip `height` above it at y.
    Flat ramp in front (the insert slides in over it), steep hard edge behind
    (it holds the insert in). Reaches as deep below the strip as it stands
    out, so it also sits firmly on a groove flank."""
    xa, xb, z = strip
    kF, kB = _kAngle(L.BUMP_FRONT_ANGLE), _kAngle(L.BUMP_BACK_ANGLE)
    h = height
    return _prismYZ(xa, xb, y - 2 * kF * h, y + 2 * kB * h, z - h, z + h,
                    [((0, y, z + h), (0, -1, kF)), ((0, y, z + h), (0, 1, kB))])


def gridFeet(des, p: dict, partial: dict, outline, radius: float):
    """Gridfinity feet for a unitsW x unitsL footprint (bin convention: foot
    cell i at x = i * baseW). A partial plate cell on a side adds one more
    row/column of feet, cut to `outline` = (x0, x1, y0, y1)."""
    foot = _getFoot(des, p['baseW'], p['baseL'], p['cl'],
                    p['screws'], const.DIMENSION_SCREW_HOLE_DIAMETER,
                    p['magnets'], False,
                    const.DIMENSION_MAGNET_CUTOUT_DIAMETER, const.DIMENSION_MAGNET_CUTOUT_DEPTH)
    eL, eR = int(partial.get('left', False)), int(partial.get('right', False))
    eF, eB = int(partial.get('front', False)), int(partial.get('back', False))
    feet = []
    for i in range(-eL, int(p['unitsW']) + eR):
        for j in range(-eF, int(p['unitsL']) + eB):
            f = _tmgr().copy(foot)
            _translate(f, i * p['baseW'], j * p['baseL'])
            feet.append(f)
    feet = _unionAll(feet)
    # The foot is built xy-clearance larger than its cell (like a bin's); a
    # bin trims that afterwards. Trim to the footprint (0..aW, 0..aL), or to
    # the extended outline on sides with a partial cell, so the feet never
    # stick out past the walls.
    x0, x1, y0, y1 = outline
    cl = float(p['cl'])
    aW = int(p['unitsW']) * float(p['baseW']) - 2 * cl
    aL = int(p['unitsL']) * float(p['baseL']) - 2 * cl
    window = _roundedSlab(x0 if eL else 0.0, x1 if eR else aW,
                          y0 if eF else 0.0, y1 if eB else aL, -10.0, 10.0, radius)
    _tmgr().booleanOperation(feet, window, adsk.fusion.BooleanTypes.IntersectionBooleanType)
    return feet


# ------------------------------------------------------------------- cabinet

def _gridCornerCuts(cab):
    """Grid on top: where a full cell's corner is the body's front corner,
    round that layer like the pocket, else a flat stub stays standing next to
    it. Not over a border / partial cell: there the pockets are cut straight
    at the edge."""
    rFront = cab['radius']
    if not cab['topIsGrid'] or cab['radius'] <= rFront:
        return []
    ox0, ox1, front = cab['x0'], cab['x1'], cab['front']
    R, zg = cab['radius'], cab['zTop'] - const.BIN_BASE_HEIGHT
    cuts = []
    for cx, sx, flush in ((ox0, 1, abs(ox0) < 1e-6), (ox1, -1, abs(ox1 - cab['aW']) < 1e-6)):
        if not flush or abs(front) > 1e-6:
            continue
        corner = _box(min(cx, cx + sx * R), max(cx, cx + sx * R), front - 0.1, front + R,
                      zg, cab['zTop'] + 0.1)
        _subtract(corner, _cylinderAxis((cx + sx * R, front + R, zg - 0.1),
                                        (cx + sx * R, front + R, cab['zTop'] + 0.2), R))
        cuts.append(corner)
    return cuts


def _topCells(des, cab):
    """Grid pockets of the top (none for a flat top). Over a partial plate
    cell the top repeats it as a cut pocket (unless the top edge is set to
    flat); over padding it stays flat."""
    if not cab['topIsGrid']:
        return []
    p = cab['p']
    cell = _getCellCutout(des, p['baseW'], p['baseL'], p['cl'])
    part = cab['partial'] if p['topEdge'] == L.TOP_EDGE_PLATE else {}
    tL, tR = int(part.get('left', False)), int(part.get('right', False))
    tF, tB = int(part.get('front', False)), int(part.get('back', False))
    tools = []
    for i in range(-tL, int(p['unitsW']) + tR):
        for j in range(-tF, int(p['unitsL']) + tB):
            tool = _tmgr().copy(cell)
            _translate(tool, i * p['baseW'], j * p['baseL'], cab['zTop'])
            tools.append(tool)
    # Like a baseplate: the whole top is cut down by the bin height clearance,
    # which leaves the ridges between the pockets flat (not knife edges).
    clr = const.BASEPLATE_BIN_Z_CLEARANCE
    if clr > 0:
        tools.append(_box(cab['x0'] - 1.0, cab['x1'] + 1.0, cab['front'] - 1.0, cab['back'] + 1.0,
                          cab['zTop'] - clr, cab['zTop'] + 1.0))
    return tools


def _rails(cab, grow=0.0, yFrom=None, yTo=None):
    """Rails on top of both side walls (grow > 0: the plate's slot, with
    play, open to the outside and below). Cross-section (left side, from the
    outer face): w wide on the wall, undercut 45 deg inwards by h, top sloped
    45 deg up to the outside."""
    rl = cab['rail']
    w, h, z = rl['w'], rl['h'], cab['ceil']
    g = grow * _SQRT2
    y0 = cab['front'] if yFrom is None else yFrom
    y1 = rl['y1'] if yTo is None else yTo
    out = 1.0 if grow > 0 else 0.0          # the slot runs on past the outside / below
    tools = []
    for face, sx in ((cab['x0'], 1), (cab['x1'], -1)):
        xa, xb = face - sx * out, face + sx * (w + h + g + 0.01)
        tools.append(_prismXZ(xa, xb, y0, y1, z - out, z + w + 2 * h + g + 0.01,
                              [((face + sx * (w + g), 0, z), (sx, 0, -1)),
                               ((face + sx * (w + h), 0, z + h + g), (sx, 0, 1))]))
    return tools


def buildCabinet(des: adsk.fusion.Design, params: dict) -> adsk.fusion.BRepBody:
    """Cabinet temp body in its local frame (see cabinetLayout); a slide-in
    top plate is merged in (dialog preview)."""
    parts = buildCabinetParts(des, params)
    if len(parts) == 1:
        return parts[0]
    merged = _tmgr().copy(parts[0])
    for part in parts[1:]:
        _union(merged, _tmgr().copy(part))
    return merged


def cabinetPartNames(params: dict):
    """Names of the extra bodies buildCabinetParts returns after the cabinet."""
    return ['top plate'] if L.cabinet(params)['rail'] else []


def buildCabinetParts(des: adsk.fusion.Design, params: dict):
    """[cabinet, slide-in top plate?] temp bodies in the cabinet's local frame."""
    with gplog.timed('cabinet build'):
        cab = L.cabinet(params)
        p = cab['p']
        ox0, ox1, front, back = cab['x0'], cab['x1'], cab['front'], cab['back']
        slide = cab['rail'] is not None
        # Front corners as round as the feet and the top (the Gridfinity
        # radius): the side walls run out into the rounding just behind the
        # front; inserts in the outer columns are rounded to match.
        rFront = cab['radius']
        body = _slab(ox0, ox1, front, back, cab['zBottom'], cab['zTop'], rFront, cab['radius'])
        cornerCuts = _gridCornerCuts(cab)
        if cornerCuts and not slide:
            _subtract(body, _unionAll(cornerCuts))

        # Interior: one open-front pocket per column.
        # Back corners rounded like the outside: the wall keeps its thickness.
        pockets = [_slab(x0, x1, front - 1.0, cab['innerBack'], cab['floorTop'], cab['ceil'],
                         0.0, cab['backCornerR'])
                   for x0, x1 in cab['columns']]
        _subtract(body, _unionAll(pockets))

        # Guides end where the rounded back corner starts (else they poke
        # through the rounded outer corner).
        y1 = cab['guideEnd']
        adds, cuts = [], []
        for x0, x1 in cab['columns']:
            for i, row in enumerate(cab['rows']):
                if cab['grooved']:
                    gc = L.grooveCenter(row)
                    cuts.append(_grooveTool(x0, +1, front, y1, gc, cab['grooveDepth']))
                    cuts.append(_grooveTool(x1, -1, front, y1, gc, cab['grooveDepth']))
                elif i > 0:
                    adds.append(_ledge(x0, +1, front, y1, row['bottom'], cab['ledgeThickness'], cab['ledgeDepth']))
                    adds.append(_ledge(x1, -1, front, y1, row['bottom'], cab['ledgeThickness'], cab['ledgeDepth']))
        if adds:
            # Ledges reach a little into the wall; clip them to the outer
            # shape so they never poke through the rounded corners.
            adds = _unionAll(adds)
            envelope = _slab(ox0, ox1, front, back, cab['zBottom'], cab['zTop'], rFront, cab['radius'])
            _tmgr().booleanOperation(adds, envelope, adsk.fusion.BooleanTypes.IntersectionBooleanType)
            _union(body, adds)
        if cuts:
            _subtract(body, _unionAll(cuts))

        catches = snapCatches(cab)
        if catches:
            _subtract(body, _unionAll(catches))

        if cab['detentR'] > 0:
            bumps = []
            for c in range(len(cab['columns'])):
                for r in range(len(cab['rows'])):
                    for strip in L.contactStrips(cab, c, r):
                        bumps.append(_detentTooth(strip, cab['detentY'], cab['detentR']))
            _union(body, _unionAll(bumps))

        plate = None
        if slide:
            # Slide-in top: the cabinet ends at the ceiling with a rail on
            # each side wall; the top is a plate of its own with matching
            # slots (open at the front, closed at the back = its stop).
            plate = _slab(ox0, ox1, front, back, cab['ceil'], cab['zTop'], rFront, cab['radius'])
            _subtract(body, _box(ox0 - 1.0, ox1 + 1.0, front - 1.0, back + 1.0, cab['ceil'], cab['zTop'] + 1.0))
            # Rails follow the rounded outer corners (front and back).
            rails = _unionAll(_rails(cab))
            envelope = _slab(ox0, ox1, front, back, cab['ceil'] - 0.1, cab['zTop'] + 0.1, rFront, cab['radius'])
            _tmgr().booleanOperation(rails, envelope, adsk.fusion.BooleanTypes.IntersectionBooleanType)
            _union(body, rails)
            plateCuts = cornerCuts + _topCells(des, cab)
            plateCuts += _rails(cab, cab['rail']['clearance'], front - 1.0,
                                cab['rail']['y1'] + cab['rail']['clearance'])
            _subtract(plate, _unionAll(plateCuts))
            holes = []
        else:
            holes = _topCells(des, cab)
        if p['wallMount']:
            # Screw from the inside, head flush with the inside of the back
            # wall (the back wall is thick enough, see cabinetLayout).
            sc = L.mountScrew(p)
            yIn = cab['innerBack']
            for x, z in L.mountHoles(cab):
                holes.append(_cylinderAxis((x, yIn - _EPS, z), (x, back + 0.1, z), sc['holeR']))
                if sc['countersunk']:
                    holes.append(_cone((x, yIn - _EPS, z), sc['headR'] + _EPS,
                                       (x, yIn + sc['depth'], z), sc['headR'] - sc['depth']))
                else:
                    holes.append(_cylinderAxis((x, yIn - _EPS, z), (x, yIn + sc['depth'], z), sc['headR']))
        if holes:
            _subtract(body, _unionAll(holes))

        if p['feet']:
            _union(body, gridFeet(des, p, cab['partial'], (ox0, ox1, front, back), cab['radius']))

        gplog.log(f'cabinet build: faces={body.faces.count} slide-in top={slide} errors={cab["errors"]}')
        return [body] + ([plate] if plate is not None else [])


# -------------------------------------------------------------------- insert

def buildInsert(des: adsk.fusion.Design, cabParams: dict, insertParams: dict) -> adsk.fusion.BRepBody:
    """All parts of the insert merged into one temp body (dialog ghost)."""
    parts = buildInsertParts(des, cabParams, insertParams)
    if len(parts) == 1:
        return parts[0]
    merged = _tmgr().copy(parts[0])
    for part in parts[1:]:
        _union(merged, _tmgr().copy(part))
    return merged


def buildInsertParts(des: adsk.fusion.Design, cabParams: dict, insertParams: dict):
    """[insert body, separate parts...] in the cabinet's local frame, closed
    position. Separate parts (spool axle) are printed on their own."""
    with gplog.timed('insert build'):
        cab = L.cabinet(cabParams)
        ins = L.insert(cab, insertParams)
        ip, cp = ins['p'], cab['p']
        x0, x1, y0, y1, z0, z1 = ins['x0'], ins['x1'], ins['y0'], ins['y1'], ins['z0'], ins['z1']
        tw = float(ip['wall'])
        tf = float(ip['floor'])
        frontT = float(ip['front'])

        # Back corners follow the cabinet's rounded interior back corners.
        # Front corners next to an outer side wall follow the cabinet's
        # rounded front corner: they touch it in the front plane.
        rBack = max(0.1, cab['backCornerR'])
        rOuterL = cab['radius'] - (x0 - cab['x0'])
        rOuterR = cab['radius'] - (cab['x1'] - x1)
        rFL = max(0.1, rOuterL) if ins['slot']['column'] == 1 else 0.1
        rFR = max(0.1, rOuterR) if ins['slot']['column'] == len(cab['columns']) else 0.1
        body = _slabCorners(x0, x1, y0, y1, z0, z1, rFL, rFR, rBack, rBack)
        panel = ins['panel']
        if panel is not None:
            _union(body, _box(panel['x0'], panel['x1'], panel['y0'], panel['y1'] + _EPS, panel['z0'], panel['z1']))
            fx0, fx1, fz0, fz1, yF, yB = panel['x0'], panel['x1'], panel['z0'], panel['z1'], panel['y0'], panel['y1']
        else:
            # Flush front: the front wall sits inside the opening.
            fx0, fx1, fz0, fz1, yF, yB = x0, x1, z0, z1, y0, y0 + frontT

        if cab['grooved']:
            gc = ins['grooveCenter']
            gd = cab['grooveDepth']
            fit = float(cp['fitLateral'])
            # The grooves end before the rounded back corner.
            ry1 = min(y1, cab['guideEnd'] - float(cp['fitBack']))
            runners = _unionAll([
                _runner(ins['colX0'], +1, y0, ry1, gc, gd, fit, x0 + tw / 2),
                _runner(ins['colX1'], -1, y0, ry1, gc, gd, fit, x1 - tw / 2),
            ])
            # Stay inside the cabinet's rounded front corners.
            outline = _slab(cab['x0'], cab['x1'], cab['front'], cab['back'], z0 - 1.0, z1 + 1.0,
                            cab['radius'], cab['radius'])
            _tmgr().booleanOperation(runners, outline, adsk.fusion.BooleanTypes.IntersectionBooleanType)
            _union(body, runners)

        # Interior pockets (behind the front).
        px0, px1 = x0 + tw, x1 - tw
        py0, py1 = yB, y1 - tw
        pz0 = z0 + tf
        top = z1 + 1.0
        interior = L.INTERIOR_EMPTY if ins['blank'] else ip['interior']
        nx, ny = 0, 0
        if interior == L.INTERIOR_GRID:
            nx, ny = L.gridCells(px1 - px0, py1 - py0, cp['baseW'], cp['baseL'], cp['cl'])
            if nx == 0 or ny == 0:
                interior = L.INTERIOR_EMPTY
            else:
                pz0 += const.BIN_BASE_HEIGHT
        tools = []
        if interior == L.INTERIOR_COMPARTMENTS and (int(ip['divX']) > 1 or int(ip['divY']) > 1):
            cx, cy = max(1, int(ip['divX'])), max(1, int(ip['divY']))
            uW = (px1 - px0 - (cx - 1) * tw) / cx
            uL = (py1 - py0 - (cy - 1) * tw) / cy
            for i in range(cx):
                for j in range(cy):
                    ox = px0 + i * (uW + tw)
                    oy = py0 + j * (uL + tw)
                    tools.append(_roundedSlab(ox, ox + uW, oy, oy + uL, pz0, top, 0.05))
            # Dividers end a little below the rim.
            tools.append(_box(px0, px1, py0, py1, z1 - 0.1, top))
        else:
            tools.append(_box(px0, px1, py0, py1, pz0, top))
        if interior == L.INTERIOR_GRID:
            cell = _getCellCutout(des, cp['baseW'], cp['baseL'], cp['cl'])
            b, d = cp['baseW'], cp['baseL']
            ox = (px0 + px1) / 2 - nx * b / 2 + cp['cl']
            oy = (py0 + py1) / 2 - ny * d / 2 + cp['cl']
            for i in range(nx):
                for j in range(ny):
                    tool = _tmgr().copy(cell)
                    _translate(tool, ox + i * b, oy + j * d, pz0)
                    tools.append(tool)
        tools = _unionAll(tools)
        if interior != L.INTERIOR_GRID and rBack - tw > 0.05:
            # Keep the wall thickness in the rounded back corners.
            envelope = _slab(px0, px1, py0, py1, pz0 - 0.01, top + 0.5, 0.0, rBack - tw)
            _tmgr().booleanOperation(tools, envelope, adsk.fusion.BooleanTypes.IntersectionBooleanType)
        _subtract(body, tools)

        snapCuts, snapAdds, snapKeep = [], [], []
        if cab['snap'] and ip.get('snapTongue') and not ins['blank']:
            _snapTongues(cab, ins, tw, snapCuts, snapAdds, snapKeep)
            if snapKeep:
                _subtract(body, _unionAll(snapKeep))
            if snapAdds:
                _union(body, _unionAll(snapAdds))
            if snapCuts:
                _subtract(body, _unionAll(snapCuts))

        # Front: label band + handle band, wire outlets.
        labelRect, band, blocked = frontLayout(ip, fx0, fx1, fz0, fz1)
        gplog.log(f'insert front: handle={ip["handle"]} label={ip["label"]} pos={ip.get("labelPos")} '
                  f'front z {fz0:.2f}..{fz1:.2f} -> label {labelRect and [round(v, 2) for v in labelRect]}')
        adds, cuts = [], []
        handleX = _handle(ip, band, (fx0, fx1, fz0, fz1), yF, yB, z0, z1, tw, adds, cuts)
        gripMode = ip.get('gripDividers', L.GRIP_FRONT_ROW)
        if (ip['handle'] in (L.HANDLE_NOTCH, L.HANDLE_SLOT) and interior == L.INTERIOR_COMPARTMENTS
                and (int(ip['divX']) > 1 or int(ip['divY']) > 1) and gripMode != L.GRIP_OFF):
            # Room for the finger behind a notch / finger hole: the same round
            # profile runs on through the dividers in its way (floor and outer
            # walls stay) - along the front row of compartments (up to the
            # first cross divider) or a set depth.
            if gripMode == L.GRIP_DEPTH:
                reach = float(ip.get('gripDepth') or GRIP_REACH)
            else:
                cy = max(1, int(ip['divY']))
                reach = (py1 - py0 - (cy - 1) * tw) / cy
            reach = min(reach, py1 - yB)
            if reach > 0.1:
                gripCuts = []
                _handle(ip, band, (fx0, fx1, fz0, fz1), yB - _EPS, yB + reach, z0, z1, tw, [], gripCuts)
                for tool in gripCuts:
                    _tmgr().booleanOperation(tool, _box(px0, px1, yB - _EPS, yB + reach, pz0, z1 + 1.0),
                                             adsk.fusion.BooleanTypes.IntersectionBooleanType)
                    cuts.append(tool)
        _label(ip, labelRect, yF, adds, cuts)
        spools = ins['spools']
        extraParts = []
        if spools is not None:
            # Wire outlets sit in front of each spool, low above the floor.
            for xc in spools['centers']:
                _wireHole(xc, spools['holeZ'], spools['wireD'] / 2, yF, yB, cuts)
            spoolAdds, axles = _spoolParts(spools, bool(ip['spoolGuides']))
            adds.extend(spoolAdds)
            extraParts.extend(axles)
            if ip.get('showSpools'):
                extraParts.append(_unionAll([spoolBody(spools, c) for c in spools['centers']]))
        else:
            _wireHoles(ip, band, ([handleX] if handleX else []) + blocked, yF, yB, cuts)
        if adds:
            _union(body, _unionAll(adds))

        # Detent (seen from the side; the cabinet's tooth rides in it):
        #   notch    - the tooth rests here when closed; its back flank is
        #              steep (detentHold): pulling out has to climb it
        #   ridge    - short flat land behind the notch
        #   channel  - the tooth travels in it while the insert is out; it
        #              starts with a flat ramp (detentRamp): closing is easy
        #   stop     - land at the back end: hard (vertical, lift to take out),
        #              soft (the steep flank again) or none
        #   lead-in  - the back end itself is ramped, so the insert slides in
        #              over the tooth when it is put in
        R = cab['detentR']
        c = L.DETENT_CLEARANCE
        r = R + c
        yd = cab['detentY']
        stop = L.stopMode(cab, ip)
        kHold = _kAngle(max(15.0, min(85.0, float(ip.get('detentHold') or L.DETENT_HOLD_ANGLE))))
        kRamp = _kAngle(max(10.0, min(85.0, float(ip.get('detentRamp') or L.DETENT_RAMP_ANGLE))))
        kF, kB = _kAngle(L.BUMP_FRONT_ANGLE), _kAngle(L.BUMP_BACK_ANGLE)
        # Back flank: clears the tooth's tip (and its steep back face) by c.
        dBack = max(kHold, kB) * R + c * math.sqrt(1.0 + kHold * kHold)
        notchFront = yd - 2 * kF * R - 2 * c
        chEnd = y1 - L.STOP_LAND if stop != L.STOP_OFF else y1 + 1.0
        ribs = []
        for strip in ins['contact']:
            xa, xb, z = strip
            xa, xb = xa - _EPS, xb + _EPS
            if not cab['grooved'] and tf < r + 0.2:
                # Thin floor: a rib inside over the notch/channel so the floor
                # is never cut through there.
                ribs.append(_box(max(xa - 0.1, x0), min(xb + 0.1, x1), notchFront - 0.1,
                                 min(max(chEnd, yd + dBack + 0.1), py1), z0, z0 + r + 0.2))
            if R <= 0:
                continue
            # Notch: front parallel to the tooth's ramp, flat top, steep back.
            cuts.append(_prismYZ(xa, xb, notchFront - r * kF, yd + dBack + r * kHold, z - r, z + r,
                                 [((0, yd - c * math.sqrt(1.0 + kF * kF), z + R), (0, -1, kF)),
                                  ((0, yd + dBack, z), (0, 1, kHold))]))
            chStart = yd + dBack + L.DETENT_RIDGE
            if chEnd > chStart + 0.05:
                cutsCh = [((0, chStart, z), (0, -1, kRamp))]              # flat ramp in
                yEnd = chEnd
                if stop == L.STOP_SOFT:
                    cutsCh.append(((0, chEnd, z), (0, 1, kHold)))         # steep, not hard
                    yEnd = chEnd + r * kHold
                cuts.append(_prismYZ(xa, xb, chStart - r * kRamp, yEnd, z - r, z + r, cutsCh))
            if stop != L.STOP_OFF:
                # Lead-in at the back end: the insert goes in over the tooth.
                cuts.append(_prismYZ(xa, xb, y1 - r * kRamp - 0.01, y1 + 0.1, z - r, z + r,
                                     [((0, y1, z + r), (0, -1, kRamp))]))
        if ribs:
            _union(body, _unionAll(ribs))
        if cuts:
            _subtract(body, _unionAll(cuts))

        if spools is not None and spools['fillet'] > 0:
            import json
            key = json.dumps([cabParams, {k: v for k, v in ip.items() if k != 'pullOut'}],
                             sort_keys=True, default=str)
            body = filletPostFeet(des, body, spools.get('footprints', []), spools['floorZ'],
                                  spools['fillet'], key)

        parts = [body] + extraParts
        pull = float(ip.get('pullOut', 0.0))
        if pull:
            for part in parts:
                _translate(part, 0.0, -pull, 0.0)
        gplog.log(f'insert build: parts={len(parts)} faces={body.faces.count} errors={ins["errors"]}')
        return parts


LABEL_MARGIN = 0.25
CARD_FRAME = 0.2      # card holder: frame width around the card
CARD_LIP = 0.15       # how far the front flange overlaps the card
CARD_GAP = 0.06       # slot for the card
CARD_FLANGE = 0.1     # flange thickness


def handleHalfWidth(ip, frontW):
    """Half the x extent the handle takes on the front (incl. housing)."""
    if ip['handle'] == L.HANDLE_NONE:
        return 0.0
    w = max(0.8, min(float(ip['handleWidth']), frontW - 0.8))
    return w / 2 + (float(ip['wall']) if ip['handle'] == L.HANDLE_RECESS else 0.0)


def frontLayout(ip, fx0, fx1, fz0, fz1):
    """(labelRect or None, handleBand, blockedX) on the front face.

    Positions form a 3 x 3 grid (top / middle / bottom x left / center /
    right). Top and bottom row: the label sits at that edge and the handle
    gets the rest of the height. Middle row: aligned to the left / right edge
    (with a handle only up to the handle), or centred. 'Auto' puts the label
    below the handle if the front is high enough, else left of it; without a
    handle it is centred. labelOffsetX / Z shift the label afterwards (kept on
    the front). blockedX: x ranges the label takes (wire outlets keep clear)."""
    W, H = fx1 - fx0, fz1 - fz0
    xc, zc = (fx0 + fx1) / 2, (fz0 + fz1) / 2
    band = (fx0, fx1, fz0, fz1)
    if ip['label'] == L.LABEL_NONE:
        return None, band, []
    frame = CARD_FRAME if ip['label'] == L.LABEL_CARD else 0.0
    m = LABEL_MARGIN + frame                      # label edge to front edge
    pos = ip['labelPos']
    hasHandle = ip['handle'] != L.HANDLE_NONE
    notch = ip['handle'] == L.HANDLE_NOTCH
    needHandle = max(1.0, float(ip['handleHeight'])) + 0.4 if hasHandle else 0.0
    lhWanted = float(ip['labelHeight'])
    stacked = H >= needHandle + lhWanted + 2 * frame + LABEL_MARGIN + 0.2
    spoolDrawer = ip.get('interior') == L.INTERIOR_SPOOLS and ip.get('insertType') != L.INSERT_BLANK
    if pos not in L.LABEL_GRID:
        if spoolDrawer:
            # Wire outlets usually sit low in front of the spools.
            pos = L.LABEL_TOP if stacked else L.LABEL_LEFT
        elif not hasHandle:
            pos = L.LABEL_CENTER
        else:
            pos = L.LABEL_BOTTOM if stacked else L.LABEL_LEFT
    row, col = L.LABEL_GRID[pos]
    # An explicit position is kept; it only moves where the handle would cut
    # right through the label.
    if notch and row == 'top' and col == 'center':
        row = 'bottom'                            # the notch is cut from the top
    if ip['handle'] == L.HANDLE_KNOB and row == 'bottom' and col == 'center':
        row, col = 'middle', 'left'               # the knob's stand reaches the bottom

    def alignX(lw, a, b):
        """x0 of a label lw wide in [a, b] for the column."""
        if col == 'left':
            return a
        if col == 'right':
            return b - lw
        return (a + b) / 2 - lw / 2

    blocked = False
    if row in ('top', 'bottom'):
        lh = max(0.4, min(lhWanted, H * 0.45))
        lw = max(0.6, min(float(ip['labelWidth']), W - 2 * m))
        if row == 'top':
            lz1 = fz1 - LABEL_MARGIN
            lz0 = lz1 - lh
            band = (fx0, fx1, fz0, lz0 - frame - 0.1)
        else:
            lz0 = fz0 + m
            lz1 = lz0 + lh
            band = (fx0, fx1, lz1 + 0.1, fz1)
        x0 = alignX(lw, fx0 + m, fx1 - m)
        rect = (x0, x0 + lw, lz0, lz1)
    else:
        lh = max(0.4, min(lhWanted, H - 2 * m))
        if col == 'center':
            a, b = fx0 + m, fx1 - m
        elif hasHandle:
            # Beside the handle: between the front edge and the handle.
            half = handleHalfWidth(ip, W) + 0.3
            a, b = (fx0 + m, xc - half - frame) if col == 'left' else (xc + half + frame, fx1 - m)
        else:
            a, b = fx0 + m, fx1 - m
        if b - a < 0.6:
            return None, band, []
        lw = min(float(ip['labelWidth']), b - a)
        lz0 = zc - lh / 2
        if notch and col == 'center':
            # Centred under the notch: stay below it.
            notchBottom = fz1 - min(float(ip['handleHeight']), H - 0.4)
            lz0 = max(fz0 + m, min(lz0, notchBottom - 0.1 - frame - lh))
        x0 = alignX(lw, a, b)
        rect = (x0, x0 + lw, lz0, lz0 + lh)
        blocked = True

    # Offset, clamped so the label (and a card holder's frame) stays on the front.
    mo = LABEL_MARGIN * 0.5 + frame
    dx = float(ip.get('labelOffsetX') or 0.0)
    dz = float(ip.get('labelOffsetZ') or 0.0)
    dx = min(max(dx, fx0 + mo - rect[0]), fx1 - mo - rect[1])
    dz = min(max(dz, fz0 + mo - rect[2]), fz1 - mo - rect[3])
    rect = (rect[0] + dx, rect[1] + dx, rect[2] + dz, rect[3] + dz)
    return rect, band, ([(rect[0] - frame - 0.2, rect[1] + frame + 0.2)] if blocked else [])


def _label(ip, rect, yF, adds, cuts):
    if rect is None:
        return
    lx0, lx1, lz0, lz1 = rect
    if ip['label'] == L.LABEL_RECESS:
        # Shallow field: the sticker sits flush and straight.
        depth = max(0.0, float(ip.get('labelDepth', 0.02) or 0.0))
        if depth > 0:
            cuts.append(_box(lx0, lx1, yF - 0.1, yF + depth, lz0, lz1))
        return
    # Card holder, open at the top: slot behind a front flange. All walls are
    # vertical, the flange stands on the bottom frame, so no supports needed.
    s, e, g, t = CARD_FRAME, CARD_LIP, CARD_GAP, CARD_FLANGE
    holder = _box(lx0 - s, lx1 + s, yF - g - t, yF + _EPS, lz0 - s, lz1)
    _subtract(holder, _box(lx0, lx1, yF - g, yF, lz0, lz1 + 1.0))
    _subtract(holder, _box(lx0 + e, lx1 - e, yF - g - t - 0.1, yF - g + _EPS, lz0 + e, lz1 + 1.0))
    adds.append(holder)


SPOOL_PREVIEW_NAME = 'spools (preview, not for printing)'


def insertPartNames(insertParams: dict):
    """Names of the extra bodies buildInsertParts returns after the insert."""
    ip = L.withDefaults(insertParams, L.INSERT_DEFAULTS)
    if ip['interior'] != L.INTERIOR_SPOOLS or ip['insertType'] == L.INSERT_BLANK:
        return []
    axles = ['axle'] if ip.get('axleSplit') == L.AXLE_ONE_PIECE else ['axle A (peg)', 'axle B (socket)']
    return axles + ([SPOOL_PREVIEW_NAME] if ip.get('showSpools') else [])


def spoolBody(sp, xc):
    """Stand-in for one spool (outer diameter x width, with its bore)."""
    half = sp['Ws'] / 2
    spool = _cylinderAxis((xc - half, sp['yA'], sp['zA']), (xc + half, sp['yA'], sp['zA']), sp['D'] / 2)
    boreR = (sp['axleD'] + L.SPOOL_AXLE_PLAY) / 2
    _subtract(spool, _cylinderAxis((xc - half - 0.1, sp['yA'], sp['zA']), (xc + half + 0.1, sp['yA'], sp['zA']), boreR))
    return spool


def _overlaps(a, b) -> bool:
    """True if two temp bodies share volume (boolean intersection not empty)."""
    try:
        probe = _tmgr().copy(a)
        _tmgr().booleanOperation(probe, _tmgr().copy(b), adsk.fusion.BooleanTypes.IntersectionBooleanType)
        return probe.faces.count > 0
    except Exception:
        return False


def spoolProblems(des, cabParams: dict, insertParams: dict):
    """Messages for spools that do not fit: size checks from the layout plus
    a real collision test of every spool against the finished drawer."""
    cab = L.cabinet(cabParams)
    ins = L.insert(cab, insertParams)
    sp = ins.get('spools')
    if sp is None:
        return []
    if sp['errors']:
        return list(sp['errors'])
    # No floor fillet here: this runs while the user types (no scratch features).
    ip = dict(ins['p'], pullOut=0.0, showSpools=False, spoolFillet=0.0)
    drawer = buildInsertParts(des, cabParams, ip)[0]
    # The recessed pull's housing reaches deep into the drawer: name it.
    housing = None
    if ip['handle'] == L.HANDLE_RECESS:
        frontT = float(ip['front'])
        if ins['panel'] is not None:
            pn = ins['panel']
            front, yF, yB = (pn['x0'], pn['x1'], pn['z0'], pn['z1']), pn['y0'], pn['y1']
        else:
            front, yF, yB = (ins['x0'], ins['x1'], ins['z0'], ins['z1']), ins['y0'], ins['y0'] + frontT
        _, band, _ = frontLayout(ip, *front)
        adds, cuts = [], []
        _handle(ip, band, front, yF, yB, ins['z0'], ins['z1'], float(ip['wall']), adds, cuts)
        housing = adds[0] if adds else None
    problems = []
    for k, xc in enumerate(sp['centers']):
        spool = spoolBody(sp, xc)
        if housing is not None and _overlaps(spool, housing):
            problems.append(f'Spool {k + 1} hits the recessed pull: use another handle, '
                            f'a narrower handle or a smaller spool')
        elif _overlaps(spool, drawer):
            problems.append(f'Spool {k + 1} touches the drawer (wall, guide or cradle): '
                            f'check diameter, width and bore')
    return problems


def _wireHole(x, z, rad, yF, yB, cuts):
    """One wire outlet through the front, chamfered on the outside."""
    cuts.append(_cylinderAxis((x, yF - 0.1, z), (x, yB + _EPS, z), rad))
    cuts.append(_cone((x, yF - _EPS, z), rad + 0.1 + _EPS, (x, yF + 0.1, z), rad))


def _spoolParts(sp, guides: bool):
    """(parts to add to the insert, separate axle body) for the spool interior.

    Cradles: posts with an open-top U slot, at both ends and between the
    spools (they keep the spools apart). Guides: a small post with an eyelet
    in line with each wire outlet. Axle: rod with collars outside the outer
    posts and a flat underside so it prints lying down."""
    adds = []
    r = sp['axleD'] / 2
    yA, zA, floorZ = sp['yA'], sp['zA'], sp['floorZ']
    slotR = r + 0.03
    # Snap-in: the cradle reaches over the axle and its opening is narrower
    # than the axle (lips), so the axle clicks in. Open: plain U, lay it in.
    top = zA + r + 0.15 if sp['snap'] else zA + r * 0.6
    opening = r - L.SPOOL_SNAP if sp['snap'] else slotR
    sp['footprints'] = []
    for xa, xb in sp['posts']:
        y0, y1 = yA - slotR - L.SPOOL_POST, yA + slotR + L.SPOOL_POST
        post = _box(xa, xb, y0, y1, floorZ - _EPS, top)
        _subtract(post, _cylinderAxis((xa - 0.1, yA, zA), (xb + 0.1, yA, zA), slotR))
        _subtract(post, _box(xa - 0.1, xb + 0.1, yA - opening, yA + opening, zA, zA + 5.0))
        adds.append(post)
        sp.setdefault('footprints', []).append((xa, xb, y0, y1))
    if guides:
        wr = sp['wireD'] / 2
        gy, hz = sp['guideY'], sp['holeZ']
        for xc in sp['centers']:
            guide = _box(xc - 0.4, xc + 0.4, gy - 0.15, gy + 0.15, floorZ - _EPS, hz + wr + 0.3)
            _subtract(guide, _cylinderAxis((xc, gy - 1.0, hz), (xc, gy + 1.0, hz), wr + 0.05))
            adds.append(guide)
            sp.setdefault('footprints', []).append((xc - 0.4, xc + 0.4, gy - 0.15, gy + 0.15))

    return adds, _axleParts(sp)


# Floor fillets are made by a real Fusion fillet (constant radius, tangent
# chain, rolling ball corners) in a scratch component; cached per drawer.
_filletCache = {}


def filletPostFeet(des, body, footprints, zFloor: float, radius: float, key=None):
    """Body with a fillet where posts (footprints x0, x1, y0, y1) meet the
    floor at zFloor. Uses Fusion's fillet feature in a scratch component, so
    the result is exactly a manual fillet. Returns the input on failure."""
    if des is None or radius <= 0 or not footprints:
        return body
    if key is not None:
        cached = _filletCache.get(key)
        if cached is not None:
            try:
                if cached.faces.count > 0:
                    return _tmgr().copy(cached)
            except Exception:
                pass
    from . import scratchUtils

    def onFoot(pt):
        if abs(pt.z - zFloor) > 1e-4:
            return False
        tol = 1e-3
        return any(x0 - tol <= pt.x <= x1 + tol and y0 - tol <= pt.y <= y1 + tol
                   for x0, x1, y0, y1 in footprints)

    result = body
    startCount = des.timeline.count
    try:
        with gplog.timed('floor fillet (parametric)'):
            scratch = scratchUtils.createScratchComponent(des)
            baseFeat = scratch.features.baseFeatures.add()
            baseFeat.startEdit()
            scratch.bRepBodies.add(body, baseFeat)
            baseFeat.finishEdit()
            target = baseFeat.bodies.item(0)
            edges = adsk.core.ObjectCollection.create()
            for edge in target.edges:
                bb = edge.boundingBox
                if abs(bb.minPoint.z - zFloor) > 1e-4 or abs(bb.maxPoint.z - zFloor) > 1e-4:
                    continue
                if onFoot(edge.pointOnEdge):
                    edges.add(edge)
            if edges.count:
                fillets = scratch.features.filletFeatures
                fin = fillets.createInput()
                fin.isRollingBallCorner = True
                fin.edgeSetInputs.addConstantRadiusEdgeSet(edges, adsk.core.ValueInput.createByReal(radius), True)
                fillets.add(fin)
                own = scratchUtils.ownBodies(scratch)
                result = _tmgr().copy(own[0] if own else target)
            gplog.log(f'floor fillet: {edges.count} edges, r={radius}')
    except Exception:
        gplog.logExc('floor fillet')
        result = body
    finally:
        lastIndex = des.timeline.count - 1
        if lastIndex >= startCount:
            des.timeline.timelineGroups.add(startCount, lastIndex).deleteMe(True)
        scratchUtils.release()
    if key is not None and result is not body:
        if len(_filletCache) > 8:
            _filletCache.clear()
        _filletCache[key] = _tmgr().copy(result)
    return result


# Bayonet joint in the middle of the axle (sizes relative to the axle radius).
BAYONET_PEG = 0.55          # peg radius / axle radius
BAYONET_PLAY = 0.02         # radial play peg / socket
BAYONET_LUG_LEN = 0.15      # lug length along the axle
BAYONET_LUG_W = 0.25        # lug width (around the axle)
BAYONET_SKIN = 0.08         # 'smooth outside': wall left outside the groove


def _axleParts(sp):
    """Axle bodies. Bayonet: two halves, each with one collar, printed
    standing on that collar; half A carries a peg with two lugs, half B a
    socket with two L-slots (push in, turn a quarter, locked). One piece: a
    single collar (spools slide on from the other end), printed lying on a
    flat."""
    r = sp['axleD'] / 2
    yA, zA = sp['yA'], sp['zA']
    xa, xb = sp['axleX']
    rc = r + 0.25
    pa, pb = sp['posts'][0][0], sp['posts'][-1][1]

    def rod(x0, x1, radius):
        return _cylinderAxis((x0, yA, zA), (x1, yA, zA), radius)

    if not sp['bayonet']:
        # Collar on one side; the other end runs on towards the side wall so
        # the axle cannot slide out there.
        axle = rod(xa, max(xb, sp['plainEnd']), r)
        _union(axle, rod(xa, pa - sp['endPlay'], rc))
        _subtract(axle, _box(xa - 1, xb + 1, yA - rc - 1, yA + rc + 1, zA - rc - 1, zA - r * 0.85))
        return [axle]

    xm = (xa + xb) / 2
    smooth = sp['axleMode'] == L.AXLE_BAYONET_SMOOTH
    pegLen = max(0.8, 2 * r)
    lugHi = xm + pegLen - 0.1
    lugLo = lugHi - BAYONET_LUG_LEN
    w = BAYONET_LUG_W
    if smooth:
        # Slots and groove stay inside the socket wall: keep an outer skin.
        rp = r * 0.5
        lugOut = min(rp + (r - rp) * 0.5, r - BAYONET_SKIN - 0.02)
        cutR = lugOut + 0.02          # how far the slots / groove reach out
    else:
        rp = r * BAYONET_PEG
        lugOut = rp + (r - rp) * 0.7
        cutR = r + 0.1                # through the wall

    # Half A: collar, shaft to the middle, peg with two lugs (+y and -y).
    halfA = rod(xa, xm, r)
    _union(halfA, rod(xa, pa - sp['endPlay'], rc))
    _union(halfA, rod(xm - _EPS, xm + pegLen, rp))
    for sgn in (1, -1):
        lug = _box(lugLo, lugHi, yA + sgn * (rp - 0.02) if sgn > 0 else yA - lugOut,
                   yA + lugOut if sgn > 0 else yA - (rp - 0.02), zA - w / 2, zA + w / 2)
        # 45° underside (towards collar A) so it prints standing on the collar.
        _cutHalfSpace(lug, (lugLo, yA + sgn * rp, zA), (-1, sgn, 0))
        _union(halfA, lug)

    # Half B: shaft from the middle, collar, socket with L-slots.
    halfB = rod(xm, xb, r)
    _union(halfB, rod(pb + sp['endPlay'], xb, rc))
    _subtract(halfB, rod(xm - 0.1, xm + pegLen + 0.05, rp + BAYONET_PLAY))
    m = w / 2 + 0.03
    for sgn in (1, -1):
        # Axial entry slot at the lug, through the socket wall.
        _subtract(halfB, _box(xm - 0.1, lugHi + 0.03,
                              yA + sgn * (rp - 0.05) if sgn > 0 else yA - cutR,
                              yA + cutR if sgn > 0 else yA - (rp - 0.05), zA - m, zA + m))
        # Quarter-turn groove: from the lug's entry (+-y) to +-z. Its wall
        # towards the socket mouth is a 45° cone, parallel to the lug's
        # chamfer: it holds the lug and prints as a 45° ceiling.
        # Cone radius rp + (x - lugLo + 0.03): 0.3 mm in front of the lug face.
        x0 = lugLo - 0.03 - 0.05
        d = cutR - (rp - 0.05)
        reach = _cone((x0, yA, zA), rp - 0.05, (x0 + d, yA, zA), rp - 0.05 + d)
        _union(reach, rod(x0 + d - _EPS, lugHi + 0.03 + d, cutR))
        groove = rod(x0, lugHi + 0.03, cutR)
        _tmgr().booleanOperation(groove, reach, adsk.fusion.BooleanTypes.IntersectionBooleanType)
        _subtract(groove, rod(lugLo - 0.1, lugHi + 0.1, rp - 0.05))
        _cutHalfSpace(groove, (0, yA - sgn * m, 0), (0, -sgn, 0))
        _cutHalfSpace(groove, (0, 0, zA - sgn * m), (0, 0, -sgn))
        _subtract(halfB, groove)
    return [halfA, halfB]


def _wireHoles(ip, band, blocked, yF, yB, cuts):
    """Outlets for wire / filament on a spool inside: in the handle band,
    clear of handle and label, with a small chamfer on the outside."""
    n = int(ip.get('wireHoles', 0) or 0)
    if n <= 0:
        return
    rad = max(0.1, float(ip['wireDiameter']) / 2)
    bx0, bx1, bz0, bz1 = band
    zc = (bz0 + bz1) / 2
    margin = rad + 0.3
    # Free x segments = band minus blocked ranges.
    segments = [(bx0 + margin, bx1 - margin)]
    for lo, hi in blocked:
        nxt = []
        for a, b in segments:
            if hi + margin <= a or lo - margin >= b:
                nxt.append((a, b))
                continue
            if lo - margin > a:
                nxt.append((a, lo - margin))
            if hi + margin < b:
                nxt.append((hi + margin, b))
        segments = nxt
    segments = sorted((s for s in segments if s[1] - s[0] > 2 * rad), key=lambda s: -(s[1] - s[0]))
    if not segments:
        return
    # Largest free segments first, evenly spread within each.
    counts = [0] * len(segments)
    for i in range(n):
        counts[i % len(segments)] += 1
    for (a, b), k in zip(segments, counts):
        for i in range(k):
            x = a + (i + 0.5) * (b - a) / k
            cuts.append(_cylinderAxis((x, yF - 0.1, zc), (x, yB + _EPS, zc), rad))
            cuts.append(_cone((x, yF - _EPS, zc), rad + 0.1 + _EPS, (x, yF + 0.1, zc), rad))


def _handle(ip, band, front, yF, yB, zFloor, zTop, tw, adds, cuts):
    """Add the handle to adds/cuts. band = (x0, x1, z0, z1) on the front face
    at y=yF (outside is -y), front material ends at y=yB. front = the whole
    front rectangle (x0, x1, z0, z1); nothing may leave it in z. zFloor/zTop:
    the insert's bottom (print bed) / rim. Returns the handle's x range."""
    kind = ip['handle']
    if kind == L.HANDLE_NONE:
        return None
    bx0, bx1, bz0, bz1 = band
    frontTop = front[3]
    W, H = bx1 - bx0, bz1 - bz0
    xc, zc = (bx0 + bx1) / 2, (bz0 + bz1) / 2
    w = max(0.8, min(float(ip['handleWidth']), W - 0.8))
    h = max(0.6, min(float(ip['handleHeight']), H - 0.4))
    frontT = yB - yF

    if kind == L.HANDLE_RECESS:
        # Hollow pocket behind the front: opening h high, the ceiling rises
        # at 45° towards the back so the fingers hook in behind the lip above
        # the opening. The housing follows at 45° top and bottom: prints
        # without supports and stays light.
        d = max(float(ip['handleDepth']), frontT + 0.6)
        zt = min(zc + h / 2, frontTop - frontT - 0.25)
        zb = max(zt - h, bz0 + 0.1)
        cav = _prismYZ(xc - w / 2, xc + w / 2, yF - 0.1, yF + d, zb, zt + d + 0.2,
                       [((0, yF, zt), (0, -1, 1))])
        hx = w / 2 + tw
        rise = tw * _SQRT2
        housing = _prismYZ(xc - hx, xc + hx, yB - _EPS, yF + d + tw, zFloor, zt + d + rise + 0.01,
                           [((0, yF, zt + rise), (0, -1, 1)),
                            ((0, yF, zb - tw), (0, -1, -1))])
        # Never above the insert's rim (the ledge / row above is there).
        _subtract(housing, _box(xc - hx - 1, xc + hx + 1, yF - 1, yF + d + 1, zTop, zTop + 10))
        adds.append(housing)
        cuts.append(cav)
        return (xc - hx, xc + hx)

    if kind == L.HANDLE_NOTCH:
        md = min(float(ip['handleHeight']), frontTop - bz0 - 0.4)
        rad = w / 2
        cz = frontTop + rad - md
        cuts.append(_cylinderAxis((xc, yF - 0.1, cz), (xc, yB + _EPS, cz), rad))
        if cz < frontTop:
            cuts.append(_box(xc - rad, xc + rad, yF - 0.1, yB + _EPS, cz, frontTop + 1.0))
        return (xc - rad, xc + rad)

    if kind == L.HANDLE_SLOT:
        rad = min(h, w) / 2
        half = w / 2 - rad
        if half > 0.01:
            cuts.append(_box(xc - half, xc + half, yF - 0.1, yB + _EPS, zc - rad, zc + rad))
            for x in (xc - half, xc + half):
                cuts.append(_cylinderAxis((x, yF - 0.1, zc), (x, yB + _EPS, zc), rad))
        else:
            cuts.append(_cylinderAxis((xc, yF - 0.1, zc), (xc, yB + _EPS, zc), rad))
        return (xc - w / 2, xc + w / 2)

    if kind in (L.HANDLE_PULL, L.HANDLE_LEDGE):
        grip = (_pullHandle if kind == L.HANDLE_PULL else _ledgeHandle)(ip, xc, w, bz0, bz1, yF)
        adds.append(_clipToFront(grip, front, yF))
        return (xc - w / 2, xc + w / 2)

    if kind == L.HANDLE_KNOB:
        knob, rk = _knob(ip, xc, w, front, zFloor, yF)
        adds.append(_clipToFront(knob, front, yF))
        return (xc - rk, xc + rk)

    return None


def _clipToFront(body, front, yF):
    """Keep a protruding handle within the front's height (and in front of
    it), so it can never reach into the cabinet or the row below / above."""
    fx0, fx1, fz0, fz1 = front
    _tmgr().booleanOperation(body, _box(fx0 - 1, fx1 + 1, yF - 20.0, yF + _EPS, fz0, fz1),
                             adsk.fusion.BooleanTypes.IntersectionBooleanType)
    return body


def _alignTop(ip, bz0, bz1, extent):
    """Top z of a protruding handle `extent` high, placed top / centre /
    bottom in the band (0.1 margin)."""
    align = ip.get('handleAlign', L.ALIGN_TOP)
    if align == L.ALIGN_TOP:
        return bz1 - 0.1
    if align == L.ALIGN_BOTTOM:
        return min(bz1 - 0.1, bz0 + 0.1 + extent)
    return min(bz1 - 0.1, (bz0 + bz1) / 2 + extent / 2)


def _pullHandle(ip, xc, w, bz0, bz1, yF):
    """Hollow grip standing out of the front, open at the bottom.

    Profile: top plate, outer grip face, 45° underside back to the front.
    Everything is configurable, so it covers a thin lip that just sticks out
    a little, a hook lip (side walls 0 = open), a D-shaped bar handle and the
    scoop (low grip face, triangular side walls). The cavity roof is a bridge
    between the side walls, everything else is vertical or 45°. Fitted into
    the band height."""
    topT = max(0.08, float(ip['pullTop']))
    barT = max(0.08, float(ip['pullBar']))
    side = max(0.0, float(ip['pullSides']))
    if side > 0 and w - 2 * side < 0.4:
        side = 0.0
    hh = max(topT + 0.05, float(ip['pullGrip']))
    p = max(barT + 0.2, float(ip['handleDepth']))
    avail = (bz1 - bz0) - 0.2
    # Side walls keep the whole 45° wedge (p high); open sides only the bar.
    wedge = p if side > 0 else barT
    if hh + wedge > avail:
        hh = max(topT + 0.05, avail - wedge)
    if side > 0 and hh + p > avail:
        p = max(barT + 0.2, avail - hh)
        wedge = p
    zt = _alignTop(ip, bz0, bz1, hh + wedge)
    grip = _prismYZ(xc - w / 2, xc + w / 2, yF - p, yF + _EPS, zt - hh - p, zt,
                    [((0, yF - p, zt - hh), (0, -1, -1))])
    if p - barT > 0.05:
        inner = side if side > 0 else -0.1
        _subtract(grip, _box(xc - w / 2 + inner, xc + w / 2 - inner,
                             yF - p + barT, yF, zt - hh - p - 1.0, zt - topT))
    return grip


def _ledgeHandle(ip, xc, w, bz0, bz1, yF):
    """Closed wedge with a finger groove on top. Defined from the top (groove
    width + depth, rim) plus its total height, which sets the slope of the
    underside: higher = steeper = easier to print (see cabinetLayout.ledgeSize)."""
    ls = L.ledgeSize(ip, (bz1 - bz0) - 0.2)
    rim, wg, dg, p, hh, H = ls['rim'], ls['wg'], ls['dg'], ls['p'], ls['hh'], ls['H']
    zt = _alignTop(ip, bz0, bz1, H)
    # Underside: from the outer bottom edge (yF - p, zt - hh) to the front
    # face at zt - H.
    ledge = _prismYZ(xc - w / 2, xc + w / 2, yF - p, yF + _EPS, zt - H, zt,
                     [((0, yF - p, zt - hh), (0, -(H - hh), -p))])
    yc = yF - rim - wg / 2
    xa, xb = xc - w / 2 - 0.1, xc + w / 2 + 0.1
    if dg <= wg / 2:
        # Shallow: circular segment, exactly wg wide and dg deep.
        rad = (wg * wg / 4 + dg * dg) / (2 * dg)
        _subtract(ledge, _cylinderAxis((xa, yc, zt - dg + rad), (xb, yc, zt - dg + rad), rad))
    else:
        # Deep: U shape (round bottom, straight sides).
        rad = wg / 2
        _subtract(ledge, _cylinderAxis((xa, yc, zt - dg + rad), (xb, yc, zt - dg + rad), rad))
        _subtract(ledge, _box(xa, xb, yc - rad, yc + rad, zt - dg + rad, zt + 1.0))
    return ledge


def _knobStand(xc, r, kz, zFloor, ya, yb):
    """Trapezoid under a horizontal round knob, from the print bed up to the
    circle's 45° points. Never wider than the circle, so the round part only
    overhangs at <= 45° and nothing floats."""
    k = r / _SQRT2
    top = kz - k
    if top - zFloor < 0.02:
        return None
    hgt = top - zFloor
    run = r - k
    return _prismXZ(xc - r, xc + r, min(ya, yb), max(ya, yb), zFloor, top + _EPS,
                    [((xc - r, 0, zFloor), (-hgt, 0, run)),
                     ((xc + r, 0, zFloor), (hgt, 0, run))])


KNOB_FIN = 0.04       # breakaway fin thickness (one 0.4 mm line)
KNOB_FIN_GAP = 0.05   # fins keep this gap to the front face


def _knobFins(xc, r, kz, zFloor, ya, yb):
    """Breakaway supports: thin vertical fins from the print bed up to the
    underside of the round part. They stand free of the front face, so they
    snap off cleanly."""
    if kz - r - zFloor < 0.02:
        return None
    offsets = (0.0,) if r < 0.6 else (-0.55 * r, 0.0, 0.55 * r)
    fins = []
    for dx in offsets:
        topZ = kz - (r * r - dx * dx) ** 0.5 + _EPS
        fins.append(_box(xc + dx - KNOB_FIN / 2, xc + dx + KNOB_FIN / 2,
                         min(ya, yb), max(ya, yb), zFloor, topZ))
    return _unionAll(fins)


def _support(support, xc, r, kz, zFloor, ya, yb):
    if support == L.KNOB_SUPPORT_STAND:
        return _knobStand(xc, r, kz, zFloor, ya, yb)
    if support == L.KNOB_SUPPORT_THIN:
        return _knobFins(xc, r, kz, zFloor, ya, yb)
    return None


def _knob(ip, xc, w, front, zFloor, yF):
    """Round knob variants, with a stand, breakaway fins or no support.
    Returns (body, largest radius)."""
    fx0, fx1, fz0, fz1 = front
    style = ip.get('knobStyle', L.KNOB_ROUND)
    support = ip.get('knobSupport', L.KNOB_SUPPORT_STAND)
    p = max(0.4, float(ip['handleDepth']))
    kz = (fz0 + fz1) / 2
    rMax = max(0.2, min(kz - zFloor, fz1 - kz - 0.1))
    rk = max(0.2, min(w / 2, rMax))
    yIn = yF + _EPS
    # Fins stay clear of the front; a stand may grow out of it.
    yFree = yF - KNOB_FIN_GAP if support == L.KNOB_SUPPORT_THIN else yIn
    parts = []

    if style == L.KNOB_MUSHROOM:
        # Thin neck, wide cap in front of it to grip behind.
        rNeck = max(0.2, rk * 0.5)
        neckLen = max(0.3, p * 0.6)
        knob = _cylinderAxis((xc, yIn, kz), (xc, yF - neckLen, kz), rNeck)
        _union(knob, _cylinderAxis((xc, yF - neckLen + _EPS, kz), (xc, yF - p, kz), rk))
        parts.append(_support(support, xc, rNeck, kz, zFloor, yFree, yF - neckLen + _EPS))
        parts.append(_support(support, xc, rk, kz, zFloor, yF - neckLen + _EPS, yF - p))
    else:
        knob = _cylinderAxis((xc, yIn, kz), (xc, yF - p, kz), rk)
        if style == L.KNOB_SPOOL:
            # Round U groove around the middle, like a hose clamped on.
            rg = max(0.1, min(p / 4, rk / 3))
            try:
                torus = _tmgr().createTorus(adsk.core.Point3D.create(xc, yF - p / 2, kz),
                                            adsk.core.Vector3D.create(0, 1, 0), rk, rg)
                _subtract(knob, torus)
            except Exception:
                # Fallback: square groove instead of a round one.
                gplog.logExc('spool knob torus')
                ring = _cylinderAxis((xc, yF - p / 2 - rg, kz), (xc, yF - p / 2 + rg, kz), rk + 0.1)
                _subtract(ring, _cylinderAxis((xc, yF - p / 2 - rg - 0.1, kz), (xc, yF - p / 2 + rg + 0.1, kz), rk - rg))
                _subtract(knob, ring)
        parts.append(_support(support, xc, rk, kz, zFloor, yFree, yF - p))

    for part in parts:
        if part is not None:
            _union(knob, part)
    return knob, rk
