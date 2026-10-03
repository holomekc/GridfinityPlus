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
                baseFeat.startEdit()
                oldBody = baseFeat.bodies.item(0)
                baseFeat.updateBody(oldBody, pending['body'])
                baseFeat.finishEdit()
            try:
                baseFeat.bodies.item(0).name = pending['name']
            except Exception:
                pass
            gplog.log(f'COMPUTE: swap done, baseFeat bodies={baseFeat.bodies.count}')
        except Exception:
            gplog.logExc('COMPUTE handler')


def register(editCommandId: str, iconFolder: str):
    """Create the CustomFeatureDefinition once at add-in start."""
    global _definition, _computeHandler
    if _definition is not None:
        return _definition
    _definition = adsk.fusion.CustomFeatureDefinition.create(FEATURE_ID, FEATURE_NAME, iconFolder)
    _definition.editCommandId = editCommandId
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
    return 'Baseplate {}'.format(plateLayout.describe(params))


def getBaseplateBRep(des: adsk.fusion.Design, params: dict):
    """Return a temporary BRep for params, using the cache when possible.

    Must be called OUTSIDE the custom feature compute context (it creates and
    deletes parametric features in a scratch component).
    """
    # Cache on geometry only; placement is applied afterwards (placedBRep).
    key = _paramsKey(placement.geometryKey(params))
    cached = _brepCache.get(key)
    if cached is not None:
        try:
            if cached.faces.count > 0:
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

    # Delete the scratch occurrence + all features it created (net timeline: zero).
    with gplog.timed('scratch cleanup'):
        lastIndex = des.timeline.count - 1
        if lastIndex >= startCount:
            group = des.timeline.timelineGroups.add(startCount, lastIndex)
            group.deleteMe(True)
        scratchUtils.release()

    if len(_brepCache) >= _BREP_CACHE_MAX:
        _brepCache.clear()
    _brepCache[key] = tempBody
    gplog.log(f'getBaseplateBRep: built, faces={tempBody.faces.count}, cached')
    return tempBody


def placedBRep(des: adsk.fusion.Design, params: dict):
    """Plate BRep moved to its plane/anchor placement (component space)."""
    return placement.placedCopy(getBaseplateBRep(des, params), params)


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

    tempBody = placedBRep(des, params)
    if tempBody is None or tempBody.faces.count == 0:
        raise RuntimeError('Generated baseplate body is empty')

    with gplog.timed('create: baseFeature add+body'):
        baseFeat = component.features.baseFeatures.add()
        baseFeat.startEdit()
        addedBody = component.bRepBodies.add(tempBody, baseFeat)
        addedBody.name = name
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

    tempBody = placedBRep(des, params)
    if tempBody is None or tempBody.faces.count == 0:
        raise RuntimeError('Rebuilt baseplate body is empty')

    _pending[customFeature.entityToken] = {'body': tempBody, 'name': name}

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

    gplog.dumpTimeline(des, 'rebuild:after')
    gplog.dumpBodies(component, 'rebuild:after')


def readParams(customFeature: adsk.fusion.CustomFeature):
    """Return the stored params dict, or None."""
    attr = customFeature.attributes.itemByName(ATTR_GROUP, ATTR_PARAMS)
    if not attr:
        return None
    try:
        return json.loads(attr.value)
    except ValueError:
        return None
