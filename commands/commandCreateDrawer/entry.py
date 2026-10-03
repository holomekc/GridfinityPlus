"""
GridfinityPlus — insert for a Gridfinity cabinet: drawer or box.

  * Drawer: overlay front panel that covers the cabinet edges.
  * Box:    flush front, bin-like.
Both run on the cabinet's ledges / grooves, get a handle, an interior
(empty, compartments or a Gridfinity grid for bins) and — when the cabinet has
a click detent — an optional pull-out stop.

Size and position are always derived from the cabinet: pick column + row (or
click the cabinet front). "Fill" creates one insert per slot in one go.
Double-click the timeline node to edit.
"""

import adsk.core, adsk.fusion, traceback
import os

from ...lib import fusion360utils as futil
from ... import config
from ...lib.gridfinityUtils import boxSystemFeature as box
from ...lib.gridfinityUtils import cabinetLayout as L
from ...lib.gridfinityUtils import cabinetGeometry
from ...lib.gridfinityUtils import gplog
from ...lib.gridfinityUtils import viewRay
from ...lib.gridfinityUtils.previewGraphics import PreviewGraphics
from ...lib.ui import paramForm as form

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdCabinetInsert'
CMD_NAME = 'Gridfinity+ Drawer'
CMD_Description = 'Create a drawer or box for a Gridfinity cabinet'
IS_PROMOTED = True
WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidCreatePanel'
COMMAND_BESIDE_ID = 'ScriptsManagerCommand'
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

IN_CABINET = 'cabinet'
IN_FILL = 'fill'
IN_INFO = 'info'
FILL_ONE = 'This slot'
FILL_COLUMN = 'Whole column'
FILL_ALL = 'All slots'
FILL_MODES = (FILL_ONE, FILL_COLUMN, FILL_ALL)

PARAM_IDS = list(L.INSERT_DEFAULTS.keys())

local_handlers = []
_previewGraphics = PreviewGraphics()
_cabinetChoices = {}    # label -> customFeature
_editedFeature = None
_hiddenBodies = []
_lastParams = dict(L.INSERT_DEFAULTS)


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
    box.INSERT.register(CMD_ID, ICON_FOLDER)


def stop():
    panel = ui.workspaces.itemById(WORKSPACE_ID).toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.itemById(CMD_ID)
    if control:
        control.deleteMe()
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()


def _selected(kind):
    try:
        for i in range(ui.activeSelections.count):
            cf = kind.fromSelection(ui.activeSelections.item(i).entity)
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
    for body in box.INSERT.bodies(_editedFeature):
        if body.isLightBulbOn:
            body.isLightBulbOn = False
            _hiddenBodies.append(body)


def command_created(args: adsk.core.CommandCreatedEventArgs):
    try:
        _commandCreated(args)
    except Exception:
        gplog.logExc('insert command_created')
        ui.messageBox(getErrorMessage('Drawer dialog failed'), CMD_NAME)


def _commandCreated(args: adsk.core.CommandCreatedEventArgs):
    global _editedFeature, _cabinetChoices
    args.command.setDialogInitialSize(380, 560)
    des = adsk.fusion.Design.cast(app.activeProduct)
    units = app.activeProduct.unitsManager.defaultLengthUnits
    inputs = args.command.commandInputs

    _editedFeature = _selected(box.INSERT)
    stored = box.INSERT.readParams(_editedFeature) if _editedFeature else None
    preselected = None
    if stored:
        gplog.session(f'INSERT dialog EDIT "{_editedFeature.name}"')
        args.command.okButtonText = 'Update drawer'
        p = L.withDefaults(stored, L.INSERT_DEFAULTS)
        preselected = box.resolveCabinet(des, stored.get('cabinetToken'))
    else:
        _editedFeature = None
        gplog.session('INSERT dialog CREATE')
        p = dict(_lastParams)
        preselected = _selected(box.CABINET)

    cabinets = box.listCabinets(des)
    if not cabinets:
        ui.messageBox('Create a Gridfinity Cabinet first.', CMD_NAME)
        return

    # --- slot
    g = inputs.addGroupCommandInput('slotGroup', 'Slot').children
    cabDd = g.addDropDownCommandInput(IN_CABINET, 'Cabinet', adsk.core.DropDownStyles.TextListDropDownStyle)
    _cabinetChoices = {}
    selectedLabel = next((lbl for lbl, _, cf in cabinets if preselected is not None and cf == preselected),
                         cabinets[-1][0])
    for label, token, cf in cabinets:
        _cabinetChoices[label] = cf
        cabDd.listItems.add(label, label == selectedLabel)
    cabDd.isEnabled = _editedFeature is None
    form.integer(g, 'column', 'Column', p, 1, 99)
    form.integer(g, 'row', 'Row (from bottom)', p, 1, 99)
    form.integer(g, 'span', 'Rows high', p, 1, 99, 'Grooved cabinets: one insert can span several rows')
    if _editedFeature is None:
        form.choice(g, IN_FILL, 'Fill', {IN_FILL: FILL_ONE}, FILL_MODES,
                    'Create one insert per slot of the column / the whole cabinet')
    g.addTextBoxCommandInput('slotHint', '', 'Click the cabinet front to pick a slot.', 1, True)
    form.length(g, 'pullOut', 'Show pulled out', p, units, minimum=0.0,
                tooltip='Only moves the insert out of the cabinet for viewing')

    # --- type & body
    g = inputs.addGroupCommandInput('bodyGroup', 'Insert').children
    form.choice(g, 'insertType', 'Type', p, L.INSERT_TYPES,
                'Drawer: full depth box.\nBlank cover: front + short frame, just closes the slot (saves filament).')
    form.choice(g, 'frontStyle', 'Front', p, L.FRONT_STYLES,
                'Flush: front sits inside the opening, flush with the cabinet when closed.\n'
                'Overlay: front panel covers the cabinet edges.')
    form.length(g, 'depth', 'Depth (0 = full)', p, units, minimum=0.0,
                tooltip='Shorter insert; blank covers default to 20 mm')
    form.length(g, 'wall', 'Wall thickness', p, units, minimum=0.08, maximum=0.5)
    form.length(g, 'floor', 'Floor thickness', p, units, minimum=0.08, maximum=0.5)
    form.length(g, 'front', 'Front thickness', p, units, minimum=0.1, maximum=1.0)
    form.length(g, 'frontGap', 'Gap between fronts', p, units, minimum=0.0, maximum=0.3)
    form.boolean(g, 'stop', 'Pull-out stop', p,
                 'Catches on the detent bump so the insert cannot fall out (pull firmly to remove)')

    # --- handle
    g = inputs.addGroupCommandInput('handleGroup', 'Handle').children
    form.choice(g, 'handle', 'Type', p, L.HANDLE_TYPES,
                'Recessed pull: hollow pocket behind the front, flush.\n'
                'Pull handle: hollow grip standing out, open at the bottom - from a thin lip\n'
                '  to a scoop or D-handle (grip face, thicknesses and side walls adjustable).\n'
                'Grooved ledge: closed 45° wedge with a finger groove on top (set groove + rim).\n'
                'Top notch, Finger hole, Knob.')
    form.choice(g, 'knobStyle', 'Knob style', p, L.KNOB_STYLES,
                'Round, Mushroom (thin neck, wide cap), Spool (round U groove in the middle)')
    form.choice(g, 'knobSupport', 'Knob support', p, L.KNOB_SUPPORTS,
                'Stand: trapezoid down to the bottom edge, stays (no supports needed).\n'
                'Thin breakaway: 0.4 mm fins down to the bed, snap them off after printing.\n'
                'None: just the knob (use slicer supports or print the drawer on its back).')
    form.length(g, 'handleWidth', 'Width', p, units, minimum=0.6, tooltip='Knob: diameter')
    form.length(g, 'handleHeight', 'Height', p, units, minimum=0.4,
                tooltip='Opening height (notch: how deep it is cut)')
    form.length(g, 'handleDepth', 'Depth', p, units, minimum=0.3,
                tooltip='Recessed pull: how deep the pocket goes in. Others: how far it sticks out')
    form.choice(g, 'handleAlign', 'Position', p, L.HANDLE_ALIGNS)
    form.length(g, 'pullGrip', 'Grip face height', p, units, minimum=0.1,
                tooltip='Height of the vertical outer face (small = thin lip, large = bar)')
    form.length(g, 'pullBar', 'Grip thickness', p, units, minimum=0.08, maximum=1.0,
                tooltip='Thickness of the outer grip bar')
    form.length(g, 'pullTop', 'Top thickness', p, units, minimum=0.08, maximum=1.0)
    form.length(g, 'fingerGrooveWidth', 'Groove width', p, units, minimum=0.2, maximum=3.0,
                tooltip='Width of the finger groove on top (front to back)')
    form.length(g, 'fingerGrooveDepth', 'Groove depth', p, units, minimum=0.05, maximum=2.0)
    form.length(g, 'ledgeHeight', 'Height (0 = 45°)', p, units, minimum=0.0,
                tooltip='Total height of the ledge. It sets the slope underneath: higher = steeper '
                        '(easier to print), lower = flatter. 0 = 45°. Raised automatically if the '
                        'groove needs more material below it.')
    form.length(g, 'ledgeRim', 'Rim', p, units, minimum=0.08, maximum=1.0,
                tooltip='Material around the groove on top. The 45° underside follows from these.')
    form.length(g, 'pullSides', 'Side walls', p, units, minimum=0.0, maximum=1.0,
                tooltip='0 = open at the sides (hook lip); > 0 closed side walls (scoop / D-handle)')

    # --- label & front extras
    g = inputs.addGroupCommandInput('labelGroup', 'Label & front').children
    form.choice(g, 'label', 'Label', p, L.LABEL_TYPES,
                'Sticker recess: 0.3 mm deep field, sticker sits flush.\n'
                'Card holder: slide a paper card in from the top.')
    form.choice(g, 'labelPos', 'Label position', p, L.LABEL_POSITIONS)
    form.length(g, 'labelWidth', 'Label width', p, units, minimum=0.6)
    form.length(g, 'labelHeight', 'Label height', p, units, minimum=0.4)
    form.integer(g, 'wireHoles', 'Wire outlets', p, 0, 4,
                 'Holes beside the handle to pull wire / filament from a spool inside')
    form.length(g, 'wireDiameter', 'Outlet diameter', p, units, minimum=0.2, maximum=2.0)

    # --- interior
    g = inputs.addGroupCommandInput('interiorGroup', 'Interior').children
    form.choice(g, 'interior', 'Interior', p, L.INTERIOR_TYPES,
                'Gridfinity grid: Gridfinity bins fit into the insert')
    form.integer(g, 'divX', 'Divisions across', p, 1, 20)
    form.integer(g, 'divY', 'Divisions deep', p, 1, 20)
    form.integer(g, 'spoolCount', 'Spools', p, 1, 10, 'Spools side by side on one axle')
    form.length(g, 'spoolDiameter', 'Spool diameter', p, units, minimum=1.0)
    form.length(g, 'spoolWidth', 'Spool width', p, units, minimum=0.3)
    form.length(g, 'spoolBore', 'Spool bore', p, units, minimum=0.3,
                tooltip='Diameter of the hole in the spool; the axle is made slightly thinner')
    form.boolean(g, 'spoolGuides', 'Wire guides', p,
                 'Eyelet between each spool and its outlet in the front')

    inputs.addTextBoxCommandInput(IN_INFO, 'Result', '', 5, True)

    _onCabinetChanged(inputs)
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


def _cabinet(inputs):
    """(customFeature, params, layout) of the selected cabinet."""
    cf = _cabinetChoices.get(form.readOne(inputs.itemById(IN_CABINET)))
    if cf is None:
        return None, None, None
    cp = box.CABINET.readParams(cf)
    return cf, cp, L.cabinet(cp)


def _params(inputs) -> dict:
    return form.read(inputs, PARAM_IDS)


def _slots(inputs, cab, p):
    """[(column, row)] to create, 1-based."""
    mode = form.readOne(inputs.itemById(IN_FILL)) if inputs.itemById(IN_FILL) else FILL_ONE
    slot = L.clampInsert(cab, p)
    if mode == FILL_ONE:
        return [(slot['column'], slot['row'])]
    cols = [slot['column']] if mode == FILL_COLUMN else range(1, len(cab['columns']) + 1)
    rows = range(1, len(cab['rows']) - slot['span'] + 2, slot['span'])
    return [(c, r) for c in cols for r in rows]


def _onCabinetChanged(inputs):
    """Clamp column/row/span onto the selected cabinet (spinner limits are
    fixed after creation, so values are clamped instead)."""
    _, cp, cab = _cabinet(inputs)
    if cab is None:
        return
    for inputId, hi in (('column', len(cab['columns'])), ('row', len(cab['rows'])), ('span', len(cab['rows']))):
        spinner = adsk.core.IntegerSpinnerCommandInput.cast(inputs.itemById(inputId))
        if spinner is not None and spinner.value > hi:
            spinner.value = hi


def _syncVisibility(inputs):
    _, cp, cab = _cabinet(inputs)
    p = _params(inputs)
    form.setVisible(inputs, 'span', bool(cab and cab['grooved']))
    form.setVisible(inputs, 'stop', bool(cp and cp.get('detent')))
    form.setVisible(inputs, 'frontGap', p['frontStyle'] == L.FRONT_OVERLAY)
    drawer = p['insertType'] == L.INSERT_DRAWER
    form.setVisible(inputs, 'interior', drawer)
    compartments = drawer and p['interior'] == L.INTERIOR_COMPARTMENTS
    spools = drawer and p['interior'] == L.INTERIOR_SPOOLS
    for inputId in ('spoolCount', 'spoolDiameter', 'spoolWidth', 'spoolBore', 'spoolGuides'):
        form.setVisible(inputs, inputId, spools)
    # Spool drawers get one outlet per spool automatically.
    form.setVisible(inputs, 'wireHoles', not spools)
    form.setVisible(inputs, 'divX', compartments)
    form.setVisible(inputs, 'divY', compartments)
    hasHandle = p['handle'] != L.HANDLE_NONE
    form.setVisible(inputs, 'handleWidth', hasHandle)
    kind = p['handle']
    form.setVisible(inputs, 'handleHeight', kind in (L.HANDLE_RECESS, L.HANDLE_NOTCH, L.HANDLE_SLOT))
    form.setVisible(inputs, 'knobStyle', kind == L.HANDLE_KNOB)
    form.setVisible(inputs, 'knobSupport', kind == L.HANDLE_KNOB)
    form.setVisible(inputs, 'handleDepth', hasHandle and kind not in (L.HANDLE_SLOT, L.HANDLE_NOTCH, L.HANDLE_LEDGE))
    form.setVisible(inputs, 'pullGrip', kind == L.HANDLE_PULL)
    for inputId in ('fingerGrooveWidth', 'fingerGrooveDepth', 'ledgeRim', 'ledgeHeight'):
        form.setVisible(inputs, inputId, kind == L.HANDLE_LEDGE)
    form.setVisible(inputs, 'handleAlign', kind in (L.HANDLE_PULL, L.HANDLE_LEDGE))
    for inputId in ('pullBar', 'pullTop', 'pullSides'):
        form.setVisible(inputs, inputId, kind == L.HANDLE_PULL)
    hasLabel = p['label'] != L.LABEL_NONE
    for inputId in ('labelPos', 'labelWidth', 'labelHeight'):
        form.setVisible(inputs, inputId, hasLabel)
    form.setVisible(inputs, 'wireDiameter', int(p['wireHoles']) > 0 or spools)


def _updateInfo(inputs):
    try:
        _, cp, cab = _cabinet(inputs)
        if cab is None:
            return
        p = _params(inputs)
        ins = L.insert(cab, p)
        mm = lambda v: '{:.1f}'.format(v * 10)
        tw = float(p['wall'])
        frontT = 0.0 if ins['overlay'] else float(p['front'])
        innerW = ins['x1'] - ins['x0'] - 2 * tw
        innerL = ins['y1'] - ins['y0'] - tw - frontT
        innerH = ins['z1'] - ins['z0'] - float(p['floor'])
        lines = ['Outside: {} x {} x {} mm'.format(mm(ins['x1'] - ins['x0']),
                                                   mm(ins['y1'] - ins['y0'] + (float(p['front']) if ins['overlay'] else 0)),
                                                   mm(ins['z1'] - ins['z0']))]
        lines.append('Inside: {} x {} x {} mm'.format(mm(innerW), mm(innerL), mm(innerH)))
        if p['interior'] == L.INTERIOR_GRID and not ins['blank']:
            if p['handle'] == L.HANDLE_RECESS:
                lines.append('Note: the recessed pull takes room at the front of the grid')
            nx, ny = L.gridCells(innerW, innerL, cp['baseW'], cp['baseL'], cp['cl'])
            if nx and ny:
                lines.append('Gridfinity grid: {} x {} cells, bins up to {} mm high'.format(
                    nx, ny, mm(innerH - 0.5)))
            else:
                lines.append('<font color="red">Too small for a Gridfinity cell - built empty</font>')
        if inputs.itemById(IN_FILL) and form.readOne(inputs.itemById(IN_FILL)) != FILL_ONE:
            lines.append('Creates {} inserts'.format(len(_slots(inputs, cab, p))))
        if p['handle'] == L.HANDLE_LEDGE:
            if ins['overlay']:
                fr = (ins['panel']['x0'], ins['panel']['x1'], ins['panel']['z0'], ins['panel']['z1'])
            else:
                fr = (ins['x0'], ins['x1'], ins['z0'], ins['z1'])
            _, band, _ = cabinetGeometry.frontLayout(L.withDefaults(p, L.INSERT_DEFAULTS), *fr)
            ls = L.ledgeSize(L.withDefaults(p, L.INSERT_DEFAULTS), (band[3] - band[2]) - 0.2)
            note = (' (raised: the groove needs it)' if ls['raised']
                    else ' (limited by the front height)' if ls['capped'] else '')
            lines.append('Ledge: {} mm high, sticks out {} mm, underside {:.0f}° from horizontal{}'.format(
                mm(ls['H']), mm(ls['p']), ls['angle'], note))
        sp = ins.get('spools')
        if sp is not None and not sp['errors']:
            maxD = (ins['z1'] - 0.1) - sp['floorZ'] - L.SPOOL_BOTTOM_GAP
            lines.append('Spools: up to {} mm diameter fit, axle {} mm (printed as a separate body)'.format(
                mm(maxD), mm(sp['axleD'])))
            tw = float(p['wall'])
            frontIn = ins['y0'] + (0.0 if ins['overlay'] else float(p['front']))
            r = sp['D'] / 2
            lines.append('Spool play: front {} / back {} / floor {} / top {} mm'.format(
                mm(sp['yA'] - r - frontIn), mm(ins['y1'] - tw - sp['yA'] - r),
                mm(sp['zA'] - r - sp['floorZ']), mm(ins['z1'] - sp['zA'] - r)))
            if p['handle'] == L.HANDLE_RECESS:
                half = float(p['handleWidth']) / 2 + float(p['wall'])
                xc = (ins['x0'] + ins['x1']) / 2
                if any(abs(x - xc) < half + 0.3 for x in sp['centers']):
                    lines.append('<font color="red">The recessed pull sits in front of a spool and blocks '
                                 'its wire path - use a narrower or another handle</font>')
        for e in ins['errors']:
            lines.append(f'<font color="red">{e}</font>')
        inputs.itemById(IN_INFO).formattedText = '<br>'.join(lines)
    except Exception:
        gplog.logExc('insert info')


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    # args.inputs only holds the changed input's group; use the whole dialog.
    inputs = args.firingEvent.sender.commandInputs
    if args.input.id in (IN_CABINET, 'column', 'row', 'span'):
        _onCabinetChanged(inputs)
    if args.input.id in (IN_CABINET, 'insertType', 'frontStyle', 'interior', 'handle', 'label', 'wireHoles', 'spoolCount', 'ledgeHeight'):
        _syncVisibility(inputs)
    _updateInfo(inputs)


def command_validate(args: adsk.core.ValidateInputsEventArgs):
    try:
        inputs = args.firingEvent.sender.commandInputs
        _, cp, cab = _cabinet(inputs)
        args.areInputsValid = cab is not None and not L.insert(cab, _params(inputs))['errors']
    except Exception:
        args.areInputsValid = False


def command_preview(args: adsk.core.CommandEventArgs):
    inputs = args.command.commandInputs
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        cf, cp, cab = _cabinet(inputs)
        if cab is None:
            return
        p = _params(inputs)
        bodies = [cabinetGeometry.buildInsert(des, cp, dict(p, column=c, row=r))
                  for c, r in _slots(inputs, cab, p)]
        tmgr = adsk.fusion.TemporaryBRepManager.get()
        ghost = bodies[0]
        for b in bodies[1:]:
            tmgr.booleanOperation(ghost, b, adsk.fusion.BooleanTypes.UnionBooleanType)
        _previewGraphics.show(des.rootComponent, ghost, None, box.insertMatrix(des, cp, world=True))
    except Exception:
        gplog.logExc('insert preview')
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
        cf, cp, cab = _cabinet(inputs)
        p = _params(inputs)
        _lastParams = dict(p)
        if _editedFeature is not None:
            _setEditedVisibility(True)
            stored = box.INSERT.readParams(_editedFeature) or {}
            box.rebuildInsert(des, _editedFeature, dict(p, cabinetToken=stored.get('cabinetToken')))
        else:
            for c, r in _slots(inputs, cab, p):
                box.createInsert(des, cf, dict(p, column=c, row=r))
    except Exception:
        args.executeFailed = True
        args.executeFailedMessage = getErrorMessage()
        gplog.logExc('insert execute')


def command_mouse_click(args: adsk.core.MouseEventArgs):
    """Click on the cabinet front -> column/row under the cursor."""
    try:
        inputs = args.firingEvent.sender.commandInputs
        des = adsk.fusion.Design.cast(app.activeProduct)
        cf, cp, cab = _cabinet(inputs)
        if cab is None:
            return
        hit = viewRay.hitLocalPlane(args, box.insertMatrix(des, cp, world=True), 1, cab['front'])
        if hit is None:
            return
        x, _, z = hit
        cols = cab['columns']
        half = cab['divider'] / 2
        col = next((i for i, (x0, x1) in enumerate(cols) if x0 - half <= x <= x1 + half), None)
        row = max((i for i, r in enumerate(cab['rows']) if r['bottom'] <= z + 1e-6), default=None)
        if col is None or row is None or z > cab['zTop']:
            return
        inputs.itemById('column').value = col + 1
        inputs.itemById('row').value = row + 1
        _updateInfo(inputs)
    except Exception:
        gplog.logExc('insert mouseClick')


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers, _editedFeature
    _previewGraphics.clear()
    _setEditedVisibility(True)
    _editedFeature = None
    local_handlers = []
