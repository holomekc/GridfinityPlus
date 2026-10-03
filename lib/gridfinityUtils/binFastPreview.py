"""
GridfinityPlus — fast in-memory ghost geometry for the bin dialog.

The full bin generator costs 1.0-1.6 s per configuration — unusable for a live
dialog. This module assembles a close approximation with TemporaryBRep booleans
in milliseconds:

  * The base FOOT (accuracy-critical, includes magnet/screw cutouts) is built
    parametrically ONCE per foot-config and cached, then replicated per cell.
  * The body is a rounded box; hollow bins get an inner pocket; the stacking
    lip is a rounded ring on top.

Ghost-only simplifications (exact geometry is built once on OK):
scoop, label tab, custom compartments, shelled split, lip notches.

All lengths are Fusion internal units (cm).
"""

import adsk.core, adsk.fusion
import json

from . import const
from . import gplog
from . import scratchUtils
from . import geometryUtils
from . import baseGenerator
from .baseGeneratorInput import BaseGeneratorInput
from .baseplateFastPreview import _roundedSlab, _tmgr, _translate, _unionAll, _subtract, _union

# Foot cache: key -> temp BRepBody of a single base foot at cell (0,0).
_footCache = {}


def _getFoot(des: adsk.fusion.Design, baseW, baseL, cl, hasScrew, screwD, hasMagnet, hasMagnetTabs, magnetD, magnetDepth):
    key = json.dumps([round(baseW, 6), round(baseL, 6), round(cl, 6),
                      bool(hasScrew), round(screwD, 6),
                      bool(hasMagnet), bool(hasMagnetTabs), round(magnetD, 6), round(magnetDepth, 6)])
    cached = _footCache.get(key)
    if cached is not None:
        try:
            if cached.faces.count > 0:
                return cached
        except Exception:
            pass
        del _footCache[key]

    root = adsk.fusion.Component.cast(des.rootComponent)
    startCount = des.timeline.count
    with gplog.timed('binFastPreview: foot parametric build'):
        scratch = scratchUtils.createScratchComponent(des)

        baseInput = BaseGeneratorInput()
        baseInput.originPoint = geometryUtils.createOffsetPoint(
            scratch.originConstructionPoint.geometry, byX=-cl, byY=-cl)
        baseInput.baseWidth = baseW
        baseInput.baseLength = baseL
        baseInput.xyClearance = cl
        baseInput.hasScrewHoles = hasScrew
        baseInput.hasMagnetCutouts = hasMagnet
        baseInput.hasMagnetCutoutsTabs = hasMagnetTabs
        baseInput.screwHolesDiameter = screwD
        baseInput.magnetCutoutsDiameter = magnetD
        baseInput.magnetCutoutsDepth = magnetDepth
        body = baseGenerator.createSingleGridfinityBaseBody(baseInput, scratch)
        temp = _tmgr().copy(body)

        lastIndex = des.timeline.count - 1
        if lastIndex >= startCount:
            group = des.timeline.timelineGroups.add(startCount, lastIndex)
            group.deleteMe(True)
        scratchUtils.release()

    _footCache[key] = temp
    return temp


def buildPreviewBin(des: adsk.fusion.Design, params: dict, inputs) -> adsk.fusion.BRepBody:
    """Assemble the ghost bin at local origin, in memory. ~ms, not seconds."""
    # Import here to avoid a circular import with the command module.
    from ...commands.commandCreateBin import entry as binEntry

    with gplog.timed('binFastPreview TOTAL'):
        baseW = params['baseW']
        baseL = params['baseL']
        cl = params['cl']
        binW = int(params['binW'])
        binL = int(params['binL'])
        binH = float(params['binH'])

        heightUnit = inputs.itemById(binEntry.BIN_HEIGHT_UNIT_INPUT_ID).value
        wall = inputs.itemById(binEntry.BIN_WALL_THICKNESS_INPUT_ID).value
        withLip = inputs.itemById(binEntry.BIN_WITH_LIP_INPUT_ID).value
        generateBase = inputs.itemById(binEntry.BIN_GENERATE_BASE_INPUT_ID).value
        generateBody = inputs.itemById(binEntry.BIN_GENERATE_BODY_INPUT_ID).value
        binTypeDropdown = inputs.itemById(binEntry.BIN_TYPE_DROPDOWN_ID)
        binType = binTypeDropdown.selectedItem.name if binTypeDropdown.selectedItem else 'Hollow'
        hasScrew = inputs.itemById(binEntry.BIN_SCREW_HOLES_INPUT_ID).value and binType != 'Shelled'
        screwD = inputs.itemById(binEntry.BIN_SCREW_DIAMETER_INPUT).value
        hasMagnet = inputs.itemById(binEntry.BIN_MAGNET_CUTOUTS_INPUT_ID).value and binType != 'Shelled'
        hasMagnetTabs = inputs.itemById(binEntry.BIN_MAGNET_CUTOUTS_TABS_INPUT_ID).value
        magnetD = inputs.itemById(binEntry.BIN_MAGNET_DIAMETER_INPUT).value
        magnetDepth = inputs.itemById(binEntry.BIN_MAGNET_HEIGHT_INPUT).value

        aW = binW * baseW - 2 * cl
        aL = binL * baseL - 2 * cl
        r = const.BIN_CORNER_FILLET_RADIUS - cl
        bodyH = (binH - 1) * heightUnit + max(0.0, heightUnit - const.BIN_BASE_HEIGHT)

        # Body overhang over plate padding (feet stay on the grid).
        ovh = params.get('ovh', {})
        ovL = float(ovh.get('left', 0))
        ovR = float(ovh.get('right', 0))
        ovF = float(ovh.get('front', 0))
        ovB = float(ovh.get('back', 0))

        result = None

        if generateBase:
            foot = _getFoot(des, baseW, baseL, cl, hasScrew, screwD,
                            hasMagnet, hasMagnetTabs, magnetD, magnetDepth)
            # Partial cell on a side: extra row/column of feet, clipped to the
            # extended outline below (cut foot).
            part = ovh.get('partial', {}) or {}
            eL = 1 if part.get('left') else 0
            eR = 1 if part.get('right') else 0
            eF = 1 if part.get('front') else 0
            eB = 1 if part.get('back') else 0
            feet = []
            for i in range(-eL, binW + eR):
                for j in range(-eF, binL + eB):
                    f = _tmgr().copy(foot)
                    _translate(f, i * baseW, j * baseL)
                    feet.append(f)
            result = _unionAll(feet)
            if eL or eR or eF or eB:
                window = _roundedSlab(-ovL, aW + ovR, -ovF, aL + ovB, -10.0, 10.0, r)
                _tmgr().booleanOperation(result, window, adsk.fusion.BooleanTypes.IntersectionBooleanType)

        if generateBody:
            x0, x1 = -ovL, aW + ovR
            y0, y1 = -ovF, aL + ovB
            body = _roundedSlab(x0, x1, y0, y1, 0, bodyH, r)
            if withLip:
                lip = _roundedSlab(x0, x1, y0, y1, bodyH, bodyH + const.BIN_LIP_EXTRA_HEIGHT, r)
                _union(body, lip)
            pocketTop = bodyH + (const.BIN_LIP_EXTRA_HEIGHT if withLip else 0) + 0.1
            if binType == 'Hollow':
                _cutCompartments(body, inputs, binEntry, x0, x1, y0, y1, bodyH, pocketTop,
                                 wall, cl, r, withLip)
            if result is None:
                result = body
            else:
                _union(result, body)

        if binType == 'Shelled' and result is not None:
            # Shelled = constant wall all around, interior follows the feet.
            # Approximation: open box above the base + hollowed feet.
            xs0, xs1 = (-ovL, aW + ovR) if generateBody else (0, aW)
            ys0, ys1 = (-ovF, aL + ovB) if generateBody else (0, aL)
            tools = []
            if generateBody:
                tools.append(_roundedSlab(xs0 + wall, xs1 - wall, ys0 + wall, ys1 - wall,
                                          0.0, bodyH + 1.0, max(0.05, r - wall)))
            if generateBase:
                inset = wall + const.BIN_BASE_TOP_SECTION_HEIGH
                for i in range(binW):
                    for j in range(binL):
                        fx0, fy0 = i * baseW, j * baseL
                        fx1, fy1 = fx0 + baseW - 2 * cl, fy0 + baseL - 2 * cl
                        tools.append(_roundedSlab(fx0 + inset, fx1 - inset, fy0 + inset, fy1 - inset,
                                                  -const.BIN_BASE_HEIGHT + wall, 0.02,
                                                  max(0.05, r - inset)))
            if tools:
                _subtract(result, _unionAll(tools))

        if result is None:
            # Nothing enabled: tiny marker slab so the ghost is still visible.
            result = _roundedSlab(0, aW, 0, aL, 0, 0.1, r)

        gplog.log(f'binFastPreview: {binW}x{binL}x{binH} faces={result.faces.count}')
        return result


def _cutCompartments(body, inputs, binEntry, x0, x1, y0, y1, bodyH, pocketTop, wall, cl, r, withLip):
    """Hollow preview: one pocket per compartment, mirroring binBodyGenerator."""
    cx = int(inputs.itemById(binEntry.BIN_COMPARTMENTS_GRID_BASE_WIDTH_ID).value)
    cy = int(inputs.itemById(binEntry.BIN_COMPARTMENTS_GRID_BASE_LENGTH_ID).value)
    hasScoop = inputs.itemById(binEntry.BIN_HAS_SCOOP_INPUT_ID).value
    layout = inputs.itemById(binEntry.BIN_COMPARTMENTS_GRID_TYPE_ID)
    custom = layout and layout.selectedItem and layout.selectedItem.name == binEntry.BIN_COMPARTMENTS_GRID_TYPE_CUSTOM

    compartments = []  # (posX, posY, w, l, depth)
    if custom:
        table = inputs.itemById(binEntry.BIN_COMPARTMENTS_TABLE_ID)
        for i in range(1, table.rowCount):
            v = [table.getInputAtPosition(i, j).value for j in range(5)]
            compartments.append((int(v[0]), int(v[1]), int(v[2]), int(v[3]), float(v[4])))
    else:
        compartments = [(i, j, 1, 1, 1e9) for i in range(cx) for j in range(cy)]

    minX, maxX = x0 + wall, x1 - wall
    minY = y0 + ((const.BIN_LIP_WALL_THICKNESS - cl) if (withLip and hasScoop) else wall)
    maxY = y1 - wall
    uW = (maxX - minX - (cx - 1) * wall) / max(1, cx)
    uL = (maxY - minY - (cy - 1) * wall) / max(1, cy)
    rr = max(0.05, r - wall)

    tools = []
    for px, py, w, l, depth in compartments:
        ox = minX + px * (uW + wall)
        oy = minY + py * (uL + wall)
        cw = uW * w + (w - 1) * wall
        cL = uL * l + (l - 1) * wall
        d = min(bodyH - const.BIN_COMPARTMENT_BOTTOM_THICKNESS, depth)
        tools.append(_roundedSlab(ox, ox + cw, oy, oy + cL, bodyH - d, pocketTop, rr))
    # Dividers sit slightly below the rim; the lip opening is always free.
    clearance = const.BIN_TAB_TOP_CLEARANCE if len(compartments) > 1 else 0.0
    tools.append(_roundedSlab(minX, maxX, minY, maxY, bodyH - clearance, pocketTop, rr))
    if tools:
        _subtract(body, _unionAll(tools))
