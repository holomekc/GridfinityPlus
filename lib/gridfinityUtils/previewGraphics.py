"""
GridfinityPlus — dialog preview via CustomGraphics.

Draws a temporary BRep as pure viewport graphics: zero timeline entries, zero
document bodies. To keep big plates smooth we tessellate the body ourselves at
LOW mesh quality and feed triangles to addMesh — addBRepBody would re-tessellate
hundreds of curved faces at render quality on every input change (the stutter).

One holder per command; show() on every preview (pass a params key so unchanged
inputs skip all work), clear() on destroy.
"""

import adsk.core, adsk.fusion

from . import gplog

_MESH_COLOR = (190, 190, 200, 255)


class PreviewGraphics:
    """Holds the dialog ghost. Fusion wipes custom graphics between preview
    events whenever inputs change (e.g. a selection), so the group can be gone
    even though our key still matches. We keep the last temp body and simply
    redraw it when that happens."""

    def __init__(self):
        self._group = None
        self._key = None
        self._body = None

    def _groupAlive(self) -> bool:
        if self._group is None:
            return False
        try:
            return bool(self._group.isValid)
        except Exception:
            return False

    def isCurrent(self, key) -> bool:
        """True if a body for this key is cached (no geometry rebuild needed)."""
        return key is not None and key == self._key and self._body is not None

    def setTransform(self, matrix: adsk.core.Matrix3D, component: adsk.fusion.Component = None) -> bool:
        """Move the ghost without rebuilding geometry. Redraws from the cached
        body if Fusion already deleted the graphics group."""
        if self._groupAlive():
            try:
                self._group.transform = matrix
                return True
            except Exception:
                gplog.logExc('PreviewGraphics.setTransform')
        if self._body is not None and component is not None:
            self._draw(component, self._body, matrix)
            return self._group is not None
        return False

    def show(self, component: adsk.fusion.Component, tempBody: adsk.fusion.BRepBody,
             key=None, transform=None):
        if key is not None and key == self._key and self._groupAlive():
            if transform is not None:
                self.setTransform(transform, component)
            else:
                gplog.log('PreviewGraphics: same key, skip redraw')
            return
        self.clear()
        self._key = key
        self._body = tempBody
        self._draw(component, tempBody, transform)

    def _draw(self, component, tempBody, transform):
        if self._groupAlive():
            try:
                self._group.deleteMe()
            except Exception:
                pass
        self._group = None
        try:
            with gplog.timed('PreviewGraphics.show'):
                group = component.customGraphicsGroups.add()
                try:
                    calc = tempBody.meshManager.createMeshCalculator()
                    calc.setQuality(adsk.fusion.TriangleMeshQualityOptions.NormalQualityTriangleMesh)
                    mesh = calc.calculate()
                    coords = adsk.fusion.CustomGraphicsCoordinates.create(mesh.nodeCoordinatesAsDouble)
                    gfxMesh = group.addMesh(coords, mesh.nodeIndices,
                                            mesh.normalVectorsAsDouble, mesh.nodeIndices)
                    color = adsk.core.Color.create(*_MESH_COLOR)
                    gfxMesh.color = adsk.fusion.CustomGraphicsSolidColorEffect.create(color)
                    gplog.log(f'PreviewGraphics: mesh tris={len(mesh.nodeIndices) // 3}')
                except Exception:
                    # Mesh path failed — fall back to direct BRep drawing.
                    gplog.logExc('PreviewGraphics mesh path, falling back to addBRepBody')
                    group.addBRepBody(tempBody)
                if transform is not None:
                    group.transform = transform
                self._group = group
        except Exception:
            self._group = None
            gplog.logExc('PreviewGraphics.show')

    def clear(self):
        if self._group is not None:
            try:
                self._group.deleteMe()
            except Exception:
                pass
            self._group = None
        self._key = None
        self._body = None
