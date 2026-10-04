"""Click picking for placement: the front-most baseplate / cabinet top whose
outline the view ray hits wins (clicking a cabinet's top stacks onto it)."""
import sys, os, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
import adsk.core
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import binFeature as B, gridRegistry as R

fails = 0


def expect(name, got, want):
    global fails
    if got != want:
        fails += 1
        print('FAIL', name, got, 'expected', want)


def grid(z, cols=2, rows=2, pad=None):
    g = types.SimpleNamespace(pitchX=4.2, pitchY=4.2, cols=cols, rows=rows, originX=0.0, originY=0.0,
                              padding=pad or {}, partial={}, z=z)
    return g


# Baseplate at z = 0 (0..8.4), cabinet top at z = 10 over cells 0..1 x 0..1.
plates = {'plate': grid(0.0, 6, 6), 'cab top': grid(10.0, 2, 2)}
B.resolvePlate = lambda des, token: (None, plates[token], None)


def transform(g, occ):
    m = adsk.core.Matrix3D.create()
    m.translation = adsk.core.Vector3D.create(0, 0, g.z)
    return m


R.gridTransform = transform
choices = {'<none>': (None, None), 'plate': ('plate', None), 'cab top': ('cab top', None)}


def click(eye, target):
    vp = types.SimpleNamespace(viewToModelSpace=lambda p: adsk.core.Point3D.create(*target),
                               camera=types.SimpleNamespace(eye=adsk.core.Point3D.create(*eye)))
    return types.SimpleNamespace(viewport=vp, viewportPosition=None)


pick = B.plateAtClick(None, click((3, 3, 50), (3, 3, 0)), choices)
expect('over the cabinet -> cabinet top', pick and pick[0], 'cab top')
expect('cell on the top', pick and (int(pick[3][0] // 4.2), int(pick[3][1] // 4.2)), (0, 0))
pick = B.plateAtClick(None, click((20, 20, 50), (20, 20, 0)), choices)
expect('beside the cabinet -> plate', pick and pick[0], 'plate')
pick = B.plateAtClick(None, click((100, 100, 50), (100, 100, 0)), choices)
expect('off everything -> None', pick, None)
pick = B.plateAtClick(None, click((3, 3, 5), (3, 3, 0)), choices)
expect('eye below the cabinet top -> plate', pick and pick[0], 'plate')
print('DONE fails', fails)
