import adsk.core, adsk.fusion, traceback
import os


from ...lib import configUtils
from ...lib import fusion360utils as futil
from ... import config
from ...lib.gridfinityUtils import baseplateFeature
from ...lib.gridfinityUtils import baseplateFastPreview
from ...lib.gridfinityUtils import placement
from ...lib.gridfinityUtils.previewGraphics import PreviewGraphics
from . import plateDialog
from ...lib.ui.commandUiState import CommandUiState
from ...lib.ui.unsupportedDesignTypeException import UnsupportedDesignTypeException

app = adsk.core.Application.get()
ui = app.userInterface


# The command identity information. ***
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdBaseplate'
CMD_NAME = 'Gridfinity Baseplate'
CMD_Description = 'Create a Gridfinity baseplate - whole cells or cut to an exact size, placed on any plane or face'

# Edit command that Fusion launches when a baseplate custom feature is double-clicked.
EDIT_CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdBaseplateEdit'

uiState = CommandUiState(CMD_NAME)
# Specify that the command will be promoted to the panel.
IS_PROMOTED = True

# TODO *** Define the location where the command button will be created. ***
# This is done by specifying the workspace, the tab, and the panel, and the 
# command it will be inserted beside. Not providing the command to position it
# will insert it at the end.
WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidCreatePanel'
COMMAND_BESIDE_ID = 'ScriptsManagerCommand'

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources', '')

CONFIG_FOLDER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'commandConfig')
UI_INPUT_DEFAULTS_CONFIG_PATH = os.path.join(CONFIG_FOLDER_PATH, "ui_input_defaults.json")

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []

# Input groups / ids owned by this command (the rest lives in plateDialog.py)
INFO_GROUP = 'info_group'
INPUT_CHANGES_GROUP = 'input_changes_group'
INPUT_CHANGES_SAVE_DEFAULTS = 'input_changes_buttons_save_new_defaults'
INPUT_CHANGES_RESET_TO_DEFAULTS = 'input_changes_button_reset_to_defaults'
INPUT_CHANGES_RESET_TO_FACTORY = 'input_changes_button_factory_reset'


INPUTS_VALID = True

def getErrorMessage(text = "An unknown error occurred, please validate your inputs and try again"):
    stackTrace = traceback.format_exc()
    return f"{text}:<br>{stackTrace}"

def showErrorInMessageBox(text = "An unknown error occurred, please validate your inputs and try again"):
    if ui:
        ui.messageBox(getErrorMessage(text), f"{CMD_NAME} Error")

# Executed when add-in is run.
def start():
    futil.log(f'{CMD_NAME} Command Start Event')
    try:
        addinConfig = configUtils.readConfig(CONFIG_FOLDER_PATH)

        # Create a command Definition.
        cmd_def = ui.commandDefinitions.itemById(CMD_ID)
        if not cmd_def:
            cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)

            # Define an event handler for the command created event. It will be called when the button is clicked.
            futil.add_handler(cmd_def.commandCreated, command_created)

            # ******** Add a button into the UI so the user can run the command. ********
            # Get the target workspace the button will be created in.
            workspace = ui.workspaces.itemById(WORKSPACE_ID)

            # Get the panel the button will be created in.
            panel = workspace.toolbarPanels.itemById(PANEL_ID)

            # Create the button command control in the UI after the specified existing command.
            control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)

            # Specify if the command is promoted to the main toolbar.
            control.isPromoted = addinConfig['UI'].getboolean('is_promoted')

        # Register the editable-baseplate custom feature definition (once).
        baseplateFeature.register(EDIT_CMD_ID, ICON_FOLDER)

        initUiState()
        ui.statusMessage = ""
    except Exception as err:
        futil.log(f'{CMD_NAME} Error occurred at the start, {err}, {getErrorMessage()}')
        ui.statusMessage = f"{CMD_NAME} failed to initialize"
        showErrorInMessageBox(f"{CMD_NAME} Critical error occurred at the start, the command will be unavailable, see gridfinityplus.log for details")


# Executed when add-in is stopped.
def stop():
    futil.log(f'{CMD_NAME} Command Stop Event')
    # Get the various UI elements for this command
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control: adsk.core.CommandControl = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    addinConfig = configUtils.readConfig(CONFIG_FOLDER_PATH)
    addinConfig['UI']['is_promoted'] = 'yes' if command_control.isPromoted else 'no'
    configUtils.writeConfig(addinConfig, CONFIG_FOLDER_PATH)

    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Created Event')
    global uiState

    args.command.setDialogInitialSize(400, 500)

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs

    created = plateDialog.build(
        inputs,
        {fid: uiState.getState(fid) for fid in plateDialog.FIELD_BY_ID},
        groupExpanded=lambda gid: uiState.getState(gid) if gid in uiState.inputState else True)
    for fid, inp in created.items():
        if fid in plateDialog.FIELD_BY_ID or isinstance(inp, adsk.core.GroupCommandInput):
            uiState.registerCommandInput(inp)

    inputChangesGroup = inputs.addGroupCommandInput(INPUT_CHANGES_GROUP, 'Defaults')
    inputChangesGroup.isExpanded = uiState.getState(INPUT_CHANGES_GROUP)
    uiState.registerCommandInput(inputChangesGroup)
    saveAsDefaultsButtonInput = inputChangesGroup.children.addBoolValueInput(INPUT_CHANGES_SAVE_DEFAULTS, 'Use current values as default', False, '', False)
    saveAsDefaultsButtonInput.text = 'Save'
    resetToDefaultsButtonInput = inputChangesGroup.children.addBoolValueInput(INPUT_CHANGES_RESET_TO_DEFAULTS, 'Load saved defaults', False, '', False)
    resetToDefaultsButtonInput.text = 'Load'
    factoryResetButtonInput = inputChangesGroup.children.addBoolValueInput(INPUT_CHANGES_RESET_TO_FACTORY, 'Forget saved defaults', False, '', False)
    factoryResetButtonInput.text = 'Reset'

    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)


# This event handler is called when the user clicks the OK button in the command dialog or 
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Execute Event')
    _previewGraphics.clear()
    generateBaseplateFeature(args)


# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Preview Event')
    # Live preview is always on so the user sees what they configure.
    if INPUTS_VALID:
        generateBaseplate(args)
    else:
        args.executeFailed = True
        args.executeFailedMessage = "Some inputs are invalid, unable to generate preview"


# This event handler is called when the user changes anything in the command dialog
# allowing you to modify values of other inputs based on that change.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    if changed_input.id in (plateDialog.SIZE_INFO_SIZE, plateDialog.SIZE_INFO_CELLS):
        return  # read-only readouts we set ourselves
    global uiState
    if changed_input.id == INPUT_CHANGES_SAVE_DEFAULTS:
        saveUIInputsAsDefaults()
    elif changed_input.id == INPUT_CHANGES_RESET_TO_DEFAULTS:
        initUiState()
        uiState.forceUIRefresh()
    elif changed_input.id == INPUT_CHANGES_RESET_TO_FACTORY:
        configUtils.deleteConfigFile(UI_INPUT_DEFAULTS_CONFIG_PATH)
        initUiState()
        uiState.forceUIRefresh()
    else:
        uiState.onInputUpdate(changed_input)

    if isinstance(changed_input, adsk.core.GroupCommandInput) and changed_input.isExpanded == True:
        for input in changed_input.children:
            uiState.registerCommandInput(input)
        uiState.forceUIRefresh()

    try:
        plateDialog.refresh(args.firingEvent.sender.commandInputs)
    except Exception as err:
        futil.log(f'{CMD_NAME} refresh failed: {err}')

    # General logging for debug.
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')


# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Validate Input Event')

    global INPUTS_VALID
    try:
        INPUTS_VALID = plateDialog.validate(plateDialog.readParams(args.inputs))
    except Exception:
        INPUTS_VALID = False

    args.areInputsValid = INPUTS_VALID
        

# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Destroy Event')
    _previewGraphics.clear()
    global local_handlers
    local_handlers = []
    global uiState


_previewGraphics = PreviewGraphics()


def _paramsWithPlacement(inputs: adsk.core.CommandInputs) -> dict:
    """Dialog state as params incl. the world frame from the plane/point picks.

    New baseplates live in a component created at identity (or in root), so
    the world frame equals the component frame.
    """
    params = plateDialog.readParams(inputs)
    pointEnt = plateDialog.selectedEntity(inputs, plateDialog.ANCHOR_POINT_INPUT) \
        if params.get(placement.KEY_CUSTOM_ANCHOR) else None
    frame = placement.frameFromSelection(
        plateDialog.selectedEntity(inputs, plateDialog.PLACE_ON_INPUT), pointEnt)
    params[placement.KEY_FRAME] = placement.matrixToList(frame)
    return params


def generateBaseplate(args: adsk.core.CommandEventArgs):
    """Live preview as pure CustomGraphics: zero timeline entries, no bodies."""
    futil.log(f'{CMD_NAME} Preview baseplate')
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        if des.designType == 0:
            raise UnsupportedDesignTypeException('Timeline must be enabled for the generator to work, projects with disabled design history currently are not supported')
        params = _paramsWithPlacement(args.command.commandInputs)
        import json as _json
        # Key on geometry only: moving the plate just re-transforms the ghost.
        key = _json.dumps(placement.geometryKey(params), sort_keys=True)
        matrix = placement.plateMatrix(params) or adsk.core.Matrix3D.create()
        if _previewGraphics.isCurrent(key):
            _previewGraphics.setTransform(matrix, des.rootComponent)
        else:
            tempBody = baseplateFastPreview.buildPreviewPlate(des, params)
            _previewGraphics.show(des.rootComponent, tempBody, key, matrix)
    except UnsupportedDesignTypeException as err:
        args.executeFailed = True
        args.executeFailedMessage = 'Design type is unsupported. Projects with disabled design history are unsupported, please enable timeline feature to proceed.'
        return False
    except Exception as err:
        args.executeFailed = True
        args.executeFailedMessage = getErrorMessage()
        futil.log(f'{CMD_NAME} Error occurred, {err}, {getErrorMessage()}')
        return False

def generateBaseplateFeature(args: adsk.core.CommandEventArgs):
    """Real execute: create the baseplate as an editable custom feature."""
    futil.log(f'{CMD_NAME} Generating baseplate custom feature')

    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        if des.designType == 0:
            raise UnsupportedDesignTypeException('Timeline must be enabled for the generator to work, projects with disabled design history currently are not supported')
        root = adsk.fusion.Component.cast(des.rootComponent)
        params = _paramsWithPlacement(args.command.commandInputs)
        baseplateName = baseplateFeature.featureName(params)

        partIntent = getattr(adsk.fusion.DesignIntentTypes, 'PartDesignIntentType', None)
        if partIntent is None or des.designIntent != partIntent:
            # Own component for Hybrid/Assembly designs (Part allows only root)
            newCmpOcc = adsk.fusion.Occurrences.cast(root.occurrences).addNewComponent(adsk.core.Matrix3D.create())
            newCmpOcc.component.name = baseplateName
            newCmpOcc.activate()
            gridfinityBaseplateComponent: adsk.fusion.Component = newCmpOcc.component
        else:
            gridfinityBaseplateComponent: adsk.fusion.Component = des.rootComponent

        baseplateFeature.createFeature(des, gridfinityBaseplateComponent, params)
    except UnsupportedDesignTypeException as err:
        args.executeFailed = True
        args.executeFailedMessage = 'Design type is unsupported. Projects with disabled design history are unsupported, please enable timeline feature to proceed.'
        return False
    except Exception as err:
        args.executeFailed = True
        args.executeFailedMessage = getErrorMessage()
        futil.log(f'{CMD_NAME} Error occurred, {err}, {getErrorMessage()}')
        return False


def initUiState():
    global uiState
    for gid, label, parent in plateDialog.GROUPS:
        uiState.initValue(gid, True, adsk.core.GroupCommandInput.classType())
    uiState.initValue(INFO_GROUP, False, adsk.core.GroupCommandInput.classType())
    uiState.initValue(INPUT_CHANGES_GROUP, False, adsk.core.GroupCommandInput.classType())
    kindTypes = {
        'bool': adsk.core.BoolValueCommandInput.classType(),
        'int': adsk.core.IntegerSpinnerCommandInput.classType(),
        'length': adsk.core.ValueCommandInput.classType(),
        'offset': adsk.core.ValueCommandInput.classType(),
        'choice': adsk.core.DropDownCommandInput.classType(),
    }
    for fid, key, kind, label, default, extra in plateDialog.FIELDS:
        uiState.initValue(fid, default, kindTypes[kind])

    recordedDefaults = configUtils.readJsonConfig(UI_INPUT_DEFAULTS_CONFIG_PATH)
    if recordedDefaults:
        futil.log(f'{CMD_NAME} Found previously saving default values, restoring {recordedDefaults}')

        try:
            uiState.initValues(recordedDefaults)
            futil.log(f'{CMD_NAME} Successfully restored default values')
        except Exception as err:
            futil.log(f'{CMD_NAME} Failed to restore default values, err: {err}')


    else:
        futil.log(f'{CMD_NAME} No previously saved default values')

def saveUIInputsAsDefaults():
    futil.log(f'{CMD_NAME} Saving UI state to file')
    result = configUtils.dumpJsonConfig(UI_INPUT_DEFAULTS_CONFIG_PATH, uiState.toDict())
    if result:
        futil.log(f'{CMD_NAME} Saved successfully')
    else:
        futil.log(f'{CMD_NAME} UI state failed to save')
