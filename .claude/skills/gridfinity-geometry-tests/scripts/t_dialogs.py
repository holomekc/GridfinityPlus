"""Build every dialog (bin, cabinet, drawer, cover) against fake inputs that
reject what Fusion rejects: non-ASCII or duplicate input ids."""
import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)


class Any:
    def __init__(s, *a, **k): pass
    def __getattr__(s, n): return Any()
    def __call__(s, *a, **k): return Any()
    def __int__(s): return 1
    def __index__(s): return 0
    def __float__(s): return 1.0
    def __bool__(s): return False
    def __iter__(s): return iter([])
    def __len__(s): return 0
    def __getitem__(s, k): return Any()
    def __lt__(s, o): return False
    __gt__ = __le__ = __ge__ = __lt__
    def __eq__(s, o): return False
    def __hash__(s): return 1
    def __str__(s): return 'any'
    def __format__(s, spec): return 'any'
    def __add__(s, o): return Any()
    __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = __truediv__ = __rtruediv__ = __add__
    def __neg__(s): return Any()


for mod in (sys.modules['adsk.core'], sys.modules['adsk.fusion']):
    mod.__getattr__ = lambda n: Any()

REG = {}
PROBLEMS = []


class FI(Any):
    def __init__(s, iid='x'):
        object.__setattr__(s, 'id', iid)
        object.__setattr__(s, '_vals', {})

    def __getattr__(s, n):
        if n.startswith('add'):
            def make(*a, **k):
                iid = a[0] if a and isinstance(a[0], str) else None
                if iid is not None:
                    if not iid.isascii() or not iid.replace('_', '').isalnum():
                        PROBLEMS.append(f'invalid id {iid!r}')
                    if iid in REG:
                        PROBLEMS.append(f'duplicate id {iid!r}')
                f = FI(iid or 'anon')
                if iid:
                    REG[iid] = f
                return f
            return make
        if n == 'children':
            return s
        if n == 'itemById':
            return lambda i: REG.get(i)
        return s._vals.get(n, Any())

    def __setattr__(s, n, v):
        s._vals[n] = v


class Args(Any):
    def __getattr__(s, n):
        if n == 'command':
            return CMD
        return Any()


class Cmd(Any):
    def __getattr__(s, n):
        if n == 'commandInputs':
            return UIROOT
        return Any()


UIROOT, CMD = FI('root'), Cmd()

from GridfinityPlus.commands.commandCreateBin import entry as B
from GridfinityPlus.commands.commandCreateCabinet import entry as C
from GridfinityPlus.commands.commandCreateDrawer import entry as D
from GridfinityPlus.commands.commandCreateCover import entry as V
from GridfinityPlus.lib.gridfinityUtils import boxSystemFeature as box, cabinetLayout as L

for E in (B, C, D, V):
    E.app = Any(); E.ui = Any()
B.binFeature.listPlates = lambda des, **kw: []
C.binFeature.listPlates = lambda des, **kw: []
V.binFeature.listPlates = lambda des, **kw: []
box.listCabinets = lambda des: [('Cabinet', 'tok', Any())]
box.CABINET.readParams = lambda cf: dict(L.CABINET_DEFAULTS)
B.initDefaultUiState()
# Fake inputs hold no values: read them from the defaults instead.
from GridfinityPlus.lib.ui import paramForm
from GridfinityPlus.lib.gridfinityUtils import coverGeometry
_DEFAULTS = {**L.CABINET_DEFAULTS, **coverGeometry.COVER_DEFAULTS, **L.INSERT_DEFAULTS,
             D.IN_CABINET: 'Cabinet', D.IN_FILL: D.FILL_ONE}
paramForm.readOne = lambda inp: _DEFAULTS.get(getattr(inp, 'id', None))

for name, create in (('bin', B.command_created), ('cabinet', C._commandCreated),
                     ('drawer', D._commandCreated), ('cover', V._commandCreated)):
    REG.clear(); PROBLEMS.clear()
    try:
        create(Args())
    except Exception as err:
        # The mock cannot attach event handlers; anything before that matters.
        tb = traceback.extract_tb(err.__traceback__)
        if not any('add_handler' in (fr.line or '') for fr in tb):
            PROBLEMS.append('crash: ' + ''.join(traceback.format_exception_only(err)).strip())
    print(f'{name}: {len(REG)} inputs', 'OK' if not PROBLEMS else PROBLEMS)
    assert not PROBLEMS, (name, PROBLEMS)
print('DONE fails 0')
