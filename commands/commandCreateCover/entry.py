"""
GridfinityPlus — grid cover: flat plate on Gridfinity feet.

Closes empty baseplate cells, e.g. in front of a cabinet. Placed like a bin:
pick a baseplate (or cabinet top), click a cell, Ctrl+Click rotates. Can fill
to the plate edge over a border / partial cell. Double-click the timeline
node to edit (Part designs: right-click "Edit Gridfinity+ Cover").
"""

import adsk.core, adsk.fusion, traceback
import os

from ...lib import fusion360utils as futil
from ... import config
from ...lib.gridfinityUtils import binFeature
from ...lib.gridfinityUtils import boxSystemFeature as box
from ...lib.gridfinityUtils import coverGeometry as C
from ...lib.gridfinityUtils import gplog
from ...lib.gridfinityUtils import gridRegistry
from ...lib.gridfinityUtils import viewRay
from ...lib.gridfinityUtils.previewGraphics import PreviewGraphics
from ...lib.ui import paramForm as form

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdCover'
CMD_NAME = 'Gridfinity+ Cover'
CMD_Description = 'Flat cover on Gridfinity feet to close empty baseplate cells'
IS_PROMOTED = True
WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidCreatePanel'
COMMAND_BESIDE_ID = 'ScriptsManagerCommand'
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

IN_PLATE = 'plate'
IN_COL = 'col'
IN_ROW = 'gridRow'
IN_ROTATION = 'rotation'
IN_ROTATE = 'rotateButton'
PLATE_NONE = '(free, no snapping)'
OVERHANG_INPUTS = (('ovhLeft', 'left', 'Fill to edge: left'), ('ovhRight', 'right', 'Fill to edge: right'),
                   ('ovhFront', 'front', 'Fill to edge: front'), ('ovhBack', 'back', 'Fill to edge: back'))
GEOMETRY_IDS = [k for k in C.COVER_DEFAULTS if k != 'ovh']

local_handlers = []
_previewGraphics = PreviewGraphics()
_plateChoices = {}      # label -> (token, grid)
_editedFeature = None
_hiddenBodies = []
_lastParams = dict(C.COVER_DEFAULTS)


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
    # This command doubles as the edit command of the cover feature.
    box.COVER.register(CMD_ID, ICON_FOLDER)


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
            cf = box.COVER.fromSelection(ui.activeSelections.item(i).entity)
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
    for body in box.COVER.bodies(_editedFeature):
        if body.isLightBulbOn:
            body.isLightBulbOn = False
            _hiddenBodies.append(body)


def command_created(args: adsk.core.CommandCreatedEventArgs):
    try:
        _commandCreated(args)
    except Exception:
        gplog.logExc('cover command_created')
        ui.messageBox(getErrorMessage('Cover dialog failed'), CMD_NAME)


def _commandCreated(args: adsk.core.CommandCreatedEventArgs):
    global _editedFeature, _plateChoices
    args.command.setDialogInitialSize(340, 420)
    des = adsk.fusion.Design.cast(app.activeProduct)
    units = app.activeProduct.unitsManager.defaultLengthUnits

    _editedFeature = _resolveEdited()
    stored = box.COVER.readParams(_editedFeature) if _editedFeature else None
    if stored:
        gplog.session(f'COVER dialog EDIT "{_editedFeature.name}"')
        args.command.okButtonText = 'Update cover'
        p = C.withDefaults(stored)
    else:
        _editedFeature = None
        gplog.session('COVER dialog CREATE')
        p = dict(_lastParams)

    inputs = args.command.commandInputs

    # --- placement
    g = inputs.addGroupCommandInput('placementGroup', 'Placement').children
    plateDd = g.addDropDownCommandInput(IN_PLATE, 'Baseplate', adsk.core.DropDownStyles.TextListDropDownStyle)
    plateDd.tooltip = 'Baseplate or cabinet top to snap onto'
    _plateChoices = {PLATE_NONE: (None, None)}
    plates = binFeature.listPlates(des)
    selected = None
    if stored:
        selected = next((lbl for lbl, _, grid in plates
                         if box.refersTo(des, p.get('plateToken'), grid.entity)), None)
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
        dd.tooltip = ('Grow the cover over the plate border / a partial cell on this side. '
                      'Auto: when the cover touches that plate edge.')
    g.addTextBoxCommandInput('placementHint', '', 'Click a cell to place, Ctrl+Click rotates.', 1, True)

    # --- size
    g = inputs.addGroupCommandInput('sizeGroup', 'Cover').children
    form.integer(g, 'unitsW', 'Width (units)', p, 1, 30)
    form.integer(g, 'unitsL', 'Depth (units)', p, 1, 30)
    form.length(g, 'thickness', 'Thickness', p, units, minimum=0.06, maximum=2.0,
                tooltip='Height of the flat plate above the baseplate. In front of a cabinet keep it '
                        'below the cabinet floor (default 1.2 mm), so the bottom drawer slides out '
                        'over the cover: 1 mm leaves 0.2 mm gap.')
    form.boolean(g, 'magnets', 'Magnet holes', p)
    form.boolean(g, 'screws', 'Screw holes', p)

    gridGroup = inputs.addGroupCommandInput('gridGroup', 'Grid unit')
    gridGroup.isExpanded = False
    g = gridGroup.children
    form.length(g, 'baseW', 'Base width', p, units, minimum=1.0)
    form.length(g, 'baseL', 'Base length', p, units, minimum=1.0)
    form.length(g, 'cl', 'XY clearance', p, units, minimum=0.0, maximum=0.1)

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


def _cycleRotation(inputs):
    current = int(form.readOne(inputs.itemById(IN_ROTATION)) or 0)
    form.selectChoice(inputs, IN_ROTATION, str((current + 90) % 360))


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    if args.input.id == IN_ROTATE:
        _cycleRotation(args.firingEvent.sender.commandInputs)


def command_validate(args: adsk.core.ValidateInputsEventArgs):
    try:
        args.areInputsValid = not C.errors(_params(args.firingEvent.sender.commandInputs))
    except Exception:
        args.areInputsValid = False


def command_preview(args: adsk.core.CommandEventArgs):
    inputs = args.command.commandInputs
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        p = _params(inputs)
        matrix, _ = box.cabinetMatrix(des, p, world=True)
        _previewGraphics.show(des.rootComponent, C.buildCover(des, p), None, matrix)
    except Exception:
        gplog.logExc('cover preview')
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
        _lastParams = {k: v for k, v in p.items() if k in C.COVER_DEFAULTS}
        if _editedFeature is not None:
            _setEditedVisibility(True)
            box.rebuildCover(des, _editedFeature, p)
        else:
            box.createCover(des, p)
    except Exception:
        args.executeFailed = True
        args.executeFailedMessage = getErrorMessage()
        gplog.logExc('cover execute')


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
                gplog.log(f'cover mouseClick: switched to "{label}"')
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
        gplog.log(f'cover mouseClick -> cell ({col},{row})')
    except Exception:
        gplog.logExc('cover mouseClick')


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers, _editedFeature
    _previewGraphics.clear()
    _setEditedVisibility(True)
    _editedFeature = None
    local_handlers = []
