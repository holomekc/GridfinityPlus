"""Viewport click -> point on a plane of some local frame."""

import adsk.core


def hitLocalPlane(args: adsk.core.MouseEventArgs, localToWorld: adsk.core.Matrix3D, axis: int, value: float = 0.0):
    """Ray from the camera eye through the clicked point, mapped into the
    local frame and intersected with the plane local[axis] == value
    (axis 0/1/2 = x/y/z). Returns (x, y, z) local, or None."""
    hit = hitLocalPlaneT(args, localToWorld, axis, value)
    return hit[0] if hit else None


def clickRay(args: adsk.core.MouseEventArgs):
    """(eye, point) in model space for a click, to evaluate later with
    hitRayPlane (e.g. once a selection made by the same click is known)."""
    vp = args.viewport
    if vp is None:
        return None
    return vp.camera.eye.copy(), vp.viewToModelSpace(args.viewportPosition).copy()


def hitRayPlane(ray, localToWorld: adsk.core.Matrix3D, axis: int, value: float = 0.0):
    """hitLocalPlane for a stored clickRay."""
    if ray is None:
        return None
    hit = _hit(ray[0], ray[1], localToWorld, axis, value)
    return hit[0] if hit else None


def hitLocalPlaneT(args: adsk.core.MouseEventArgs, localToWorld: adsk.core.Matrix3D, axis: int, value: float = 0.0):
    """Like hitLocalPlane, but returns ((x, y, z) local, t) with t the ray
    parameter (comparable between frames: smaller = closer to the eye), or
    None when the plane is parallel or behind the eye."""
    vp = args.viewport
    if vp is None:
        return None
    return _hit(vp.camera.eye, vp.viewToModelSpace(args.viewportPosition), localToWorld, axis, value)


def _hit(eyeWorld, modelPt, localToWorld, axis, value):
    inv = localToWorld.copy()
    inv.invert()
    eye = eyeWorld.copy()
    eye.transformBy(inv)
    pt = modelPt.copy()
    pt.transformBy(inv)
    e = eye.asArray()
    d = eye.vectorTo(pt).asArray()
    if abs(d[axis]) < 1e-9:
        return None
    t = (value - e[axis]) / d[axis]
    if t <= 0:
        return None
    return tuple(e[i] + t * d[i] for i in range(3)), t
