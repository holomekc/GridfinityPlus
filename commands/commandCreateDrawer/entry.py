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
import json
import os
import time

from ...lib import fusion360utils as futil
from ... import config
from ...lib.gridfinityUtils import boxSystemFeature as box
from ...lib.gridfinityUtils import binFeature
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
IN_RESULT = 'result'
RESULT_KEYS = ('Outside', 'Inside', 'Compartment', 'Gridfinity grid', 'Ledge', 'Spool max Ø', 'Spool play front/back',
               'Spool play floor/top', 'Spool slot', 'Axle', 'Inserts')
FILL_ONE = 'This slot'
FILL_COLUMN = 'Whole column'
FILL_ALL = 'All slots'
FILL_PICK = 'Picked slots'
FILL_MODES = (FILL_ONE, FILL_PICK, FILL_COLUMN, FILL_ALL)
_picked = []          # Picked slots: [(column, row)] 1-based, toggled by clicks
_toggledClick = None  # the click that last toggled (one click = one toggle)

PARAM_IDS = list(L.INSERT_DEFAULTS.keys())

local_handlers = []
_previewGraphics = PreviewGraphics()
_cabinet_cf = None      # the picked cabinet (custom feature)
_cabinetBodies = None   # BodyIndex of all cabinet bodies (preSelect)
_previewCache = {}      # insert ghost bodies by (cabinet, insert params, slot)
IN_CABINET_NAME = 'cabinetName'
_editedFeature = None
_hiddenBodies = []
_lastParams = dict(L.INSERT_DEFAULTS)

# Copy / paste settings (contextEdit): pasted onto the next edit dialog.
_pasteSeed = None


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


_lastClick = None      # view ray of the last click (slot picking)


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
    global _editedFeature, _cabinet_cf, _lastClick, _pasteSeed, _picked, _toggledClick
    _picked, _toggledClick = [], None
    _lastClick = None
    _cabinet_cf = None
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
        p = L.withDefaults(dict(stored, **(_pasteSeed or {})), L.INSERT_DEFAULTS)
        _pasteSeed = None
        preselected = box.resolveCabinet(des, stored.get('cabinetToken'))
    else:
        _editedFeature = None
        gplog.session('INSERT dialog CREATE')
        p = dict(_lastParams)
        preselected = _selected(box.CABINET)

    cabinets = box.listCabinets(des)
    global _cabinetBodies
    with gplog.timed('drawer dialog: body index'):
        _cabinetBodies = binFeature.BodyIndex([cf for _, _, cf in cabinets])
    _previewCache.clear()
    if not cabinets:
        ui.messageBox('Create a Gridfinity Cabinet first.', CMD_NAME)
        return

    # --- slot
    g = inputs.addGroupCommandInput('slotGroup', 'Slot').children
    # Pick the cabinet like a body: click it in the viewport (only cabinet
    # bodies are selectable). Clicking its front also picks the slot. The
    # selection is only used to find the cabinet and then cleared again, so
    # the cabinet does not stay highlighted over the drawer preview.
    cabSel = g.addSelectionInput(IN_CABINET, 'Pick', 'Click a cabinet (its front picks the slot)')
    cabSel.addSelectionFilter('SolidBodies')
    cabSel.setSelectionLimits(0, 1)
    _cabinet_cf = preselected if preselected is not None else (cabinets[-1][2] if len(cabinets) == 1 else None)
    cabSel.isVisible = _editedFeature is None
    g.addTextBoxCommandInput(IN_CABINET_NAME, 'Cabinet', _cabinetLabel(), 1, True)
    form.integer(g, 'column', 'Column', p, 1, 99)
    form.integer(g, 'row', 'Row (from bottom)', p, 1, 99)
    form.integer(g, 'span', 'Rows high', p, 1, 99, 'Grooved cabinets: one insert can span several rows')
    if _editedFeature is None:
        form.choice(g, IN_FILL, 'Fill', {IN_FILL: FILL_ONE}, FILL_MODES,
                    'This slot: one insert.\n'
                    'Picked slots: click slots on the cabinet front to add / remove them.\n'
                    'Whole column / All slots: one insert per slot.')
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
    form.choice(g, 'stop', 'Pull-out stop', p, L.STOP_MODES,
                'Side bump: a nose at the back of each side wall stops at a bump just behind the cabinet '
                'front, tilted or not; pull firmly to take the insert out (the walls give a little).\n'
                'Top catch (ledges): a nose on the rim at the back hits a tooth under the ledge above when '
                'the insert tilts; hold it level to take it out.\n'
                'Both need Stop bumps on the cabinet.\n'
                'Hard / Like the detent: older stops at the bottom.\n'
                'Auto: side bump plus a stop at the bottom / in the groove (like the detent in grooves, '
                'hard on ledges) if the cabinet has stop bumps; else hard (ledges) / like the detent.')
    form.unitless(g, 'detentHold', 'Detent hold angle (°)', p,
                  tooltip='Steepness of the flank that keeps the insert closed (degrees, steeper = holds better)')
    form.unitless(g, 'detentRamp', 'Detent push-in ramp (°)', p,
                  tooltip='Ramp the insert is pushed in over (degrees, flatter = closes more easily)')

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
    form.choice(g, 'gripDividers', 'Dividers behind', p, L.GRIP_MODES,
                'Compartments: dividers in the way of the notch / finger hole get the same round cut.\n'
                'Front row: along the front row of compartments (up to the first cross divider).\n'
                'Custom depth: this far behind the front. Off: dividers stay full height.')
    form.length(g, 'gripDepth', 'Divider cut depth', p, units, minimum=0.2,
                tooltip='How far behind the front the dividers are cut')
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
    form.choice(g, 'labelPos', 'Label position', p, L.LABEL_POSITIONS,
                '3 x 3 grid on the front. Top / bottom row: the label sits at that edge, the handle uses '
                'the rest of the height. Middle row: at the left / right edge (with a handle up to the '
                'handle) or centred. Auto: below the handle if the front is high enough, else left of '
                'it; centred without a handle.')
    form.length(g, 'labelWidth', 'Label width', p, units, minimum=0.6)
    form.length(g, 'labelHeight', 'Label height', p, units, minimum=0.4)
    form.length(g, 'labelDepth', 'Label depth', p, units, minimum=0.0, maximum=0.1,
                tooltip='Sticker recess: how deep the field is (default 0.2 mm)')
    form.offset(g, 'labelOffsetX', 'Label offset X', p, units, 'Shift right (+) / left (-), stays on the front')
    form.offset(g, 'labelOffsetZ', 'Label offset Z', p, units, 'Shift up (+) / down (-), stays on the front')
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
    form.length(g, 'spoolPlay', 'Side play per spool', p, units, minimum=0.0, maximum=1.0,
                tooltip='Gap between the spool and the divider on each side')
    form.length(g, 'spoolDivider', 'Divider thickness', p, units, minimum=L.MIN_SPOOL_WALL, maximum=1.0,
                tooltip='Cradles between the spools')
    form.length(g, 'spoolEnd', 'End support thickness', p, units, minimum=L.MIN_SPOOL_WALL, maximum=1.0,
                tooltip='The two outer cradles')
    form.choice(g, 'spoolMount', 'Axle mount', p, L.SPOOL_MOUNTS,
                'Open: lay the axle into an open U.\nSnap-in: the cradle reaches over the axle with two '
                'lips (0.3 mm overlap each); press the axle in, it clicks.')
    form.choice(g, 'spoolHolePos', 'Outlet height', p, L.HOLE_POSITIONS,
                'Height of the wire outlets in the front (and the eyelets): at the floor, at the axle or '
                'at the top of the spool')
    form.offset(g, 'spoolHoleOffset', 'Outlet offset', p, units, 'Move the outlets up (+) / down (-)')
    form.choice(g, 'axleSplit', 'Axle', p, L.AXLE_SPLITS,
                'Bayonet: two halves, each printed standing on its collar; push together, turn a quarter.\n'
                'Bayonet, smooth outside: same, but slots and groove stay inside, the axle is smooth outside.\n'
                'One piece: one collar, printed lying down; spools slide on from the other end, which runs '
                'on towards the side wall (Axle end length).')
    form.length(g, 'spoolFillet', 'Fillet at the floor', p, units, minimum=0.0, maximum=1.0,
                tooltip='Round fillet where the cradles and eyelet posts meet the floor (0 = off)')
    form.length(g, 'axleEndLength', 'Axle end length', p, units, minimum=0.0,
                tooltip='One piece: how far the end without collar runs past the end support. '
                        '0 = up to the side wall (minus the end play), so the axle cannot slide out.')
    form.length(g, 'axleEndPlay', 'Axle end play', p, units, minimum=0.0, maximum=1.0,
                tooltip='Gap between each axle collar and the outer support (how far the axle can slide)')
    form.length(g, 'axleCollar', 'Axle collar thickness', p, units, minimum=0.04, maximum=1.0,
                tooltip='Collars at both axle ends keep the axle in its cradles')
    form.length(g, 'spoolHoleDiameter', 'Outlet diameter', p, units, minimum=0.05, maximum=2.0,
                tooltip='Wire outlet in the front and eyelet; about 2-2.5 mm for AWG 26-30')
    form.boolean(g, 'showSpools', 'Show spools in model', p,
                 'Also draw the spools as a separate body (planning only, not for printing; '
                 'hide or delete it, or switch this off when editing). Also shows them in the preview.')

    form.resultGroup(inputs, IN_RESULT, 'Result', RESULT_KEYS)

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
    futil.add_handler(args.command.preSelect, command_pre_select, local_handlers=local_handlers)


def _cabinetLabel() -> str:
    return _cabinet_cf.name if _cabinet_cf is not None else '(click a cabinet)'


def _takeSelection(inputs) -> bool:
    """A cabinet body was clicked: remember the cabinet, clear the selection
    (no blue highlight). True if a cabinet was taken."""
    global _cabinet_cf, _toggledClick
    sel = adsk.core.SelectionCommandInput.cast(inputs.itemById(IN_CABINET))
    if sel is None or sel.selectionCount == 0:
        return False
    cf = _cabinetOf(sel.selection(0).entity)
    sel.clearSelection()
    if cf is None:
        return False
    if cf != _cabinet_cf:
        # Picked slots belong to one cabinet; this click picks on the new one.
        _picked.clear()
        _toggledClick = None
    _cabinet_cf = cf
    box_ = adsk.core.TextBoxCommandInput.cast(inputs.itemById(IN_CABINET_NAME))
    if box_ is not None:
        box_.text = _cabinetLabel()
    return True


def command_pre_select(args: adsk.core.SelectionEventArgs):
    """Only cabinet bodies can be picked as the cabinet."""
    try:
        if args.activeInput is None or args.activeInput.id != IN_CABINET:
            return
        start = time.perf_counter()
        args.isSelectable = _cabinetOf(args.selection.entity) is not None
        ms = (time.perf_counter() - start) * 1000
        if ms > 20:
            gplog.log(f'drawer preSelect slow: {ms:.0f} ms')
    except Exception:
        gplog.logExc('drawer preSelect')


def _cabinetOf(entity):
    if _cabinetBodies is None:
        return box.CABINET.fromSelection(entity)
    return _cabinetBodies.feature(entity)


def _cabinet(inputs):
    """(customFeature, params, layout) of the selected cabinet."""
    cf = _cabinet_cf
    try:
        if cf is None or not cf.isValid:
            return None, None, None
    except Exception:
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
    if mode == FILL_PICK:
        return list(_picked) or [(slot['column'], slot['row'])]
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
    for inputId in ('stop', 'detentHold', 'detentRamp'):
        form.setVisible(inputs, inputId, bool(cp and cp.get('detent')))
    form.setVisible(inputs, 'frontGap', p['frontStyle'] == L.FRONT_OVERLAY)
    drawer = p['insertType'] == L.INSERT_DRAWER
    form.setVisible(inputs, 'interior', drawer)
    compartments = drawer and p['interior'] == L.INTERIOR_COMPARTMENTS
    spools = drawer and p['interior'] == L.INTERIOR_SPOOLS
    for inputId in ('spoolCount', 'spoolDiameter', 'spoolWidth', 'spoolBore', 'spoolGuides', 'showSpools',
                    'spoolPlay', 'spoolDivider', 'spoolEnd', 'spoolMount', 'spoolHolePos', 'spoolHoleOffset',
                    'spoolHoleDiameter', 'axleEndPlay', 'axleCollar', 'axleSplit', 'spoolFillet'):
        form.setVisible(inputs, inputId, spools)
    form.setVisible(inputs, 'axleEndLength', spools and p.get('axleSplit') == L.AXLE_ONE_PIECE)
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
    grip = compartments and kind in (L.HANDLE_NOTCH, L.HANDLE_SLOT)
    form.setVisible(inputs, 'gripDividers', grip)
    form.setVisible(inputs, 'gripDepth', grip and p.get('gripDividers') == L.GRIP_DEPTH)
    for inputId in ('fingerGrooveWidth', 'fingerGrooveDepth', 'ledgeRim', 'ledgeHeight'):
        form.setVisible(inputs, inputId, kind == L.HANDLE_LEDGE)
    form.setVisible(inputs, 'handleAlign', kind in (L.HANDLE_PULL, L.HANDLE_LEDGE))
    for inputId in ('pullBar', 'pullTop', 'pullSides'):
        form.setVisible(inputs, inputId, kind == L.HANDLE_PULL)
    hasLabel = p['label'] != L.LABEL_NONE
    for inputId in ('labelPos', 'labelWidth', 'labelHeight', 'labelOffsetX', 'labelOffsetZ'):
        form.setVisible(inputs, inputId, hasLabel)
    form.setVisible(inputs, 'labelDepth', p['label'] == L.LABEL_RECESS)
    form.setVisible(inputs, 'wireDiameter', int(p['wireHoles']) > 0 and not spools)


_spoolCheck = {'key': None, 'problems': []}


def _spoolIssues(des, cp, p):
    """Collision check of the spools against the drawer (cached per input set)."""
    if p.get('interior') != L.INTERIOR_SPOOLS:
        return []
    key = json.dumps([cp, p], sort_keys=True, default=str)
    if _spoolCheck['key'] != key:
        try:
            _spoolCheck['problems'] = cabinetGeometry.spoolProblems(des, cp, p)
        except Exception:
            gplog.logExc('spool check')
            _spoolCheck['problems'] = []
        _spoolCheck['key'] = key
    return _spoolCheck['problems']


def _updateInfo(inputs):
    try:
        _, cp, cab = _cabinet(inputs)
        if cab is None:
            return
        des = adsk.fusion.Design.cast(app.activeProduct)
        p = _params(inputs)
        ins = L.insert(cab, p)
        mm = lambda v: '{:.1f}'.format(v * 10)
        tw = float(p['wall'])
        frontT = 0.0 if ins['overlay'] else float(p['front'])
        innerW = ins['x1'] - ins['x0'] - 2 * tw
        innerL = ins['y1'] - ins['y0'] - tw - frontT
        innerH = ins['z1'] - ins['z0'] - float(p['floor'])
        values = {
            'Outside': '{} x {} x {} mm'.format(
                mm(ins['x1'] - ins['x0']),
                mm(ins['y1'] - ins['y0'] + (float(p['front']) if ins['overlay'] else 0)),
                mm(ins['z1'] - ins['z0'])),
            'Inside': '{} x {} x {} mm'.format(mm(innerW), mm(innerL), mm(innerH)),
        }
        problems = list(ins['errors'])
        if (p['interior'] == L.INTERIOR_COMPARTMENTS and not ins['blank']
                and (int(p['divX']) > 1 or int(p['divY']) > 1)):
            # Same split as the geometry: equal compartments, walls in between.
            cx, cy = max(1, int(p['divX'])), max(1, int(p['divY']))
            uW = (innerW - (cx - 1) * tw) / cx
            uL = (innerL - (cy - 1) * tw) / cy
            values['Compartment'] = '{} x {} x {} mm ({} x {})'.format(mm(uW), mm(uL), mm(innerH), cx, cy)
            if tw < L.THIN_WALL_WARNING - 1e-9:
                problems.append('Note: dividers {} mm thin - below {} mm (two lines) they may come off '
                                'the floor'.format(mm(tw), mm(L.THIN_WALL_WARNING)))
        if p['interior'] == L.INTERIOR_GRID and not ins['blank']:
            nx, ny = L.gridCells(innerW, innerL, cp['baseW'], cp['baseL'], cp['cl'])
            if nx and ny:
                values['Gridfinity grid'] = '{} x {} cells, bins up to {} mm'.format(nx, ny, mm(innerH - 0.5))
                if p['handle'] == L.HANDLE_RECESS:
                    values['Gridfinity grid'] += ' (recessed pull takes room in front)'
            else:
                problems.append('Too small for a Gridfinity cell - built empty')
        if inputs.itemById(IN_FILL) and form.readOne(inputs.itemById(IN_FILL)) != FILL_ONE:
            values['Inserts'] = str(len(_slots(inputs, cab, p)))
        if p['handle'] == L.HANDLE_LEDGE:
            if ins['overlay']:
                fr = (ins['panel']['x0'], ins['panel']['x1'], ins['panel']['z0'], ins['panel']['z1'])
            else:
                fr = (ins['x0'], ins['x1'], ins['z0'], ins['z1'])
            full = L.withDefaults(p, L.INSERT_DEFAULTS)
            _, band, _ = cabinetGeometry.frontLayout(full, *fr)
            ls = L.ledgeSize(full, (band[3] - band[2]) - 0.2)
            note = (' (raised for the groove)' if ls['raised']
                    else ' (limited by the front)' if ls['capped'] else '')
            values['Ledge'] = '{} mm high, {} mm out, {:.0f}°{}'.format(
                mm(ls['H']), mm(ls['p']), ls['angle'], note)
        sp = ins.get('spools')
        if sp is not None:
            thin = [name for key, name in (('spoolDivider', 'divider'), ('spoolEnd', 'end support'))
                    if float(p[key]) < L.THIN_WALL_WARNING - 1e-9]
            if thin:
                problems.append('Note: spool {} below {} mm (two lines) - may come off the floor'.format(
                    ' and '.join(thin), mm(L.THIN_WALL_WARNING)))
            values['Spool max Ø'] = '{} mm ({} mm inside height - {} mm under the spool)'.format(
                mm(sp['maxD']), mm(innerH), mm(L.SPOOL_BOTTOM_GAP + L.SPOOL_TOP_GAP))
            if not sp['errors']:
                frontIn = ins['y0'] + frontT
                r = sp['D'] / 2
                values['Spool play front/back'] = '{} / {} mm'.format(
                    mm(sp['yA'] - r - frontIn), mm(ins['y1'] - tw - sp['yA'] - r))
                values['Spool play floor/top'] = '{} / {} mm'.format(
                    mm(sp['zA'] - r - sp['floorZ']), mm(ins['z1'] - sp['zA'] - r))
                values['Axle'] = '{} mm, separate body'.format(mm(sp['axleD']))
                values['Spool slot'] = '{} mm between cradles (spool {} + 2 x {} play)'.format(
                    mm(sp['Ws'] + 2 * sp['play']), mm(sp['Ws']), mm(sp['play']))
                problems.extend(_spoolIssues(des, cp, p))
                if p['handle'] == L.HANDLE_RECESS:
                    half = float(p['handleWidth']) / 2 + tw
                    xc = (ins['x0'] + ins['x1']) / 2
                    if any(abs(x - xc) < half + 0.3 for x in sp['centers']):
                        problems.append('The recessed pull blocks the wire path of a spool: '
                                        'use a narrower or another handle')
        form.setResults(inputs, IN_RESULT, values, problems)
    except Exception:
        gplog.logExc('insert info')


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    # args.inputs only holds the changed input's group; use the whole dialog.
    inputs = args.firingEvent.sender.commandInputs
    if form.isResultInput(IN_RESULT, args.input.id):
        return  # our own read-only result lines
    if args.input.id == IN_CABINET:
        if not _takeSelection(inputs):
            return  # our own clearSelection, or not a cabinet
        # The click that picked the cabinet also picks the slot on its front.
        _slotFromClick(inputs)
    if args.input.id in (IN_CABINET, 'column', 'row', 'span'):
        _onCabinetChanged(inputs)
    if args.input.id in (IN_CABINET, 'insertType', 'frontStyle', 'interior', 'handle', 'label', 'wireHoles', 'spoolCount', 'ledgeHeight', 'axleSplit', 'gripDividers'):
        _syncVisibility(inputs)
    _updateInfo(inputs)


def command_validate(args: adsk.core.ValidateInputsEventArgs):
    try:
        inputs = args.firingEvent.sender.commandInputs
        _, cp, cab = _cabinet(inputs)
        p = _params(inputs)
        des = adsk.fusion.Design.cast(app.activeProduct)
        args.areInputsValid = (cab is not None and not L.insert(cab, p)['errors']
                               and not _spoolIssues(des, cp, p))
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
        tmgr = adsk.fusion.TemporaryBRepManager.get()
        bodies = []
        for c, r in _slots(inputs, cab, p):
            # One click fires the preview twice (click + cabinet selection),
            # and picked slots rebuild every drawer: reuse what is built.
            key = json.dumps([cp, p, c, r], sort_keys=True, default=str)
            body = _previewCache.get(key)
            if body is None:
                if len(_previewCache) > 64:
                    _previewCache.clear()
                body = _previewCache[key] = cabinetGeometry.buildInsert(des, cp, dict(p, column=c, row=r))
            bodies.append(tmgr.copy(body))
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
        # New drawers start like the last one, but without wire outlets.
        _lastParams = dict(p, wireHoles=0)
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
    """Click on the cabinet front -> column/row under the cursor. When the
    click also selects another cabinet, inputChanged repeats this for it."""
    global _lastClick
    try:
        _lastClick = viewRay.clickRay(args)
        _slotFromClick(args.firingEvent.sender.commandInputs)
    except Exception:
        gplog.logExc('insert mouseClick')


def _slotFromClick(inputs):
    """Column / row under the last click on the selected cabinet's front."""
    if _lastClick is None:
        return
    des = adsk.fusion.Design.cast(app.activeProduct)
    cf, cp, cab = _cabinet(inputs)
    if cab is None:
        return
    hit = viewRay.hitRayPlane(_lastClick, box.insertMatrix(des, cp, world=True), 1, cab['front'])
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
    _togglePick(inputs, col + 1, row + 1)
    _updateInfo(inputs)


def _togglePick(inputs, column, row):
    """Picked slots: a click adds the slot or removes it again (each click
    counts once, although mouseClick and the cabinet selection both report it)."""
    global _toggledClick
    fill = inputs.itemById(IN_FILL)
    if fill is None or form.readOne(fill) != FILL_PICK or _toggledClick is _lastClick:
        return
    _toggledClick = _lastClick
    if (column, row) in _picked:
        _picked.remove((column, row))
    else:
        _picked.append((column, row))
    gplog.log(f'drawer: picked slots {_picked}')


def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers, _editedFeature
    _previewGraphics.clear()
    _setEditedVisibility(True)
    _editedFeature = None
    local_handlers = []
