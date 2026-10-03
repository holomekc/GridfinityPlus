"""Viewport click -> point on a plane of some local frame."""

import adsk.core


def hitLocalPlane(args: adsk.core.MouseEventArgs, localToWorld: adsk.core.Matrix3D, axis: int, value: float = 0.0):
    """Ray from the camera eye through the clicked point, mapped into the
    local frame and intersected with the plane local[axis] == value
    (axis 0/1/2 = x/y/z). Returns (x, y, z) local, or None."""
    vp = args.viewport
    if vp is None:
        return None
    modelPt = vp.viewToModelSpace(args.viewportPosition)
    inv = localToWorld.copy()
    inv.invert()
    eye = vp.camera.eye.copy()
    eye.transformBy(inv)
    pt = modelPt.copy()
    pt.transformBy(inv)
    e = eye.asArray()
    d = eye.vectorTo(pt).asArray()
    if abs(d[axis]) < 1e-9:
        return None
    t = (value - e[axis]) / d[axis]
    return tuple(e[i] + t * d[i] for i in range(3))
