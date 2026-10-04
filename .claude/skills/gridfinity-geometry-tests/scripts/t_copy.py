"""Copy / paste settings: everything but the position is copied; a copy seeds
new features of that kind."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mockadsk; mockadsk.install()
ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), *(['..'] * 5)))
mockadsk.quietLog(ROOT)
sys.path.insert(0, ROOT)
from GridfinityPlus.commands import contextEdit as CE
from GridfinityPlus.lib.gridfinityUtils import boxSystemFeature as box, binFeature, baseplateFeature, placement
from GridfinityPlus.lib.gridfinityUtils import cabinetLayout as L

fails = 0


def expect(name, ok):
    global fails
    if not ok:
        fails += 1
        print('FAIL', name)


drawer = dict(L.INSERT_DEFAULTS, cabinetToken='T', column=2, row=3, span=1, pullOut=1.0, handle=L.HANDLE_NOTCH)
s = CE.settingsOf(box.INSERT.featureId, drawer)
expect('drawer: position not copied', not any(k in s for k in ('cabinetToken', 'column', 'row', 'span', 'pullOut')))
expect('drawer: settings copied', s['handle'] == L.HANDLE_NOTCH and 'interior' in s)
CE._seedCreate(box.INSERT.featureId, s)
expect('drawer: new drawers start with the copy', CE.createDrawer._lastParams['handle'] == L.HANDLE_NOTCH)

binP = {'plateToken': 'P', 'col': 1, 'row': 2, 'rotation': 90, 'ovh': {}, 'overhangFlags': {}, 'placed': [1],
        'binW': 2, 'geom': {'with_lip': {'value': True}}, 'compartmentsTable': []}
s = CE.settingsOf(binFeature.FEATURE_ID, binP)
expect('bin: position not copied', not any(k in s for k in ('plateToken', 'col', 'row', 'rotation', 'placed')))
expect('bin: geometry copied', 'geom' in s and 'compartmentsTable' in s)
CE._seedCreate(binFeature.FEATURE_ID, s)
expect('bin: create seed set', CE.createBin._createSeed is s)

plate = {placement.KEY_FRAME: [1], placement.KEY_OFFSET_X: 1.0, 'plateWidth': 13}
s = CE.settingsOf(baseplateFeature.FEATURE_ID, plate)
expect('baseplate: placement not copied', placement.KEY_FRAME not in s and placement.KEY_OFFSET_X not in s)
expect('baseplate: size copied', s.get('plateWidth') == 13)
print('DONE fails', fails)

# Bin rebuilt without its dialog: stored values stand in for the inputs.
from GridfinityPlus.commands.commandCreateBin import entry as BE
geom = {BE.BIN_TYPE_DROPDOWN_ID: {'id': BE.BIN_TYPE_DROPDOWN_ID, 'value': BE.BIN_TYPE_HOLLOW, 'type': 'dd'},
        BE.BIN_WIDTH_INPUT_ID: {'id': BE.BIN_WIDTH_INPUT_ID, 'value': 3, 'type': 'int'}}
rows = [{'x_input_1': {'value': 0}, 'y_input_1': {'value': 1}, 'w_input_1': {'value': 2},
         'l_input_1': {'value': 1}, 'd_input_1': {'value': 2.5}}]
si = BE._StoredInputs(geom, rows)
expect('stored dropdown', si.itemById(BE.BIN_TYPE_DROPDOWN_ID).selectedItem.name == BE.BIN_TYPE_HOLLOW)
expect('stored value', si.itemById(BE.BIN_WIDTH_INPUT_ID).value == 3)
t = si.itemById(BE.BIN_COMPARTMENTS_TABLE_ID)
expect('stored table rows', t.rowCount == 2)
expect('stored table cells', [t.getInputAtPosition(1, c).value for c in range(5)] == [0, 1, 2, 1, 2.5])
print('DONE fails', fails)
