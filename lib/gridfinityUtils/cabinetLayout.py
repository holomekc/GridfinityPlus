"""
GridfinityPlus — box system (cabinet + inserts): pure layout math.

No geometry here, only numbers, so every dimension the cabinet and its inserts
agree on comes from ONE place. Both the cabinet generator and the insert
(drawer / box) generator call into this module with the cabinet's params.

Cabinet local frame (same convention as a bin, so bin placement code applies):
  x: width  0 .. aW   (aW = unitsW * baseW - 2 * cl)
  y: depth  0 .. aL   front (open side) at y = 0, back wall at y = aL
  On a plate with padding / partial cells the outline may grow past that
  footprint ('ovh', like a bin): x from -ovh.left to aW + ovh.right, front at
  y = -ovh.front, back at aL + ovh.back. The feet stay on the grid.
  z: up     feet from -BIN_BASE_HEIGHT to 0, body from 0 (or -BIN_BASE_HEIGHT
            without feet) up to zTop = height * heightUnit - BIN_BASE_HEIGHT.

Inside, the cabinet is split into columns (vertical dividers) and rows. Inserts
run on either
  * ledges  — shelf strips on the walls; the insert's bottom rests on them, or
  * grooves — V-grooves in the walls; the insert carries matching runners.

Inserts are always derived from the cabinet: pick column + row (+ span), the
insert size follows from walls, guides and clearances.

All lengths in Fusion internal units (cm).
"""

from . import const

GUIDE_LEDGE = 'Ledges'
GUIDE_GROOVE = 'Grooves'
GUIDE_TYPES = (GUIDE_LEDGE, GUIDE_GROOVE)

TOP_FLAT = 'Flat'
TOP_GRID = 'Gridfinity grid (stackable)'
TOP_TYPES = (TOP_FLAT, TOP_GRID)
# Top grid over the plate border / partial cells (cabinet 'Fill to edge').
TOP_EDGE_PLATE = 'Like the plate (partial pockets)'
TOP_EDGE_FLAT = 'Flat'
TOP_EDGE_TYPES = (TOP_EDGE_PLATE, TOP_EDGE_FLAT)

INSERT_DRAWER = 'Drawer'
INSERT_BLANK = 'Blank cover'
INSERT_TYPES = (INSERT_DRAWER, INSERT_BLANK)
# Default depth of a blank cover (front + short frame for the guides).
BLANK_DEPTH = 1.2

FRONT_FLUSH = 'Flush'
FRONT_OVERLAY = 'Overlay'
FRONT_STYLES = (FRONT_FLUSH, FRONT_OVERLAY)

INTERIOR_EMPTY = 'Empty'
INTERIOR_COMPARTMENTS = 'Compartments'
INTERIOR_GRID = 'Gridfinity grid'
INTERIOR_TYPES = (INTERIOR_EMPTY, INTERIOR_COMPARTMENTS, INTERIOR_GRID)

HANDLE_NONE = 'None'
HANDLE_RECESS = 'Recessed pull'
HANDLE_SCOOP = 'Scoop pull'
HANDLE_LIP = 'Hook lip'
HANDLE_BAR = 'Bar handle'
HANDLE_NOTCH = 'Top notch'
HANDLE_SLOT = 'Finger hole'
HANDLE_KNOB = 'Knob'
HANDLE_TYPES = (HANDLE_RECESS, HANDLE_SCOOP, HANDLE_LIP, HANDLE_BAR, HANDLE_NOTCH, HANDLE_SLOT, HANDLE_KNOB, HANDLE_NONE)

KNOB_ROUND = 'Round'
KNOB_MUSHROOM = 'Mushroom'
KNOB_SPOOL = 'Spool (U groove)'
KNOB_STYLES = (KNOB_ROUND, KNOB_MUSHROOM, KNOB_SPOOL)

LABEL_NONE = 'None'
LABEL_RECESS = 'Sticker recess'
LABEL_CARD = 'Card holder'
LABEL_TYPES = (LABEL_RECESS, LABEL_CARD, LABEL_NONE)
LABEL_AUTO = 'Auto'
LABEL_BOTTOM = 'Below handle'
LABEL_TOP = 'Above handle'
LABEL_LEFT = 'Left of handle'
LABEL_RIGHT = 'Right of handle'
LABEL_POSITIONS = (LABEL_AUTO, LABEL_BOTTOM, LABEL_TOP, LABEL_LEFT, LABEL_RIGHT)

# Values stored by earlier versions -> current ones.
_LEGACY = {
    'insertType': {'Drawer (overlay front)': INSERT_DRAWER, 'Box (flush front)': INSERT_DRAWER},
    'handle': {'Finger notch': HANDLE_NOTCH, 'Finger slot': HANDLE_SLOT, 'Pull tab': HANDLE_LIP},
    'labelPos': {'Bottom': LABEL_BOTTOM, 'Top': LABEL_TOP},
}

# Smallest free row height an insert can live in.
MIN_ROW_HEIGHT = 1.0
# Minimum material left behind a groove.
GROOVE_MIN_BACKING = 0.12
# Flat tip of the V-groove / runner profile.
GROOVE_TIP = 0.1
# Detent: default bump height on the cabinet, its distance from the front and
# the ridge the insert climbs over before it clicks in.
DETENT_HEIGHT = 0.06
DETENT_FRONT_OFFSET = 0.6
DETENT_RIDGE = 0.15
DETENT_CLEARANCE = 0.02
# Pull-out stop: solid land at the insert's back end that hits the bump.
STOP_LAND = 0.4

CABINET_DEFAULTS = {
    'unitsW': 2,
    'unitsL': 3,
    'heightMode': 'Units',
    'heightUnits': 12,
    'heightMm': 12 * const.DIMENSION_DEFAULT_HEIGHT_UNIT,
    'baseW': const.DIMENSION_DEFAULT_WIDTH_UNIT,
    'baseL': const.DIMENSION_DEFAULT_WIDTH_UNIT,
    'heightUnit': const.DIMENSION_DEFAULT_HEIGHT_UNIT,
    'cl': const.BIN_XY_CLEARANCE,
    'wall': 0.12,
    'backWall': 0.12,
    'floor': 0.12,
    'top': 0.12,
    'divider': 0.12,
    'columns': 1,
    'rows': 3,
    'rowWeights': '',
    'guide': GUIDE_LEDGE,
    'ledgeDepth': 0.3,
    'ledgeThickness': 0.15,
    'grooveDepth': 0.2,
    'fitLateral': 0.05,
    'fitVertical': 0.08,
    'fitBack': 0.0,
    'detent': True,
    'detentHeight': DETENT_HEIGHT,
    'feet': True,
    'magnets': False,
    'screws': False,
    'topType': TOP_GRID,
    'wallMount': False,
    # Body extension over plate border / partial cells, resolved from the plate.
    'ovh': {},
    'topEdge': TOP_EDGE_PLATE,
}

INSERT_DEFAULTS = {
    'insertType': INSERT_DRAWER,
    'frontStyle': FRONT_FLUSH,
    'depth': 0.0,
    'column': 1,
    'row': 1,
    'span': 1,
    'pullOut': 0.0,
    'wall': 0.12,
    'floor': 0.12,
    'front': 0.15,
    'frontGap': 0.05,
    'handle': HANDLE_RECESS,
    'handleWidth': 4.0,
    'handleHeight': 1.6,
    'handleDepth': 1.5,
    'knobStyle': KNOB_ROUND,
    'label': LABEL_RECESS,
    'labelPos': LABEL_AUTO,
    'labelWidth': 5.0,
    'labelHeight': 1.2,
    'wireHoles': 0,
    'wireDiameter': 0.5,
    'interior': INTERIOR_EMPTY,
    'divX': 2,
    'divY': 1,
    'stop': True,
}


def withDefaults(params: dict, defaults: dict) -> dict:
    out = dict(defaults)
    out.update({k: v for k, v in (params or {}).items() if v is not None})
    for key, mapping in _LEGACY.items():
        if out.get(key) in mapping:
            if key == 'insertType' and 'frontStyle' not in (params or {}):
                out['frontStyle'] = FRONT_OVERLAY if out[key] == 'Drawer (overlay front)' else FRONT_FLUSH
            out[key] = mapping[out[key]]
    return out


def heightUnits(p: dict) -> float:
    """Effective height in height units (fractional for mm mode)."""
    if p.get('heightMode') == 'Total height':
        hu = float(p['heightUnit'])
        return float(p['heightMm']) / hu if hu > 0 else 1.0
    return float(p['heightUnits'])


def parseWeights(text: str, count: int):
    """'1, 1, 2' -> [1, 1, 2]; empty/invalid -> count equal rows."""
    weights = []
    for part in str(text or '').replace(';', ',').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            w = float(part)
        except ValueError:
            return [1.0] * max(1, count)
        if w <= 0:
            return [1.0] * max(1, count)
        weights.append(w)
    return weights if weights else [1.0] * max(1, count)


def footprint(p: dict):
    cl = float(p['cl'])
    return int(p['unitsW']) * float(p['baseW']) - 2 * cl, int(p['unitsL']) * float(p['baseL']) - 2 * cl


def cabinet(params: dict) -> dict:
    """Every cabinet dimension, derived from its params. Pure numbers."""
    p = withDefaults(params, CABINET_DEFAULTS)
    aW, aL = footprint(p)
    ovh = p.get('ovh') or {}
    ox0 = -float(ovh.get('left', 0) or 0)
    ox1 = aW + float(ovh.get('right', 0) or 0)
    oy0 = -float(ovh.get('front', 0) or 0)
    oy1 = aL + float(ovh.get('back', 0) or 0)
    baseH = const.BIN_BASE_HEIGHT
    zTop = heightUnits(p) * float(p['heightUnit']) - baseH
    zBottom = -baseH if not p['feet'] else 0.0
    grooved = p['guide'] == GUIDE_GROOVE
    gd = float(p['grooveDepth'])

    wall = float(p['wall'])
    divider = float(p['divider'])
    if grooved:
        wall = max(wall, gd + GROOVE_MIN_BACKING)
        divider = max(divider, 2 * gd + GROOVE_MIN_BACKING)
    backWall = float(p['backWall'])
    floorTop = zBottom + float(p['floor']) if not p['feet'] else float(p['floor'])
    topIsGrid = p['topType'] == TOP_GRID
    topThickness = float(p['top']) + (baseH if topIsGrid else 0.0)
    ceil = zTop - topThickness
    innerBack = oy1 - backWall

    nCols = max(1, int(p['columns']))
    innerW = (ox1 - ox0) - 2 * wall
    colW = (innerW - (nCols - 1) * divider) / nCols
    columns = []
    x = ox0 + wall
    for i in range(nCols):
        columns.append((x, x + colW))
        x += colW + divider

    weights = parseWeights(p['rowWeights'], int(p['rows']))
    nRows = len(weights)
    ledgeZone = float(p['ledgeThickness']) + float(p['ledgeDepth']) if not grooved else 0.0
    avail = (ceil - floorTop) - (nRows - 1) * ledgeZone
    rows = []
    z = floorTop
    total = sum(weights)
    for i, w in enumerate(weights):
        h = avail * w / total
        rows.append({'bottom': z, 'top': z + h, 'height': h})
        z += h + ledgeZone

    errors = []
    if innerW <= 0 or colW < 2.0:
        errors.append('Columns too narrow (min 20 mm inside)')
    if innerBack - oy0 < 3.0:
        errors.append('Cabinet too shallow')
    if any(r['height'] < MIN_ROW_HEIGHT for r in rows):
        errors.append('Rows too low (min {:g} mm free height)'.format(MIN_ROW_HEIGHT * 10))
    if grooved and any(r['height'] < 2 * gd + GROOVE_TIP + 0.4 for r in rows):
        errors.append('Rows too low for the grooves')

    return {
        'p': p,
        'aW': aW, 'aL': aL,
        'x0': ox0, 'x1': ox1, 'front': oy0, 'back': oy1,
        'detentY': oy0 + DETENT_FRONT_OFFSET,
        'detentR': float(p['detentHeight']) if p['detent'] else 0.0,
        'partial': {k: bool(v) for k, v in ((ovh.get('partial') or {}).items())},
        'zBottom': zBottom, 'zTop': zTop,
        'radius': const.BIN_CORNER_FILLET_RADIUS - float(p['cl']),
        'wall': wall, 'divider': divider, 'backWall': backWall,
        'floorTop': floorTop, 'ceil': ceil, 'innerBack': innerBack,
        'topIsGrid': topIsGrid,
        'columns': columns, 'rows': rows,
        'grooved': grooved, 'grooveDepth': gd,
        'ledgeDepth': float(p['ledgeDepth']), 'ledgeThickness': float(p['ledgeThickness']),
        'errors': errors,
    }


def grooveCenter(row: dict) -> float:
    return (row['bottom'] + row['top']) / 2


def supportZ(cab: dict, rowIndex: int) -> float:
    """z of the surface an insert in this row rests / runs on (ledge variant)."""
    return cab['rows'][rowIndex]['bottom']


def contactStrips(cab: dict, colIndex: int, rowIndex: int):
    """Detent strips [(xA, xB, z)] for one column/row: where the cabinet bump
    sits and the insert gets its notch + relief channel.

    Only a narrow sub-strip of the support is used, so the rest of the ledge /
    groove flank keeps carrying the insert along its full length (a channel over
    the whole support would let the back of the insert sag)."""
    x0, x1 = cab['columns'][colIndex]
    row = cab['rows'][rowIndex]
    if cab['grooved']:
        gd = cab['grooveDepth']
        # Outer half of the lower flank (towards the groove tip).
        z = grooveCenter(row) - GROOVE_TIP / 2 - 0.25 * gd
        return [(x0 - gd, x0 - gd / 2, z), (x1 + gd / 2, x1 + gd, z)]
    # Middle of the strip where the insert overlaps the ledge, so it is still
    # carried on both sides of the channel. The floor (bottom row) uses the
    # same strips.
    mid = (float(cab['p']['fitLateral']) + cab['ledgeDepth']) / 2
    z = row['bottom']
    return [(x0 + mid - 0.05, x0 + mid + 0.05, z), (x1 - mid - 0.05, x1 - mid + 0.05, z)]


def clampInsert(cab: dict, ip: dict) -> dict:
    """Column/row/span (1-based in params) clamped onto the cabinet layout."""
    nCols = len(cab['columns'])
    nRows = len(cab['rows'])
    col = max(1, min(int(ip['column']), nCols))
    row = max(1, min(int(ip['row']), nRows))
    span = 1 if not cab['grooved'] else max(1, int(ip.get('span', 1)))
    span = min(span, nRows - row + 1)
    return {'column': col, 'row': row, 'span': span}


def insert(cab: dict, insertParams: dict) -> dict:
    """Insert dimensions (closed position, cabinet local frame)."""
    ip = withDefaults(insertParams, INSERT_DEFAULTS)
    cp = cab['p']
    slot = clampInsert(cab, ip)
    c = slot['column'] - 1
    r0 = slot['row'] - 1
    r1 = r0 + slot['span'] - 1
    x0, x1 = cab['columns'][c]
    lat = float(cp['fitLateral'])
    vert = float(cp['fitVertical'])
    if cab['detentR'] > 0:
        # The insert rides over the bump: it lifts by the bump height.
        vert = max(vert, cab['detentR'] + DETENT_CLEARANCE)

    rowLo = cab['rows'][r0]
    rowHi = cab['rows'][r1]
    if cab['grooved']:
        z0 = rowLo['bottom'] + vert / 2
        z1 = rowHi['top'] - vert / 2
    else:
        z0 = rowLo['bottom']
        z1 = rowHi['top'] - vert
    y1 = cab['innerBack'] - float(cp['fitBack'])
    depth = float(ip.get('depth') or 0.0)
    if ip['insertType'] == INSERT_BLANK and depth <= 0:
        depth = BLANK_DEPTH
    if depth > 0:
        y1 = min(y1, cab['front'] + max(depth, DETENT_FRONT_OFFSET + 0.6))

    overlay = ip['frontStyle'] == FRONT_OVERLAY
    gap = float(ip['frontGap'])
    # Overlay front: covers the walls/dividers half way and the ledge zone above.
    nCols = len(cab['columns'])
    left = cab['x0'] if c == 0 else x0 - cab['divider'] / 2
    right = cab['x1'] if c == nCols - 1 else x1 + cab['divider'] / 2
    if r1 + 1 < len(cab['rows']):
        nxt = cab['rows'][r1 + 1]['bottom'] + (vert / 2 if cab['grooved'] else 0.0)
        panelTop = nxt - gap
    else:
        panelTop = cab['zTop'] - gap / 2
    panel = {
        'x0': left + gap / 2, 'x1': right - gap / 2,
        'z0': z0, 'z1': panelTop,
        'y0': cab['front'] - float(ip['front']), 'y1': cab['front'],
    }

    errors = list(cab['errors'])
    w = (x1 - lat) - (x0 + lat)
    h = z1 - z0
    if w < 1.0 or h < 0.6:
        errors.append('Slot too small for an insert')

    return {
        'p': ip,
        'slot': slot,
        'overlay': overlay,
        'blank': ip['insertType'] == INSERT_BLANK,
        'x0': x0 + lat, 'x1': x1 - lat,
        'y0': cab['front'], 'y1': y1,
        'z0': z0, 'z1': z1,
        'colX0': x0, 'colX1': x1,
        'panel': panel if overlay else None,
        'grooveCenter': grooveCenter(rowLo) if cab['grooved'] else None,
        'contact': contactStrips(cab, c, r0) if cp['detent'] else [],
        'errors': errors,
    }


def gridCells(innerW: float, innerL: float, baseW: float, baseL: float, cl: float):
    """How many Gridfinity cells fit an inner area (cell cutout = base + 2 cl)."""
    nx = int((innerW - 2 * cl) // baseW) if baseW > 0 else 0
    ny = int((innerL - 2 * cl) // baseL) if baseL > 0 else 0
    return max(0, nx), max(0, ny)


def describeCabinet(params: dict) -> str:
    p = withDefaults(params, CABINET_DEFAULTS)
    h = heightUnits(p)
    hText = str(int(round(h))) if abs(h - round(h)) < 1e-6 else '{:g}mm'.format(round(h * float(p['heightUnit']) * 10, 1))
    cab = cabinet(p)
    return 'Cabinet {}x{}x{} ({} col x {} rows)'.format(
        int(p['unitsW']), int(p['unitsL']), hText, len(cab['columns']), len(cab['rows']))


def describeInsert(cab: dict, params: dict) -> str:
    ip = withDefaults(params, INSERT_DEFAULTS)
    slot = clampInsert(cab, ip)
    kind = 'Drawer' if ip['insertType'] == INSERT_DRAWER else 'Cover'
    rows = str(slot['row']) if slot['span'] == 1 else '{}-{}'.format(slot['row'], slot['row'] + slot['span'] - 1)
    return '{} - col {}, row {}'.format(kind, slot['column'], rows)
