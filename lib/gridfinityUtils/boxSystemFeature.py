"""
GridfinityPlus — box system custom features (cabinet + insert).

Same proven mechanics as binFeature / baseplateFeature: one CustomFeature node
wrapping one BaseFeature body; the body is swapped ONLY inside compute, via the
pending + rev-bump pattern.

Links:
  * A cabinet is placed like a bin (plateToken, col, row, rotation). With a
    Gridfinity grid on top it tags itself as a baseplate, so bins and further
    cabinets snap onto it with the existing placement code (stacking).
  * An insert stores its cabinet's entityToken and lives in the cabinet's
    component. Its size and position are always derived from the cabinet.
  * Editing a cabinet rebuilds its inserts and every cabinet stacked on it.

All lengths in cm.
"""

import adsk.core, adsk.fusion
import json
import types

from . import gplog
from . import gridRegistry
from . import binFeature
from . import cabinetLayout
from . import cabinetGeometry
from . import coverGeometry

ATTR_GROUP = 'GridfinityPlus'

# Pending body swaps for all box-system kinds: entityToken -> {'body', 'name'}.
_pending = {}


class _ComputeHandler(adsk.fusion.CustomFeatureEventHandler):
    def notify(self, args):
        try:
            cf = adsk.fusion.CustomFeatureEventArgs.cast(args).customFeature
            pending = _pending.pop(cf.entityToken, None)
            if pending is None:
                return
            baseFeat = _findBaseFeature(cf)
            if baseFeat is None:
                gplog.log(f'BOX COMPUTE: "{cf.name}" has no BaseFeature')
                return
            # Several bodies (e.g. drawer + spool axle); the count may change.
            new = pending['bodies']
            baseFeat.startEdit()
            old = [baseFeat.bodies.item(i) for i in range(baseFeat.bodies.count)]
            for i, body in enumerate(new):
                if i < len(old):
                    baseFeat.updateBody(old[i], body)
                else:
                    cf.parentComponent.bRepBodies.add(body, baseFeat)
            for body in old[len(new):]:
                body.deleteMe()
            baseFeat.finishEdit()
            _nameBodies(baseFeat, pending['names'])
        except Exception:
            gplog.logExc('BOX COMPUTE handler')


def _asList(bodies):
    return list(bodies) if isinstance(bodies, (list, tuple)) else [bodies]


def _names(name: str, count: int, partNames=None):
    """Body names: the feature name for the main body, then the part names."""
    extra = list(partNames or [])
    return [name] + [f'{name} - {extra[i - 1] if i - 1 < len(extra) else "part " + str(i)}'
                     for i in range(1, count)]


def _nameBodies(baseFeat, names):
    for i in range(min(baseFeat.bodies.count, len(names))):
        try:
            baseFeat.bodies.item(i).name = names[i]
        except Exception:
            pass


def _findBaseFeature(cf: adsk.fusion.CustomFeature):
    for feat in cf.features:
        if feat.objectType == adsk.fusion.BaseFeature.classType():
            return adsk.fusion.BaseFeature.cast(feat)
    return None


class FeatureKind:
    """One custom feature definition (id, timeline name, params attribute)."""

    def __init__(self, featureId: str, featureName: str, attrName: str):
        self.featureId = featureId
        self.featureName = featureName
        self.attrName = attrName
        self._definition = None
        self._handler = None

    def register(self, editCommandId: str, iconFolder: str):
        if self._definition is None:
            self._definition = adsk.fusion.CustomFeatureDefinition.create(
                self.featureId, self.featureName, iconFolder)
            self._definition.editCommandId = editCommandId
            gplog.log(f'register: {self.featureId} edit={self._definition.editCommandId}')
            self._handler = _ComputeHandler()
            self._definition.customFeatureCompute.add(self._handler)
        return self._definition

    def isKind(self, entity) -> bool:
        cf = adsk.fusion.CustomFeature.cast(entity)
        try:
            return bool(cf) and cf.definition.id == self.featureId
        except Exception:
            return False

    def readParams(self, cf):
        attr = cf.attributes.itemByName(ATTR_GROUP, self.attrName) if cf else None
        if not attr:
            return None
        try:
            return json.loads(attr.value)
        except ValueError:
            return None

    def all(self, des: adsk.fusion.Design):
        result = []
        for attr in des.findAttributes(ATTR_GROUP, self.attrName):
            cf = adsk.fusion.CustomFeature.cast(attr.parent)
            try:
                if cf and not cf.isSuppressed:
                    result.append(cf)
            except Exception:
                pass
        return result

    def fromSelection(self, entity):
        """This kind's custom feature for a selected timeline node / feature
        or one of its bodies, else None."""
        if self.isKind(entity):
            return adsk.fusion.CustomFeature.cast(entity)
        body = adsk.fusion.BRepBody.cast(entity)
        if not body:
            return None
        try:
            native = body.nativeObject if body.nativeObject else body
            feats = native.parentComponent.features.customFeatures
            for i in range(feats.count):
                cf = feats.item(i)
                if not self.isKind(cf):
                    continue
                for b in self.bodies(cf):
                    if b == native:
                        return cf
        except Exception:
            gplog.logExc('fromSelection')
        return None

    def bodies(self, cf):
        base = _findBaseFeature(cf)
        return list(base.bodies) if base else []

    def create(self, component: adsk.fusion.Component, bodies, params: dict, name: str, partNames=None):
        """bodies: one temp body or a list (main body first)."""
        gplog.session(f'{self.featureName} create "{name}"')
        bodies = _asList(bodies)
        names = _names(name, len(bodies), partNames)
        baseFeat = component.features.baseFeatures.add()
        baseFeat.startEdit()
        for body, bodyName in zip(bodies, names):
            component.bRepBodies.add(body, baseFeat).name = bodyName
        baseFeat.finishEdit()
        cfInput = component.features.customFeatures.createInput(self._definition)
        cfInput.addCustomParameter('rev', 'Revision', adsk.core.ValueInput.createByReal(1), '', False)
        cfInput.setStartAndEndFeatures(baseFeat, baseFeat)
        cf = component.features.customFeatures.add(cfInput)
        cf.name = name
        cf.attributes.add(ATTR_GROUP, self.attrName, json.dumps(params))
        return cf

    def rebuild(self, cf, bodies, params: dict, name: str, partNames=None):
        """Swap in new bodies via compute. Returns the feature (a new one if
        the body count changed and Fusion did not take it in compute)."""
        gplog.session(f'{self.featureName} rebuild "{name}"')
        bodies = _asList(bodies)
        tmgr = adsk.fusion.TemporaryBRepManager.get()
        # Compute may consume the bodies; keep the originals for a recreate.
        _pending[cf.entityToken] = {'bodies': [tmgr.copy(b) for b in bodies],
                                    'names': _names(name, len(bodies), partNames)}
        cf.attributes.add(ATTR_GROUP, self.attrName, json.dumps(params))
        cf.name = name
        revParam = cf.parameters.itemById('rev')
        if revParam is None:
            raise RuntimeError(f'"{cf.name}" has no revision parameter, please recreate it.')
        revParam.value = revParam.value + 1
        base = _findBaseFeature(cf)
        count = base.bodies.count if base else -1
        if count == len(bodies):
            return cf
        gplog.log(f'{self.featureName} rebuild: bodies={count}, expected {len(bodies)} -> recreate')
        return self._recreate(cf, bodies, params, name, partNames)

    def _recreate(self, cf, bodies, params, name, partNames):
        """New feature at the same timeline position, old one deleted."""
        des = adsk.fusion.Design.cast(cf.parentComponent.parentDesign)
        timeline = des.timeline
        timeline.markerPosition = cf.timelineObject.index + 1
        try:
            newCf = self.create(cf.parentComponent, bodies, params, name, partNames)
        finally:
            timeline.moveToEnd()
        base = _findBaseFeature(cf)
        cf.deleteMe()
        try:
            if base is not None and base.isValid:
                base.deleteMe()
        except Exception:
            pass
        return newCf


CABINET = FeatureKind('GridfinityPlus_cabinet', 'Gridfinity Cabinet', 'cabinetParams')
INSERT = FeatureKind('GridfinityPlus_cabinetInsert', 'Gridfinity Drawer', 'insertParams')
COVER = FeatureKind('GridfinityPlus_cover', 'Gridfinity Cover', 'coverParams')


# ------------------------------------------------------------------ cabinet

def binPlacementParams(params: dict) -> dict:
    """Cabinet params in the shape binFeature.placementMatrix expects."""
    return {
        'binW': int(params['unitsW']), 'binL': int(params['unitsL']),
        'baseW': float(params['baseW']), 'baseL': float(params['baseL']),
        'cl': float(params['cl']),
        'rotation': int(params.get('rotation', 0)),
        'plateToken': params.get('plateToken'),
        'col': int(params.get('col', 0)), 'row': int(params.get('row', 0)),
    }


def withOverhang(des: adsk.fusion.Design, params: dict) -> dict:
    """Params with 'ovh' resolved from the plate (border padding / partial
    cells, 'Fill to edge' modes in 'overhangFlags'), like a bin."""
    p = dict(params)
    grid = None
    if p.get('plateToken'):
        _, grid, _ = binFeature.resolvePlate(des, p['plateToken'])
    p['ovh'] = binFeature.overhangAmounts(grid, binPlacementParams(p),
                                          binFeature.extendModes(p.get('overhangFlags', {})))
    return p


def cabinetMatrix(des: adsk.fusion.Design, params: dict, world: bool = True):
    """(cabinet local -> world/component matrix, target component or None)."""
    return binFeature.placementMatrix(des, binPlacementParams(params), world=world)


def _placed(body, matrix):
    tmgr = adsk.fusion.TemporaryBRepManager.get()
    placed = tmgr.copy(body)
    tmgr.transform(placed, matrix)
    return placed


def _tagTop(des: adsk.fusion.Design, cf, params: dict):
    """Cabinet with a grid on top = baseplate for bins / stacked cabinets."""
    cab = cabinetLayout.cabinet(params)
    if not cab['topIsGrid']:
        for name in (gridRegistry.ATTR_IS_BASEPLATE, gridRegistry.ATTR_GRID):
            attr = cf.attributes.itemByName(ATTR_GROUP, name)
            if attr:
                attr.deleteMe()
        return
    matrix, _ = cabinetMatrix(des, params, world=False)
    top = adsk.core.Matrix3D.create()
    top.translation = adsk.core.Vector3D.create(0, 0, cab['zTop'])
    top.transformBy(matrix)
    # Overhang on top = plate border: partial cell (pockets) or padding (flat),
    # so bins on the cabinet can 'Fill to edge' like on a baseplate.
    ovh = cab['p'].get('ovh') or {}
    asPartial = cab['p'].get('topEdge') == cabinetLayout.TOP_EDGE_PLATE
    pad, part = {}, {}
    for side, gridSide in (('left', 'left'), ('right', 'right'), ('front', 'bottom'), ('back', 'top')):
        amount = float(ovh.get(side, 0) or 0)
        isPartial = asPartial and cab['partial'].get(side, False)
        part[gridSide] = amount if isPartial else 0.0
        pad[gridSide] = 0.0 if isPartial else amount
    gridInput = types.SimpleNamespace(
        baseWidth=float(params['baseW']), baseLength=float(params['baseL']),
        baseplateWidth=int(params['unitsW']), baseplateLength=int(params['unitsL']),
        xyClearance=float(params['cl']), hasPadding=any(v > 0 for v in pad.values()),
        paddingLeft=pad['left'], paddingRight=pad['right'], paddingTop=pad['top'], paddingBottom=pad['bottom'])
    gridRegistry.tagBaseplate(cf, gridInput, top,
                              cols=int(params['unitsW']), rows=int(params['unitsL']), partial=part)


def createCabinet(des: adsk.fusion.Design, params: dict):
    params = withOverhang(des, params)
    matrix, comp = cabinetMatrix(des, params, world=False)
    body = _placed(cabinetGeometry.buildCabinet(des, params), matrix)
    component = comp if comp is not None else des.rootComponent
    cf = CABINET.create(component, body, params, cabinetLayout.describeCabinet(params))
    _tagTop(des, cf, params)
    return cf


def rebuildCabinet(des: adsk.fusion.Design, cf, params: dict, _visited=None):
    """Rebuild a cabinet, then everything that depends on it."""
    visited = _visited if _visited is not None else set()
    token = cf.entityToken
    if token in visited:
        return
    visited.add(token)
    params = withOverhang(des, params)
    matrix, _ = cabinetMatrix(des, params, world=False)
    body = _placed(cabinetGeometry.buildCabinet(des, params), matrix)
    CABINET.rebuild(cf, body, params, cabinetLayout.describeCabinet(params))
    _tagTop(des, cf, params)

    for ins in INSERT.all(des):
        ip = INSERT.readParams(ins)
        if ip and refersTo(des, ip.get('cabinetToken'), cf):
            try:
                rebuildInsert(des, ins, ip)
            except Exception:
                gplog.logExc('rebuild dependent insert')
    for other in CABINET.all(des):
        op = CABINET.readParams(other)
        if op and refersTo(des, op.get('plateToken'), cf):
            try:
                rebuildCabinet(des, other, op, visited)
            except Exception:
                gplog.logExc('rebuild stacked cabinet')
    for cover in COVER.all(des):
        cp = COVER.readParams(cover)
        if cp and refersTo(des, cp.get('plateToken'), cf):
            try:
                rebuildCover(des, cover, cp)
            except Exception:
                gplog.logExc('rebuild cover on cabinet')


def refersTo(des: adsk.fusion.Design, token, entity) -> bool:
    """True if `token` resolves to `entity`. Tokens of the same entity may
    differ as strings (Fusion only guarantees findEntityByToken), so compare
    the resolved entities."""
    if not token or entity is None:
        return False
    try:
        if token == entity.entityToken:
            return True
        return any(e == entity for e in des.findEntityByToken(token))
    except Exception:
        return False


def resolveCabinet(des: adsk.fusion.Design, token):
    if not token:
        return None
    try:
        for e in des.findEntityByToken(token):
            if CABINET.isKind(e):
                return adsk.fusion.CustomFeature.cast(e)
    except Exception:
        gplog.logExc('resolveCabinet')
    return None


def listCabinets(des: adsk.fusion.Design):
    """[(label, token, customFeature)] with unique labels."""
    result = []
    for cf in CABINET.all(des):
        label = cf.name
        n = 2
        while any(r[0] == label for r in result):
            label = f'{cf.name} #{n}'
            n += 1
        result.append((label, cf.entityToken, cf))
    return result


# ------------------------------------------------------------------- insert

def insertMatrix(des: adsk.fusion.Design, cabParams: dict, world: bool = True):
    matrix, _ = cabinetMatrix(des, cabParams, world=world)
    return matrix


def insertName(cabParams: dict, insertParams: dict) -> str:
    return cabinetLayout.describeInsert(cabinetLayout.cabinet(cabParams), insertParams)


def _insertBodies(des, cabParams, insertParams):
    matrix = insertMatrix(des, cabParams, world=False)
    parts = [_placed(b, matrix) for b in cabinetGeometry.buildInsertParts(des, cabParams, insertParams)]
    return parts, ['axle'] * (len(parts) - 1)


def createInsert(des: adsk.fusion.Design, cabCf, insertParams: dict):
    cabParams = CABINET.readParams(cabCf)
    parts, partNames = _insertBodies(des, cabParams, insertParams)
    params = dict(insertParams, cabinetToken=cabCf.entityToken)
    return INSERT.create(cabCf.parentComponent, parts, params, insertName(cabParams, params), partNames)


def rebuildInsert(des: adsk.fusion.Design, cf, insertParams: dict):
    cabCf = resolveCabinet(des, insertParams.get('cabinetToken'))
    if cabCf is None:
        raise RuntimeError('The cabinet of this insert no longer exists.')
    cabParams = CABINET.readParams(cabCf)
    parts, partNames = _insertBodies(des, cabParams, insertParams)
    return INSERT.rebuild(cf, parts, insertParams, insertName(cabParams, insertParams), partNames)


# -------------------------------------------------------------------- cover

def _placedCover(des, params):
    params = withOverhang(des, coverGeometry.withDefaults(params))
    matrix, comp = cabinetMatrix(des, params, world=False)
    return params, _placed(coverGeometry.buildCover(des, params), matrix), comp


def createCover(des: adsk.fusion.Design, params: dict):
    params, body, comp = _placedCover(des, params)
    component = comp if comp is not None else des.rootComponent
    return COVER.create(component, body, params, coverGeometry.describe(params))


def rebuildCover(des: adsk.fusion.Design, cf, params: dict):
    params, body, _ = _placedCover(des, params)
    COVER.rebuild(cf, body, params, coverGeometry.describe(params))
