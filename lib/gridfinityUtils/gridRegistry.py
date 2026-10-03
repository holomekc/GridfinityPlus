"""
Grid registry — GridfinityPlus feature (a): make baseplates grid-aware.

The upstream generator anchors every baseplate at its component origin and grows
in +X/+Y, but stores no metadata about the grid. This module tags a baseplate
component with its grid definition (origin, pitch, cell counts, clearance,
padding) as Fusion Attributes, and provides lookup + snap helpers so a later
"Place Bin" command can align bins to an existing grid.

All lengths are in Fusion internal units (cm). 1 grid unit = 4.2 cm = 42 mm.

Attributes are namespaced under ATTR_GROUP so upstream data is never touched,
keeping the fork mergeable with upstream.
"""

import adsk.core, adsk.fusion
import json

# Attribute group name. Kept distinct from upstream so a merge never collides.
ATTR_GROUP = 'GridfinityPlus'
# Marker attribute: presence identifies an entity as a tagged baseplate.
ATTR_IS_BASEPLATE = 'isBaseplate'
# JSON blob holding the full grid definition.
ATTR_GRID = 'grid'
# Schema version so future readers can migrate old tags.
SCHEMA_VERSION = 1


class GridInfo:
    """Parsed grid definition for one baseplate."""

    def __init__(self, data: dict, entity: adsk.core.Base = None):
        self.version: int = data.get('version', SCHEMA_VERSION)
        # Pitch: distance between adjacent cell origins, per axis (cm).
        self.pitchX: float = data['pitchX']
        self.pitchY: float = data['pitchY']
        # Grid extent in whole cells.
        self.cols: int = data['cols']
        self.rows: int = data['rows']
        # Bin xy clearance baked into the plate (cm).
        self.xyClearance: float = data.get('xyClearance', 0.025)
        # Side padding around the usable grid (cm), if any.
        self.padding: dict = data.get('padding', {'left': 0, 'top': 0, 'right': 0, 'bottom': 0})
        # Partial (cut) cell beyond the whole cells, per side (cm). Never on a
        # side that has padding.
        self.partial: dict = data.get('partial', {'left': 0, 'top': 0, 'right': 0, 'bottom': 0})
        # Plate local frame -> component space (16 floats). None = identity
        # (plates created before plane/anchor placement existed).
        self.placement = data.get('placement')
        # Local position of cell (0, 0) — non-zero when an exact-size plate
        # starts with a cut (partial) cell. Only whole cells are addressable.
        self.originX: float = data.get('originX', 0.0)
        self.originY: float = data.get('originY', 0.0)
        # The entity the attribute was read from (component or body). May be None.
        self.entity = entity

    def placementMatrix(self) -> adsk.core.Matrix3D:
        m = adsk.core.Matrix3D.create()
        if self.placement:
            m.setWithArray(list(self.placement))
        return m

    def toDict(self) -> dict:
        d = {
            'version': self.version,
            'pitchX': self.pitchX,
            'pitchY': self.pitchY,
            'cols': self.cols,
            'rows': self.rows,
            'xyClearance': self.xyClearance,
            'padding': self.padding,
        }
        if self.placement:
            d['placement'] = list(self.placement)
        d['partial'] = self.partial
        d['originX'] = self.originX
        d['originY'] = self.originY
        return d

    def cellLocalOrigin(self, col: int, row: int) -> adsk.core.Point3D:
        """Local-space corner where a bin at (col, row) should be anchored.

        Matches upstream baseplateGenerator: the first base sits at the
        component origin and the rectangular pattern steps by pitch per axis.
        """
        return adsk.core.Point3D.create(self.originX + col * self.pitchX, self.originY + row * self.pitchY, 0)


def tagBaseplate(entity: adsk.core.Base, input, placementMatrix: adsk.core.Matrix3D = None,
                 cols: int = None, rows: int = None, originX: float = 0.0, originY: float = 0.0,
                 exact: bool = False, partial: dict = None) -> None:
    """Write the grid definition onto a baseplate entity (component preferred).

    `input` is the BaseplateGeneratorInput used to build the plate. Tag the
    component: it survives body merges and never dangles when a body is consumed
    by later timeline ops. Click-on-body resolution is handled separately by
    findNearestBaseplate (world-point based), so body tagging is not needed.
    """
    grid = GridInfo({
        'version': SCHEMA_VERSION,
        'pitchX': input.baseWidth,
        'pitchY': input.baseLength,
        'cols': int(input.baseplateWidth) if cols is None else int(cols),
        'rows': int(input.baseplateLength) if rows is None else int(rows),
        'originX': originX,
        'originY': originY,
        'partial': partial or {'left': 0, 'top': 0, 'right': 0, 'bottom': 0},
        'xyClearance': input.xyClearance,
        'padding': {
            'left': getattr(input, 'paddingLeft', 0) if getattr(input, 'hasPadding', False) and not exact else 0,
            'top': getattr(input, 'paddingTop', 0) if getattr(input, 'hasPadding', False) and not exact else 0,
            'right': getattr(input, 'paddingRight', 0) if getattr(input, 'hasPadding', False) and not exact else 0,
            'bottom': getattr(input, 'paddingBottom', 0) if getattr(input, 'hasPadding', False) and not exact else 0,
        },
        'placement': [float(v) for v in placementMatrix.asArray()] if placementMatrix is not None else None,
    })
    entity.attributes.add(ATTR_GROUP, ATTR_IS_BASEPLATE, '1')
    entity.attributes.add(ATTR_GROUP, ATTR_GRID, json.dumps(grid.toDict()))


def readGrid(entity: adsk.core.Base):
    """Return GridInfo if `entity` carries a grid tag, else None."""
    attr = entity.attributes.itemByName(ATTR_GROUP, ATTR_GRID)
    if not attr:
        return None
    try:
        return GridInfo(json.loads(attr.value), entity)
    except (ValueError, KeyError):
        return None


def findBaseplates(design: adsk.fusion.Design):
    """All tagged baseplates in the design, as (occurrence, GridInfo) pairs.

    Uses Design.findAttributes to locate tagged entities in one pass, then
    resolves each to its owning occurrence so we can read its world transform.
    Only component-level tags are returned here (body tags are for click
    resolution via readGrid).
    """
    results = []
    attrs = design.findAttributes(ATTR_GROUP, ATTR_IS_BASEPLATE)
    featureTagged = []
    componentTagged = []
    for attr in attrs:
        parent = attr.parent
        if adsk.fusion.CustomFeature.cast(parent):
            featureTagged.append(adsk.fusion.CustomFeature.cast(parent))
        elif adsk.fusion.Component.cast(parent):
            componentTagged.append(adsk.fusion.Component.cast(parent))

    entities = list(featureTagged)
    # Legacy component tags only where no per-feature tag exists in that
    # component (several plates in one component would collide otherwise).
    tokensWithFeatures = set()
    for cf in featureTagged:
        try:
            tokensWithFeatures.add(cf.parentComponent.entityToken)
        except Exception:
            pass
    for comp in componentTagged:
        if comp.entityToken not in tokensWithFeatures:
            entities.append(comp)

    for entity in entities:
        # Deleted plates stay reachable through their attributes (undo
        # history); never offer them, clicks on them would go nowhere.
        try:
            if not entity.isValid:
                continue
            if adsk.fusion.CustomFeature.cast(entity):
                if entity.isSuppressed:
                    continue
                tlo = entity.timelineObject
                if tlo is not None and tlo.isRolledBack:
                    continue
                # Deleted features can still look valid (undo history), but
                # they are no longer in their component's feature list.
                feats = entity.parentComponent.features.customFeatures
                if not any(feats.item(i) == entity for i in range(feats.count)):
                    continue
        except Exception:
            continue
        grid = readGrid(entity)
        if not grid:
            continue
        comp = ownerComponent(entity)
        # Find the occurrence(s) that reference this component.
        occs = design.rootComponent.allOccurrencesByComponent(comp)
        if occs.count == 0:
            # Component lives directly in root (non-hybrid design).
            results.append((None, grid))
        else:
            for i in range(occs.count):
                results.append((occs.item(i), grid))
    return results


def ownerComponent(entity) -> adsk.fusion.Component:
    """Component of a tagged entity (component itself or a feature's parent)."""
    comp = adsk.fusion.Component.cast(entity)
    if comp:
        return comp
    return entity.parentComponent


def _occurrenceTransform(occ: adsk.fusion.Occurrence) -> adsk.core.Matrix3D:
    """World transform of an occurrence, or identity for a root-level plate."""
    if occ is None:
        return adsk.core.Matrix3D.create()
    return occ.transform2  # full world transform incl. parent chain


def gridTransform(grid: GridInfo, occ: adsk.fusion.Occurrence) -> adsk.core.Matrix3D:
    """Grid local space -> world: plate placement, then occurrence transform."""
    m = grid.placementMatrix() if grid is not None else adsk.core.Matrix3D.create()
    if occ is not None:
        m.transformBy(occ.transform2)
    return m


def worldToLocal(occ: adsk.fusion.Occurrence, worldPoint: adsk.core.Point3D, grid: GridInfo = None) -> adsk.core.Point3D:
    """Map a world point into the baseplate's local grid space."""
    m = gridTransform(grid, occ)
    inv = m.copy()
    inv.invert()
    p = worldPoint.copy()
    p.transformBy(inv)
    return p


def localToWorld(occ: adsk.fusion.Occurrence, localPoint: adsk.core.Point3D, grid: GridInfo = None) -> adsk.core.Point3D:
    """Map a local grid-space point into world space."""
    m = gridTransform(grid, occ)
    p = localPoint.copy()
    p.transformBy(m)
    return p


def snapCell(grid: GridInfo, occ: adsk.fusion.Occurrence, worldPoint: adsk.core.Point3D,
             binCols: int = 1, binRows: int = 1):
    """Snap a world click to the nearest valid cell for a binCols x binRows bin.

    Returns (col, row, worldOrigin) where worldOrigin is the world-space corner
    the bin's local origin should be placed at. Clamps so the bin stays fully
    on the plate. Returns None if the point is outside a reasonable margin.
    """
    local = worldToLocal(occ, worldPoint, grid)
    # Nearest cell index by rounding to pitch.
    col = int(round((local.x - grid.originX) / grid.pitchX))
    row = int(round((local.y - grid.originY) / grid.pitchY))
    # Clamp so the whole bin footprint stays on the grid.
    col = max(0, min(col, grid.cols - binCols))
    row = max(0, min(row, grid.rows - binRows))
    worldOrigin = localToWorld(occ, grid.cellLocalOrigin(col, row), grid)
    return col, row, worldOrigin


def findNearestBaseplate(design: adsk.fusion.Design, worldPoint: adsk.core.Point3D):
    """Pick the tagged baseplate whose grid is closest to a world point.

    Returns (occurrence, GridInfo) or None. Distance is measured to the grid's
    local-space center after mapping the point into each plate's frame, so
    baseplates placed anywhere in the assembly resolve correctly.
    """
    best = None
    bestDist = None
    for occ, grid in findBaseplates(design):
        local = worldToLocal(occ, worldPoint, grid)
        cx = grid.originX + grid.cols * grid.pitchX / 2
        cy = grid.originY + grid.rows * grid.pitchY / 2
        dist = ((local.x - cx) ** 2 + (local.y - cy) ** 2) ** 0.5
        if bestDist is None or dist < bestDist:
            bestDist = dist
            best = (occ, grid)
    return best
