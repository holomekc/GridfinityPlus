"""Drawer 'Picked slots': a click adds / removes a slot, the same click
reported twice (mouseClick + cabinet selection) toggles only once."""
import sys, os, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.commands.commandCreateDrawer import entry as D
from GridfinityPlus.lib.gridfinityUtils import cabinetLayout as L

fails = 0


def expect(name, got, want):
    global fails
    if got != want:
        fails += 1
        print('FAIL', name, got, 'expected', want)


mode = {'v': D.FILL_PICK}
D.form.readOne = lambda inp: mode['v']
inputs = types.SimpleNamespace(itemById=lambda i: object())
D._picked, D._toggledClick = [], None


def click(col, row, twice=True):
    D._lastClick = object()                   # a new click
    for _ in range(2 if twice else 1):        # mouseClick + selection report the same click
        D._togglePick(inputs, col, row)


click(1, 1); click(2, 1); click(1, 2)
expect('three picked', D._picked, [(1, 1), (2, 1), (1, 2)])
click(2, 1)
expect('second click removes', D._picked, [(1, 1), (1, 2)])
cab = L.cabinet(dict(L.CABINET_DEFAULTS, columns=2, rows=3))
p = dict(L.INSERT_DEFAULTS, column=1, row=1, span=1)
expect('slots = picked', D._slots(inputs, cab, p), [(1, 1), (1, 2)])
D._picked.clear()
expect('nothing picked -> current slot', D._slots(inputs, cab, p), [(1, 1)])
mode['v'] = D.FILL_ONE
click(2, 2)
expect('other modes do not pick', D._picked, [])
print('DONE fails', fails)
