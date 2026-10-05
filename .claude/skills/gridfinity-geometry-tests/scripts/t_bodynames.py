"""Body roles: bodies of a multi-body feature (cabinet + top plate, drawer +
axles) are matched and named by their stored part role, never by the order
Fusion lists them in."""
import sys, os, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.lib.gridfinityUtils import boxSystemFeature as B

fails = 0


class Attrs:
    def __init__(s): s.d = {}
    def add(s, g, n, v): s.d[(g, n)] = types.SimpleNamespace(value=v)
    def itemByName(s, g, n): return s.d.get((g, n))


class Body:
    def __init__(s, name): s.name, s.attributes = name, Attrs()


class Bodies(list):
    count = property(len)
    def item(s, i): return s[i]


def expect(name, ok):
    global fails
    if not ok:
        fails += 1
        print('FAIL', name)


names = B._names('Cabinet 1x1x6', 2, ['top plate'])
main, plate = Body('Body1864'), Body('Cabinet 1x1x6')
B._setRole(main, 0); B._setRole(plate, 1)
# Fusion lists the plate first.
base = types.SimpleNamespace(bodies=Bodies([plate, main]))
B._nameBodies(base, names)
expect('main body named after the feature', main.name == 'Cabinet 1x1x6')
expect('plate named as part', plate.name == 'Cabinet 1x1x6 - top plate')
expect('roles read back', B._role(plate, 0) == 1 and B._role(main, 1) == 0)
old = Body('old')                     # body from before roles: falls back to its position
expect('fallback to position', B._role(old, 3) == 3)
print('DONE fails', fails)
