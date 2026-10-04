import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
import adsk.core, adsk.fusion
from GridfinityPlus.lib.gridfinityUtils import cabinetGeometry as G, cabinetLayout as L
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _box

G._getFoot = lambda des, b, l, cl, *a: _box(0.05, b - 2 * cl - 0.05, 0.05, l - 2 * cl - 0.05, -0.5, 0.0)
tm = adsk.fusion.TemporaryBRepManager.get()
fails = 0

cp = dict(L.CABINET_DEFAULTS, unitsW=3, unitsL=3, rows=1, heightUnits=14)
cab = L.cabinet(cp)
ip = dict(L.INSERT_DEFAULTS, interior=L.INTERIOR_SPOOLS, spoolCount=2, spoolDiameter=5.0, spoolWidth=2.1,
          spoolBore=1.0, handle=L.HANDLE_PULL)
sp = L.insert(cab, ip)['spools']
for MODE in (L.AXLE_BAYONET, L.AXLE_BAYONET_SMOOTH):
    print('--', MODE)
    ip = dict(ip, axleSplit=MODE)
    sp = L.insert(cab, ip)['spools']
    parts = G.buildInsertParts(None, cp, ip)
    assert len(parts) == 3 and G.insertPartNames(ip) == ['axle A (peg)', 'axle B (socket)'], G.insertPartNames(ip)
    drawer, A, B = parts
    r, yA, zA = sp['axleD'] / 2, sp['yA'], sp['zA']
    xa, xb = sp['axleX']
    xm = (xa + xb) / 2
    pegLen = max(0.8, 2 * r)


    def moved(body, dx=0.0, quarter=False):
        b = tm.copy(body)
        m = adsk.core.Matrix3D.create()
        if quarter:   # +90 deg about the axle (x axis through yA, zA): +y -> +z
            m.setWithArray([1, 0, 0, 0,
                            0, 0, -1, yA + zA,
                            0, 1, 0, zA - yA,
                            0, 0, 0, 1])
        t = adsk.core.Matrix3D.create()
        t.translation = adsk.core.Vector3D.create(dx, 0, 0)
        m.transformBy(t)
        tm.transform(b, m)
        return b


    def touch(a, b, step=0.025):
        x = xm - 0.25 + 0.0011
        while x < xm + pegLen + 0.25:
            y = yA - r - 0.15 + 0.0013
            while y < yA + r + 0.15:
                z = zA - r - 0.15 + 0.0017
                while z < zA + r + 0.15:
                    if a.contains([x, y, z]) and b.contains([x, y, z]):
                        return (round(x, 3), round(y, 3), round(z, 3))
                    z += step
                y += step
            x += step
        return None


    def expect(name, got, want):
        global fails
        if (got is not None) != want:
            fails += 1
            print('FAIL', name, 'touch at' if got else 'no touch', got)
        else:
            print('ok  ', name)


    expect('inserted: halves do not touch', touch(A, B), False)
    expect('turned a quarter: halves do not touch', touch(moved(A, quarter=True), B), False)
    expect('turned: pulling apart is blocked (locked)', touch(moved(A, -0.08, quarter=True), B), True)
    expect('not turned: pulls out freely', touch(moved(A, -0.6), B), False)
    # each half has a collar, both print standing on it
    for name, half, x in (('A', A, xa + 0.05), ('B', B, xb - 0.05)):
        if not half.contains([x, yA, zA + r + 0.15]):
            fails += 1
            print('FAIL collar', name)
    lugLo = xm + pegLen - 0.1 - G.BAYONET_LUG_LEN
    rp = r * (0.5 if MODE == L.AXLE_BAYONET_SMOOTH else G.BAYONET_PEG)
    lugOut = (min(rp + (r - rp) * 0.5, r - G.BAYONET_SKIN - 0.02) if MODE == L.AXLE_BAYONET_SMOOTH else rp + (r - rp) * 0.7)
    if A.contains([lugLo + 0.005, yA + lugOut - 0.01, zA]):
        fails += 1
        print('FAIL lug underside not chamfered')
    # neither half touches the drawer (loose in the cradles)
    def touchAlong(a, b, step=0.05):
        x = xa + 0.0011
        while x < xb:
            y = yA - r - 0.3 + 0.0013
            while y < yA + r + 0.3:
                z = zA - r - 0.3 + 0.0017
                while z < zA + r + 0.3:
                    if a.contains([x, y, z]) and b.contains([x, y, z]):
                        return (round(x, 3), round(y, 3), round(z, 3))
                    z += step
                y += step
            x += step
        return None
    expect('half A loose in the drawer', touchAlong(A, drawer), False)
    expect('half B loose in the drawer', touchAlong(B, drawer), False)

    if MODE == L.AXLE_BAYONET_SMOOTH:
        # outside skin: no slot or groove opening anywhere around the joint
        hole = None
        for k in range(72):
            a = k * math.pi / 36
            for x in (xm + 0.02 + i * 0.05 for i in range(int(pegLen / 0.05))):
                pt = [x, yA + (r - 0.02) * math.cos(a), zA + (r - 0.02) * math.sin(a)]
                if not B.contains(pt):
                    hole = pt
        if hole:
            fails += 1
            print('FAIL smooth outside: opening at', [round(v, 3) for v in hole])
        else:
            print('ok   smooth outside')
# one-piece axle: one collar, the other end runs to the side wall
one = dict(ip, axleSplit=L.AXLE_ONE_PIECE)
so = L.insert(cab, one)['spools']
d1, ax1 = G.buildInsertParts(None, cp, one)
inner = L.insert(cab, one)
wallX = inner['x1'] - float(one['wall'])
check_end = ax1.contains([wallX - so['endPlay'] - 0.02, so['yA'], so['zA']]) and not ax1.contains([wallX - so['endPlay'] + 0.02, so['yA'], so['zA']])
print('one piece reaches the wall' if check_end else 'FAIL one piece end'); fails += 0 if check_end else 1
short = dict(one, axleEndLength=0.5)
ss = L.insert(cab, short)['spools']
_, ax2 = G.buildInsertParts(None, cp, short)
ok = ax2.contains([ss['posts'][-1][1] + 0.48, ss['yA'], ss['zA']]) and not ax2.contains([ss['posts'][-1][1] + 0.52, ss['yA'], ss['zA']])
print('end length 5 mm' if ok else 'FAIL end length'); fails += 0 if ok else 1
print('DONE fails', fails)
