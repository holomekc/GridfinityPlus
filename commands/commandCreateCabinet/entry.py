"""
GridfinityPlus — Gridfinity cabinet (box system housing).

A tall open-front box on Gridfinity feet with columns and rows for drawers /
boxes (see commandCreateDrawer). Optional Gridfinity grid on top: bins and
further cabinets snap onto it, so cabinets stack into a wall.

Placement works like a bin: pick a baseplate (or a cabinet top), column/row,
click a cell in the viewport, Ctrl+Click rotates. Double-click the timeline
node to edit; inserts and stacked cabinets follow automatically.
"""

import adsk.core, adsk.fusion, traceback
import json
import os

from ...lib import fusion360utils as futil
from ... import config
from ...lib.gridfinityUtils import binFeature
from ...lib.gridfinityUtils import boxSystemFeature as box
from ...lib.gridfinityUtils import cabinetLayout as L
from ...lib.gridfinityUtils import cabinetGeometry
from ...lib.gridfinityUtils import const
from ...lib.gridfinityUtils import gplog
from ...lib.gridfinityUtils import gridRegistry
from ...lib.gridfinityUtils import viewRay
from ...lib.gridfinityUtils.previewGraphics import PreviewGraphics
from ...lib.ui import paramForm as form

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdCabinet'
CMD_NAME = 'Gridfinity+ Cabinet'
CMD_Description = 'Create a stackable Gridfinity cabinet for drawers and boxes'
IS_PROMOTED = True
WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidCreatePanel'
COMMAND_BESIDE_ID = 'ScriptsManagerCommand'
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

# Placement inputs (not geometry params).
IN_PLATE = 'plate'
IN_COL = 'col'
IN_ROW = 'gridRow'
IN_ROTATION = 'rotation'
IN_ROTATE = 'rotateButton'
IN_RESULT = 'result'
RESULT_KEYS = ('Outside', 'Column inside', 'Rows (free height)', 'Back wall', 'Wall mount')
PLATE_NONE = '(free, no snapping)'
# 'Fill to edge' (bin-style overhang over plate border / partial cells).
OVERHANG_INPUTS = (('ovhLeft', 'left', 'Fill to edge: left'), ('ovhRight', 'right', 'Fill to edge: right'),
                   ('ovhFront', 'front', 'Fill to edge: front'), ('ovhBack', 'back', 'Fill to edge: back'))
HEIGHT_MODES = ('Units', 'Total height')

GEOMETRY_IDS = list(L.CABINET_DEFAULTS.keys())

local_handlers = []
_previewGraphics = PreviewGraphics()
_plateChoices = {}      # label -> (token, grid)
_editedFeature = None
_hiddenBodies = []
_lastParams = dict(L.CABINET_DEFAULTS)
_bodyCache = {}         # geometry key -> temp body (dialog session)


def getErrorMessage(text='An unknown error occurred'):
    return f"{text}:<br>{traceback.format_exc()}"


def start():
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if not cmd_def:
        cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)
        futil.add_handler(cmd_def.commandCreated, command_created)
        panel = ui.workspaces.itemById(WORKSPACE_ID).toolbarPanels.itemById(PANEL_ID)
        control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)
        control.isPromoted = IS_PROMOTED
    # This command doubles as the edit command of the cabinet feature.
    box.CABINET.register(CMD_ID, ICON_FOLDER)


def stop():
    panel = ui.workspaces.itemById(WORKSPACE_ID).toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.itemById(CMD_ID)
    if control:
        control.deleteMe()
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()


def _resolveEdited():
    try:
        for i in range(ui.activeSelections.count):
            cf = box.CABINET.fromSelection(ui.activeSelections.item(i).entity)
            if cf is not None:
                return cf
    except Exception:
        pass
    return None


def _setEditedVisibility(visible: bool):
    global _hiddenBodies
    if visible:
        for body in _hiddenBodies:
            try:
                body.isLightBulbOn = True
            except Exception:
                pass
        _hiddenBodies = []
        return
    _hiddenBodies = []
    if _editedFeature is None:
        return
    for body in box.CABINET.bodies(_editedFeature):
        if body.isLightBulbOn:
            body.isLightBulbOn = False
            _hiddenBodies.append(body)


def command_created(args: adsk.core.CommandCreatedEventArgs):
    try:
        _commandCreated(args)
    except Exception:
        gplog.logExc('cabinet command_created')
        ui.messageBox(getErrorMessage('Cabinet dialog failed'), CMD_NAME)


def _commandCreated(args: adsk.core.CommandCreatedEventArgs):
    global _editedFeature, _plateChoices
    _bodyCache.clear()
    args.command.setDialogInitialSize(380, 600)
    des = adsk.fusion.Design.cast(app.activeProduct)
    units = app.activeProduct.unitsManager.defaultLengthUnits

    _editedFeature = _resolveEdited()
    stored = box.CABINET.readParams(_editedFeature) if _editedFeature else None
    if stored:
        gplog.session(f'CABINET dialog EDIT "{_editedFeature.name}"')
        args.command.okButtonText = 'Update cabinet'
        p = L.withDefaults(stored, L.CABINET_DEFAULTS)
    else:
        _editedFeature = None
        gplog.session('CABINET dialog CREATE')
        p = dict(_lastParams)

    inputs = args.command.commandInputs

    # --- placement
    g = inputs.addGroupCommandInput('placementGroup', 'Placement').children
    plateDd = g.addDropDownCommandInput(IN_PLATE, 'Baseplate', adsk.core.DropDownStyles.TextListDropDownStyle)
    plateDd.tooltip = 'Baseplate or cabinet top to snap onto'
    _plateChoices = {PLATE_NONE: (None, None)}
    # Never offer the edited cabinet's own top as its baseplate, nor a
    # cabinet stacked on it (that would stack it on itself).
    blocked = [] if _editedFeature is None else [_editedFeature] + box.cabinetsAbove(des, _editedFeature)
    plates = [pl for pl in binFeature.listPlates(des) if pl[2].entity not in blocked]
    selected = None
    if stored:
        selected = next((lbl for lbl, _, grid in plates
                         if box.refersTo(des, p.get('plateToken'), grid.entity)), None)
        if selected is None:
            legacy = binFeature.matchPlateToken(des, p.get('plateToken'), plates)
            selected = next((lbl for lbl, t, _ in plates if t == legacy), None)
    elif plates:
        selected = plates[0][0]
    plateDd.listItems.add(PLATE_NONE, selected is None)
    for label, token, grid in plates:
        _plateChoices[label] = (token, grid)
        plateDd.listItems.add(label, label == selected)
    g.addIntegerSpinnerCommandInput(IN_COL, 'Column', 1, 999, 1, int(p.get('col', 0)) + 1)
    g.addIntegerSpinnerCommandInput(IN_ROW, 'Row', 1, 999, 1, int(p.get('row', 0)) + 1)
    rot = g.addDropDownCommandInput(IN_ROTATION, 'Rotation', adsk.core.DropDownStyles.TextListDropDownStyle)
    for r in ('0', '90', '180', '270'):
        rot.listItems.add(r, r == str(int(p.get('rotation', 0))))
    rotBtn = g.addBoolValueInput(IN_ROTATE, 'Rotate 90°', False, '', False)
    rotBtn.text = 'Rotate'
    modes = binFeature.extendModes(p.get('overhangFlags', {}))
    for inputId, side, label in OVERHANG_INPUTS:
        dd = g.addDropDownCommandInput(inputId, label, adsk.core.DropDownStyles.TextListDropDownStyle)
        for choice in binFeature.EXTEND_CHOICES:
            dd.listItems.add(choice, choice == modes[side])
        dd.tooltip = ('Grow the cabinet over the plate border / a partial cell on this side. '
                      'Auto: when the cabinet touches that plate edge.')
    g.addTextBoxCommandInput('placementHint', '', 'Click a cell to place, Ctrl+Click rotates.', 1, True)

    # --- size
    g = inputs.addGroupCommandInput('sizeGroup', 'Size').children
    form.integer(g, 'unitsW', 'Width (units)', p, 1, 20)
    form.integer(g, 'unitsL', 'Depth (units)', p, 1, 20)
    form.choice(g, 'heightMode', 'Height by', p, HEIGHT_MODES,
                'Units: Gridfinity height units (7 mm). Total height: any height in mm.')
    form.integer(g, 'heightUnits', 'Height (units)', p, 3, 200, 'Total height incl. feet and top grid')
    form.length(g, 'heightMm', 'Height', p, units, minimum=2.0, tooltip='Total height incl. feet and top grid')

    gridGroup = inputs.addGroupCommandInput('gridGroup', 'Grid unit')
    gridGroup.isExpanded = False
    g = gridGroup.children
    form.length(g, 'baseW', 'Base width', p, units, minimum=1.0)
    form.length(g, 'baseL', 'Base length', p, units, minimum=1.0)
    form.length(g, 'heightUnit', 'Height unit', p, units, minimum=0.1)
    form.length(g, 'cl', 'XY clearance', p, units, minimum=0.0, maximum=0.1)

    # --- layout
    g = inputs.addGroupCommandInput('layoutGroup', 'Compartments').children
    form.integer(g, 'columns', 'Columns', p, 1, 10, 'Side-by-side drawer columns (vertical dividers)')
    form.integer(g, 'rows', 'Rows', p, 1, 30, 'Equal rows (ignored when row weights are set)')
    form.text(g, 'rowWeights', 'Row weights', p,
              'Optional, e.g. "1,1,2": three rows, the top one twice as high. Empty = equal rows.')
    form.choice(g, 'guide', 'Guides', p, L.GUIDE_TYPES,
                'Ledges: inserts rest on shelf strips (simple, strong).\n'
                'Grooves: V-grooves in the walls, inserts carry runners; with many rows an insert can span several.')
    form.length(g, 'ledgeDepth', 'Ledge depth', p, units, minimum=0.15, maximum=1.0)
    form.length(g, 'ledgeThickness', 'Ledge thickness', p, units, minimum=0.08, maximum=0.5)
    form.length(g, 'grooveDepth', 'Groove depth', p, units, minimum=0.1, maximum=0.5)
    form.boolean(g, 'detent', 'Click detent', p,
                 'Small bump near the front: inserts click shut, with a stop they cannot fall out')
    form.length(g, 'detentHeight', 'Detent height', p, units, minimum=0.02, maximum=0.15,
                tooltip='How far the bump sticks up (default 0.6 mm). Higher = firmer click. '
                        'The insert height clearance grows with it.')

    # --- walls
    wallGroup = inputs.addGroupCommandInput('wallGroup', 'Walls')
    wallGroup.isExpanded = False
    g = wallGroup.children
    form.length(g, 'wall', 'Side walls', p, units, minimum=0.08, maximum=1.0)
    form.length(g, 'divider', 'Dividers', p, units, minimum=0.08, maximum=1.0)
    form.length(g, 'backWall', 'Back wall', p, units, minimum=0.08, maximum=1.0)
    form.length(g, 'floor', 'Floor', p, units, minimum=0.08, maximum=1.0)
    form.length(g, 'top', 'Top', p, units, minimum=0.08, maximum=1.0)

    fitGroup = inputs.addGroupCommandInput('fitGroup', 'Insert fit')
    fitGroup.isExpanded = False
    g = fitGroup.children
    form.length(g, 'fitLateral', 'Side clearance', p, units, minimum=0.0, maximum=0.3)
    form.length(g, 'fitVertical', 'Height clearance', p, units, minimum=0.0, maximum=0.5)
    form.length(g, 'fitBack', 'Back clearance', p, units, minimum=0.0, maximum=1.0)

    # --- bottom / top
    g = inputs.addGroupCommandInput('bottomGroup', 'Bottom').children
    form.boolean(g, 'feet', 'Gridfinity feet', p, 'Off: flat bottom (same total height)')
    form.boolean(g, 'magnets', 'Magnet holes', p)
    form.boolean(g, 'screws', 'Screw holes', p)

    g = inputs.addGroupCommandInput('topGroup', 'Top').children
    form.choice(g, 'topType', 'Top', p, L.TOP_TYPES,
                'Gridfinity grid: bins and further cabinets snap onto the top')
    form.choice(g, 'topEdge', 'Top over border', p, L.TOP_EDGE_TYPES,
                'Where the cabinet fills to the plate edge: repeat a partial cell as a cut '
                'pocket (like the baseplate), or keep it flat')

    mountGroup = inputs.addGroupCommandInput('mountGroup', 'Wall mount')
    mountGroup.isExpanded = bool(p['wallMount'])
    g = mountGroup.children
    form.boolean(g, 'wallMount', 'Screw holes', p,
                 'Screw holes in the back wall, screwed from the inside (pull the drawers out). '
                 'The back wall gets thick enough for the head to sit flush.')
    form.choice(g, 'mountScrew', 'Screw', p, L.MOUNT_SCREW_NAMES)
    form.choice(g, 'mountHead', 'Head', p, L.MOUNT_HEADS,
                'Countersunk: 90° countersink. Pan / cheese head: flat-bottomed counterbore.')
    form.integer(g, 'mountRows', 'Rows', p, 1, 2, '1 = near the top, 2 = near the top and the bottom')
    form.integer(g, 'mountPerRow', 'Holes per row', p, 1, 6, 'Evenly spread across the back')
    form.length(g, 'mountEdge', 'From the sides', p, units, minimum=0.0,
                tooltip='Distance of the outer holes from the side walls (inside)')
    form.length(g, 'mountTop', 'From the top', p, units, minimum=0.0,
                tooltip='Distance of the top row from the ceiling (inside)')
    form.length(g, 'mountBottom', 'From the bottom', p, units, minimum=0.0,
                tooltip='Distance of the bottom row from the floor (inside)')

    form.resultGroup(inputs, IN_RESULT, 'Result', RESULT_KEYS)

    _syncVisibility(inputs)
    _updateInfo(inputs)
    if _editedFeature is not None:
        _setEditedVisibility(False)

    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)
    futil.add_handler(args.command.mouseClick, command_mouse_click, local_handlers=local_handlers)


def _params(inputs) -> dict:
    p = form.read(inputs, GEOMETRY_IDS)
    label = form.readOne(inputs.itemById(IN_PLATE))
    p['plateToken'] = _plateChoices.get(label, (None, None))[0]
    p['col'] = int(inputs.itemById(IN_COL).value) - 1
    p['row'] = int(inputs.itemById(IN_ROW).value) - 1
    p['rotation'] = int(form.readOne(inputs.itemById(IN_ROTATION)) or 0)
    p['overhangFlags'] = {side: form.readOne(inputs.itemById(inputId)) or binFeature.EXTEND_AUTO
                          for inputId, side, _ in OVERHANG_INPUTS}
    if p['plateToken']:
        _, grid = _plateChoices[label]
        p['col'], p['row'] = binFeature.clampCell(grid, box.binPlacementParams(p))
        p['ovh'] = binFeature.overhangAmounts(grid, box.binPlacementParams(p),
                                              binFeature.extendModes(p['overhangFlags']))
    else:
        p['ovh'] = {}
    return p


def _geomKey(p: dict) -> str:
    return json.dumps({k: p.get(k) for k in GEOMETRY_IDS + ['ovh']}, sort_keys=True)


def _body(des, p):
    key = _geomKey(p)
    body = _bodyCache.get(key)
    if body is None:
        if len(_bodyCache) > 6:
            _bodyCache.clear()
        body = cabinetGeometry.buildCabinet(des, p)
        _bodyCache[key] = body
    return body


def _syncVisibility(inputs):
    p = form.read(inputs, ('heightMode', 'guide', 'feet', 'rows', 'rowWeights', 'topType', 'detent',
                           'wallMount', 'mountRows', 'mountPerRow'))
    byUnits = p['heightMode'] == HEIGHT_MODES[0]
    form.setVisible(inputs, 'heightUnits', byUnits)
    form.setVisible(inputs, 'heightMm', not byUnits)
    grooved = p['guide'] == L.GUIDE_GROOVE
    form.setVisible(inputs, 'ledgeDepth', not grooved)
    form.setVisible(inputs, 'ledgeThickness', not grooved)
    form.setVisible(inputs, 'grooveDepth', grooved)
    form.setVisible(inputs, 'magnets', bool(p['feet']))
    form.setVisible(inputs, 'screws', bool(p['feet']))
    form.setVisible(inputs, 'topEdge', p['topType'] == L.TOP_GRID)
    form.setVisible(inputs, 'detentHeight', bool(p['detent']))
    mount = bool(p['wallMount'])
    for inputId in ('mountScrew', 'mountHead', 'mountRows', 'mountPerRow', 'mountEdge', 'mountTop'):
        form.setVisible(inputs, inputId, mount)
    form.setVisible(inputs, 'mountBottom', mount and int(p['mountRows']) > 1)
    form.setVisible(inputs, 'mountEdge', mount and int(p['mountPerRow']) > 1)
    rows = inputs.itemById('rows')
    if rows is not None:
        rows.isEnabled = not str(p['rowWeights'] or '').strip()


def _updateInfo(inputs):
    try:
        p = _params(inputs)
        cab = L.cabinet(p)
        mm = lambda v: '{:.1f}'.format(v * 10)
        x0, x1 = cab['columns'][0]
        values = {
            'Outside': '{} x {} x {} mm'.format(mm(cab['x1'] - cab['x0']), mm(cab['back'] - cab['front']),
                                                mm(cab['zTop'] + const.BIN_BASE_HEIGHT)),
            'Column inside': '{} wide, {} deep (mm)'.format(mm(x1 - x0), mm(cab['innerBack'] - cab['front'])),
            'Rows (free height)': ', '.join(mm(r['height']) for r in cab['rows']) + ' mm',
            'Back wall': '{} mm'.format(mm(cab['backWall'])),
        }
        if p['wallMount']:
            values['Wall mount'] = '{} x {} {} (head flush inside)'.format(
                len(L.mountHoles(cab)), p['mountScrew'], p['mountHead'].lower())
        form.setResults(inputs, IN_RESULT, values, cab['errors'])
    except Exception:
        gplog.logExc('cabinet info')


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    # args.inputs only holds the changed input's group; use the whole dialog.
    inputs = args.firingEvent.sender.commandInputs
    changed = args.input
    if form.isResultInput(IN_RESULT, changed.id):
        return  # our own read-only result lines
    if changed.id == IN_ROTATE:
        _cycleRotation(inputs)
        return
    if changed.id in ('heightMode', 'guide', 'feet', 'rowWeights', 'topType', 'detent', 'wallMount', 'mountRows', 'mountPerRow'):
        _syncVisibility(inputs)
    if changed.id == 'heightMode':
        # Carry the height across modes.
        unit = inputs.itemById('heightUnit').value
        if form.readOne(changed) == HEIGHT_MODES[1]:
            inputs.itemById('heightMm').value = inputs.itemById('heightUnits').value * unit
        else:
            inputs.itemById('heightUnits').value = max(3, int(round(inputs.itemById('heightMm').value / unit)))
    _updateInfo(inputs)


def _cycleRotation(inputs):
    current = int(form.readOne(inputs.itemById(IN_ROTATION)) or 0)
    form.selectChoice(inputs, IN_ROTATION, str((current + 90) % 360))


def command_validate(args: adsk.core.ValidateInputsEventArgs):
    try:
        args.areInputsValid = not L.cabinet(_params(args.firingEvent.sender.commandInputs))['errors']
    except Exception:
        args.areInputsValid = False


def command_preview(args: adsk.core.CommandEventArgs):
    inputs = args.command.commandInputs
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        p = _params(inputs)
        if L.cabinet(p)['errors']:
            return
        matrix, _ = box.cabinetMatrix(des, p, world=True)
        _previewGraphics.show(des.rootComponent, _body(des, p), None, matrix)
    except Exception:
        gplog.logExc('cabinet preview')
        args.executeFailed = True
        args.executeFailedMessage = getErrorMessage()


def command_execute(args: adsk.core.CommandEventArgs):
    global _lastParams
    _previewGraphics.clear()
    inputs = args.command.commandInputs
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        if des.designType == adsk.fusion.DesignTypes.DirectDesignType:
            args.executeFailed = True
            args.executeFailedMessage = 'Projects with disabled design history are unsupported, please enable the timeline.'
            return
        p = _params(inputs)
        _lastParams = dict(p)
        if _editedFeature is not None:
            _setEditedVisibility(True)
            box.rebuildCabinet(des, _editedFeature, p)
        else:
            box.createCabinet(des, p)
    except Exception:
        args.executeFailed = True
        args.executeFailedMessage = getErrorMessage()
        gplog.logExc('cabinet execute')


def command_mouse_click(args: adsk.core.MouseEventArgs):
    try:
        inputs = args.firingEvent.sender.commandInputs
        if args.keyboardModifiers & adsk.core.KeyboardModifiers.CtrlKeyboardModifier:
            _cycleRotation(inputs)
            return
        des = adsk.fusion.Design.cast(app.activeProduct)
        # Whatever grid is under the cursor: a baseplate or a cabinet top
        # (stacking). Switches the Baseplate dropdown if needed.
        pick = binFeature.plateAtClick(des, args, _plateChoices)
        if pick is not None:
            label, occ, grid, hit = pick
            if binFeature.selectPlate(inputs.itemById(IN_PLATE), label):
                gplog.log(f'cabinet mouseClick: switched to "{label}"')
            p = _params(inputs)
        else:
            p = _params(inputs)
            if not p['plateToken']:
                return
            occ, grid, _ = binFeature.resolvePlate(des, p['plateToken'])
            if grid is None:
                return
            hit = viewRay.hitLocalPlane(args, gridRegistry.gridTransform(grid, occ), 2, 0.0)
            if hit is None:
                return
        p['col'] = int((hit[0] - grid.originX) // grid.pitchX)
        p['row'] = int((hit[1] - grid.originY) // grid.pitchY)
        col, row = binFeature.clampCell(grid, box.binPlacementParams(p))
        inputs.itemById(IN_COL).value = col + 1
        inputs.itemById(IN_ROW).value = row + 1
    except Exception:
        gplog.logExc('cabinet mouseClick')


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers, _editedFeature
    _previewGraphics.clear()
    _setEditedVisibility(True)
    _editedFeature = None
    _bodyCache.clear()
    local_handlers = []
