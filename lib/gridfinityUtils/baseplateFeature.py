"""
GridfinityPlus — Baseplate as an editable Custom Feature.

One timeline node, editable via double-click, geometry swaps in place.

Architecture (official Autodesk custom-feature pattern):
  * The plate geometry lives as a single body inside a BaseFeature wrapped by a
    CustomFeature (one timeline node, custom icon).
  * The body may ONLY be swapped inside the customFeatureCompute event — editing
    a wrapped BaseFeature from outside the compute context silently destroys its
    bodies (verified via gridfinityplus.log).
  * Editing therefore: build new BRep -> stash as "pending" -> bump the hidden
    'rev' custom parameter -> Fusion fires compute -> compute swaps the body via
    BaseFeature.updateBody.
  * Compute events with no pending body (document reopen, timeline replay) are
    no-ops: the BaseFeature body persists in the document, nothing to do.

Geometry generation runs the upstream parametric generator in an isolated
scratch component, copies the result to a TemporaryBRep, then deletes the
scratch (net timeline: zero). Results are cached by params so repeated
previews / the final OK are instant.

All lengths are Fusion internal units (cm).
"""

import adsk.core, adsk.fusion
import json

from . import const
from . import gridRegistry
from . import gplog
from . import scratchUtils
from . import placement
from . import plateLayout
from . import plateSplit
from .baseplateGeneratorInput import BaseplateGeneratorInput
from .baseplateGenerator import createGridfinityBaseplate

# Custom feature identity.
FEATURE_ID = 'GridfinityPlus_baseplate'
FEATURE_NAME = 'Gridfinity Baseplate'
ATTR_GROUP = 'GridfinityPlus'
ATTR_PARAMS = 'baseplateParams'

# Plate type values (mirror commandCreateBaseplate.entry constants).
PLATE_TYPE_LIGHT = 'Light'
PLATE_TYPE_FULL = 'Full'
PLATE_TYPE_SKELETONIZED = 'Skeletonized'

# Module-level so the definition + handler survive garbage collection.
_definition = None
_computeHandler = None

# BRep cache: paramsKey -> temporary BRepBody (kept alive by this dict).
_brepCache = {}
_BREP_CACHE_MAX = 8

# Pending body swaps for the compute handler: customFeature.entityToken -> dict.
_pending = {}


def _paramsKey(params: dict) -> str:
    return json.dumps(params, sort_keys=True)


class _BaseplateComputeHandler(adsk.fusion.CustomFeatureEventHandler):
    """Swap the BaseFeature body when an edit staged a pending BRep.

    This is the ONLY place the wrapped BaseFeature may be modified. Without a
    pending entry the stored body is already correct — do nothing.
    """

    def notify(self, args):
        try:
            eventArgs = adsk.fusion.CustomFeatureEventArgs.cast(args)
            cf = eventArgs.customFeature
            pending = _pending.pop(cf.entityToken, None)
            if pending is None:
                gplog.log(f'COMPUTE: "{cf.name}" no pending swap -> no-op')
                return
            gplog.log(f'COMPUTE: "{cf.name}" applying pending swap')
            baseFeat = _findBaseFeature(cf)
            if baseFeat is None:
                gplog.log('COMPUTE: no BaseFeature found!')
                return
            with gplog.timed('COMPUTE body swap'):
                # One body per tile; the tile count may change with an edit.
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
            _nameBodies(baseFeat, pending['name'])
            gplog.log(f'COMPUTE: swap done, baseFeat bodies={baseFeat.bodies.count}')
        except Exception:
            gplog.logExc('COMPUTE handler')


def bodyName(name: str, index: int, count: int) -> str:
    return name if count <= 1 else '{} - tile {}/{}'.format(name, index + 1, count)


def _nameBodies(baseFeat, name: str):
    count = baseFeat.bodies.count
    for i in range(count):
        try:
            baseFeat.bodies.item(i).name = bodyName(name, i, count)
        except Exception:
            pass


def register(editCommandId: str, iconFolder: str):
    """Create the CustomFeatureDefinition once at add-in start."""
    global _definition, _computeHandler
    if _definition is not None:
        return _definition
    _definition = adsk.fusion.CustomFeatureDefinition.create(FEATURE_ID, FEATURE_NAME, iconFolder)
    _definition.editCommandId = editCommandId
    gplog.log(f'register: {FEATURE_ID} edit={_definition.editCommandId}')
    _computeHandler = _BaseplateComputeHandler()
    _definition.customFeatureCompute.add(_computeHandler)
    return _definition


def buildInput(params: dict) -> BaseplateGeneratorInput:
    """Map a stored params dict onto a BaseplateGeneratorInput."""
    i = BaseplateGeneratorInput()
    i.baseWidth = params['baseWidth']
    i.baseLength = params['baseLength']
    i.xyClearance = params['xyClearance']
    i.baseplateWidth = params['plateWidth']
    i.baseplateLength = params['plateLength']
    plateType = params['plateType']
    i.hasExtendedBottom = plateType != PLATE_TYPE_LIGHT
    i.hasSkeletonizedBottom = plateType == PLATE_TYPE_SKELETONIZED
    i.hasMagnetCutouts = params['hasMagnetSockets']
    i.magnetCutoutsDiameter = params['magnetSocketSize']
    i.magnetCutoutsDepth = params['magnetSocketDepth']
    i.hasScrewHoles = params['hasScrewHoles']
    i.screwHolesDiameter = params['screwHoleSize']
    i.screwHeadCutoutDiameter = params['screwHeadSize']
    i.hasPadding = params['hasPadding']
    i.paddingLeft = params['paddingLeft']
    i.paddingTop = params['paddingTop']
    i.paddingRight = params['paddingRight']
    i.paddingBottom = params['paddingBottom']
    i.bottomExtensionHeight = params['extraBottomThickness']
    i.binZClearance = params['verticalClearance']
    i.hasConnectionHoles = params['hasConnectionHoles']
    i.connectionScrewHolesDiameter = params['connectionHoleSize']
    i.cornerFilletRadius = const.BIN_CORNER_FILLET_RADIUS
    return i


def featureName(params: dict) -> str:
    name = 'Baseplate {}'.format(plateLayout.describe(params))
    if plateSplit.enabled(params):
        nx, ny = plateSplit.plan(params)['tiles']
        if nx * ny > 1:
            name += ' ({} tiles)'.format(nx * ny)
    return name


def getBaseplateBRep(des: adsk.fusion.Design, params: dict):
    """Temporary BReps for params (one per tile), using the cache when possible.

    Must be called OUTSIDE the custom feature compute context (it creates and
    deletes parametric features in a scratch component).
    """
    # Cache on geometry only; placement is applied afterwards (placedBRep).
    key = _paramsKey(placement.geometryKey(params))
    cached = _brepCache.get(key)
    if cached is not None:
        try:
            if all(b.faces.count > 0 for b in cached):
                gplog.log('getBaseplateBRep: cache HIT')
                return cached
        except Exception:
            pass
        del _brepCache[key]

    root = adsk.fusion.Component.cast(des.rootComponent)
    genInput = buildInput(plateLayout.generatorParams(params))

    startCount = des.timeline.count
    with gplog.timed('generator (parametric build)'):
        scratchComp = scratchUtils.createScratchComponent(des)
        body = createGridfinityBaseplate(genInput, scratchComp)
    tempBody = adsk.fusion.TemporaryBRepManager.get().copy(body)
    tempBody = plateLayout.cutToSize(tempBody, params)
    tiles = plateSplit.pieces(tempBody, params)

    # Delete the scratch occurrence + all features it created (net timeline: zero).
    with gplog.timed('scratch cleanup'):
        lastIndex = des.timeline.count - 1
        if lastIndex >= startCount:
            group = des.timeline.timelineGroups.add(startCount, lastIndex)
            group.deleteMe(True)
        scratchUtils.release()

    if len(_brepCache) >= _BREP_CACHE_MAX:
        _brepCache.clear()
    _brepCache[key] = tiles
    gplog.log(f'getBaseplateBRep: built, tiles={len(tiles)}, cached')
    return tiles


def placedBRep(des: adsk.fusion.Design, params: dict):
    """Plate BReps (one per tile) moved to the plane/anchor placement
    (component space)."""
    return [placement.placedCopy(b, params) for b in getBaseplateBRep(des, params)]


def _tag(customFeature, params: dict):
    """Grid tag on the custom feature (one per plate, also in Part design
    where several plates share the root component)."""
    lo = plateLayout.layout(params)
    gridRegistry.tagBaseplate(customFeature, buildInput(plateLayout.generatorParams(params)),
                              placement.plateMatrix(params),
                              cols=lo['fullX'], rows=lo['fullY'],
                              originX=lo['originX'], originY=lo['originY'],
                              exact=False,
                              partial={'left': lo['partLeft'], 'right': lo['partRight'],
                                       'bottom': lo['partFront'], 'top': lo['partBack']})


def _findBaseFeature(customFeature: adsk.fusion.CustomFeature):
    for feat in customFeature.features:
        if feat.objectType == adsk.fusion.BaseFeature.classType():
            return adsk.fusion.BaseFeature.cast(feat)
    return None


def createFeature(des: adsk.fusion.Design, component: adsk.fusion.Component, params: dict):
    """Create a new editable baseplate custom feature in `component`."""
    name = featureName(params)
    gplog.session(f'createFeature "{name}" in component "{component.name}"')

    tiles = placedBRep(des, params)
    if not tiles or any(b.faces.count == 0 for b in tiles):
        raise RuntimeError('Generated baseplate body is empty')
    return _createFromTiles(des, component, params, tiles, name)


def _createFromTiles(des, component, params, tiles, name):

    with gplog.timed('create: baseFeature add+body'):
        baseFeat = component.features.baseFeatures.add()
        baseFeat.startEdit()
        for i, body in enumerate(tiles):
            component.bRepBodies.add(body, baseFeat).name = bodyName(name, i, len(tiles))
        baseFeat.finishEdit()

    with gplog.timed('create: customFeature wrap'):
        cfInput = component.features.customFeatures.createInput(_definition)
        # Hidden revision parameter: bumping it triggers compute for edits.
        cfInput.addCustomParameter('rev', 'Revision', adsk.core.ValueInput.createByReal(1), '', False)
        cfInput.setStartAndEndFeatures(baseFeat, baseFeat)
        customFeature = component.features.customFeatures.add(cfInput)
        customFeature.name = name

    customFeature.attributes.add(ATTR_GROUP, ATTR_PARAMS, json.dumps(params))
    _tag(customFeature, params)

    gplog.dumpTimeline(des, 'create:after')
    gplog.dumpBodies(component, 'create:after')
    return customFeature


def rebuildFeature(des: adsk.fusion.Design, customFeature: adsk.fusion.CustomFeature, params: dict):
    """Apply new params to an existing feature.

    Builds the BRep now (outside compute), stages it as pending, and bumps the
    'rev' parameter so Fusion fires our compute, which performs the actual
    updateBody inside the sanctioned context.
    """
    component = customFeature.parentComponent
    name = featureName(params)
    gplog.session(f'rebuildFeature "{name}"')

    tiles = placedBRep(des, params)
    if not tiles or any(b.faces.count == 0 for b in tiles):
        raise RuntimeError('Rebuilt baseplate body is empty')

    _pending[customFeature.entityToken] = {'bodies': tiles, 'name': name}

    customFeature.attributes.add(ATTR_GROUP, ATTR_PARAMS, json.dumps(params))
    customFeature.name = name
    _tag(customFeature, params)

    # Trigger compute by bumping the hidden revision parameter.
    revParam = customFeature.parameters.itemById('rev')
    if revParam is None:
        raise RuntimeError("Feature has no 'rev' parameter (created by an older version). "
                           'Delete and recreate this baseplate once.')
    with gplog.timed('rebuild: rev bump -> compute'):
        revParam.value = revParam.value + 1

    # The tile count may have changed. Check the result outside compute; if
    # Fusion did not take the added / removed bodies, rebuild the feature at
    # the same timeline position instead.
    base = _findBaseFeature(customFeature)
    count = base.bodies.count if base else -1
    gplog.log(f'rebuild: bodies after compute={count}, expected={len(tiles)}')
    if count != len(tiles):
        _recreate(des, customFeature, params, name)

    gplog.dumpTimeline(des, 'rebuild:after')
    gplog.dumpBodies(component, 'rebuild:after')


def _dependents(des, customFeature):
    """[(customFeature, attrName, params)] of bins / cabinets standing on
    this plate (they store its entityToken as plateToken)."""
    out = []
    for attrName in ('binParams', 'cabinetParams', 'coverParams'):
        for attr in des.findAttributes(ATTR_GROUP, attrName):
            cf = adsk.fusion.CustomFeature.cast(attr.parent)
            if not cf:
                continue
            try:
                params = json.loads(attr.value)
                token = params.get('plateToken')
                if token and any(e == customFeature for e in des.findEntityByToken(token)):
                    out.append((cf, attrName, params))
            except Exception:
                gplog.logExc('baseplate dependents')
    return out


def _recreate(des, customFeature, params, name):
    """Replace the feature by a new one at the same timeline position (used
    when the number of tile bodies changed), keeping bins / cabinets linked."""
    gplog.log(f'rebuild: recreating "{name}" (tile count changed)')
    component = customFeature.parentComponent
    dependents = _dependents(des, customFeature)
    timeline = des.timeline
    index = customFeature.timelineObject.index
    timeline.markerPosition = index + 1
    try:
        tiles = placedBRep(des, params)
        newFeature = _createFromTiles(des, component, params, tiles, name)
    finally:
        timeline.moveToEnd()
    base = _findBaseFeature(customFeature)
    customFeature.deleteMe()
    try:
        if base is not None and base.isValid:
            base.deleteMe()
    except Exception:
        pass
    for cf, attrName, depParams in dependents:
        depParams['plateToken'] = newFeature.entityToken
        cf.attributes.add(ATTR_GROUP, attrName, json.dumps(depParams))
    return newFeature


def readParams(customFeature: adsk.fusion.CustomFeature):
    """Return the stored params dict, or None."""
    attr = customFeature.attributes.itemByName(ATTR_GROUP, ATTR_PARAMS)
    if not attr:
        return None
    try:
        return json.loads(attr.value)
    except ValueError:
        return None
