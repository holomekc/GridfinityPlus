"""
GridfinityPlus — Bin as an editable, grid-snapped Custom Feature.

Same proven mechanics as baseplateFeature (one CustomFeature node wrapping one
BaseFeature body; swaps only inside compute via the pending + rev-bump pattern).

Geometry is built by commandCreateBin (the full upstream dialog — magnets,
scoop, tab, compartments, ...) into a temp BRep and handed to this module.
This module owns: placement (plate cell col/row + 90° rotation steps),
the custom feature lifecycle, and the params attribute.

Placement params (top level):
  plateToken (component entityToken or None for free placement),
  col, row, rotation (0/90/180/270),
  binW, binL (units), baseW, baseL (dialog base unit, cm), cl (xy clearance)
Full dialog state for edit-seeding lives in params['geom'] / params['compartmentsTable'].
"""

import adsk.core, adsk.fusion
import json
import math

from . import gridRegistry
from . import gplog

FEATURE_ID = 'GridfinityPlus_bin'
FEATURE_NAME = 'Gridfinity Bin'
ATTR_GROUP = 'GridfinityPlus'
ATTR_PARAMS = 'binParams'

_definition = None
_computeHandler = None

# Pending body swaps: customFeature.entityToken -> {'body': ..., 'name': ...}.
_pending = {}

# Geometry cache: key -> temp BRepBody at local origin (position-independent).
_brepCache = {}
_BREP_CACHE_MAX = 6


class _BinComputeHandler(adsk.fusion.CustomFeatureEventHandler):
    def notify(self, args):
        try:
            eventArgs = adsk.fusion.CustomFeatureEventArgs.cast(args)
            cf = eventArgs.customFeature
            pending = _pending.pop(cf.entityToken, None)
            if pending is None:
                gplog.log(f'BIN COMPUTE: "{cf.name}" no pending swap -> no-op')
                return
            gplog.log(f'BIN COMPUTE: "{cf.name}" applying pending swap')
            baseFeat = _findBaseFeature(cf)
            if baseFeat is None:
                gplog.log('BIN COMPUTE: no BaseFeature found!')
                return
            with gplog.timed('BIN COMPUTE body swap'):
                baseFeat.startEdit()
                oldBody = baseFeat.bodies.item(0)
                baseFeat.updateBody(oldBody, pending['body'])
                baseFeat.finishEdit()
            try:
                baseFeat.bodies.item(0).name = pending['name']
            except Exception:
                pass
        except Exception:
            gplog.logExc('BIN COMPUTE handler')


def register(editCommandId: str, iconFolder: str):
    global _definition, _computeHandler
    if _definition is not None:
        return _definition
    _definition = adsk.fusion.CustomFeatureDefinition.create(FEATURE_ID, FEATURE_NAME, iconFolder)
    _definition.editCommandId = editCommandId
    gplog.log(f'register: {FEATURE_ID} edit={_definition.editCommandId}')
    _computeHandler = _BinComputeHandler()
    _definition.customFeatureCompute.add(_computeHandler)
    return _definition


def _findBaseFeature(customFeature: adsk.fusion.CustomFeature):
    for feat in customFeature.features:
        if feat.objectType == adsk.fusion.BaseFeature.classType():
            return adsk.fusion.BaseFeature.cast(feat)
    return None


def getCachedBody(key: str):
    cached = _brepCache.get(key)
    if cached is not None:
        try:
            if cached.faces.count > 0:
                return cached
        except Exception:
            pass
        del _brepCache[key]
    return None


def setCachedBody(key: str, body):
    if len(_brepCache) >= _BREP_CACHE_MAX:
        _brepCache.clear()
    _brepCache[key] = body


def resolvePlate(des: adsk.fusion.Design, plateToken=None):
    """Return (occurrence, GridInfo, component) of the target baseplate.

    plateToken is the baseplate custom feature's entityToken (or, for older
    documents, the tagged component's).
    """
    if plateToken:
        try:
            for e in des.findEntityByToken(plateToken):
                grid = gridRegistry.readGrid(e)
                if grid:
                    comp = gridRegistry.ownerComponent(e)
                    occs = des.rootComponent.allOccurrencesByComponent(comp)
                    occ = occs.item(0) if occs.count > 0 else None
                    return occ, grid, comp
        except Exception:
            gplog.logExc('resolvePlate by token')
    plates = gridRegistry.findBaseplates(des)
    if not plates:
        return None, None, None
    occ, grid = plates[0]
    return occ, grid, gridRegistry.ownerComponent(grid.entity)


def listPlates(des: adsk.fusion.Design):
    """[(label, componentToken, grid)] for all tagged baseplates."""
    result = []
    seen = set()
    for occ, grid in gridRegistry.findBaseplates(des):
        e = grid.entity
        try:
            token = e.entityToken
        except Exception:
            continue
        if token in seen:
            continue
        seen.add(token)
        label = e.name
        n = 2
        while any(r[0] == label for r in result):
            label = f'{e.name} #{n}'
            n += 1
        result.append((label, token, grid))
    return result


def plateAtClick(des: adsk.fusion.Design, args, choices: dict):
    """The baseplate / cabinet top under the cursor: (label, occ, grid,
    (x, y) local hit) for the front-most grid whose top plane the view ray
    hits inside its outline, or None. choices: {label: (token, grid)}.
    Clicking a cabinet's top therefore stacks onto that cabinet."""
    from . import viewRay
    best = None
    for label, (token, _) in choices.items():
        if not token:
            continue
        try:
            occ, grid, _ = resolvePlate(des, token)
            if grid is None:
                continue
            hit = viewRay.hitLocalPlaneT(args, gridRegistry.gridTransform(grid, occ), 2, 0.0)
            if hit is None:
                continue
            (x, y, _), t = hit
            pad, part = grid.padding or {}, grid.partial or {}
            side = lambda k: float(pad.get(k, 0) or 0) + float(part.get(k, 0) or 0)
            m = 0.05
            x0 = grid.originX - side('left') - m
            x1 = grid.originX + grid.cols * grid.pitchX + side('right') + m
            y0 = grid.originY - side('bottom') - m
            y1 = grid.originY + grid.rows * grid.pitchY + side('top') + m
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            if best is None or t < best[0]:
                best = (t, label, occ, grid, (x, y))
        except Exception:
            gplog.logExc(f'plateAtClick "{label}"')
    return best[1:] if best else None


def selectPlate(dropdown, label) -> bool:
    """Select `label` in a plate dropdown. True if the selection changed."""
    if dropdown is None or (dropdown.selectedItem and dropdown.selectedItem.name == label):
        return False
    for item in dropdown.listItems:
        if item.name == label:
            item.isSelected = True
            return True
    return False


def matchPlateToken(des: adsk.fusion.Design, storedToken, plates):
    """Map a bin's stored plateToken onto one of listPlates() tokens.

    Older bins stored the plate's component token; plates are now tagged per
    feature. Fall back to the first plate living in that component.
    """
    if not storedToken:
        return None
    tokens = [t for _, t, _ in plates]
    if storedToken in tokens:
        return storedToken
    try:
        for e in des.findEntityByToken(storedToken):
            comp = adsk.fusion.Component.cast(e)
            if comp:
                for _, t, grid in plates:
                    if gridRegistry.ownerComponent(grid.entity) == comp:
                        return t
    except Exception:
        gplog.logExc('matchPlateToken')
    return None


def footprintUnits(params: dict):
    """Bin footprint in grid units, rotation-aware (90/270 swaps W/L)."""
    if int(params.get('rotation', 0)) % 180 == 90:
        return int(params['binL']), int(params['binW'])
    return int(params['binW']), int(params['binL'])


def clampCell(grid, params: dict):
    fw, fl = footprintUnits(params)
    col = max(0, min(int(params['col']), max(0, grid.cols - fw)))
    row = max(0, min(int(params['row']), max(0, grid.rows - fl)))
    return col, row


def placementMatrix(des: adsk.fusion.Design, params: dict, world: bool = True):
    """World matrix: rotation (about z, footprint re-anchored to its min corner)
    -> cell translation -> plate occurrence transform. Identity when free."""
    rotation = int(params.get('rotation', 0)) % 360
    aW = params['binW'] * params['baseW'] - 2 * params['cl']
    aL = params['binL'] * params['baseL'] - 2 * params['cl']

    m = adsk.core.Matrix3D.create()
    if rotation:
        m.setToRotation(math.radians(rotation),
                        adsk.core.Vector3D.create(0, 0, 1),
                        adsk.core.Point3D.create(0, 0, 0))
        # Shift so the rotated footprint's min corner is back at (0, 0).
        shift = {90: (aL, 0), 180: (aW, aL), 270: (0, aW)}[rotation]
        t = adsk.core.Matrix3D.create()
        t.translation = adsk.core.Vector3D.create(shift[0], shift[1], 0)
        m.transformBy(t)  # m = t * m

    occ, grid, comp = (None, None, None)
    if params.get('plateToken'):
        occ, grid, comp = resolvePlate(des, params['plateToken'])
    if grid is not None:
        col, row = clampCell(grid, params)
        t = adsk.core.Matrix3D.create()
        cell = grid.cellLocalOrigin(col, row)
        t.translation = adsk.core.Vector3D.create(cell.x, cell.y, 0)
        m.transformBy(t)
        # Plate placement (plane/anchor), then — for world space (preview,
        # clicks) — the plate's occurrence. Bodies go INTO the plate component
        # and therefore stay in component space (world=False).
        m.transformBy(gridRegistry.gridTransform(grid, occ if world else None))
    return m, comp


# Plate sides by outward direction (deg) and their GridInfo dict keys.
_PLATE_SIDE_BY_ANGLE = {0: 'right', 90: 'top', 180: 'left', 270: 'bottom'}
_BIN_SIDE_ANGLE = {'right': 0, 'back': 90, 'left': 180, 'front': 270}
EXTEND_AUTO = 'Auto'
EXTEND_ON = 'Yes'
EXTEND_OFF = 'No'
EXTEND_CHOICES = (EXTEND_AUTO, EXTEND_ON, EXTEND_OFF)


def extendModes(flags: dict) -> dict:
    """Normalise stored overhang flags (legacy bools) to Auto/Yes/No."""
    out = {}
    for side in ('left', 'right', 'front', 'back'):
        v = (flags or {}).get(side, EXTEND_AUTO)
        if v is True:
            v = EXTEND_ON
        elif v is False:
            v = EXTEND_OFF
        out[side] = v if v in EXTEND_CHOICES else EXTEND_AUTO
    return out


def _plateEdgeExtras(grid):
    """(border, partial) per plate side, keys left/right/top/bottom (cm).

    Computed from the baseplate's own stored params when available, so plates
    tagged by an older add-in version work without being re-saved.
    """
    try:
        attr = grid.entity.attributes.itemByName('GridfinityPlus', 'baseplateParams')
        if attr:
            from . import plateLayout
            lo = plateLayout.layout(json.loads(attr.value))
            pad = {'left': lo['padLeft'], 'right': lo['padRight'],
                   'bottom': lo['padFront'], 'top': lo['padBack']}
            part = {'left': lo['partLeft'], 'right': lo['partRight'],
                    'bottom': lo['partFront'], 'top': lo['partBack']}
            return pad, part
    except Exception:
        gplog.logExc('plateEdgeExtras')
    return (grid.padding or {}), (getattr(grid, 'partial', None) or {})


def overhangAmounts(grid, params: dict, modes: dict) -> dict:
    """Body extension per BIN side (cm) over the plate's border / partial cells.

    Auto: extend where the bin touches that plate edge. Yes: always extend by
    that edge's border/partial width. No: never. Rotation-aware.
    """
    out = {'left': 0.0, 'right': 0.0, 'front': 0.0, 'back': 0.0,
           # True where the extension covers a PARTIAL cell: the bin then also
           # gets a (cut) foot there, not just a wider body.
           'partial': {'left': False, 'right': False, 'front': False, 'back': False}}
    if grid is None:
        return out
    pad, part = _plateEdgeExtras(grid)
    col, row = clampCell(grid, params)
    fw, fl = footprintUnits(params)
    touches = {'left': col == 0, 'right': col + fw >= grid.cols,
               'bottom': row == 0, 'top': row + fl >= grid.rows}
    rot = int(params.get('rotation', 0)) % 360
    for side, angle in _BIN_SIDE_ANGLE.items():
        plateSide = _PLATE_SIDE_BY_ANGLE[(angle + rot) % 360]
        extra = float(pad.get(plateSide, 0) or 0) + float(part.get(plateSide, 0) or 0)
        mode = modes.get(side, EXTEND_AUTO)
        if mode == EXTEND_ON or (mode == EXTEND_AUTO and touches[plateSide]):
            out[side] = extra
            out['partial'][side] = float(part.get(plateSide, 0) or 0) > 1e-4
    gplog.log(f'overhang: cell=({col},{row}) fp={fw}x{fl} rot={rot} touches={touches} '
              f'pad={pad} part={part} modes={modes} -> {out}')
    return out


def placedCopy(body, matrix):
    tmgr = adsk.fusion.TemporaryBRepManager.get()
    placed = tmgr.copy(body)
    tmgr.transform(placed, matrix)
    return placed


def featureName(params: dict) -> str:
    # e.g. "Bin 2x1x3 - col 2, row 1 - 2 tool cutouts"
    h = float(params.get('binH', 0))
    if abs(h - round(h)) < 1e-6:
        hText = str(int(round(h)))
    else:
        hText = '{:g}mm'.format(round(h * float(params.get('heightUnit', 0.7)) * 10, 1))
    name = 'Bin {}x{}x{}'.format(int(params['binW']), int(params['binL']), hText)
    if params.get('plateToken'):
        name += ' - col {}, row {}'.format(int(params['col']) + 1, int(params['row']) + 1)
    cutouts = params.get('cutouts', [])
    if cutouts:
        name += ' - {} tool cutout{}'.format(len(cutouts), 's' if len(cutouts) > 1 else '')
    return name


def createFeature(des: adsk.fusion.Design, placedBody, params: dict):
    """Create a new editable bin custom feature from an already-placed body."""
    name = featureName(params)
    gplog.session(f'bin createFeature "{name}"')

    _, plateComp = placementMatrix(des, params)
    component = plateComp if plateComp is not None else des.rootComponent

    baseFeat = component.features.baseFeatures.add()
    baseFeat.startEdit()
    addedBody = component.bRepBodies.add(placedBody, baseFeat)
    addedBody.name = name
    baseFeat.finishEdit()

    cfInput = component.features.customFeatures.createInput(_definition)
    cfInput.addCustomParameter('rev', 'Revision', adsk.core.ValueInput.createByReal(1), '', False)
    cfInput.setStartAndEndFeatures(baseFeat, baseFeat)
    customFeature = component.features.customFeatures.add(cfInput)
    customFeature.name = name

    customFeature.attributes.add(ATTR_GROUP, ATTR_PARAMS, json.dumps(params))
    gplog.dumpTimeline(des, 'bin create:after')
    return customFeature


def rebuildFeature(des: adsk.fusion.Design, customFeature: adsk.fusion.CustomFeature,
                   placedBody, params: dict):
    """Swap in a new placed body via the pending + rev-bump compute pattern."""
    name = featureName(params)
    gplog.session(f'bin rebuildFeature "{name}"')

    _pending[customFeature.entityToken] = {'body': placedBody, 'name': name}
    customFeature.attributes.add(ATTR_GROUP, ATTR_PARAMS, json.dumps(params))
    customFeature.name = name

    # Trigger compute via the rev parameter. On legacy features (created by an
    # older add-in version) the setter can throw "Bad index parameter" — fall
    # back to Fusion's automatic post-edit recompute, which also fires our
    # compute handler and consumes the pending swap.
    try:
        revParam = customFeature.parameters.itemById('rev')
        if revParam is not None:
            with gplog.timed('bin rebuild: rev bump -> compute'):
                revParam.value = revParam.value + 1
        else:
            gplog.log('bin rebuild: no rev param (legacy feature), relying on auto recompute')
    except Exception:
        gplog.logExc('bin rebuild: rev bump failed (legacy feature?), relying on auto recompute')
    gplog.dumpTimeline(des, 'bin rebuild:after')


def readParams(customFeature: adsk.fusion.CustomFeature):
    attr = customFeature.attributes.itemByName(ATTR_GROUP, ATTR_PARAMS)
    if not attr:
        return None
    try:
        return json.loads(attr.value)
    except ValueError:
        return None
