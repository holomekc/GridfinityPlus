import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import cabinetGeometry as G, cabinetLayout as L
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _box

G._getFoot = lambda des, b, l, cl, *a: _box(0.05, b - 2 * cl - 0.05, 0.05, l - 2 * cl - 0.05, -0.5, 0.0)
fails = 0
def check(name, body, p, expect):
    global fails
    if body.contains(list(p)) != expect:
        fails += 1
        print('FAIL', name, [round(v, 3) for v in p], 'expected', expect)

cp = dict(L.CABINET_DEFAULTS, unitsW=3, unitsL=3, rows=1, heightUnits=14)
cab = L.cabinet(cp)
ip = dict(L.INSERT_DEFAULTS, interior=L.INTERIOR_SPOOLS, spoolCount=3, spoolDiameter=5.0, spoolWidth=2.1,
          spoolBore=1.0, spoolPlay=0.05, spoolDivider=0.25, spoolEnd=0.5, handle=L.HANDLE_PULL, axleSplit=L.AXLE_ONE_PIECE)
sp = L.insert(cab, ip)['spools']
assert not sp['errors'], sp['errors']
posts = sp['posts']
gaps = [round(posts[i + 1][0] - posts[i][1], 4) for i in range(len(posts) - 1)]
widths = [round(b - a, 4) for a, b in posts]
print('gaps between cradles', gaps, 'cradle widths', widths)
assert all(abs(g - (2.1 + 2 * 0.05)) < 1e-9 for g in gaps)
assert widths == [0.5, 0.25, 0.25, 0.5]
for c, (a, b) in zip(sp['centers'], zip(posts, posts[1:])):
    assert abs(c - (a[1] + b[0]) / 2) < 1e-9

# snap-in: lips over the axle, opening narrower than the axle
snap = dict(ip, spoolMount=L.MOUNT_SNAP)
spS = L.insert(cab, snap)['spools']
drawer, axle = G.buildInsertParts(None, cp, snap)
r = spS['axleD'] / 2
xm = sum(spS['posts'][1]) / 2
check('snap lip above axle', drawer, (xm, spS['yA'] + r - 0.01, spS['zA'] + r * 0.8), True)
check('snap opening', drawer, (xm, spS['yA'], spS['zA'] + r + 0.05), False)
check('snap seat', drawer, (xm, spS['yA'], spS['zA']), False)
openD = G.buildInsertParts(None, cp, ip)[0]
spO = L.insert(cab, ip)['spools']
check('open: no lip', openD, (xm, spO['yA'] + r - 0.01, spO['zA'] + r * 0.8), False)

# outlet heights
ins = L.insert(cab, ip)
for pos, off in ((L.HOLE_BOTTOM, 0), (L.HOLE_MIDDLE, 0), (L.HOLE_TOP, 0), (L.HOLE_MIDDLE, 0.5), (L.HOLE_TOP, 5.0)):
    s2 = L.insert(cab, dict(ip, spoolHolePos=pos, spoolHoleOffset=off))['spools']
    print(pos, off, '-> outlet z above floor', round((s2['holeZ'] - s2['floorZ']) * 10, 1), 'mm')
    assert s2['floorZ'] < s2['holeZ'] < ins['z1']
    d = G.buildInsertParts(None, cp, dict(ip, spoolHolePos=pos, spoolHoleOffset=off))[0]
    check(f'outlet {pos} {off}', d, (s2['centers'][0], ins['y0'] + 0.05, s2['holeZ']), False)
mid = L.insert(cab, dict(ip, spoolHolePos=L.HOLE_MIDDLE))['spools']
assert abs(mid['holeZ'] - mid['zA']) < 1e-9

# label without handle: Auto -> centre; positions + offsets stay on the front
fr = (0.0, 10.0, 0.0, 4.0)
base = dict(L.INSERT_DEFAULTS, handle=L.HANDLE_NONE, label=L.LABEL_RECESS, labelWidth=4.0, labelHeight=1.2)
rect, band, blocked = G.frontLayout(base, *fr)
print('no handle auto', [round(v, 2) for v in rect])
assert abs((rect[0] + rect[1]) / 2 - 5.0) < 1e-9 and abs((rect[2] + rect[3]) / 2 - 2.0) < 1e-9
for pos in L.LABEL_POSITIONS[1:]:
    rect, band, _ = G.frontLayout(dict(base, labelPos=pos), *fr)
    print(pos, [round(v, 2) for v in rect])
    assert 0 <= rect[0] < rect[1] <= 10 and 0 <= rect[2] < rect[3] <= 4
rl, _, _ = G.frontLayout(dict(base, labelPos=L.LABEL_LEFT), *fr)
rr, _, _ = G.frontLayout(dict(base, labelPos=L.LABEL_RIGHT), *fr)
assert rl[1] <= 5.0 and rr[0] >= 5.0
ro, _, _ = G.frontLayout(dict(base, labelOffsetX=1.0, labelOffsetZ=-0.3), *fr)
assert abs(ro[0] - (3.0 + 1.0)) < 1e-9 and abs(ro[2] - (1.4 - 0.3)) < 1e-9, ro
rc, _, _ = G.frontLayout(dict(base, labelOffsetX=50.0), *fr)
assert rc[1] <= 10.0, rc
# with a handle Auto still picks below / beside
withH = dict(base, handle=L.HANDLE_RECESS)
rh, bandH, _ = G.frontLayout(withH, 0.0, 10.0, 0.0, 6.0)
assert rh[3] < bandH[2], (rh, bandH)
# thin dividers / end supports down to one line
thin = L.insert(cab, dict(ip, spoolDivider=0.04, spoolEnd=0.04))['spools']
assert [round(b - a, 4) for a, b in thin['posts']] == [0.04] * 4, thin['posts']
# own outlet diameter for spool drawers
h = dict(ip, spoolHoleDiameter=0.2, wireDiameter=0.8)
sh = L.insert(cab, h)['spools']
assert abs(sh['wireD'] - 0.2) < 1e-9
dh = G.buildInsertParts(None, cp, h)[0]
y0 = L.insert(cab, h)['y0']
check('outlet 2 mm open', dh, (sh['centers'][0] + 0.09, y0 + 0.12, sh['holeZ']), False)
check('outlet 2 mm, wall beside', dh, (sh['centers'][0] + 0.15, y0 + 0.12, sh['holeZ']), True)
# preview / model: spools only with the option
ghost = G.buildInsert(None, cp, ip)
check('no spools without option', ghost, (sp['centers'][0], sp['yA'], sp['zA'] + sp['D'] / 2 - 0.1), False)
ghost = G.buildInsert(None, cp, dict(ip, showSpools=True))
check('spools with option', ghost, (sp['centers'][0], sp['yA'], sp['zA'] + sp['D'] / 2 - 0.1), True)
# axle end play + collar thickness
e = dict(ip, axleEndPlay=0.15, axleCollar=0.3)
se = L.insert(cab, e)['spools']
_, ax = G.buildInsertParts(None, cp, e)
pa = se['posts'][0][0]
rcol = se['axleD'] / 2 + 0.25
check('collar 3 mm thick', ax, (pa - 0.15 - 0.29, se['yA'], se['zA'] + rcol - 0.05), True)
check('end play 1.5 mm free', ax, (pa - 0.1, se['yA'], se['zA'] + rcol - 0.05), False)
assert abs(se['axleX'][0] - (pa - 0.15 - 0.3)) < 1e-9
# The floor fillet is a real Fusion fillet (scratch component): not in the
# mock. Here only: without a design it is skipped and the footprints are known.
sp_f = L.insert(cab, dict(ip, spoolFillet=0.2))['spools']
G.buildInsertParts(None, cp, dict(ip, spoolFillet=0.2))
# 3 x 3 grid without handle: corners at the edges
g = {}
for pos in L.LABEL_POSITIONS[1:]:
    g[pos] = G.frontLayout(dict(base, labelPos=pos), *fr)[0]
m = G.LABEL_MARGIN
assert abs(g[L.LABEL_TOP_LEFT][0] - m) < 1e-9 and abs(g[L.LABEL_TOP_LEFT][3] - (4 - m)) < 1e-9, g[L.LABEL_TOP_LEFT]
assert abs(g[L.LABEL_BOTTOM_RIGHT][1] - (10 - m)) < 1e-9 and abs(g[L.LABEL_BOTTOM_RIGHT][2] - m) < 1e-9
assert abs(g[L.LABEL_TOP][0] - 3.0) < 1e-9 and abs(g[L.LABEL_CENTER][2] - 1.4) < 1e-9
assert g[L.LABEL_LEFT][0] == g[L.LABEL_TOP_LEFT][0] and g[L.LABEL_RIGHT][1] == g[L.LABEL_TOP_RIGHT][1]
# legacy names map onto the grid
assert L.withDefaults({'labelPos': 'Below handle'}, L.INSERT_DEFAULTS)['labelPos'] == L.LABEL_BOTTOM
assert L.withDefaults({'labelPos': 'Left'}, L.INSERT_DEFAULTS)['labelPos'] == L.LABEL_LEFT
# explicit positions are kept, whatever the handle (only true collisions move)
for h in L.HANDLE_TYPES:
    for pos in (L.LABEL_LEFT, L.LABEL_CENTER, L.LABEL_RIGHT):
        r, _, _ = G.frontLayout(dict(L.INSERT_DEFAULTS, handle=h, labelPos=pos), 0, 10, 0, 6)
        assert r is not None and r[2] > 1.0 and r[3] < 5.0, (h, pos, r)     # middle row stays middle
    r, _, _ = G.frontLayout(dict(L.INSERT_DEFAULTS, handle=h, labelPos=L.LABEL_TOP_LEFT), 0, 10, 0, 6)
    assert r[3] > 5.0, (h, 'top left', r)                                    # top stays top
notchC, _, _ = G.frontLayout(dict(L.INSERT_DEFAULTS, handle=L.HANDLE_NOTCH, labelPos=L.LABEL_CENTER), 0, 10, 0, 6)
nd = float(L.INSERT_DEFAULTS['handleHeight'])
assert notchC[3] <= 6 - nd - 0.1 + 1e-9, ('center label under the notch', notchC)
print('DONE fails', fails)
