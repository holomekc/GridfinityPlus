"""
GridfinityPlus — baseplate size layout.

Every side of the plate (left, right, front, back) has an EDGE type:

    Flush         the plate ends with a whole cell
    Border        solid border
    Partial cell  the outer cell is cut

Per axis:
  * both sides Flush  -> size is given as a cell count (columns / rows)
  * otherwise         -> size is given in mm; whole cells are placed first and
                         the leftover is split evenly over the non-flush sides
                         (border width / partial cell size are automatic).
A side is never border AND partial cell.

Local plate frame (upstream convention): cell i spans [i*pitch, (i+1)*pitch],
top surface at z = 0. The plate is the window [x0, x0 + width] over a
whole-cell plate of n cells (with border = generator padding).

Params written by this version carry 'layoutVersion' = 2. Older params (cell
count + manual padding, or the first exact-size version) are still read.

All lengths in Fusion internal units (cm).
"""

import math

import adsk.core, adsk.fusion

from . import const

KEY_VERSION = 'layoutVersion'
KEY_EDGE_LEFT = 'edgeLeft'
KEY_EDGE_RIGHT = 'edgeRight'
KEY_EDGE_FRONT = 'edgeFront'
KEY_EDGE_BACK = 'edgeBack'
KEY_WIDTH = 'plateSizeWidth'
KEY_DEPTH = 'plateSizeDepth'
KEY_SIZE_MODE = 'sizeMode'
KEY_BORDER_LEFT = 'borderLeft'
KEY_BORDER_RIGHT = 'borderRight'
KEY_BORDER_FRONT = 'borderFront'
KEY_BORDER_BACK = 'borderBack'

SIZE_CELLS = 'Cells'
SIZE_EXACT = 'Exact size'
SIZE_MODES = (SIZE_CELLS, SIZE_EXACT)
# legacy (v1) keys
KEY_FIT = 'fitWholeCells'
KEY_CUT_WIDTH = 'cutCellsWidth'
KEY_CUT_DEPTH = 'cutCellsDepth'

EDGE_FLUSH = 'Flush (whole cell)'
EDGE_BORDER = 'Border'
EDGE_PARTIAL = 'Partial cell'
EDGE_CHOICES = (EDGE_FLUSH, EDGE_BORDER, EDGE_PARTIAL)

_EPS = 1e-4

# v1 exact-mode choices -> (start edge, end edge)
_V1_FILL = {
    'Both sides': (EDGE_PARTIAL, EDGE_PARTIAL), 'Partial cells: both sides': (EDGE_PARTIAL, EDGE_PARTIAL),
    'Left': (EDGE_PARTIAL, EDGE_FLUSH), 'Front': (EDGE_PARTIAL, EDGE_FLUSH),
    'Partial cells: left': (EDGE_PARTIAL, EDGE_FLUSH), 'Partial cells: front': (EDGE_PARTIAL, EDGE_FLUSH),
    'Right': (EDGE_FLUSH, EDGE_PARTIAL), 'Back': (EDGE_FLUSH, EDGE_PARTIAL),
    'Partial cells: right': (EDGE_FLUSH, EDGE_PARTIAL), 'Partial cells: back': (EDGE_FLUSH, EDGE_PARTIAL),
    'Border: both sides': (EDGE_BORDER, EDGE_BORDER),
    'Border: left': (EDGE_BORDER, EDGE_FLUSH), 'Border: front': (EDGE_BORDER, EDGE_FLUSH),
    'Border: right': (EDGE_FLUSH, EDGE_BORDER), 'Border: back': (EDGE_FLUSH, EDGE_BORDER),
}


def _isV2(params: dict) -> bool:
    return (params.get(KEY_VERSION) or 0) >= 2


def sizeMode(params: dict):
    """'Cells' | 'Exact size' | None (v2 params from before the size switch)."""
    if (params.get(KEY_VERSION) or 0) >= 3:
        return params.get(KEY_SIZE_MODE, SIZE_CELLS)
    return None


def edges(params: dict):
    """(left, right, front, back) edge types for any params version."""
    if _isV2(params):
        return (params.get(KEY_EDGE_LEFT, EDGE_FLUSH), params.get(KEY_EDGE_RIGHT, EDGE_FLUSH),
                params.get(KEY_EDGE_FRONT, EDGE_FLUSH), params.get(KEY_EDGE_BACK, EDGE_FLUSH))
    if params.get(KEY_FIT, True) is False:
        l, r = _V1_FILL.get(params.get(KEY_CUT_WIDTH, 'Both sides'), (EDGE_PARTIAL, EDGE_PARTIAL))
        f, b = _V1_FILL.get(params.get(KEY_CUT_DEPTH, 'Both sides'), (EDGE_PARTIAL, EDGE_PARTIAL))
        return l, r, f, b
    return (EDGE_FLUSH,) * 4


def axisUsesCount(startEdge: str, endEdge: str) -> bool:
    return startEdge == EDGE_FLUSH and endEdge == EDGE_FLUSH


def _axis(size: float, pitch: float, cl: float, startEdge: str, endEdge: str) -> dict:
    """Layout of one mm-sized axis.

    A normal plate of k cells is k*pitch - 2*cl wide, so the 'equivalent' size
    is size + 2*cl; rest = what k whole cells leave over, split evenly over
    the non-flush sides.
    """
    eq = size + 2 * cl
    whole = int(math.floor(eq / pitch + 1e-9))
    if whole == 0 and EDGE_PARTIAL not in (startEdge, endEdge):
        # Not even one whole cell fits: only partial cells make sense.
        startEdge, endEdge = EDGE_PARTIAL, EDGE_PARTIAL
    rest = eq - whole * pitch
    sides = [e for e in (startEdge, endEdge) if e != EDGE_FLUSH]
    share = rest / len(sides) if sides else 0.0

    padStart = share if startEdge == EDGE_BORDER else 0.0
    padEnd = share if endEdge == EDGE_BORDER else 0.0
    partStart = share if startEdge == EDGE_PARTIAL and share > _EPS else 0.0
    partEnd = share if endEdge == EDGE_PARTIAL and share > _EPS else 0.0

    first = 1 if partStart else 0
    x0 = (pitch - partStart) if partStart else -padStart
    n = whole + first + (1 if partEnd else 0)
    # Both sides flush: the plate is just the whole cells (size rounds down).
    actual = size if sides else whole * pitch - 2 * cl
    return dict(x0=x0, n=max(1, n), whole=whole, first=first, size=actual,
                padStart=padStart, padEnd=padEnd, partStart=partStart, partEnd=partEnd,
                partial=bool(partStart or partEnd))


def _axisCells(count: int, pitch: float, cl: float, startEdge: str, endEdge: str,
               startVal: float, endVal: float) -> dict:
    """Cells mode: whole cells + per side a border or a partial cell of the
    given size (mm values from the dialog, in cm)."""
    def side(edge, val):
        val = max(0.0, float(val or 0))
        if edge == EDGE_BORDER:
            return val, 0.0
        if edge == EDGE_PARTIAL:
            return 0.0, min(val, pitch - 0.01)
        return 0.0, 0.0
    padStart, partStart = side(startEdge, startVal)
    padEnd, partEnd = side(endEdge, endVal)
    partStart = partStart if partStart > _EPS else 0.0
    partEnd = partEnd if partEnd > _EPS else 0.0
    first = 1 if partStart else 0
    x0 = (pitch - partStart) if partStart else -padStart
    size = count * pitch - 2 * cl + padStart + padEnd + partStart + partEnd
    n = count + first + (1 if partEnd else 0)
    return dict(x0=x0, n=n, whole=count, first=first, size=size,
                padStart=padStart, padEnd=padEnd, partStart=partStart, partEnd=partEnd,
                partial=bool(partStart or partEnd))


def layout(params: dict) -> dict:
    """Everything the generators, placement and grid tag need."""
    p, q, cl = params['baseWidth'], params['baseLength'], params['xyClearance']
    l, r, f, b = edges(params)

    legacyCells = not _isV2(params) and params.get(KEY_FIT, True) is not False
    pad = legacyCells and params.get('hasPadding', False)

    def countAxis(cells, pitch, padS, padE):
        return dict(x0=-padS, n=cells, whole=cells, first=0, padStart=padS, padEnd=padE,
                    partStart=0.0, partEnd=0.0,
                    partial=False, size=cells * pitch - 2 * cl + padS + padE)

    mode = sizeMode(params)
    if mode == SIZE_CELLS:
        # Cell count + per side a border or partial cell with user-defined size.
        ax = _axisCells(int(params['plateWidth']), p, cl, l, r,
                        params.get(KEY_BORDER_LEFT), params.get(KEY_BORDER_RIGHT))
        ay = _axisCells(int(params['plateLength']), q, cl, f, b,
                        params.get(KEY_BORDER_FRONT), params.get(KEY_BORDER_BACK))
    else:
        exactX = mode == SIZE_EXACT or not axisUsesCount(l, r)
        exactY = mode == SIZE_EXACT or not axisUsesCount(f, b)
        if not exactX:
            ax = countAxis(int(params['plateWidth']), p,
                           params['paddingLeft'] if pad else 0.0, params['paddingRight'] if pad else 0.0)
        else:
            ax = _axis(params[KEY_WIDTH], p, cl, l, r)
        if not exactY:
            ay = countAxis(int(params['plateLength']), q,
                           params['paddingBottom'] if pad else 0.0, params['paddingTop'] if pad else 0.0)
        else:
            ay = _axis(params[KEY_DEPTH], q, cl, f, b)

    return dict(x0=ax['x0'], x1=ax['x0'] + ax['size'], y0=ay['x0'], y1=ay['x0'] + ay['size'],
                nX=ax['n'], nY=ay['n'], fullX=ax['whole'], fullY=ay['whole'],
                originX=ax['first'] * p, originY=ay['first'] * q,
                padLeft=ax['padStart'], padRight=ax['padEnd'],
                padFront=ay['padStart'], padBack=ay['padEnd'],
                partLeft=ax['partStart'], partRight=ax['partEnd'],
                partFront=ay['partStart'], partBack=ay['partEnd'],
                needsCut=ax['partial'] or ay['partial'],
                exact=(mode == SIZE_EXACT) or (mode is None and not (axisUsesCount(l, r) and axisUsesCount(f, b))))


def isExact(params: dict) -> bool:
    return layout(params)['exact']


def zBottom(params: dict) -> float:
    ext = params['extraBottomThickness'] if params['plateType'] != 'Light' else 0.0
    return -(const.BIN_BASE_HEIGHT + ext)


def localExtents(params: dict):
    """(x0, x1, y0, y1, zBottom) of the plate outline in its local frame."""
    lo = layout(params)
    return lo['x0'], lo['x1'], lo['y0'], lo['y1'], zBottom(params)


def outerSize(params: dict):
    """(width, depth) of the finished plate in cm."""
    x0, x1, y0, y1, _ = localExtents(params)
    return x1 - x0, y1 - y0


def generatorParams(params: dict) -> dict:
    """Params for the whole-cell generators: covering cell count + border as padding."""
    lo = layout(params)
    g = dict(params)
    g['plateWidth'] = lo['nX']
    g['plateLength'] = lo['nY']
    g['paddingLeft'] = lo['padLeft']
    g['paddingRight'] = lo['padRight']
    g['paddingBottom'] = lo['padFront']
    g['paddingTop'] = lo['padBack']
    g['hasPadding'] = any(v > _EPS for v in (lo['padLeft'], lo['padRight'], lo['padFront'], lo['padBack']))
    return g


def cutToSize(tempBody, params: dict):
    """Partial cells: intersect the covering plate with the exact outline."""
    if not layout(params)['needsCut']:
        return tempBody
    from .baseplateFastPreview import _roundedSlab
    x0, x1, y0, y1, zb = localExtents(params)
    r = const.BIN_CORNER_FILLET_RADIUS - params['xyClearance']
    window = _roundedSlab(x0, x1, y0, y1, zb - 0.1, 0.1, r)
    adsk.fusion.TemporaryBRepManager.get().booleanOperation(
        tempBody, window, adsk.fusion.BooleanTypes.IntersectionBooleanType)
    return tempBody


def toV2(params: dict) -> dict:
    """Express any params version in current (v3) terms, for the edit dialog."""
    if (params.get(KEY_VERSION) or 0) >= 3:
        return dict(params)
    out = dict(params)
    l, r, f, b = edges(params)
    lo = layout(params)
    w, d = outerSize(params)
    if lo['exact']:
        mode = SIZE_EXACT
    else:
        mode = SIZE_CELLS
        l = EDGE_BORDER if lo['padLeft'] > _EPS else EDGE_FLUSH
        r = EDGE_BORDER if lo['padRight'] > _EPS else EDGE_FLUSH
        f = EDGE_BORDER if lo['padFront'] > _EPS else EDGE_FLUSH
        b = EDGE_BORDER if lo['padBack'] > _EPS else EDGE_FLUSH
        out.update({KEY_BORDER_LEFT: lo['padLeft'], KEY_BORDER_RIGHT: lo['padRight'],
                    KEY_BORDER_FRONT: lo['padFront'], KEY_BORDER_BACK: lo['padBack']})
    out.update({KEY_VERSION: 3, KEY_SIZE_MODE: mode, KEY_EDGE_LEFT: l, KEY_EDGE_RIGHT: r,
                KEY_EDGE_FRONT: f, KEY_EDGE_BACK: b, KEY_WIDTH: w, KEY_DEPTH: d})
    return out


def describe(params: dict) -> str:
    """Short human-readable size, e.g. '5 x 3 cells' or '200 x 150 mm'."""
    if not isExact(params):
        lo = layout(params)
        if lo['padLeft'] + lo['padRight'] + lo['padFront'] + lo['padBack'] < _EPS:
            return '{} x {} cells'.format(lo['fullX'], lo['fullY'])
        if not lo['needsCut']:
            return '{} x {} cells + border'.format(lo['fullX'], lo['fullY'])
    w, d = outerSize(params)
    return '{:g} x {:g} mm'.format(round(w * 10, 1), round(d * 10, 1))
