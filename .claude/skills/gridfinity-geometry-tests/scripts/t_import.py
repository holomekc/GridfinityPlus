import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
# Folder that CONTAINS the GridfinityPlus package (scripts -> skill -> skills -> .claude -> add-in -> parent).
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
import importlib
for m in ('GridfinityPlus.lib.ui.paramForm', 'GridfinityPlus.lib.gridfinityUtils.viewRay',
          'GridfinityPlus.lib.gridfinityUtils.boxSystemFeature',
          'GridfinityPlus.commands.commandCreateCabinet.entry', 'GridfinityPlus.commands.commandCreateDrawer.entry',
          'GridfinityPlus.commands'):
    importlib.import_module(m); print('ok', m)
