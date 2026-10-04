import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import cabinetGeometry as G, cabinetLayout as L
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _box

G._getFoot = lambda des, b, l, cl, *a: _box(0.05, b - 2 * cl - 0.05, 0.05, l - 2 * cl - 0.05, -0.5, 0.0)
G._getCellCutout = lambda des, b, l, cl: _box(-2 * cl + 0.3, b - 0.3, -2 * cl + 0.3, l - 0.3, -0.5, 0.0)
fails = 0
def check(name, body, p, expect):
    global fails
    if body.contains(list(p)) != expect:
        fails += 1
        print('FAIL', name, [round(v, 3) for v in p], 'expected', expect)

def frange(a, b, st):
    v = a
    while v <= b + 1e-9:
        yield v
        v += st

cp = dict(L.CABINET_DEFAULTS, unitsW=3, unitsL=3, rows=1, heightUnits=14)
cab = L.cabinet(cp)
ip = dict(L.INSERT_DEFAULTS, interior=L.INTERIOR_SPOOLS, spoolCount=2, spoolDiameter=5.0,
          spoolWidth=2.5, spoolBore=1.0, handle=L.HANDLE_PULL, axleSplit=L.AXLE_ONE_PIECE)
ins = L.insert(cab, ip)
sp = ins['spools']
print('errors', ins['errors'], 'centers', [round(c, 2) for c in sp['centers']], 'zA', round(sp['zA'], 2))
assert not ins['errors'], ins['errors']
drawer, axle = G.buildInsertParts(None, cp, ip)
yA, zA, r = sp['yA'], sp['zA'], sp['axleD'] / 2
xa, xb = sp['posts'][0]
pm = (xa + xb) / 2
check('post below slot', drawer, (pm, yA, zA - r - 0.1), True)
check('slot empty', drawer, (pm, yA, zA), False)
check('slot open top', drawer, (pm, yA, zA + r + 0.05), False)
check('post wall beside slot', drawer, (pm, yA + r + 0.15, zA), True)
check('axle in slot', axle, (pm, yA, zA), True)
check('axle flat bottom', axle, (pm, yA, zA - r * 0.95), False)
x0 = sp['axleX'][0]
check('collar outside post', axle, (x0 + 0.1, yA, zA + r + 0.15), True)
for c in sp['centers']:
    check('spool space free', drawer, (c, yA - 1.5, zA + 1.0), False)
    check('front outlet', drawer, (c, ins['y0'] + 0.05, sp['holeZ']), False)
    check('guide post', drawer, (c + 0.37, sp['guideY'], sp['holeZ']), True)
    check('guide eyelet', drawer, (c, sp['guideY'], sp['holeZ']), False)
# axle must not touch the drawer anywhere (loose in the cradles)
touch = 0
for x in frange(sp['axleX'][0] + 0.0013, sp['axleX'][1], 0.05):
    for y in frange(yA - r - 0.3, yA + r + 0.3, 0.05):
        for z in frange(zA - r - 0.3, zA + r + 0.3, 0.05):
            if axle.contains([x, y, z]) and drawer.contains([x, y, z]):
                touch += 1
if touch:
    fails += 1
    print('FAIL axle intersects drawer at', touch, 'points')
# centred: same play front/back (no guides) and floor/top
ipc = dict(ip, spoolGuides=False)
insc = L.insert(cab, ipc); spc = insc['spools']
py0 = insc['y0'] + float(ipc['front']); py1 = insc['y1'] - float(ipc['wall'])
front, back = spc['yA'] - spc['D'] / 2 - py0, py1 - spc['yA'] - spc['D'] / 2
bottom, top = spc['zA'] - spc['D'] / 2 - spc['floorZ'], (insc['z1'] - 0.1) - spc['zA'] - spc['D'] / 2
print('play front/back', round(front * 10, 1), round(back * 10, 1), 'floor/top', round(bottom * 10, 1), round(top * 10, 1))
assert abs(front - back) < 1e-6 and abs(bottom - top) < 1e-6
# with guides: the eyelet post fits between the front and the spool at its height
import math
pyF = ins['y0'] + float(ip['front'])
postTop = sp['holeZ'] + sp['wireD'] / 2 + 0.3
r = sp['D'] / 2
dz = sp['zA'] - min(postTop, sp['zA'])
spoolAt = sp['yA'] - (math.sqrt(r * r - dz * dz) if dz < r else 0.0)
gy = sp['guideY']
assert gy - L.EYELET_DEPTH / 2 - pyF >= 0.1 - 1e-9, 'eyelet touches the front'
assert spoolAt - (gy + L.EYELET_DEPTH / 2) >= 0.1 - 1e-9, 'eyelet touches the spool'
# 90 mm spool, low eyelets: no extra depth needed (round spool is far back down there)
c90 = L.cabinet(dict(L.CABINET_DEFAULTS, unitsW=3, unitsL=3, rows=1, heightUnits=20))
low = L.insert(c90, dict(L.INSERT_DEFAULTS, interior=L.INTERIOR_SPOOLS, spoolDiameter=9.0, spoolGuides=True,
                         spoolHolePos=L.HOLE_BOTTOM, depth=9.9, column=1, row=1))
assert not low['spools']['errors'], low['spools']['errors']
# too big spool / too many spools are reported
big = L.insert(cab, dict(ip, spoolDiameter=9.0))
many = L.insert(cab, dict(ip, spoolCount=6))
print('big:', big['errors']); print('many:', many['errors'])
assert big['errors'] and many['errors']
# merged ghost still works
G.buildInsert(None, cp, ip)
print('DONE fails', fails)
