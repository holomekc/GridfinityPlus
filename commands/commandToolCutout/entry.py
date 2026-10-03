"""
GridfinityPlus — add a tool-shaped, top-insertable cutout to a Gridfinity bin.

Select the bin body + one or more tool bodies, set the tolerance, OK. The
cavity clears everything above the tool (insert/remove realistically, no exact
negative like Fusion's Combine/Cut) and is stored in the bin's params, so bin
edits re-apply it automatically.
"""

import adsk.core, adsk.fusion, traceback
import os

from ...lib import fusion360utils as futil
from ... import config
from ...lib.gridfinityUtils import binFeature
from ...lib.gridfinityUtils import binCutout
from ...lib.gridfinityUtils import gplog
from ...lib.gridfinityUtils.previewGraphics import PreviewGraphics

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdToolCutout'
CMD_NAME = 'Gridfinity Tool Cutout'
CMD_Description = 'Cut a top-insertable tool cavity into a Gridfinity bin'
IS_PROMOTED = True

WORKSPACE_ID = 'FusionSolidEnvironment'
# Modify panel: this command modifies an existing bin, it does not create.
PANEL_ID = 'SolidModifyPanel'
COMMAND_BESIDE_ID = ''
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

IN_BIN_SELECT = 'bin_select'
IN_TOOL_SELECT = 'tool_select'
IN_TOLERANCE = 'cut_tolerance'
IN_STEP = 'cut_step'

local_handlers = []
_previewGraphics = PreviewGraphics()
_hiddenBodies = []


def getErrorMessage(text='An unknown error occurred'):
    return f"{text}:<br>{traceback.format_exc()}"


def start():
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if not cmd_def:
        cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)
        futil.add_handler(cmd_def.commandCreated, command_created)
        workspace = ui.workspaces.itemById(WORKSPACE_ID)
        panel = workspace.toolbarPanels.itemById(PANEL_ID)
        control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)
        control.isPromoted = IS_PROMOTED
    binCutout.register(ICON_FOLDER)


def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_control:
        command_control.deleteMe()
    if command_definition:
        command_definition.deleteMe()


def _findBinFeatureForBody(des: adsk.fusion.Design, body: adsk.fusion.BRepBody):
    """Resolve the bin custom feature whose BaseFeature owns `body`."""
    try:
        native = body.nativeObject if body.nativeObject else body
        comp = native.parentComponent
        for i in range(comp.features.customFeatures.count):
            cf = comp.features.customFeatures.item(i)
            if cf.definition.id != binFeature.FEATURE_ID:
                continue
            base = binFeature._findBaseFeature(cf)
            if base is None:
                continue
            for b in base.bodies:
                if b.entityToken == native.entityToken:
                    return cf
    except Exception:
        gplog.logExc('cutout: findBinFeatureForBody')
    return None


def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f'{CMD_NAME} Command Created Event')
    gplog.session('TOOL CUTOUT command created')
    inputs = args.command.commandInputs
    args.command.setDialogInitialSize(340, 260)
    lengthUnits = app.activeProduct.unitsManager.defaultLengthUnits

    binSelect = inputs.addSelectionInput(IN_BIN_SELECT, 'Bin', 'Select the bin body to cut into')
    binSelect.addSelectionFilter('SolidBodies')
    binSelect.setSelectionLimits(1, 1)

    toolSelect = inputs.addSelectionInput(IN_TOOL_SELECT, 'Tool bodies', 'Select the tool bodies to make cavities for')
    toolSelect.addSelectionFilter('SolidBodies')
    toolSelect.setSelectionLimits(1, 0)

    tolInput = inputs.addValueInput(IN_TOLERANCE, 'Fit tolerance', lengthUnits,
                                    adsk.core.ValueInput.createByReal(0.025))
    tolInput.tooltip = 'Lateral clearance so the part slides in smoothly (default 0.25 mm)'

    stepInput = inputs.addValueInput(IN_STEP, 'Sweep resolution', lengthUnits,
                                     adsk.core.ValueInput.createByReal(0.05))
    stepInput.tooltip = 'Vertical resolution of the upward clearing (smaller = smoother walls, slower)'

    # No live preview on purpose: the sweep cutter costs real compute time and
    # the user prefers a fast dialog. Everything happens once, on OK.
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


def _setBodyVisibility(body, visible: bool):
    global _hiddenBodies
    if visible:
        for b in _hiddenBodies:
            try:
                b.isLightBulbOn = True
            except Exception:
                pass
        _hiddenBodies = []
    elif body is not None and body.isLightBulbOn:
        body.isLightBulbOn = False
        _hiddenBodies.append(body)


def _buildCutters(des, inputs):
    """Returns (binBodyProxy, [cutter temp bodies]) or (None, None).
    Cutters are built from the LIVE selections (proxies = true world position)."""
    binSelect: adsk.core.SelectionCommandInput = inputs.itemById(IN_BIN_SELECT)
    toolSelect: adsk.core.SelectionCommandInput = inputs.itemById(IN_TOOL_SELECT)
    if binSelect.selectionCount == 0 or toolSelect.selectionCount == 0:
        return None, None
    binBody = adsk.fusion.BRepBody.cast(binSelect.selection(0).entity)

    tolerance = inputs.itemById(IN_TOLERANCE).value
    step = max(0.005, inputs.itemById(IN_STEP).value)
    topZ = binBody.boundingBox.maxPoint.z

    cutters = []
    for i in range(toolSelect.selectionCount):
        tool = adsk.fusion.BRepBody.cast(toolSelect.selection(i).entity)
        cutters.append(binCutout.buildCutter(tool, tolerance, step, topZ))
    return binBody, cutters


def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Execute Event')
    _previewGraphics.clear()
    _setBodyVisibility(None, True)
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        inputs = args.command.commandInputs
        binBody, cutters = _buildCutters(des, inputs)
        if binBody is None:
            args.executeFailed = True
            args.executeFailedMessage = 'Select the bin body and at least one tool body.'
            return
        native = binBody.nativeObject if binBody.nativeObject else binBody
        toolSelect: adsk.core.SelectionCommandInput = inputs.itemById(IN_TOOL_SELECT)
        name = 'Tool cutout ({} tool{})'.format(toolSelect.selectionCount,
                                                's' if toolSelect.selectionCount > 1 else '')
        # One visible timeline node: BaseFeature (cutters) + Combine/Cut wrapped
        # in a CustomFeature. Deleting the node removes the cut; bin edits
        # upstream recompute the cut automatically.
        binCutout.createCutoutFeature(des, native, cutters, name)
    except Exception as err:
        args.executeFailed = True
        args.executeFailedMessage = getErrorMessage()
        futil.log(f'{CMD_NAME} Error, {err}, {getErrorMessage()}')


def command_destroy(args: adsk.core.CommandEventArgs):
    _previewGraphics.clear()
    _setBodyVisibility(None, True)
    global local_handlers
    local_handlers = []
