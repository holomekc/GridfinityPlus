"""
GridfinityPlus — split a baseplate into printable tiles.

Large plates (e.g. 13 x 8 cells) do not fit the print bed. The plate is cut
into tiles along cell boundaries (the seam runs along the middle of the ridge
between two cells), as evenly as possible within the max print size.

Connectors: vertical dovetails, one per cell along each seam, at the middle of
the cell edge (away from corners and magnet holes). They run through the full
plate height, so tiles are pushed together from the top and then hold
sideways. On Full / Skeletonized plates they sit in the solid floor; on Light
plates they interlock in the lower part of the ridge.

The tiles stay assembled in place, one body per tile with a small gap on
every seam, so each tile exports on its own.

All lengths in cm, plate local frame (see plateLayout).
"""

import math

import adsk.core, adsk.fusion

from . import plateLayout

KEY_MODE = 'splitMode'
KEY_MAX_W = 'splitMaxWidth'
KEY_MAX_D = 'splitMaxDepth'
KEY_CONNECTOR = 'splitConnector'
KEY_CLEARANCE = 'splitClearance'            # seam gap, tile to tile
KEY_DOVETAIL_CLEARANCE = 'splitDovetailClearance'   # gap around the dovetail

SPLIT_OFF = 'Off'
SPLIT_MAX = 'Max print size'
SPLIT_MODES = (SPLIT_OFF, SPLIT_MAX)

CONN_DOVETAIL = 'Dovetail (push in from top)'
CONN_NONE = 'None (straight seams)'
CONNECTORS = (CONN_DOVETAIL, CONN_NONE)

DEFAULTS = {
    KEY_MODE: SPLIT_OFF,
    KEY_MAX_W: 25.0,
    KEY_MAX_D: 25.0,
    KEY_CONNECTOR: CONN_DOVETAIL,
    KEY_CLEARANCE: 0.015,
    KEY_DOVETAIL_CLEARANCE: 0.015,
}

# Dovetail (top view): neck width at the seam, head width, depth across it.
DOVETAIL_NECK = 0.5
DOVETAIL_HEAD = 0.8
DOVETAIL_DEPTH_LIGHT = 0.2
DOVETAIL_DEPTH_FLOOR = 0.3


def _get(params: dict, key):
    v = params.get(key)
    return DEFAULTS[key] if v is None else v


def dovetailClearance(params: dict) -> float:
    """Gap around the dovetail. Plates made before it was separate used the
    seam gap for both."""
    v = params.get(KEY_DOVETAIL_CLEARANCE)
    return float(_get(params, KEY_CLEARANCE) if v is None else v)


def enabled(params: dict) -> bool:
    return _get(params, KEY_MODE) == SPLIT_MAX


def _seams(start: float, end: float, pitch: float, cl: float, nCells: int, maxLen: float):
    """Seam positions (cell boundaries) so no segment exceeds maxLen.

    Tries an even split with as few tiles as possible; returns None if a
    single cell already exceeds maxLen."""
    total = end - start
    if total <= maxLen + 1e-9:
        return []
    cands = [k * pitch - cl for k in range(1, nCells)]
    cands = [c for c in cands if start + 0.5 < c < end - 0.5]
    for k in range(int(math.ceil(total / maxLen)), len(cands) + 2):
        chosen = []
        prev = start
        for j in range(1, k):
            target = start + j * total / k
            options = [c for c in cands if c > prev + 1e-6]
            if not options:
                break
            c = min(options, key=lambda v: abs(v - target))
            chosen.append(c)
            prev = c
        if len(chosen) != k - 1:
            continue
        bounds = [start] + chosen + [end]
        if all(b - a <= maxLen + 1e-9 for a, b in zip(bounds, bounds[1:])):
            return chosen
    return None


def plan(params: dict) -> dict:
    """{'xs': seams x, 'ys': seams y, 'tiles': (nx, ny), 'sizes': [...], 'error'}."""
    lo = plateLayout.layout(params)
    cl = params['xyClearance']
    xs = _seams(lo['x0'], lo['x1'], params['baseWidth'], cl, lo['nX'], float(_get(params, KEY_MAX_W)))
    ys = _seams(lo['y0'], lo['y1'], params['baseLength'], cl, lo['nY'], float(_get(params, KEY_MAX_D)))
    if xs is None or ys is None:
        return {'xs': [], 'ys': [], 'tiles': (1, 1), 'sizes': [],
                'error': 'One cell is larger than the max print size'}
    bx = [lo['x0']] + xs + [lo['x1']]
    by = [lo['y0']] + ys + [lo['y1']]
    widths = [b - a for a, b in zip(bx, bx[1:])]
    depths = [b - a for a, b in zip(by, by[1:])]
    return {'xs': xs, 'ys': ys, 'tiles': (len(widths), len(depths)),
            'widths': widths, 'depths': depths, 'error': None}


def describe(params: dict) -> str:
    if not enabled(params):
        return ''
    pl = plan(params)
    if pl['error']:
        return pl['error']
    nx, ny = pl['tiles']
    if nx * ny == 1:
        return 'Fits in one piece'
    mm = lambda vals: ' + '.join('{:g}'.format(round(v * 10)) for v in vals)
    return '{} x {} tiles, widths {} mm, depths {} mm'.format(nx, ny, mm(pl['widths']), mm(pl['depths']))


# ------------------------------------------------------------------ geometry

def _dovetail(axis: int, seam: float, center: float, neck: float, head: float, depth: float,
              z0: float, z1: float, back: float, offset: float = 0.0):
    """Dovetail prism protruding +x (axis 0) or +y (axis 1) from the seam,
    reaching `back` behind it into its own tile.

    offset > 0 builds the matching socket: every face moved outwards by
    `offset` (flanks parallel to the tab), so the gap is the same all around."""
    import math
    from .cabinetGeometry import _cutHalfSpace
    from .baseplateFastPreview import _box
    flare = (head - neck) / 2
    length = math.hypot(flare, depth)
    # Flank normals (pointing away from the tab), in (along seam normal, along seam).
    nA, nS = -flare / length, depth / length
    half = head / 2 + offset + flare + 0.1
    if axis == 0:
        body = _box(seam - back, seam + depth + offset, center - half, center + half, z0, z1)
        for sgn in (1, -1):
            px, py = seam + nA * offset, center + sgn * (neck / 2 + nS * offset)
            _cutHalfSpace(body, (px, py, 0), (nA, sgn * nS, 0))
    else:
        body = _box(center - half, center + half, seam - back, seam + depth + offset, z0, z1)
        for sgn in (1, -1):
            px, py = center + sgn * (neck / 2 + nS * offset), seam + nA * offset
            _cutHalfSpace(body, (px, py, 0), (sgn * nS, nA, 0))
    return body


def split(tempBody, params: dict):
    """All tiles merged into one temp body (dialog preview)."""
    tiles = pieces(tempBody, params)
    if len(tiles) == 1:
        return tiles[0]
    from .baseplateFastPreview import _unionAll
    return _unionAll(tiles)


def pieces(tempBody, params: dict):
    """Cut the finished plate (local frame) into tiles: one temp body per
    tile, ordered left to right, front to back. [tempBody] when splitting is
    off or not needed."""
    if not enabled(params):
        return [tempBody]
    pl = plan(params)
    if pl['error'] or pl['tiles'] == (1, 1):
        return [tempBody]
    from .baseplateFastPreview import _box, _union, _subtract, _tmgr
    lo = plateLayout.layout(params)
    zb = plateLayout.zBottom(params)
    z0, z1 = zb - 1.0, 1.0
    c = float(_get(params, KEY_CLEARANCE))
    dc = dovetailClearance(params)
    big = 1000.0
    bx = [-big] + pl['xs'] + [big]
    by = [-big] + pl['ys'] + [big]
    nx, ny = pl['tiles']
    # Straight seam gap: half the clearance on each side.
    regions = [[_box(bx[i] + (c / 2 if i > 0 else 0), bx[i + 1] - (c / 2 if i < nx - 1 else 0),
                     by[j] + (c / 2 if j > 0 else 0), by[j + 1] - (c / 2 if j < ny - 1 else 0), z0, z1)
                for j in range(ny)] for i in range(nx)]

    if _get(params, KEY_CONNECTOR) == CONN_DOVETAIL:
        depth = DOVETAIL_DEPTH_LIGHT if params.get('plateType') == 'Light' else DOVETAIL_DEPTH_FLOOR
        p, q, cl = params['baseWidth'], params['baseLength'], params['xyClearance']
        # Cell edge middles along each seam, inside the plate.
        midsY = [j * q + q / 2 - cl for j in range(lo['nY'])]
        midsX = [i * p + p / 2 - cl for i in range(lo['nX'])]
        midsY = [m for m in midsY if lo['y0'] + 0.8 < m < lo['y1'] - 0.8]
        midsX = [m for m in midsX if lo['x0'] + 0.8 < m < lo['x1'] - 0.8]
        tabs, sockets = [], []
        for k, s in enumerate(pl['xs']):
            for m in midsY:
                j = next(t for t in range(ny) if by[t] <= m < by[t + 1])
                if min(m - by[j], by[j + 1] - m) < DOVETAIL_HEAD:
                    continue
                tabs.append((k, j, _dovetail(0, s, m, DOVETAIL_NECK, DOVETAIL_HEAD, depth, z0, z1, 0.3)))
                sockets.append((k + 1, j, _dovetail(0, s, m, DOVETAIL_NECK, DOVETAIL_HEAD,
                                                    depth, z0 - 1, z1 + 1, 0.3, dc)))
        for k, s in enumerate(pl['ys']):
            for m in midsX:
                i = next(t for t in range(nx) if bx[t] <= m < bx[t + 1])
                if min(m - bx[i], bx[i + 1] - m) < DOVETAIL_HEAD:
                    continue
                tabs.append((i, k, _dovetail(1, s, m, DOVETAIL_NECK, DOVETAIL_HEAD, depth, z0, z1, 0.3)))
                sockets.append((i, k + 1, _dovetail(1, s, m, DOVETAIL_NECK, DOVETAIL_HEAD,
                                                    depth, z0 - 1, z1 + 1, 0.3, dc)))
        for i, j, tab in tabs:
            _union(regions[i][j], tab)
        for i, j, sock in sockets:
            _subtract(regions[i][j], sock)

    result = []
    for j in range(ny):
        for i in range(nx):
            piece = _tmgr().copy(tempBody)
            _tmgr().booleanOperation(piece, regions[i][j], adsk.fusion.BooleanTypes.IntersectionBooleanType)
            result.append(piece)
    return result
