import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import cabinetGeometry as G, cabinetLayout as L
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _box

G._getFoot = lambda des, b, l, cl, *a: _box(0.05, b - 2 * cl - 0.05, 0.05, l - 2 * cl - 0.05, -0.5, 0.0)

# Mock has no volumes: test overlap by sampling the last spool's bounding box.
_box_of_spool = {}
_spoolBody = G.spoolBody
def spoolBody(sp, xc):
    _box_of_spool['b'] = (xc - sp['Ws'] / 2, xc + sp['Ws'] / 2, sp['yA'] - sp['D'] / 2, sp['yA'] + sp['D'] / 2,
                          sp['zA'] - sp['D'] / 2, sp['zA'] + sp['D'] / 2)
    return _spoolBody(sp, xc)
G.spoolBody = spoolBody
def overlaps(a, b, step=0.07):
    x0, x1, y0, y1, z0, z1 = _box_of_spool['b']
    x = x0 + 0.0013
    while x < x1:
        y = y0 + 0.0011
        while y < y1:
            z = z0 + 0.0017
            while z < z1:
                if a.contains([x, y, z]) and b.contains([x, y, z]):
                    return True
                z += step
            y += step
        x += step
    return False
G._overlaps = overlaps

cp = dict(L.CABINET_DEFAULTS, unitsW=3, unitsL=3, rows=1, heightUnits=14)
base = dict(L.INSERT_DEFAULTS, interior=L.INTERIOR_SPOOLS, spoolCount=2, spoolDiameter=5.0,
            spoolWidth=2.5, spoolBore=1.0, handle=L.HANDLE_PULL, axleSplit=L.AXLE_ONE_PIECE)
ok = G.spoolProblems(None, cp, base)
print('fits:', ok)
assert ok == [], ok

# extra body only with showSpools
parts = G.buildInsertParts(None, cp, base)
assert len(parts) == 2 and G.insertPartNames(base) == ['axle']
shown = dict(base, showSpools=True)
parts = G.buildInsertParts(None, cp, shown)
assert len(parts) == 3 and G.insertPartNames(shown) == ['axle', G.SPOOL_PREVIEW_NAME]
sp = L.insert(L.cabinet(cp), shown)['spools']
assert parts[2].contains([sp['centers'][0], sp['yA'], sp['zA'] + sp['D'] / 2 - 0.1])
assert not parts[2].contains([sp['centers'][0], sp['yA'], sp['zA']])   # bore

# recessed pull in front of a centred spool in a short drawer
bad = dict(base, spoolCount=1, depth=6.0, spoolDiameter=4.0, handle=L.HANDLE_RECESS, spoolGuides=False)
probs = G.spoolProblems(None, cp, bad)
print('recess:', probs)
assert probs and 'recessed pull' in probs[0]

# spool too big -> layout error passed through
big = G.spoolProblems(None, cp, dict(base, spoolDiameter=12.0))
print('too big:', big)
assert big and 'too big' in big[0]
print('DONE fails 0')
