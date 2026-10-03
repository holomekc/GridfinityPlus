"""Scratch build context for parametric geometry generation.

The generators build real (parametric) features and then copy the result into
a TemporaryBRep. Normally that happens in a throw-away child component. Part
Design documents (DesignIntent = Part) only allow ONE component, so there we
fall back to building directly in the root component and remember which bodies
already existed, so they are never touched or picked up by the generators.
"""
import adsk.core, adsk.fusion

# Bodies that existed in the scratch component before the build started.
# Only non-empty when the root component is used as scratch (Part Design).
_preexisting: list = []
_scratchIsRoot = False


def canAddComponents(des: adsk.fusion.Design) -> bool:
    try:
        intent = des.designIntent
    except Exception:
        return True
    partIntent = getattr(adsk.fusion.DesignIntentTypes, 'PartDesignIntentType', None)
    return partIntent is None or intent != partIntent


def createScratchComponent(des: adsk.fusion.Design) -> adsk.fusion.Component:
    """Return a component to build scratch geometry in (origin = world origin).

    All features created in it must be removed afterwards via the usual
    timeline-group cleanup; call release() after that.
    """
    global _preexisting, _scratchIsRoot
    root = adsk.fusion.Component.cast(des.rootComponent)
    if canAddComponents(des):
        try:
            occ = adsk.fusion.Occurrences.cast(root.occurrences).addNewComponent(adsk.core.Matrix3D.create())
            _preexisting = []
            _scratchIsRoot = False
            return occ.component
        except RuntimeError:
            pass  # e.g. Part Design document -> fall back to root
    _preexisting = [root.bRepBodies.item(i) for i in range(root.bRepBodies.count)]
    _scratchIsRoot = True
    return root


def release():
    global _preexisting, _scratchIsRoot
    _preexisting = []
    _scratchIsRoot = False


def _isPreexisting(body) -> bool:
    for b in _preexisting:
        try:
            if b == body:
                return True
        except Exception:
            pass
    return False


def ownBodies(component: adsk.fusion.Component) -> list:
    """Bodies in `component` created by the current scratch build."""
    bodies = [component.bRepBodies.item(i) for i in range(component.bRepBodies.count)]
    if not _scratchIsRoot or not _preexisting:
        return bodies
    return [b for b in bodies if not _isPreexisting(b)]
