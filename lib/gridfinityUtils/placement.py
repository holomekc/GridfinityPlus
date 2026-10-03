"""
GridfinityPlus — baseplate placement (plane/face + anchor point).

A baseplate is always generated in its own LOCAL frame (upstream convention):
outer outline x in [-padL, trueW + padR], y in [-padB, trueL + padT],
top surface at z = 0, bottom at z = -(BIN_BASE_HEIGHT + extra bottom).

The plate matrix maps that local frame into the target component:

    plate = anchorOffset (+ bottom onto z=0) -> rotation about z -> frame

  * frame: coordinate system of the chosen plane/face, origin = anchor point.
    Stored in params['placementFrame'] (16 floats, component space).
  * anchor: 'Center' keeps the plate centred on the anchor point when rows /
    columns change; 'Corner' puts the outer min corner on it.

Params WITHOUT 'placementFrame' (plates created before this feature) keep the
legacy identity placement, so existing documents do not move.

All lengths in Fusion internal units (cm).
"""

import adsk.core, adsk.fusion
import math

from . import plateLayout

ANCHOR_CENTER = 'Center'
ANCHOR_CORNER = 'Corner'
ANCHOR_ORIGINAL = 'Original (unchanged)'

KEY_FRAME = 'placementFrame'
KEY_ANCHOR = 'anchorMode'
KEY_ROTATION = 'placementRotation'
KEY_CUSTOM_ANCHOR = 'customAnchor'
KEY_OFFSET_X = 'placementOffsetX'
KEY_OFFSET_Y = 'placementOffsetY'
KEY_OFFSET_Z = 'placementOffsetZ'

PLACEMENT_KEYS = (KEY_FRAME, KEY_ANCHOR, KEY_ROTATION, KEY_CUSTOM_ANCHOR,
                  KEY_OFFSET_X, KEY_OFFSET_Y, KEY_OFFSET_Z)

ROTATIONS = ('0', '90', '180', '270')


# ---------------------------------------------------------------- matrices

def matrixToList(m: adsk.core.Matrix3D) -> list:
    return [float(v) for v in m.asArray()]


def listToMatrix(values) -> adsk.core.Matrix3D:
    m = adsk.core.Matrix3D.create()
    m.setWithArray(list(values))
    return m


def hasPlacement(params: dict) -> bool:
    return bool(params.get(KEY_FRAME))


def geometryKey(params: dict) -> dict:
    """Params without placement keys (geometry caches stay valid on moves)."""
    return {k: v for k, v in params.items() if k not in PLACEMENT_KEYS}


# ----------------------------------------------------------- local extents

def localExtents(params: dict):
    """(x0, x1, y0, y1, zBottom) of the plate outline in its local frame."""
    return plateLayout.localExtents(params)


def plateMatrix(params: dict):
    """Local plate frame -> component space. None = legacy identity."""
    if not hasPlacement(params):
        return None
    x0, x1, y0, y1, zBottom = localExtents(params)
    if params.get(KEY_CUSTOM_ANCHOR, True) and params.get(KEY_ANCHOR, ANCHOR_CENTER) == ANCHOR_CORNER:
        ax, ay = x0, y0
    else:
        ax, ay = (x0 + x1) / 2, (y0 + y1) / 2

    m = adsk.core.Matrix3D.create()
    m.translation = adsk.core.Vector3D.create(-ax, -ay, -zBottom)

    rot = int(float(params.get(KEY_ROTATION, 0) or 0)) % 360
    if rot:
        r = adsk.core.Matrix3D.create()
        r.setToRotation(math.radians(rot), adsk.core.Vector3D.create(0, 0, 1),
                        adsk.core.Point3D.create(0, 0, 0))
        m.transformBy(r)

    # Offsets along the plane's own axes (X/Y in plane, Z along its normal).
    off = adsk.core.Matrix3D.create()
    off.translation = adsk.core.Vector3D.create(
        float(params.get(KEY_OFFSET_X, 0) or 0),
        float(params.get(KEY_OFFSET_Y, 0) or 0),
        float(params.get(KEY_OFFSET_Z, 0) or 0))
    m.transformBy(off)

    m.transformBy(listToMatrix(params[KEY_FRAME]))
    return m


def placedCopy(tempBody, params: dict):
    """Copy of a local-frame temp body moved to its placement (or as is)."""
    tmgr = adsk.fusion.TemporaryBRepManager.get()
    body = tmgr.copy(tempBody)
    m = plateMatrix(params)
    if m is not None:
        tmgr.transform(body, m)
    return body


# ------------------------------------------------------ frames from picks

def _upPrefersY() -> bool:
    try:
        app = adsk.core.Application.get()
        pref = app.preferences.generalPreferences.defaultModelingOrientation
        return pref == adsk.core.DefaultModelingOrientations.YUpModelingOrientation
    except Exception:
        return False


def defaultFrame() -> adsk.core.Matrix3D:
    """'Top' origin plane at (0,0,0): XY for Z-up, XZ (normal +Y) for Y-up."""
    m = adsk.core.Matrix3D.create()
    if _upPrefersY():
        m.setWithCoordinateSystem(
            adsk.core.Point3D.create(0, 0, 0),
            adsk.core.Vector3D.create(1, 0, 0),
            adsk.core.Vector3D.create(0, 0, -1),
            adsk.core.Vector3D.create(0, 1, 0))
    return m


def _frameParts(m: adsk.core.Matrix3D):
    origin, x, y, z = m.getAsCoordinateSystem()
    return origin, x, y, z


def _projectOntoPlane(p: adsk.core.Point3D, origin: adsk.core.Point3D, n: adsk.core.Vector3D):
    v = origin.vectorTo(p)
    d = v.dotProduct(n)
    q = p.copy()
    shift = n.copy()
    shift.scaleBy(-d)
    q.translateBy(shift)
    return q


def _inPlaneXAxis(n: adsk.core.Vector3D) -> adsk.core.Vector3D:
    """World X projected into the plane (world Y if X is the normal)."""
    for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        a = adsk.core.Vector3D.create(*axis)
        d = a.dotProduct(n)
        x = adsk.core.Vector3D.create(a.x - n.x * d, a.y - n.y * d, a.z - n.z * d)
        if x.length > 1e-6:
            x.normalize()
            return x
    return adsk.core.Vector3D.create(1, 0, 0)


def _pointOf(entity):
    """World point of a vertex / sketch point / construction point."""
    if entity is None:
        return None
    v = adsk.fusion.BRepVertex.cast(entity)
    if v:
        return v.geometry
    sp = adsk.fusion.SketchPoint.cast(entity)
    if sp:
        return sp.worldGeometry
    cp = adsk.fusion.ConstructionPoint.cast(entity)
    if cp:
        return cp.geometry
    return None


def _planeOf(entity):
    """(origin, normal, defaultAnchor) for a planar face / construction plane."""
    face = adsk.fusion.BRepFace.cast(entity)
    if face:
        plane = adsk.core.Plane.cast(face.geometry)
        if plane is None:
            raise ValueError('Selected face is not planar')
        ok, n = face.evaluator.getNormalAtPoint(face.pointOnFace)
        if not ok:
            n = plane.normal
        n.normalize()
        return plane.origin, n, face.centroid
    cpl = adsk.fusion.ConstructionPlane.cast(entity)
    if cpl:
        plane = cpl.geometry
        n = plane.normal.copy()
        n.normalize()
        # Construction planes have no "outside": point the normal to the
        # positive side of its dominant world axis (XZ plane -> +Y, ...).
        comps = (n.x, n.y, n.z)
        dominant = max(range(3), key=lambda i: abs(comps[i]))
        if comps[dominant] < 0:
            n.scaleBy(-1)
        anchor = _projectOntoPlane(adsk.core.Point3D.create(0, 0, 0), plane.origin, n)
        return plane.origin, n, anchor
    raise ValueError('Select a planar face or a construction plane')


def frameFromSelection(planeEntity=None, pointEntity=None, fallback: adsk.core.Matrix3D = None) -> adsk.core.Matrix3D:
    """World frame for the plate from optional plane + point picks.

    No plane picked -> plane/axes of `fallback` (default: top origin plane).
    No point picked -> face centroid / origin projected onto the plane /
    fallback origin.
    """
    if planeEntity is not None:
        planeOrigin, n, anchor = _planeOf(planeEntity)
        x = _inPlaneXAxis(n)
    else:
        base = fallback if fallback is not None else defaultFrame()
        anchor, x, _, n = _frameParts(base)
        planeOrigin = anchor
    p = _pointOf(pointEntity)
    if p is not None:
        anchor = _projectOntoPlane(p, planeOrigin, n)
    y = n.crossProduct(x)
    y.normalize()
    m = adsk.core.Matrix3D.create()
    m.setWithCoordinateSystem(anchor, x, y, n)
    return m


def worldToComponent(des: adsk.fusion.Design, component: adsk.fusion.Component,
                     worldMatrix: adsk.core.Matrix3D) -> adsk.core.Matrix3D:
    """Express a world-space frame in `component`'s space."""
    m = worldMatrix.copy()
    try:
        if component is None or component == des.rootComponent:
            return m
        occs = des.rootComponent.allOccurrencesByComponent(component)
        if occs.count > 0:
            inv = occs.item(0).transform2.copy()
            inv.invert()
            m.transformBy(inv)
    except Exception:
        pass
    return m


def componentToWorld(des: adsk.fusion.Design, component: adsk.fusion.Component,
                     localMatrix: adsk.core.Matrix3D) -> adsk.core.Matrix3D:
    m = localMatrix.copy()
    try:
        if component is None or component == des.rootComponent:
            return m
        occs = des.rootComponent.allOccurrencesByComponent(component)
        if occs.count > 0:
            m.transformBy(occs.item(0).transform2)
    except Exception:
        pass
    return m
