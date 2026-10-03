import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
# Folder that CONTAINS the GridfinityPlus package (scripts -> skill -> skills -> .claude -> add-in -> parent).
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
import adsk.core
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
REG = {}
class FI(Any):
    def __init__(s, iid='x'):
        object.__setattr__(s, 'id', iid)
        object.__setattr__(s, '_vals', {})
    def __getattr__(s, n):
        if n.startswith('add'):
            def make(*a, **k):
                iid = a[0] if a and isinstance(a[0], str) else 'anon'
                f = FI(iid); REG[iid] = f; return f
            return make
        if n == 'children':
            return s
        if n == 'itemById':
            return lambda i: REG.get(i)
        return s._vals.get(n, Any())
    def __setattr__(s, n, v):
        s._vals[n] = v
class Cmd(Any):
    def __getattr__(s, n):
        if n == 'commandInputs':
            return UIROOT
        return Any()
class Args(Any):
    def __getattr__(s, n):
        if n == 'command':
            return CMD
        return Any()
UIROOT = FI('root'); CMD = Cmd()
import types
for mod in (sys.modules['adsk.core'], sys.modules['adsk.fusion']):
    mod.__getattr__ = lambda n: Any()
sys.path.insert(0, ROOT)
from GridfinityPlus.commands.commandCreateBin import entry as E
from GridfinityPlus.lib.gridfinityUtils import gplog
gplog.LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mock.log')
E.app = Any(); E.ui = Any()
E.binFeature.listPlates = lambda des: []
E.initDefaultUiState()
for k in range(3):
    try:
        REG.clear(); E.command_created(Args())
        print('created', k, 'ok')
    except Exception:
        print('created', k, 'FAILED'); traceback.print_exc(limit=6)
    try:
        E.command_destroy(Any())
    except Exception:
        traceback.print_exc(limit=3)
