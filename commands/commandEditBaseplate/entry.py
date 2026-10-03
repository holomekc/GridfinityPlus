"""
GridfinityPlus — Edit command for the baseplate custom feature.

A normal toolbar command (NOT Fusion's double-click editCommandId, which forces
a custom-feature recompute the feature-based generator cannot service). The user
selects a baseplate custom feature and runs this; it shows a seeded dialog with
live preview and, on OK, rebuilds the feature in place via BaseFeature.updateBody.

During editing the edited feature's body is hidden so the live preview (loose
geometry) reads cleanly without overlap; visibility is restored on OK/cancel.
"""

import adsk.core, adsk.fusion, traceback
import os

from ...lib import fusion360utils as futil
from ... import config
from ...lib.gridfinityUtils import baseplateFeature
from ...lib.gridfinityUtils import baseplateFastPreview
from ...lib.gridfinityUtils import gplog
from ...lib.gridfinityUtils import placement
from ..commandCreateBaseplate import plateDialog
from ...lib.gridfinityUtils.previewGraphics import PreviewGraphics

app = adsk.core.Application.get()
ui = app.userInterface

CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdBaseplateEdit'
CMD_NAME = 'Edit Gridfinity+ Baseplate'
CMD_Description = 'Edit an existing Gridfinity baseplate custom feature'
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

PLATE_TYPE_LIGHT = baseplateFeature.PLATE_TYPE_LIGHT
PLATE_TYPE_FULL = baseplateFeature.PLATE_TYPE_FULL
PLATE_TYPE_SKELETONIZED = baseplateFeature.PLATE_TYPE_SKELETONIZED

local_handlers = []

# State for the current edit session.
_editedFeature = None
_editedParams = None
_hiddenBodies = []
_previewGraphics = PreviewGraphics()


def getErrorMessage(text='An unknown error occurred'):
    return f"{text}:<br>{traceback.format_exc()}"


def start():
    # Hidden command: no toolbar button. Fusion launches it when a baseplate
    # custom feature is double-clicked in the timeline (editCommandId).
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if not cmd_def:
        cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)
        futil.add_handler(cmd_def.commandCreated, command_created)


def stop():
    cmd_def = ui.commandDefinitions.itemById(CMD_ID)
    if cmd_def:
        cmd_def.deleteMe()


def _featureOfBody(body: adsk.fusion.BRepBody):
    """Baseplate custom feature whose BaseFeature owns `body`, or None."""
    native = body.nativeObject if body.nativeObject else body
    comp = native.parentComponent
    for i in range(comp.features.customFeatures.count):
        cf = comp.features.customFeatures.item(i)
        if cf.definition.id != baseplateFeature.FEATURE_ID:
            continue
        base = baseplateFeature._findBaseFeature(cf)
        if base is None:
            continue
        for b in base.bodies:
            if b.entityToken == native.entityToken or b == native:
                return cf
    return None


def _resolveSelectedFeature():
    """The selected baseplate: its timeline node / custom feature or its body."""
    try:
        for i in range(ui.activeSelections.count):
            entity = ui.activeSelections.item(i).entity
            cf = adsk.fusion.CustomFeature.cast(entity)
            if cf and cf.definition.id == baseplateFeature.FEATURE_ID:
                return cf
            body = adsk.fusion.BRepBody.cast(entity)
            if body:
                cf = _featureOfBody(body)
                if cf is not None:
                    return cf
    except Exception:
        gplog.logExc('edit: resolve selection')
    return None


def _setEditedVisibility(visible: bool):
    """Hide/restore the edited feature's bodies so preview reads cleanly."""
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
    base = baseplateFeature._findBaseFeature(_editedFeature)
    if base:
        for body in base.bodies:
            if body.isLightBulbOn:
                body.isLightBulbOn = False
                _hiddenBodies.append(body)


def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f'{CMD_NAME} Command Created Event')
    global _editedFeature, _editedParams

    gplog.session('EDIT command created')
    try:
        sels = []
        for i in range(ui.activeSelections.count):
            e = ui.activeSelections.item(i).entity
            sels.append(e.objectType.split('::')[-1] if e else 'None')
        gplog.log(f'edit: activeSelections={sels}')
    except Exception:
        gplog.logExc('edit: selection dump')

    _editedFeature = _resolveSelectedFeature()
    if _editedFeature is None:
        ui.messageBox('Could not resolve the baseplate feature to edit. '
                      'Double-click the feature node in the timeline.', CMD_NAME)
        return

    _editedParams = baseplateFeature.readParams(_editedFeature)
    if _editedParams is None:
        ui.messageBox('This feature has no stored GridfinityPlus parameters.')
        return

    p = _editedParams
    inputs = args.command.commandInputs
    args.command.setDialogInitialSize(380, 560)
    values = plateDialog.valuesFromParams(p)
    plateDialog.build(inputs, values, isEdit=True)
    if not placement.hasPlacement(p):
        # Plate from before placement existed: keep it exactly where it is
        # unless the user opts in.
        anchor = adsk.core.DropDownCommandInput.cast(inputs.itemById(plateDialog.ANCHOR_ALIGN))
        item = anchor.listItems.add(placement.ANCHOR_ORIGINAL, True, '', 0)
        item.isSelected = True

    # Hide the existing body so the live preview does not overlap it.
    _setEditedVisibility(False)

    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    if args.input.id in (plateDialog.SIZE_INFO_SIZE, plateDialog.SIZE_INFO_CELLS, plateDialog.SPLIT_INFO):
        return  # read-only readouts we set ourselves
    try:
        plateDialog.refresh(args.firingEvent.sender.commandInputs)
    except Exception:
        gplog.logExc('edit: refresh')


def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    try:
        args.areInputsValid = plateDialog.validate(plateDialog.readParams(args.inputs, _editedParams))
    except Exception:
        args.areInputsValid = False


def _paramsFromInputs(inputs) -> dict:
    params = plateDialog.readParams(inputs, _editedParams)
    _applyPlacement(inputs, params)
    return params


def _applyPlacement(inputs, params: dict):
    """Update the placement frame from the dialog (component space)."""
    planeEnt = plateDialog.selectedEntity(inputs, plateDialog.PLACE_ON_INPUT)
    custom = bool(params.get(placement.KEY_CUSTOM_ANCHOR))
    pointEnt = plateDialog.selectedEntity(inputs, plateDialog.ANCHOR_POINT_INPUT) if custom else None
    anchor = params.get(placement.KEY_ANCHOR)

    legacy = not placement.hasPlacement(_editedParams)
    if legacy and anchor == placement.ANCHOR_ORIGINAL and planeEnt is None and pointEnt is None:
        moved = any(float(params.get(k, 0) or 0) != 0 for k in
                    (placement.KEY_OFFSET_X, placement.KEY_OFFSET_Y, placement.KEY_OFFSET_Z)) \
            or str(params.get(placement.KEY_ROTATION, '0')) != '0'
        if not moved:
            for k in placement.PLACEMENT_KEYS:
                params.pop(k, None)
            return
    if anchor == placement.ANCHOR_ORIGINAL:
        if planeEnt is None and pointEnt is None:
            # Only rotation/offset changed: stay anchored at the old corner.
            params[placement.KEY_ANCHOR] = placement.ANCHOR_CORNER
            params[placement.KEY_CUSTOM_ANCHOR] = True
        else:
            params[placement.KEY_ANCHOR] = placement.ANCHOR_CENTER

    des = adsk.fusion.Design.cast(app.activeProduct)
    component = _editedFeature.parentComponent
    if legacy:
        # Legacy plates: top at z=0, outline corner at (x0, y0). A frame at
        # that corner/bottom + Corner anchor reproduces the old position.
        from ...lib.gridfinityUtils import plateLayout
        x0, _, y0, _, zb = plateLayout.localExtents(_editedParams)
        currentLocal = adsk.core.Matrix3D.create()
        currentLocal.translation = adsk.core.Vector3D.create(x0, y0, zb)
    else:
        currentLocal = placement.listToMatrix(_editedParams[placement.KEY_FRAME])
    if planeEnt is not None or pointEnt is not None:
        currentWorld = placement.componentToWorld(des, component, currentLocal)
        frameWorld = placement.frameFromSelection(planeEnt, pointEnt, currentWorld)
        frameLocal = placement.worldToComponent(des, component, frameWorld)
    else:
        frameLocal = currentLocal
    params[placement.KEY_FRAME] = placement.matrixToList(frameLocal)


def command_preview(args: adsk.core.CommandEventArgs):
    gplog.log('edit: PREVIEW event')
    if _editedFeature is None or _editedParams is None:
        return
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        component = _editedFeature.parentComponent
        import json as _json
        params = _paramsFromInputs(args.command.commandInputs)
        key = _json.dumps(placement.geometryKey(params), sort_keys=True)
        matrix = placement.plateMatrix(params) or adsk.core.Matrix3D.create()
        if _previewGraphics.isCurrent(key):
            _previewGraphics.setTransform(matrix, component)
        else:
            tempBody = baseplateFastPreview.buildPreviewPlate(des, params)
            _previewGraphics.show(component, tempBody, key, matrix)
    except Exception as err:
        gplog.logExc('edit: preview')
        args.executeFailed = True
        args.executeFailedMessage = getErrorMessage()
        futil.log(f'{CMD_NAME} Preview error, {err}, {getErrorMessage()}')


def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Execute Event')
    gplog.log('edit: EXECUTE event')
    global _editedFeature, _editedParams
    if _editedFeature is None or _editedParams is None:
        gplog.log('edit: execute skipped, no edited feature/params')
        return
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        params = _paramsFromInputs(args.command.commandInputs)
        _previewGraphics.clear()
        _setEditedVisibility(True)  # restore before rebuild replaces the body
        baseplateFeature.rebuildFeature(des, _editedFeature, params)
        gplog.log('edit: execute done OK')
    except Exception as err:
        gplog.logExc('edit: execute')
        args.executeFailed = True
        args.executeFailedMessage = getErrorMessage()
        futil.log(f'{CMD_NAME} Error, {err}, {getErrorMessage()}')


def command_destroy(args: adsk.core.CommandEventArgs):
    gplog.log('edit: DESTROY event')
    _previewGraphics.clear()
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        gplog.dumpTimeline(des, 'edit:destroy')
    except Exception:
        gplog.logExc('edit: destroy dump')
    global local_handlers
    # Restore visibility if the command was cancelled without executing.
    _setEditedVisibility(True)
    local_handlers = []
