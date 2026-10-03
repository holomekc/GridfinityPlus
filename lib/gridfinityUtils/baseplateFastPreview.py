"""
GridfinityPlus — fast in-memory preview geometry for the baseplate dialog.

The full parametric generator costs 300-400 ms per run (sketches, extrudes,
patterns, fillets in a scratch component) — too slow for a live dialog. This
module assembles the plate with pure TemporaryBRepManager booleans instead:

  * The single-cell cutout (the accuracy-critical stepped profile) is built
    parametrically ONCE per (baseWidth, baseLength, clearance) and cached.
  * A plate is then: rounded-corner slab  minus  N x M translated cell copies
    minus  magnet/screw cylinders. All in-memory, milliseconds.

Preview-only simplifications (final geometry on OK uses the exact generator):
  * no bottom print chamfer
  * no connection holes, no screw-head chamfer, no top bin-z-clearance cut
(Skeletonized bottoms ARE shown: the exact per-cell skeleton cutout is built
parametrically once, cached, and replicated like the cell profile.)

All lengths are Fusion internal units (cm).
"""

import adsk.core, adsk.fusion
import json

from . import const
from . import gplog
from . import scratchUtils
from . import plateLayout
from . import geometryUtils
from . import baseGenerator
from . import baseplateGenerator
from .baseGeneratorInput import BaseGeneratorInput
from .baseplateGeneratorInput import BaseplateGeneratorInput

# Cell cutout cache: key -> temporary BRepBody (kept alive by this dict).
_cellCache = {}
# Skeleton center-cutout cache (same idea, extra params in key).
_skeletonCache = {}


def _tmgr():
    return adsk.fusion.TemporaryBRepManager.get()


def _box(x0, x1, y0, y1, z0, z1):
    center = adsk.core.Point3D.create((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    obb = adsk.core.OrientedBoundingBox3D.create(
        center,
        adsk.core.Vector3D.create(1, 0, 0),
        adsk.core.Vector3D.create(0, 1, 0),
        abs(x1 - x0), abs(y1 - y0), abs(z1 - z0),
    )
    return _tmgr().createBox(obb)


def _cylinder(x, y, z0, z1, radius):
    return _tmgr().createCylinderOrCone(
        adsk.core.Point3D.create(x, y, z0), radius,
        adsk.core.Point3D.create(x, y, z1), radius,
    )


def _union(target, tool):
    _tmgr().booleanOperation(target, tool, adsk.fusion.BooleanTypes.UnionBooleanType)


def _subtract(target, tool):
    _tmgr().booleanOperation(target, tool, adsk.fusion.BooleanTypes.DifferenceBooleanType)


def _translate(body, dx, dy, dz=0.0):
    m = adsk.core.Matrix3D.create()
    m.translation = adsk.core.Vector3D.create(dx, dy, dz)
    _tmgr().transform(body, m)


def _unionAll(bodies):
    """Merge many (mostly disjoint) bodies into one via binary-tree union.

    One combined tool + one subtract beats N separate subtracts against an
    ever-larger plate — that per-cell cost was the big-grid stutter."""
    while len(bodies) > 1:
        merged = []
        for k in range(0, len(bodies) - 1, 2):
            _union(bodies[k], bodies[k + 1])
            merged.append(bodies[k])
        if len(bodies) % 2 == 1:
            merged.append(bodies[-1])
        bodies = merged
    return bodies[0]


def _roundedSlab(x0, x1, y0, y1, z0, z1, r):
    """Rounded-rectangle prism == box with 4 vertical corner fillets (exact)."""
    if r <= 0:
        return _box(x0, x1, y0, y1, z0, z1)
    slab = _box(x0 + r, x1 - r, y0, y1, z0, z1)
    _union(slab, _box(x0, x1, y0 + r, y1 - r, z0, z1))
    for cx in (x0 + r, x1 - r):
        for cy in (y0 + r, y1 - r):
            _union(slab, _cylinder(cx, cy, z0, z1, r))
    return slab


def _getCellCutout(des: adsk.fusion.Design, baseWidth: float, baseLength: float, xyClearance: float):
    """Single-cell cutting body, built parametrically once and cached.

    Mirrors baseplateGenerator's cutout construction exactly so the preview
    cell profile matches the final plate.
    """
    key = json.dumps([round(baseWidth, 6), round(baseLength, 6), round(xyClearance, 6)])
    cached = _cellCache.get(key)
    if cached is not None:
        try:
            if cached.faces.count > 0:
                return cached
        except Exception:
            pass
        del _cellCache[key]

    root = adsk.fusion.Component.cast(des.rootComponent)
    startCount = des.timeline.count
    with gplog.timed('fastPreview: cell cutout parametric build'):
        scratchComp = scratchUtils.createScratchComponent(des)

        cutoutInput = BaseGeneratorInput()
        cutoutInput.xyClearance = xyClearance
        cutoutInput.originPoint = geometryUtils.createOffsetPoint(
            scratchComp.originConstructionPoint.geometry,
            byX=-xyClearance * 2,
            byY=-xyClearance * 2,
        )
        cutoutInput.baseWidth = baseWidth + xyClearance * 2
        cutoutInput.baseLength = baseLength + xyClearance * 2
        cutoutInput.cornerFilletRadius = const.BIN_CORNER_FILLET_RADIUS + xyClearance
        body = baseGenerator.createSingleGridfinityBaseBody(cutoutInput, scratchComp)
        temp = _tmgr().copy(body)

        lastIndex = des.timeline.count - 1
        if lastIndex >= startCount:
            group = des.timeline.timelineGroups.add(startCount, lastIndex)
            group.deleteMe(True)
        scratchUtils.release()

    _cellCache[key] = temp
    return temp


def _getSkeletonCutout(des: adsk.fusion.Design, params: dict):
    """Per-cell skeleton center cutout, built parametrically once and cached."""
    baseWidth = params['baseWidth']
    baseLength = params['baseLength']
    cl = params['xyClearance']
    key = json.dumps([round(baseWidth, 6), round(baseLength, 6), round(cl, 6),
                      round(params['magnetSocketSize'], 6), round(params['screwHeadSize'], 6),
                      round(params['extraBottomThickness'], 6)])
    cached = _skeletonCache.get(key)
    if cached is not None:
        try:
            if cached.faces.count > 0:
                return cached
        except Exception:
            pass
        del _skeletonCache[key]

    root = adsk.fusion.Component.cast(des.rootComponent)
    startCount = des.timeline.count
    with gplog.timed('fastPreview: skeleton cutout parametric build'):
        scratchComp = scratchUtils.createScratchComponent(des)

        cutoutInput = BaseGeneratorInput()
        cutoutInput.xyClearance = cl
        cutoutInput.originPoint = geometryUtils.createOffsetPoint(
            scratchComp.originConstructionPoint.geometry,
            byX=-cl * 2,
            byY=-cl * 2,
        )
        cutoutInput.baseWidth = baseWidth + cl * 2
        cutoutInput.baseLength = baseLength + cl * 2
        cutoutInput.cornerFilletRadius = const.BIN_CORNER_FILLET_RADIUS + cl
        baseBody = baseGenerator.createSingleGridfinityBaseBody(cutoutInput, scratchComp)

        genInput = BaseplateGeneratorInput()
        genInput.xyClearance = cl
        genInput.baseWidth = baseWidth
        genInput.baseLength = baseLength
        genInput.magnetCutoutsDiameter = params['magnetSocketSize']
        genInput.screwHeadCutoutDiameter = params['screwHeadSize']
        genInput.bottomExtensionHeight = params['extraBottomThickness']
        genInput.hasConnectionHoles = False
        skelBody, _, _ = baseplateGenerator.createSkeletonCenterCutout(genInput, baseBody, scratchComp)
        temp = _tmgr().copy(skelBody)

        lastIndex = des.timeline.count - 1
        if lastIndex >= startCount:
            group = des.timeline.timelineGroups.add(startCount, lastIndex)
            group.deleteMe(True)
        scratchUtils.release()

    _skeletonCache[key] = temp
    return temp


def buildPreviewPlate(des: adsk.fusion.Design, params: dict):
    """Assemble the preview plate purely in memory. Returns a temp BRepBody."""
    with gplog.timed('fastPreview TOTAL'):
        baseWidth = params['baseWidth']
        baseLength = params['baseLength']
        cl = params['xyClearance']
        lo = plateLayout.layout(params)
        cols = lo['nX']
        rows = lo['nY']
        plateType = params['plateType']
        hasExtended = plateType != 'Light'
        ext = params['extraBottomThickness'] if hasExtended else 0.0


        trueW = cols * baseWidth - cl * 2
        trueL = rows * baseLength - cl * 2
        zBottom = -(const.BIN_BASE_HEIGHT + ext)
        r = const.BIN_CORNER_FILLET_RADIUS - cl

        # Outline: whole cells (+ padding) or the exact-size window.
        slab = _roundedSlab(lo['x0'], lo['x1'], lo['y0'], lo['y1'], zBottom, 0.0, r)

        # Collect ALL cutting tools, merge once, subtract once.
        tools = []

        cell = _getCellCutout(des, baseWidth, baseLength, cl)
        skeleton = _getSkeletonCutout(des, params) if plateType == 'Skeletonized' else None
        with gplog.timed('fastPreview: cell copies'):
            for i in range(cols):
                for j in range(rows):
                    tool = _tmgr().copy(cell)
                    _translate(tool, i * baseWidth, j * baseLength)
                    tools.append(tool)
                    if skeleton is not None:
                        skelTool = _tmgr().copy(skeleton)
                        _translate(skelTool, i * baseWidth, j * baseLength)
                        tools.append(skelTool)

        # Magnet / screw holes as plain cylinders (Full/Skeleton plates only).
        if hasExtended and (params['hasMagnetSockets'] or params['hasScrewHoles']):
            off = const.DIMENSION_SCREW_HOLES_OFFSET
            spanX = baseWidth - off * 2
            spanY = baseLength - off * 2
            for i in range(cols):
                for j in range(rows):
                    for a in (0, 1):
                        for b in (0, 1):
                            hx = i * baseWidth + (off - cl) + a * spanX
                            hy = j * baseLength + (off - cl) + b * spanY
                            if params['hasMagnetSockets']:
                                tools.append(_cylinder(
                                    hx, hy, zBottom, zBottom + params['magnetSocketDepth'],
                                    params['magnetSocketSize'] / 2))
                            if params['hasScrewHoles'] and ext > 0:
                                tools.append(_cylinder(
                                    hx, hy, zBottom, zBottom + ext,
                                    params['screwHoleSize'] / 2))

        with gplog.timed(f'fastPreview: union {len(tools)} tools'):
            combinedTool = _unionAll(tools)
        with gplog.timed('fastPreview: single subtract'):
            _subtract(slab, combinedTool)

        from . import plateSplit
        slab = plateSplit.split(slab, params)
        gplog.log(f'fastPreview: plate {cols}x{rows} faces={slab.faces.count}')
        return slab
