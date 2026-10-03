"""
GridfinityPlus — grid cover: a flat plate on Gridfinity feet.

Closes empty baseplate cells, e.g. in front of a cabinet. Placed like a bin
(same local frame and placement code), only the body is a thin flat slab
just above the baseplate. Can fill to the plate edge over padding / partial
cells like a cabinet.

All lengths in cm. Local frame: footprint x 0..aW, y 0..aL (aW = unitsW *
baseW - 2 cl), feet from -BIN_BASE_HEIGHT to 0, slab from 0 to thickness.
"""

import adsk.fusion

from . import const
from . import gplog
from .baseplateFastPreview import _roundedSlab
from .cabinetGeometry import gridFeet

COVER_DEFAULTS = {
    'unitsW': 2,
    'unitsL': 1,
    # Below the bottom drawer of a cabinet: its floor (1.2 mm default) minus
    # a gap, so drawers slide out over the cover.
    'thickness': 0.1,
    'baseW': const.DIMENSION_DEFAULT_WIDTH_UNIT,
    'baseL': const.DIMENSION_DEFAULT_WIDTH_UNIT,
    'cl': const.BIN_XY_CLEARANCE,
    'magnets': False,
    'screws': False,
    # Body extension over plate border / partial cells, resolved from the plate.
    'ovh': {},
}


def withDefaults(params: dict) -> dict:
    out = dict(COVER_DEFAULTS)
    out.update({k: v for k, v in (params or {}).items() if v is not None})
    return out


def outline(p: dict):
    """(x0, x1, y0, y1) incl. the fill-to-edge extension."""
    cl = float(p['cl'])
    aW = int(p['unitsW']) * float(p['baseW']) - 2 * cl
    aL = int(p['unitsL']) * float(p['baseL']) - 2 * cl
    ovh = p.get('ovh') or {}
    return (-float(ovh.get('left', 0) or 0), aW + float(ovh.get('right', 0) or 0),
            -float(ovh.get('front', 0) or 0), aL + float(ovh.get('back', 0) or 0))


def errors(params: dict):
    p = withDefaults(params)
    out = []
    if float(p['thickness']) < 0.06:
        out.append('Cover thinner than 0.6 mm')
    return out


def describe(params: dict) -> str:
    p = withDefaults(params)
    return 'Cover {}x{}'.format(int(p['unitsW']), int(p['unitsL']))


def buildCover(des: adsk.fusion.Design, params: dict) -> adsk.fusion.BRepBody:
    """Cover temp body in its local frame."""
    with gplog.timed('cover build'):
        p = withDefaults(params)
        x0, x1, y0, y1 = outline(p)
        radius = const.BIN_CORNER_FILLET_RADIUS - float(p['cl'])
        body = _roundedSlab(x0, x1, y0, y1, 0.0, float(p['thickness']), radius)
        partial = {k: bool(v) for k, v in ((p.get('ovh') or {}).get('partial') or {}).items()}
        feet = gridFeet(des, p, partial, (x0, x1, y0, y1), radius)
        adsk.fusion.TemporaryBRepManager.get().booleanOperation(
            body, feet, adsk.fusion.BooleanTypes.UnionBooleanType)
        gplog.log(f'cover build: faces={body.faces.count}')
        return body
