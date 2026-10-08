import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
# Folder that CONTAINS the GridfinityPlus package (scripts -> skill -> skills -> .claude -> add-in -> parent).
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import cabinetGeometry as G, cabinetLayout as L
from GridfinityPlus.lib.gridfinityUtils.baseplateFastPreview import _box


def fakeFoot(des, b, l, cl, *a):
    return _box(0.05, b - 2 * cl - 0.05, 0.05, l - 2 * cl - 0.05, -0.5, 0.0)


def fakeCell(des, b, l, cl):
    return _box(-2 * cl + 0.3, b - 0.3, -2 * cl + 0.3, l - 0.3, -0.5, 0.0)


G._getFoot = fakeFoot
G._getCellCutout = fakeCell

fails = 0
CAB0 = dict(L.CABINET_DEFAULTS, wall=0.2, backWall=0.2, floor=0.2, top=0.2, divider=0.2)
INS0 = dict(L.INSERT_DEFAULTS, floor=0.16, front=0.25)


def check(name, body, p, expect):
    global fails
    got = body.contains(list(p))
    if got != expect:
        fails += 1
        print('FAIL', name, p, 'expected', expect, 'got', got)


def frange(a, b, s):
    v = a
    while v <= b + 1e-9:
        yield v
        v += s


def collisions(cab, ins, cabBody, insBody, shift=0.0):
    hits = []
    zs = list(frange(ins['z0'] - 0.3 + 0.0013, ins['z1'] + 0.1, 0.025))
    for x0, x1 in cab['columns']:
        for xs in (list(frange(x0 - 0.35 + 0.0011, x0 + 0.45, 0.025)), list(frange(x1 - 0.45 + 0.0011, x1 + 0.35, 0.025))):
            for x in xs:
                for y in frange(0.3 - shift, ins['y1'] - 0.1 - shift, 0.37):
                    for z in zs:
                        p = [x, y, z]
                        if insBody.contains(p) and cabBody.contains(p):
                            hits.append(tuple(round(v, 3) for v in p))
                            if len(hits) > 5:
                                return hits
    return hits


t0 = time.time()
# ---------------- ledge cabinet
cp = dict(CAB0)
cab = L.cabinet(cp)
body = G.buildCabinet(None, cp)
r2 = cab['rows'][1]['bottom']
check('interior empty', body, (4, 6, 1.0), False)
check('side wall', body, (0.1, 6, 1.0), True)
check('back wall', body, (4, 12.45, 1.0), True)
check('ledge flat', body, (0.35, 6, r2 - 0.05), True)
check('ledge under chamfer outer', body, (0.45, 6, r2 - 0.25), False)
check('ledge chamfer root', body, (0.25, 6, r2 - 0.25), True)
check('right ledge under chamfer', body, (cab['columns'][0][1] - 0.25, 6, r2 - 0.25), False)
check('right ledge root', body, (cab['columns'][0][1] - 0.05, 6, r2 - 0.25), True)
check('no ledge in middle', body, (4, 6, r2 - 0.05), False)
check('bump ledge', body, (0.375, 0.6, r2 + 0.02), True)
check('no bump behind', body, (0.375, 2.0, r2 + 0.04), False)
check('bump floor', body, (0.375, 0.6, 0.2 + 0.02), True)
check('top pocket', body, (2.075, 2.1, cab['zTop'] - 0.2), False)
check('top roof', body, (2.075, 2.1, cab['ceil'] + 0.1), True)
check('foot', body, (2.0, 2.0, -0.2), True)
check('between feet empty', body, (4.175, 2.0, -0.2), False)

for row in (1, 2, 3):
    for typ in L.INSERT_TYPES:
        ip = dict(INS0, row=row, insertType=typ)
        ins = L.insert(cab, ip)
        ib = G.buildInsert(None, cp, ip)
        h = collisions(cab, ins, body, ib)
        if h:
            fails += 1
            print('FAIL collision ledge', row, typ, h)
        ibp = G.buildInsert(None, cp, dict(ip, pullOut=3.0))
        h = collisions(cab, ins, body, ibp, 3.0)
        if h:
            fails += 1
            print('FAIL collision ledge pulled', row, typ, h)

ip = dict(INS0, row=2, frontStyle=L.FRONT_OVERLAY, handle=L.HANDLE_NONE, label=L.LABEL_NONE, stop=L.STOP_HARD)
ins = L.insert(cab, ip)
ib = G.buildInsert(None, cp, ip)
z0 = ins['z0']
check('drawer floor', ib, (4, 6, z0 + 0.08), True)
check('drawer pocket', ib, (4, 6, z0 + 1.0), False)
check('drawer side', ib, (0.3, 6, z0 + 1.0), True)
check('drawer back', ib, (4, 12.3, z0 + 1.0), True)
check('panel', ib, (4, -0.1, z0 + 1.0), True)
check('panel over ledge zone', ib, (4, -0.1, ins['panel']['z1'] - 0.05), True)
check('nothing above tray', ib, (4, 6, ins['z1'] + 0.05), False)
check('notch', ib, (0.375, 0.6, z0 + 0.03), False)
check('land front', ib, (0.375, 0.3, z0 + 0.03), True)
check('ridge', ib, (0.375, 0.75, z0 + 0.03), True)
check('channel', ib, (0.375, 3.0, z0 + 0.03), False)
check('stop land', ib, (0.375, ins['y1'] - 0.2, z0 + 0.03), True)
check('support beside channel', ib, (0.29, 3.0, z0 + 0.03), True)

# flush default drawer: recessed pull + sticker recess
ip = dict(INS0, row=2)
ins = L.insert(cab, ip); ib = G.buildInsert(None, cp, ip)
z0, z1 = ins['z0'], ins['z1']
xc = (ins['x0'] + ins['x1']) / 2
check('flush front wall', ib, (1.0, 0.1, z0 + 1.0), True)
check('nothing in front of cabinet', ib, (1.0, -0.05, z0 + 1.0), False)
check('not wider than column', ib, (ins['colX0'] - 0.01, 3.0, z0 + 1.0), False)
rect, band, _ = G.frontLayout(ins['p'], ins['x0'], ins['x1'], z0, z1)
check('auto label left of handle', None, None, None) if False else None
print('flush layout label', [round(v, 3) for v in rect], 'band', [round(v, 3) for v in band])
check('sticker recess', ib, ((rect[0] + rect[1]) / 2, 0.01, (rect[2] + rect[3]) / 2), False)
check('front behind recess', ib, ((rect[0] + rect[1]) / 2, 0.1, (rect[2] + rect[3]) / 2), True)
assert rect[1] < xc - 2.0, ('label not beside handle', rect)
bz0, bz1 = band[2], band[3]
h = max(0.6, min(1.6, bz1 - bz0 - 0.4)); zc = (bz0 + bz1) / 2
zt = min(zc + h / 2, z1 - 0.25 - 0.25); zb = max(zt - h, bz0 + 0.1)
print('recess zb zt', round(zb, 3), round(zt, 3), 'z1', round(z1, 3))
check('recess opening', ib, (xc, 0.1, (zb + zt) / 2), False)
check('recess hook space', ib, (xc, 0.9, zt + 0.5), False)
check('recess lip', ib, (xc, 0.05, zt + 0.15), True)
check('recess housing roof', ib, (xc, 0.9, zt + 0.9 + 0.1), True if zt + 1.0 < z1 else False)
check('recess housing side', ib, (xc + 2.0 + 0.06, 0.9, (zb + zt) / 2), True)
check('recess housing back', ib, (xc, 1.5 + 0.06, (zb + zt) / 2), True)
check('recess pocket floor', ib, (xc, 0.8, zb - 0.05), True)

for hd in L.HANDLE_TYPES:
    for fs in L.FRONT_STYLES:
        for lb in L.LABEL_TYPES:
            G.buildInsert(None, cp, dict(INS0, row=2, handle=hd, frontStyle=fs, label=lb, wireHoles=2))
for row in (1, 2, 3):
    for hd in (L.HANDLE_RECESS, L.HANDLE_PULL):
        ip = dict(INS0, row=row, handle=hd, label=L.LABEL_CARD, wireHoles=1)
        ins = L.insert(cab, ip); ib = G.buildInsert(None, cp, ip)
        hh = collisions(cab, ins, body, ib)
        if hh:
            fails += 1; print('FAIL collision flush', row, hd, hh)

# card holder
ip = dict(INS0, row=2, label=L.LABEL_CARD, handle=L.HANDLE_NONE, labelPos=L.LABEL_BOTTOM)
ins = L.insert(cab, ip); ib = G.buildInsert(None, cp, ip)
rect, band, _ = G.frontLayout(ins['p'], ins['x0'], ins['x1'], ins['z0'], ins['z1'])
lx = (rect[0] + rect[1]) / 2; lz = (rect[2] + rect[3]) / 2
check('card slot', ib, (lx, -0.03, lz), False)
check('card window', ib, (lx, -0.11, lz), False)
check('card flange', ib, (rect[0] + 0.05, -0.11, lz), True)
check('card frame bottom', ib, (lx, -0.11, rect[2] - 0.1), True)
check('card slot open top', ib, (lx, -0.03, rect[3] + 0.05), False)

# protruding handles stay inside the front height
def frontBounds(name, b, ins, zTopFront):
    global fails
    for x in frange(ins['x0'] + 0.05, ins['x1'] - 0.05, 0.2):
        for y in frange(-3.0, -0.01, 0.1):
            for z in list(frange(ins['z0'] - 1.0, ins['z0'] - 0.005, 0.05)) + list(frange(zTopFront + 0.005, zTopFront + 1.0, 0.05)):
                if b.contains([x, y, z]):
                    fails += 1; print('FAIL', name, 'outside front height', (round(x, 2), round(y, 2), round(z, 2))); return
PULLS = {'thin lip': dict(pullGrip=0.3, pullBar=0.12, pullTop=0.12, pullSides=0.0, handleDepth=0.5),
         'hook': dict(pullGrip=1.6, pullBar=0.35, pullTop=0.3, pullSides=0.0),
         'D': dict(pullGrip=1.6, pullBar=0.35, pullTop=0.3, pullSides=0.5),
         'scoop thick': dict(pullGrip=0.5, pullBar=0.4, pullTop=0.3, pullSides=0.4)}
for fs in L.FRONT_STYLES:
    for row in (1, 2):
        cfgs = [(L.HANDLE_PULL, k, v) for k, v in PULLS.items()] + [(L.HANDLE_LEDGE, 'ledge', {})]
        cfgs += [(L.HANDLE_KNOB, ks + '/' + su, dict(knobStyle=ks, knobSupport=su)) for ks in L.KNOB_STYLES for su in L.KNOB_SUPPORTS]
        for hd, nm, extra in cfgs:
            ip = dict(INS0, row=row, handle=hd, frontStyle=fs, **dict(dict(handleDepth=2.0), **extra))
            ins = L.insert(cab, ip); b = G.buildInsert(None, cp, ip)
            ftop = ins['panel']['z1'] if ins['panel'] else ins['z1']
            frontBounds('%s %s r%d' % (fs, nm, row), b, ins, ftop)

def pullAt(cfg):
    ip = dict(INS0, row=2, handle=L.HANDLE_PULL, label=L.LABEL_NONE, **cfg)
    ins = L.insert(cab, ip); return ins, G.buildInsert(None, cp, ip)
ins, b = pullAt(PULLS['thin lip'])
z1 = ins['z1']
check('thin lip top', b, (xc, -0.3, z1 - 0.1 - 0.05), True)
check('thin lip hollow', b, (xc, -0.2, z1 - 0.1 - 0.25), False)
check('thin lip bar', b, (xc, -0.45, z1 - 0.1 - 0.25), True)
check('thin lip nothing below', b, (xc, -0.3, z1 - 1.0), False)
ins, b = pullAt(PULLS['scoop thick'])
zc = (ins['z0'] + ins['z1']) / 2
check('scoop thick side wall', b, (xc - 2.0 + 0.3, -0.2, ins['z1'] - 0.5), True)
check('scoop thick hollow', b, (xc, -0.3, ins['z1'] - 0.5), False)
ins, b = pullAt(PULLS['hook'])
check('hook open side', b, (xc + 1.95, -0.4, ins['z1'] - 0.5), False)
# grooved ledge: defined by groove + rim
ip = dict(INS0, row=2, handle=L.HANDLE_LEDGE, label=L.LABEL_NONE, fingerGrooveWidth=0.8, fingerGrooveDepth=0.3, ledgeRim=0.2)
ins = L.insert(cab, ip); b = G.buildInsert(None, cp, ip)
zt = ins['z1'] - 0.1   # Top aligned
yc = -0.2 - 0.4
check('ledge groove center', b, (xc, yc, zt - 0.25), False)
check('ledge below groove', b, (xc, yc, zt - 0.3 - 0.08), True)
check('ledge outer rim', b, (xc, -1.2 + 0.1, zt - 0.05), True)
check('ledge inner rim', b, (xc, -0.1, zt - 0.05), True)
check('ledge beyond protrusion', b, (xc, -1.25, zt - 0.05), False)
check('ledge closed underside', b, (xc, -0.3, zt - 0.6), True)
check('ledge 45 below', b, (xc, -1.1, zt - 0.6), False)
ls = L.ledgeSize(ip, 5.0)
assert abs(ls['angle'] - 45) < 0.01, ls
steep = dict(ip, ledgeHeight=2.5)
ins = L.insert(cab, steep); b = G.buildInsert(None, cp, steep)
check('steep ledge reaches lower (capped to the front height)', b, (xc, -0.3, zt - 1.2), True)
print('steep angle', round(L.ledgeSize(steep, 5.0)['angle'], 1))
flat = dict(ip, ledgeHeight=0.9)
ins = L.insert(cab, flat); b = G.buildInsert(None, cp, flat)
check('flat ledge ends higher', b, (xc, -0.3, zt - 1.0), False)
check('flat ledge keeps material under groove', b, (xc, yc, zt - 0.3 - 0.05), True)
tooLow = L.ledgeSize(dict(ip, ledgeHeight=0.3), 5.0)
assert tooLow['raised'] and abs(tooLow['H'] - tooLow['hMin']) < 1e-9, tooLow
print('flat angle', round(L.ledgeSize(flat, 5.0)['angle'], 1), 'min height', round(tooLow['H'] * 10, 1), 'mm')
ipd = dict(ip, fingerGrooveWidth=0.6, fingerGrooveDepth=0.8)
ins = L.insert(cab, ipd); b = G.buildInsert(None, cp, ipd)
check('deep U groove', b, (xc, -0.5, zt - 0.6), False)
# knobs: supports
for ks in L.KNOB_STYLES:
    for su in L.KNOB_SUPPORTS:
        ip = dict(INS0, row=2, handle=L.HANDLE_KNOB, knobStyle=ks, knobSupport=su, label=L.LABEL_NONE, handleWidth=1.6)
        ins = L.insert(cab, ip); b = G.buildInsert(None, cp, ip)
        kz = (ins['z0'] + ins['z1']) / 2
        yk = -1.2
        base = b.contains([xc, yk, ins['z0'] + 0.02])
        wide = b.contains([xc + 0.5, yk, ins['z0'] + 0.02])
        expect = {L.KNOB_SUPPORT_STAND: (True, True), L.KNOB_SUPPORT_THIN: (True, False), L.KNOB_SUPPORT_NONE: (False, False)}[su]
        if (base, wide) != expect:
            fails += 1; print('FAIL knob support', ks, su, (base, wide), 'expected', expect)
        if su == L.KNOB_SUPPORT_THIN and b.contains([xc, -0.02, ins['z0'] + 0.02]):
            fails += 1; print('FAIL fin touches front', ks)
        check(ks + '/' + su + ' cap top', b, (xc, yk, kz + 0.75), True)
ip = dict(INS0, row=2, handle=L.HANDLE_KNOB, knobStyle=L.KNOB_SPOOL, label=L.LABEL_NONE, handleWidth=1.6)
ins = L.insert(cab, ip); b = G.buildInsert(None, cp, ip)
kz = (ins['z0'] + ins['z1']) / 2
check('spool groove', b, (xc, -0.75, kz + 0.78), False)
# legacy handle values map onto the pull handle presets
lp = L.withDefaults({'handle': 'Bar handle'}, L.INSERT_DEFAULTS)
assert lp['handle'] == L.HANDLE_PULL and lp['pullSides'] == 0.5, lp
# finger hole narrower than high (crashed in Fusion)
G.buildInsert(None, cp, dict(INS0, row=2, handle=L.HANDLE_SLOT, handleWidth=1.0))
# detent height + thin floor rib
cpd = dict(CAB0, detentHeight=0.1)
cabd = L.cabinet(cpd); bd = G.buildCabinet(None, cpd)
check('higher bump', bd, (0.375, 0.6, cabd['rows'][1]['bottom'] + 0.09), True)
ipd = dict(L.INSERT_DEFAULTS, row=2)
insd = L.insert(cabd, ipd); ibd = G.buildInsert(None, cpd, ipd)
print('detent 1mm: insert height', round(insd['z1'] - insd['z0'], 3), 'vs', round(L.insert(cab, ipd)['z1'] - L.insert(cab, ipd)['z0'], 3))
check('thin floor channel', ibd, (0.375, 3.0, insd['z0'] + 0.05), False)
check('thin floor rib', ibd, (0.375, 3.0, insd['z0'] + 0.12 + 0.1), True)
hh = collisions(cabd, insd, bd, ibd)
if hh:
    fails += 1; print('FAIL collision detent 1mm', hh)

# wire outlets beside the recessed pull
ip = dict(INS0, row=2, wireHoles=2, label=L.LABEL_NONE)
ins = L.insert(cab, ip); ib = G.buildInsert(None, cp, ip)
xr = ((xc + 2.0 + 0.12 + 0.55) + (ins['x1'] - 0.55)) / 2
check('wire hole right', ib, (xr, 0.1, (ins['z0'] + ins['z1']) / 2), False)

# blank cover
ip = dict(INS0, row=2, insertType=L.INSERT_BLANK, handle=L.HANDLE_NOTCH)
ins = L.insert(cab, ip); ib = G.buildInsert(None, cp, ip)
check('blank short', ib, (4, 1.5, ins['z0'] + 0.05), False)
check('blank frame floor', ib, (4, 1.0, ins['z0'] + 0.05), True)
hh = collisions(cab, ins, body, ib)
if hh:
    fails += 1; print('FAIL collision blank', hh)

# ---------------- groove cabinet, 2 columns, 6 rows
gp = dict(CAB0, guide=L.GUIDE_GROOVE, rows=6, columns=2, unitsW=4, heightUnits=14)
gcab = L.cabinet(gp)
gbody = G.buildCabinet(None, gp)
x0 = gcab['columns'][0][0]
gc = L.grooveCenter(gcab['rows'][0])
check('groove void', gbody, (x0 - 0.1, 6, gc), False)
check('groove tip', gbody, (x0 - 0.19, 6, gc), False)
check('groove flank solid', gbody, (x0 - 0.19, 6, gc + 0.1), True)
check('groove open near face', gbody, (x0 - 0.05, 6, gc + 0.17), False)
check('wall beyond groove', gbody, (x0 - 0.05, 6, gc + 0.3), True)
xd = gcab['columns'][0][1]
check('divider groove', gbody, (xd + 0.1, 6, gc), False)
check('divider core', gbody, (xd + gcab['divider'] / 2, 6, gc), True)
for col in (1, 2):
    for row, span in ((1, 1), (3, 2), (6, 1)):
        ip = dict(INS0, column=col, row=row, span=span)
        ins = L.insert(gcab, ip)
        ib = G.buildInsert(None, gp, ip)
        h = collisions(gcab, ins, gbody, ib)
        if h:
            fails += 1
            print('FAIL collision groove', col, row, span, h)
        ibp = G.buildInsert(None, gp, dict(ip, pullOut=3.0))
        h = collisions(gcab, ins, gbody, ibp, 3.0)
        if h:
            fails += 1
            print('FAIL collision groove pulled', col, row, span, h)
ip = dict(INS0, column=1, row=1)
ins = L.insert(gcab, ip)
ib = G.buildInsert(None, gp, ip)
check('runner in groove', ib, (x0 - 0.05, 6, gc), True)
check('runner clear of flank', ib, (x0 - 0.05, 6, gc + 0.19), False)

# no feet, flat top, grid interior in a wide cabinet
fp = dict(CAB0, feet=False, topType=L.TOP_FLAT, unitsW=3, unitsL=3, rows=2)
fcab = L.cabinet(fp)
fbody = G.buildCabinet(None, fp)
check('flat bottom', fbody, (2.0, 2.0, -0.45), True)
check('flat top solid', fbody, (2.075, 2.1, fcab['zTop'] - 0.1), True)
ipg = dict(INS0, interior=L.INTERIOR_GRID)
ins = L.insert(fcab, ipg)
b = G.buildInsert(None, fp, ipg)
print('grid cells', L.gridCells(ins['x1'] - ins['x0'] - 0.24, ins['y1'] - 0.12, 4.2, 4.2, 0.025))
check('grid raster solid at edge', b, (ins['x0'] + 0.2, 1.0, ins['z0'] + 0.16 + 0.25), True)
h = collisions(fcab, ins, fbody, b)
if h:
    fails += 1
    print('FAIL collision flat', h)


# ---------------- overhang: partial cell left (1.0), padding front (0.5)
op = dict(CAB0, columns=2, unitsW=3,
          ovh={'left': 1.0, 'right': 0.0, 'front': 0.5, 'back': 0.0,
               'partial': {'left': True, 'right': False, 'front': False, 'back': False}})
ocab = L.cabinet(op); obody = G.buildCabinet(None, op)
check('ovh left wall', obody, (-0.9, 6, 1.0), True)
check('ovh left interior', obody, (-0.7, 6, 1.0), False)
check('ovh front open', obody, (2.0, -0.45, 1.0), False)
check('ovh front side wall', obody, (-0.9, 0.0, 1.0), True)
check('partial foot', obody, (-0.5, 2.0, -0.2), True)
check('partial foot clipped', obody, (-1.5, 2.0, -0.2), False)
check('ovh bump at new front', obody, (ocab['columns'][0][0] + 0.175, -0.5 + 0.6, ocab['rows'][1]['bottom'] + 0.02), True)
for col in (1, 2):
    for row in (1, 2):
        ip = dict(INS0, column=col, row=row)
        ins = L.insert(ocab, ip); ib = G.buildInsert(None, op, ip)
        h = collisions(ocab, ins, obody, ib)
        if h:
            fails += 1; print('FAIL collision ovh', col, row, h)
ins = L.insert(ocab, dict(INS0, column=1, row=2, frontStyle=L.FRONT_OVERLAY))
ib = G.buildInsert(None, op, dict(INS0, column=1, row=2, frontStyle=L.FRONT_OVERLAY))
check('ovh panel in front', ib, (0.0, -0.6, ins['z0'] + 0.5), True)
check('ovh notch at new front', ib, (ocab['columns'][0][0] + 0.175, 0.1, ins['z0'] + 0.03), False)
print('ovh cols', ocab['columns'], 'front', ocab['front'], 'panel', ins['panel'])

op2 = dict(op, topType=L.TOP_GRID)
check('top partial pocket', G.buildCabinet(None, op2), (-0.8, 2.0, ocab['zTop'] - 0.2), False)
check('top partial flat', G.buildCabinet(None, dict(op2, topEdge=L.TOP_EDGE_FLAT)), (-0.8, 2.0, ocab['zTop'] - 0.2), True)
for pos in L.LABEL_POSITIONS:
    for hd in L.HANDLE_TYPES:
        G.buildInsert(None, cp, dict(INS0, row=2, labelPos=pos, handle=hd, label=L.LABEL_CARD, wireHoles=3))
tall = dict(CAB0, rows=1)
tins = L.insert(L.cabinet(tall), dict(INS0))
r2, b2, _ = G.frontLayout(tins['p'], tins['x0'], tins['x1'], tins['z0'], tins['z1'])
print('tall front auto: label', [round(v, 2) for v in r2], 'band', [round(v, 2) for v in b2])
real = dict(L.CABINET_DEFAULTS)
rcab = L.cabinet(real); rb = G.buildCabinet(None, real)
# Front corners as round as feet and top: the wall runs out into the rounding.
Rf = rcab['radius']
check('wall right behind the front rounding', rb, (0.06, Rf + 0.02, 1.0), True)
check('right wall right behind the front rounding', rb, (rcab['aW'] - 0.06, Rf + 0.02, 1.0), True)
check('front corner rounded like the feet', rb, (0.06, 0.02, 1.0), False)
check('ledge near the front', rb, (0.2, 0.3, rcab['rows'][1]['bottom'] - 0.05), True)
check('nothing in front of cabinet', rb, (0.2, -0.02, rcab['rows'][1]['bottom'] - 0.05), False)
check('back corner still rounded', rb, (0.02, rcab['aL'] - 0.02, 1.0), False)
print('errors default', cab['errors'], 'groove', gcab['errors'])
print('DONE fails=%d in %.1fs' % (fails, time.time() - t0))
