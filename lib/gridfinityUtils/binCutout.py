"""
GridfinityPlus — tool-shaped cutouts in (solid) bins, insertable from the top.

Unlike Fusion's exact Combine/Cut, the cavity here is REALISTIC for inserting
and removing a physical part:

  * lateral tolerance (default 0.25 mm): the tool is "fattened" by unioning
    copies shifted in 8 horizontal directions (+ one downward copy for the seat)
  * upward clearing: the fattened tool is swept upward by unioning translated
    copies up to the bin top — undercuts and overhangs cannot trap the part

Known v1 limitation: a bore/void that opens DOWNWARD (e.g. hollow nozzle tip)
still leaves a thin pin in the bin (the upward sweep only fills columns that
have material below). Slice-based hole filling is the planned phase 2.

Cutouts are stored in the bin's params (tool entityToken + settings), so they
are re-applied automatically whenever the bin feature is rebuilt/edited.

All lengths are Fusion internal units (cm).
"""

import adsk.core, adsk.fusion
import math

from . import gplog

# Cap for sweep copies; the step is widened if the height needs more.
_MAX_SWEEP_COPIES = 120


def _tmgr():
    return adsk.fusion.TemporaryBRepManager.get()


def _translatedCopy(body, dx, dy, dz):
    c = _tmgr().copy(body)
    m = adsk.core.Matrix3D.create()
    m.translation = adsk.core.Vector3D.create(dx, dy, dz)
    _tmgr().transform(c, m)
    return c


def _unionInto(target, tool):
    _tmgr().booleanOperation(target, tool, adsk.fusion.BooleanTypes.UnionBooleanType)


def buildCutter(toolBody, tolerance: float, step: float, sweepTopZ: float):
    """In-memory cutter body for one tool. toolBody may be any BRepBody
    (a temp copy is taken; proxies resolve to world coordinates)."""
    with gplog.timed('cutout: buildCutter'):
        base = _tmgr().copy(toolBody)

        # Lateral tolerance: 8 horizontal directions + straight down (seat).
        if tolerance > 0:
            for k in range(8):
                ang = k * math.pi / 4
                _unionInto(base, _translatedCopy(toolBody, tolerance * math.cos(ang),
                                                 tolerance * math.sin(ang), 0))
            _unionInto(base, _translatedCopy(toolBody, 0, 0, -tolerance))

        # Upward sweep: union copies from the tool up to the bin top.
        bb = base.boundingBox
        height = max(0.0, sweepTopZ - bb.minPoint.z)
        if height > 0 and step > 0:
            copies = int(math.ceil(height / step))
            if copies > _MAX_SWEEP_COPIES:
                copies = _MAX_SWEEP_COPIES
                step = height / copies
            gplog.log(f'cutout: sweep {copies} copies, step {step * 10:.2f} mm, height {height * 10:.1f} mm')
            # Doubling trick: sweep by unioning the accumulated body shifted by
            # its own covered span — log2(N) booleans instead of N.
            covered = 0.0
            span = step
            seed = _tmgr().copy(base)
            m = adsk.core.Matrix3D.create()
            m.translation = adsk.core.Vector3D.create(0, 0, step)
            _tmgr().transform(seed, m)
            _unionInto(base, seed)
            covered = step
            while covered < height:
                shifted = _translatedCopy(base, 0, 0, covered + step)
                _unionInto(base, shifted)
                covered = covered * 2 + step

        gplog.log(f'cutout: cutter faces={base.faces.count}')
        return base


CUTOUT_FEATURE_ID = 'GridfinityPlus_toolCutout'
CUTOUT_FEATURE_NAME = 'Gridfinity Tool Cutout'

_definition = None


def register(iconFolder: str):
    """Custom feature definition for the cutout timeline node. No compute
    handler: the wrapped BaseFeature (cutter) + Combine recompute natively,
    so bin edits downstream re-apply the cut automatically."""
    global _definition
    if _definition is None:
        _definition = adsk.fusion.CustomFeatureDefinition.create(
            CUTOUT_FEATURE_ID, CUTOUT_FEATURE_NAME, iconFolder)
    return _definition


def createCutoutFeature(des: adsk.fusion.Design, binBodyNative: adsk.fusion.BRepBody,
                        cutterBodies, name: str):
    """Create ONE visible timeline node performing the cut:
    BaseFeature (cutter bodies) + Combine/Cut, wrapped in a CustomFeature."""
    component = binBodyNative.parentComponent

    baseFeat = component.features.baseFeatures.add()
    baseFeat.startEdit()
    for cutter in cutterBodies:
        component.bRepBodies.add(cutter, baseFeat)
    baseFeat.finishEdit()

    # Body references from inside startEdit/finishEdit are DEAD afterwards —
    # re-fetch fresh references from the finished base feature for the combine.
    tools = adsk.core.ObjectCollection.create()
    for i in range(baseFeat.bodies.count):
        tools.add(baseFeat.bodies.item(i))
    gplog.log(f'cutout: baseFeature holds {tools.count} cutter bodies after finishEdit')
    if tools.count == 0:
        raise RuntimeError('Cutter bodies were lost when finishing the base feature')

    combineFeatures = component.features.combineFeatures
    combineInput = combineFeatures.createInput(binBodyNative, tools)
    combineInput.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
    combineInput.isKeepToolBodies = False
    combineFeat = combineFeatures.add(combineInput)

    cfInput = component.features.customFeatures.createInput(_definition)
    cfInput.setStartAndEndFeatures(baseFeat, combineFeat)
    customFeature = component.features.customFeatures.add(cfInput)
    customFeature.name = name
    gplog.log(f'cutout: created timeline feature "{name}"')
    return customFeature


def resolveTool(des: adsk.fusion.Design, tokens):
    """Find the tool BRepBody by any of the stored entityTokens; returns a
    world-positioned body (proxy when the tool lives in an occurrence)."""
    for token in tokens:
        if not token:
            continue
        try:
            for e in des.findEntityByToken(token):
                body = adsk.fusion.BRepBody.cast(e)
                if not body:
                    continue
                if body.assemblyContext is not None:
                    return body  # already a proxy: world coordinates
                # Native body: wrap in the first occurrence so geometry copies
                # come out in world coordinates.
                comp = body.parentComponent
                occs = des.rootComponent.allOccurrencesByComponent(comp)
                if occs.count > 0:
                    proxy = body.createForAssemblyContext(occs.item(0))
                    if proxy:
                        return proxy
                return body  # root-level body: world == local
        except Exception:
            gplog.logExc(f'cutout: resolveTool token failed')
    return None


def applyCutouts(des: adsk.fusion.Design, placedBody, cutouts):
    """Subtract all stored cutouts from an (already placed) bin temp body.
    Returns the modified body. Missing tools are skipped with a log entry."""
    if not cutouts:
        return placedBody
    topZ = placedBody.boundingBox.maxPoint.z
    for i, cut in enumerate(cutouts):
        tokens = cut.get('toolTokens') or [cut.get('toolToken', '')]
        tool = resolveTool(des, tokens)
        if tool is None:
            gplog.log(f'cutout #{i}: tool body not found (deleted?), skipping')
            continue
        cutter = buildCutter(tool, float(cut.get('tolerance', 0.025)),
                             float(cut.get('step', 0.05)), topZ)
        with gplog.timed(f'cutout #{i}: subtract'):
            _tmgr().booleanOperation(placedBody, cutter, adsk.fusion.BooleanTypes.DifferenceBooleanType)
    return placedBody
