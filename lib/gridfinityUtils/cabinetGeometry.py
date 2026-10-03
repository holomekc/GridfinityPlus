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


# ------------------------------------------------------------------- cabinet

def buildCabinet(des: adsk.fusion.Design, params: dict) -> adsk.fusion.BRepBody:
    """Cabinet temp body in its local frame (see cabinetLayout)."""
    with gplog.timed('cabinet build'):
        cab = L.cabinet(params)
        p = cab['p']
        ox0, ox1, front, back = cab['x0'], cab['x1'], cab['front'], cab['back']
        body = _roundedSlab(ox0, ox1, front, back, cab['zBottom'], cab['zTop'], cab['radius'])

        # Interior: one open-front pocket per column.
        pockets = [_box(x0, x1, front - 1.0, cab['innerBack'], cab['floorTop'], cab['ceil'])
                   for x0, x1 in cab['columns']]
        _subtract(body, _unionAll(pockets))

        y1 = cab['innerBack'] + _EPS
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
            _union(body, _unionAll(adds))
        if cuts:
            _subtract(body, _unionAll(cuts))

        if p['detent']:
            bumps = []
            for c in range(len(cab['columns'])):
                for r in range(len(cab['rows'])):
                    for strip in L.contactStrips(cab, c, r):
                        bumps.append(_detentCylinder(strip, cab['detentY'], L.DETENT_RADIUS))
            _union(body, _unionAll(bumps))

        holes = []
        if cab['topIsGrid']:
            # Over a partial plate cell the top repeats it as a cut pocket
            # (unless the top edge is set to flat); over padding it stays flat.
            cell = _getCellCutout(des, p['baseW'], p['baseL'], p['cl'])
            part = cab['partial'] if p['topEdge'] == L.TOP_EDGE_PLATE else {}
            tL, tR = int(part.get('left', False)), int(part.get('right', False))
            tF, tB = int(part.get('front', False)), int(part.get('back', False))
            for i in range(-tL, int(p['unitsW']) + tR):
                for j in range(-tF, int(p['unitsL']) + tB):
                    tool = _tmgr().copy(cell)
                    _translate(tool, i * p['baseW'], j * p['baseL'], cab['zTop'])
                    holes.append(tool)
        if p['wallMount']:
            cols = cab['columns']
            xs = sorted({(cols[0][0] + cols[0][1]) / 2, (cols[-1][0] + cols[-1][1]) / 2})
            z = cab['ceil'] - 1.0
            yIn = cab['innerBack']
            for x in xs:
                holes.append(_cylinderAxis((x, yIn - _EPS, z), (x, back + 0.1, z), 0.225))
                head = min(0.2, cab['backWall'])
                holes.append(_cone((x, yIn - _EPS, z), 0.425 + _EPS, (x, yIn + head, z), 0.425 - head))
        if holes:
            _subtract(body, _unionAll(holes))

        if p['feet']:
            foot = _getFoot(des, p['baseW'], p['baseL'], p['cl'],
                            p['screws'], const.DIMENSION_SCREW_HOLE_DIAMETER,
                            p['magnets'], False,
                            const.DIMENSION_MAGNET_CUTOUT_DIAMETER, const.DIMENSION_MAGNET_CUTOUT_DEPTH)
            # Partial plate cell on a side: one more row/column of feet, cut
            # to the outline below (like a bin's partial feet).
            part = cab['partial']
            eL, eR = int(part.get('left', False)), int(part.get('right', False))
            eF, eB = int(part.get('front', False)), int(part.get('back', False))
            feet = []
            for i in range(-eL, int(p['unitsW']) + eR):
                for j in range(-eF, int(p['unitsL']) + eB):
                    f = _tmgr().copy(foot)
                    _translate(f, i * p['baseW'], j * p['baseL'])
                    feet.append(f)
            feet = _unionAll(feet)
            if eL or eR or eF or eB:
                window = _roundedSlab(ox0, ox1, front, back, -10.0, 10.0, cab['radius'])
                _tmgr().booleanOperation(feet, window, adsk.fusion.BooleanTypes.IntersectionBooleanType)
            _union(body, feet)

        gplog.log(f'cabinet build: faces={body.faces.count} errors={cab["errors"]}')
        return body


# -------------------------------------------------------------------- insert

def buildInsert(des: adsk.fusion.Design, cabParams: dict, insertParams: dict) -> adsk.fusion.BRepBody:
    """Insert temp body in the cabinet's local frame, closed position."""
    with gplog.timed('insert build'):
        cab = L.cabinet(cabParams)
        ins = L.insert(cab, insertParams)
        ip, cp = ins['p'], cab['p']
        x0, x1, y0, y1, z0, z1 = ins['x0'], ins['x1'], ins['y0'], ins['y1'], ins['z0'], ins['z1']
        tw = float(ip['wall'])
        tf = float(ip['floor'])
        frontT = float(ip['front'])

        body = _roundedSlab(x0, x1, y0, y1, z0, z1, 0.1)
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
            runners = [
                _runner(ins['colX0'], +1, y0, y1, gc, gd, fit, x0 + tw / 2),
                _runner(ins['colX1'], -1, y0, y1, gc, gd, fit, x1 - tw / 2),
            ]
            _union(body, _unionAll(runners))

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
        _subtract(body, _unionAll(tools))

        # Front: label band + handle band, wire outlets.
        labelRect, band, blocked = frontLayout(ip, fx0, fx1, fz0, fz1)
        adds, cuts = [], []
        handleX = _handle(ip, band, fz1, yF, yB, z0, z1, tw, adds, cuts)
        _label(ip, labelRect, yF, adds, cuts)
        _wireHoles(ip, band, ([handleX] if handleX else []) + blocked, yF, yB, cuts)
        if adds:
            _union(body, _unionAll(adds))

        # Detent: notch where the bump rests when closed, ridge, relief channel
        # behind it; with a stop, the channel ends before the back (solid land
        # that catches on the bump when pulled out).
        r = L.DETENT_RADIUS + L.DETENT_CLEARANCE
        yd = cab['detentY']
        chEnd = y1 - L.STOP_LAND if ip['stop'] else y1 + 1.0
        for strip in ins['contact']:
            xa, xb, z = strip
            cuts.append(_detentCylinder((xa - _EPS, xb + _EPS, z), yd, r))
            chStart = yd + r + L.DETENT_RIDGE
            if chEnd > chStart:
                cuts.append(_box(xa - _EPS, xb + _EPS, chStart, chEnd, z - r, z + r))
        if cuts:
            _subtract(body, _unionAll(cuts))

        pull = float(ip.get('pullOut', 0.0))
        if pull:
            _translate(body, 0.0, -pull, 0.0)
        gplog.log(f'insert build: faces={body.faces.count} errors={ins["errors"]}')
        return body


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

    The label goes below / above the handle when the front is high enough for
    both, otherwise beside it (handle stays centred). 'Auto' picks for you.
    blockedX: x ranges taken by the label (wire outlets keep clear)."""
    W, H = fx1 - fx0, fz1 - fz0
    xc = (fx0 + fx1) / 2
    band = (fx0, fx1, fz0, fz1)
    if ip['label'] == L.LABEL_NONE:
        return None, band, []
    frame = CARD_FRAME if ip['label'] == L.LABEL_CARD else 0.0
    pos = ip['labelPos']
    notch = ip['handle'] == L.HANDLE_NOTCH
    needHandle = 0.0 if ip['handle'] == L.HANDLE_NONE else max(1.0, float(ip['handleHeight'])) + 0.4
    lhWanted = float(ip['labelHeight'])
    if pos == L.LABEL_AUTO:
        stacked = H >= needHandle + lhWanted + 2 * frame + LABEL_MARGIN + 0.2
        pos = L.LABEL_BOTTOM if stacked else L.LABEL_LEFT
    if notch and pos == L.LABEL_TOP:
        pos = L.LABEL_BOTTOM

    if pos in (L.LABEL_BOTTOM, L.LABEL_TOP):
        lh = max(0.4, min(lhWanted, H * 0.45))
        lw = max(0.6, min(float(ip['labelWidth']), W - 2 * frame - 0.4))
        if pos == L.LABEL_TOP:
            lz1 = fz1 - LABEL_MARGIN
            lz0 = lz1 - lh
            band = (fx0, fx1, fz0, lz0 - frame - 0.1)
        else:
            lz0 = fz0 + LABEL_MARGIN + frame
            lz1 = lz0 + lh
            band = (fx0, fx1, lz1 + 0.1, fz1)
        return (xc - lw / 2, xc + lw / 2, lz0, lz1), band, []

    # Beside the handle: centred in the free part left / right of it.
    half = handleHalfWidth(ip, W) + 0.3
    if pos == L.LABEL_LEFT:
        a, b = fx0 + LABEL_MARGIN + frame, xc - half - frame
    else:
        a, b = xc + half + frame, fx1 - LABEL_MARGIN - frame
    if b - a < 0.6:
        return None, band, []
    lw = min(float(ip['labelWidth']), b - a)
    lh = max(0.4, min(lhWanted, H - 2 * LABEL_MARGIN - 2 * frame))
    if notch:
        # Notch is cut from the top; keep the label low.
        lz0 = fz0 + LABEL_MARGIN + frame
    else:
        lz0 = (fz0 + fz1) / 2 - lh / 2
    cx = (a + b) / 2
    rect = (cx - lw / 2, cx + lw / 2, lz0, lz0 + lh)
    return rect, band, [(rect[0] - frame - 0.2, rect[1] + frame + 0.2)]


def _label(ip, rect, yF, adds, cuts):
    if rect is None:
        return
    lx0, lx1, lz0, lz1 = rect
    if ip['label'] == L.LABEL_RECESS:
        # 0.3 mm deep field: the sticker sits flush and straight.
        cuts.append(_box(lx0, lx1, yF - 0.1, yF + 0.03, lz0, lz1))
        return
    # Card holder, open at the top: slot behind a front flange. All walls are
    # vertical, the flange stands on the bottom frame, so no supports needed.
    s, e, g, t = CARD_FRAME, CARD_LIP, CARD_GAP, CARD_FLANGE
    holder = _box(lx0 - s, lx1 + s, yF - g - t, yF + _EPS, lz0 - s, lz1)
    _subtract(holder, _box(lx0, lx1, yF - g, yF, lz0, lz1 + 1.0))
    _subtract(holder, _box(lx0 + e, lx1 - e, yF - g - t - 0.1, yF - g + _EPS, lz0 + e, lz1 + 1.0))
    adds.append(holder)


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


def _handle(ip, band, frontTop, yF, yB, zFloor, zTop, tw, adds, cuts):
    """Add the handle to adds/cuts. band = (x0, x1, z0, z1) on the front face
    at y=yF (outside is -y), front material ends at y=yB. zFloor/zTop: the
    insert's bottom/top. Returns the handle's x range (or None)."""
    kind = ip['handle']
    if kind == L.HANDLE_NONE:
        return None
    bx0, bx1, bz0, bz1 = band
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
        rad = h / 2
        half = max(0.0, w / 2 - rad)
        cuts.append(_box(xc - half, xc + half, yF - 0.1, yB + _EPS, zc - rad, zc + rad))
        for x in (xc - half, xc + half):
            cuts.append(_cylinderAxis((x, yF - 0.1, zc), (x, yB + _EPS, zc), rad))
        return (xc - w / 2, xc + w / 2)

    if kind in (L.HANDLE_LIP, L.HANDLE_BAR):
        # Top plate + outer grip bar, hollow behind the bar and open at the
        # bottom. Underside of the bar at 45°, the cavity roof is a bridge.
        # Lip: open at the sides too; bar: closed by posts (D-handle).
        topT, barT = 0.3, 0.35
        p = max(barT + 0.8, float(ip['handleDepth']))
        hh = max(topT + 0.5, min(h, H - 0.3))
        zt = min(bz1 - 0.1, zc + (hh + p) / 2)
        p = max(barT + 0.5, min(p, zt - hh - bz0))
        grip = _prismYZ(xc - w / 2, xc + w / 2, yF - p, yF + _EPS, zt - hh - p, zt,
                        [((0, yF - p, zt - hh), (0, -1, -1))])
        post = 0.5 if kind == L.HANDLE_BAR and w > 2.0 else -0.1
        _subtract(grip, _box(xc - w / 2 + post, xc + w / 2 - post,
                             yF - p + barT, yF, zt - hh - p - 1.0, zt - topT))
        adds.append(grip)
        return (xc - w / 2, xc + w / 2)

    if kind == L.HANDLE_KNOB:
        rk = max(0.3, min(w / 2, (H - 0.2) / (1 + _SQRT2)))
        p = float(ip['handleDepth'])
        kz = zc + (rk * _SQRT2 - rk) / 2
        knob = _cylinderAxis((xc, yF + _EPS, kz), (xc, yF - p, kz), rk)
        # Teardrop: 45° diamond below the axis so it prints without support.
        c = 1 / _SQRT2
        obb = adsk.core.OrientedBoundingBox3D.create(
            adsk.core.Point3D.create(xc, yF - p / 2 + _EPS / 2, kz),
            adsk.core.Vector3D.create(c, 0, c), adsk.core.Vector3D.create(0, 1, 0),
            2 * rk, p + _EPS, 2 * rk)
        diamond = _tmgr().createBox(obb)
        _subtract(diamond, _box(xc - 3 * rk, xc + 3 * rk, yF - p - 1.0, yF + 1.0, kz, kz + 3 * rk))
        _union(knob, diamond)
        adds.append(knob)
        return (xc - rk, xc + rk)

    return None
