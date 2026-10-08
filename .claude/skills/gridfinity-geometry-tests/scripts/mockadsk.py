"""Minimal adsk mock: CSG point-membership kernel for TemporaryBRepManager."""
import os, sys, types, math

def _sub(a, b): return [a[i]-b[i] for i in range(3)]
def _dot(a, b): return sum(a[i]*b[i] for i in range(3))
def _cross(a, b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
def _norm(a):
    l = math.sqrt(_dot(a, a)); return [v/l for v in a]

class Point3D:
    def __init__(s, x, y, z): s.x, s.y, s.z = x, y, z
    @staticmethod
    def create(x=0, y=0, z=0): return Point3D(x, y, z)
    def copy(s): return Point3D(s.x, s.y, s.z)
    def asArray(s): return [s.x, s.y, s.z]
    def transformBy(s, m):
        s.x, s.y, s.z = m.apply([s.x, s.y, s.z])
    def vectorTo(s, o): return Vector3D(o.x-s.x, o.y-s.y, o.z-s.z)

class Vector3D(Point3D):
    @staticmethod
    def create(x=0, y=0, z=0): return Vector3D(x, y, z)
    def normalize(s):
        l = math.sqrt(s.x**2+s.y**2+s.z**2); s.x, s.y, s.z = s.x/l, s.y/l, s.z/l
    def crossProduct(s, o): return Vector3D(*_cross(s.asArray(), o.asArray()))

class Matrix3D:
    def __init__(s): s.m = [[1 if i == j else 0 for j in range(4)] for i in range(4)]
    @staticmethod
    def create(): return Matrix3D()
    def copy(s):
        c = Matrix3D(); c.m = [r[:] for r in s.m]; return c
    @property
    def translation(s): return Vector3D(s.m[0][3], s.m[1][3], s.m[2][3])
    @translation.setter
    def translation(s, v): s.m[0][3], s.m[1][3], s.m[2][3] = v.x, v.y, v.z
    def apply(s, p):
        return [sum(s.m[i][j]*p[j] for j in range(3)) + s.m[i][3] for i in range(3)]
    def transformBy(s, o):  # s = o * s
        s.m = [[sum(o.m[i][k]*s.m[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
    def invert(s):
        import numpy as np
        s.m = np.linalg.inv(np.array(s.m)).tolist(); return True
    def setToRotation(s, ang, axis, origin):
        c, sn = math.cos(ang), math.sin(ang)
        assert abs(axis.z - 1) < 1e-9
        s.m = [[c, -sn, 0, 0], [sn, c, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    def asArray(s): return [v for r in s.m for v in r]
    def setWithArray(s, a): s.m = [list(a[i*4:i*4+4]) for i in range(4)]

class OrientedBoundingBox3D:
    @staticmethod
    def create(c, l, w, L, W, H):
        assert L > 0 and W > 0 and H > 0, ('invalid argument box', L, W, H)
        o = OrientedBoundingBox3D(); o.c = c.asArray(); o.l = _norm(l.asArray()); o.w = _norm(w.asArray())
        o.h = _norm(_cross(o.l, o.w)); o.size = (L, W, H); return o

class Faces:
    count = 1
class Body:
    def __init__(s, f): s.f = f; s.faces = Faces()
    def contains(s, p): return s.f(p)

class BooleanTypes:
    UnionBooleanType, DifferenceBooleanType, IntersectionBooleanType = 0, 1, 2

class TBM:
    def createBox(s, o):
        def f(p):
            d = _sub(p, o.c)
            return all(abs(_dot(d, ax)) <= sz/2 + 1e-12 for ax, sz in ((o.l, o.size[0]), (o.w, o.size[1]), (o.h, o.size[2])))
        return Body(f)
    def createCylinderOrCone(s, p1, r1, p2, r2):
        a, b = p1.asArray(), p2.asArray(); ax = _sub(b, a); L2 = _dot(ax, ax)
        def f(p):
            t = _dot(_sub(p, a), ax) / L2
            if t < 0 or t > 1: return False
            q = [a[i] + t*ax[i] for i in range(3)]
            r = r1 + (r2 - r1)*t
            return _dot(_sub(p, q), _sub(p, q)) <= r*r
        return Body(f)
    def createSphere(s, center, r):
        c = center.asArray()
        return Body(lambda p: _dot(_sub(p, c), _sub(p, c)) <= r * r)
    def createTorus(s, center, axis, R, r):
        c = center.asArray(); a = _norm(axis.asArray())
        def f(p):
            d = _sub(p, c); h = _dot(d, a)
            radial = [d[i] - h * a[i] for i in range(3)]
            q = math.sqrt(_dot(radial, radial)) - R
            return q * q + h * h <= r * r
        return Body(f)
    def booleanOperation(s, target, tool, kind):
        f, g = target.f, tool.f
        target.f = {0: lambda p: f(p) or g(p), 1: lambda p: f(p) and not g(p), 2: lambda p: f(p) and g(p)}[kind]
        return True
    def copy(s, b): return Body(b.f)
    def transform(s, b, m):
        inv = m.copy(); inv.invert(); f = b.f
        b.f = lambda p: f(inv.apply(p))
        return True
_tbm = TBM()

def install():
    adsk = types.ModuleType('adsk'); core = types.ModuleType('adsk.core'); fusion = types.ModuleType('adsk.fusion')
    adsk.core, adsk.fusion = core, fusion
    for n in ('Point3D', 'Vector3D', 'Matrix3D', 'OrientedBoundingBox3D'):
        setattr(core, n, globals()[n])
    class _Any:
        def __init__(s, *a, **k): pass
        def __getattr__(s, n): return _Any()
        def __call__(s, *a, **k): return _Any()
    for n in ('Application', 'ValueInput', 'Base', 'CommandInputs', 'CommandInput', 'MouseEventArgs', 'Event'):
        setattr(core, n, _Any())
    fusion.TemporaryBRepManager = types.SimpleNamespace(get=lambda: _tbm)
    fusion.BooleanTypes = BooleanTypes
    fusion.CustomFeatureEventHandler = object
    for n in ('Design', 'Component', 'BRepBody', 'BRepBodies', 'CustomFeature', 'Occurrence', 'BRepFaces', 'BRepEdge',
              'BRepFace', 'Sketch', 'SketchLine', 'SketchCurves', 'FeatureOperations', 'ExtentDirections',
              'BaseFeature', 'CustomFeatureEventArgs', 'CustomFeatureDefinition', 'DesignTypes', 'TriangleMeshQualityOptions',
              'CustomGraphicsCoordinates', 'CustomGraphicsSolidColorEffect', 'Features', 'ExtrudeFeatures', 'FilletFeatures',
              'ChamferFeatures', 'ConstructionPlaneInput', 'Sketches', 'SketchDimensions', 'GeometricConstraints', 'SketchLines',
              'DimensionOrientations', 'PatternDistanceType', 'SurfaceExtendTypes', 'RectangularPatternFeatures', 'DesignIntentTypes'):
        setattr(fusion, n, _Any())
    core.__getattr__ = lambda n: _Any()
    fusion.__getattr__ = lambda n: _Any()
    sys.modules.update({'adsk': adsk, 'adsk.core': core, 'adsk.fusion': fusion})


def quietLog(root):
    """Send gplog output to a temp file instead of the real gridfinityplus.log."""
    import tempfile, importlib
    sys.path.insert(0, root)
    gplog = importlib.import_module('GridfinityPlus.lib.gridfinityUtils.gplog')
    gplog.LOG_PATH = os.path.join(tempfile.gettempdir(), 'gridfinityplus-mock.log')
