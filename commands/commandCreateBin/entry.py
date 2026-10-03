import adsk.core, adsk.fusion, traceback
import os
import math
import json


from ...lib import configUtils
from ...lib import fusion360utils as futil
from ... import config
from ...lib.gridfinityUtils import combineUtils
from ...lib.gridfinityUtils import geometryUtils
from ...lib.gridfinityUtils import faceUtils
from ...lib.gridfinityUtils import shellUtils
from ...lib.gridfinityUtils import commonUtils
from ...lib.gridfinityUtils import const
from ...lib.gridfinityUtils import scratchUtils
from ...lib.gridfinityUtils import gridRegistry
from ...lib.gridfinityUtils.baseGenerator import createSingleGridfinityBaseBody, createBaseBodyPattern, cutBaseClearance
from ...lib.gridfinityUtils.baseGeneratorInput import BaseGeneratorInput
from ...lib.gridfinityUtils.binBodyGenerator import createGridfinityBinBody, uniformCompartments
from ...lib.gridfinityUtils.binBodyGeneratorInput import BinBodyGeneratorInput, BinBodyCompartmentDefinition
from ...lib.gridfinityUtils.binBodyTabGeneratorInput import BinBodyTabGeneratorInput
from ...lib.gridfinityUtils.binBodyTabGenerator import createGridfinityBinBodyTab
from ...lib.gridfinityUtils import binFeature
from ...lib.gridfinityUtils import binCutout
from ...lib.gridfinityUtils import binFastPreview
from ...lib.gridfinityUtils import gplog
from ...lib.gridfinityUtils.previewGraphics import PreviewGraphics
from ...lib.ui.commandUiState import CommandUiState
from ...lib.ui.unsupportedDesignTypeException import UnsupportedDesignTypeException

app = adsk.core.Application.get()
ui = app.userInterface


# *** The command identity information. ***
CMD_ID = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_cmdBin'
CMD_NAME = 'Gridfinity Bin'
CMD_Description = 'Create a Gridfinity bin and snap it onto a baseplate'

commandUIState = CommandUiState(CMD_NAME)
actualDimensionsTableUiState = CommandUiState(CMD_NAME)
actualCompartmentDimensionsUiState = CommandUiState(CMD_NAME)
commandCompartmentsTableUIState: list[CommandUiState] = []

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

# Constants
BIN_BASIC_SIZES_GROUP = "bin_basic_sizes_group"
BIN_DIMENSIONS_GROUP = "bin_dimensions_group"
BIN_FEATURES_GROUP = "bin_features_group"
BIN_COMPARTMENTS_GROUP_ID = 'compartments_group'
BIN_SCOOP_GROUP_ID = 'bin_scoop_group'
BIN_TAB_FEATURES_GROUP_ID = 'bin_tab_features_group'
BIN_BASE_FEATURES_GROUP_ID = 'bin_base_features_group'
USER_CHANGES_GROUP_ID = 'user_changes_group'
PREVIEW_GROUP_ID = 'preview_group'
INFO_GROUP = 'info_group'

BIN_BASE_WIDTH_UNIT_INPUT_ID = 'base_width_unit'
BIN_BASE_LENGTH_UNIT_INPUT_ID = 'base_length_unit'
BIN_HEIGHT_UNIT_INPUT_ID = 'height_unit'
BIN_XY_CLEARANCE_INPUT_ID = 'bin_xy_tolerance'
BIN_WIDTH_INPUT_ID = 'bin_width'
BIN_LENGTH_INPUT_ID = 'bin_length'
BIN_HEIGHT_INPUT_ID = 'bin_height'  # hidden: effective height in units (may be fractional)
BIN_HEIGHT_MODE_ID = 'bin_height_mode'
BIN_HEIGHT_UNITS_ID = 'bin_height_units'
BIN_HEIGHT_MM_ID = 'bin_height_mm'
HEIGHT_MODE_UNITS = 'Units'
HEIGHT_MODE_MM = 'Total height'
BIN_WIDTH_INPUT_ID = 'bin_width'
BIN_REAL_DIMENSIONS_TABLE = "real_dimensions"
BIN_REAL_DIMENSIONS_TABLE_TOTAL_WIDTH = "total_real_width"
BIN_REAL_DIMENSIONS_TABLE_TOTAL_LENGTH = "total_real_length"
BIN_REAL_DIMENSIONS_TABLE_TOTAL_HEIGHT = "total_real_height"
BIN_WALL_THICKNESS_INPUT_ID = 'bin_wall_thickness'
BIN_GENERATE_BASE_INPUT_ID = 'bin_generate_base'
BIN_GENERATE_BODY_INPUT_ID = 'bin_generate_body'
BIN_SCREW_HOLES_INPUT_ID = 'bin_screw_holes'
BIN_MAGNET_CUTOUTS_INPUT_ID = 'bin_magnet_cutouts'
BIN_MAGNET_CUTOUTS_TABS_INPUT_ID = 'bin_magnet_cutouts_tabs'
BIN_SCREW_DIAMETER_INPUT = 'screw_diameter'
BIN_MAGNET_DIAMETER_INPUT = 'magnet_diameter'
BIN_MAGNET_HEIGHT_INPUT = 'magnet_height'
BIN_HAS_SCOOP_INPUT_ID = 'bin_has_scoop'
BIN_SCOOP_MAX_RADIUS_INPUT_ID = 'bin_scoop_max_radius'
BIN_HAS_TAB_INPUT_ID = 'bin_has_tab'
BIN_TAB_LENGTH_INPUT_ID = 'bin_tab_length'
BIN_TAB_WIDTH_INPUT_ID = 'bin_tab_width'
BIN_TAB_POSITION_INPUT_ID = 'bin_tab_position'
BIN_TAB_ANGLE_INPUT_ID = 'bin_tab_angle'
BIN_WITH_LIP_INPUT_ID = 'with_lip'
BIN_WITH_LIP_NOTCHES_INPUT_ID = 'with_lip_notches'
BIN_COMPARTMENT_REAL_DIMENSIONS_TABLE = "compartment_real_dimensions"
BIN_COMPARTMENT_REAL_DIMENSIONS_WIDTH = "compartment_width_u"
BIN_COMPARTMENT_REAL_DIMENSIONS_LENGTH = "compartment_length_u"
BIN_COMPARTMENTS_GRID_TYPE_ID = 'compartments_grid_type'
BIN_COMPARTMENTS_GRID_TYPE_UNIFORM = 'Uniform'
BIN_COMPARTMENTS_GRID_TYPE_CUSTOM = 'Custom grid'
BIN_COMPARTMENTS_GRID_TYPE_INFO = 'grid_type_info'
BIN_COMPARTMENTS_GRID_TYPE_INFO_UNIFORM = 'Equal compartments across the width and depth'
BIN_COMPARTMENTS_GRID_TYPE_INFO_CUSTOM = 'Define each compartment: position (column, row) and size (width, depth) in divisions'
BIN_COMPARTMENTS_GRID_BASE_WIDTH_ID = 'compartments_grid_w'
BIN_COMPARTMENTS_GRID_BASE_LENGTH_ID = 'compartments_grid_l'
BIN_COMPARTMENTS_TABLE_ID = 'compartments_table'
BIN_COMPARTMENTS_TABLE_ADD_ID = 'compartments_table_add'
BIN_COMPARTMENTS_TABLE_REMOVE_ID = 'compartments_table_remove'
BIN_COMPARTMENTS_TABLE_UNIFORM_ID = 'compartments_table_uniform'
BIN_TYPE_DROPDOWN_ID = 'bin_type'
BIN_TYPE_HOLLOW = 'Hollow'
BIN_TYPE_SHELLED = 'Shelled'
BIN_TYPE_SOLID = 'Solid'

INPUT_CHANGES_SAVE_DEFAULTS = 'input_changes_buttons_save_new_defaults'
INPUT_CHANGES_RESET_TO_DEFAULTS = 'input_changes_button_reset_to_defaults'
INPUT_CHANGES_RESET_TO_FACTORY = 'input_changes_button_factory_reset'
PRESERVE_CHAGES_RADIO_GROUP = 'preserve_changes'
PRESERVE_CHAGES_RADIO_GROUP_PRESERVE = 'Preserve inputs'
PRESERVE_CHAGES_RADIO_GROUP_RESET = 'Reset inputs after creation'
RESET_CHAGES_INPUT = 'reset_changes'
SHOW_PREVIEW_INPUT = 'show_preview'
SHOW_PREVIEW_MANUAL_INPUT = 'show_preview_manual'

INFO_TEXT = ("<b>GridfinityPlus</b><br>"
             "Based on FusionGridfinityGenerator by Lev Mishin (CC-BY-NC-SA 4.0).")

# --- GridfinityPlus grid placement ---
GRID_PLACEMENT_GROUP = 'grid_placement_group'
GRID_PLATE_DROPDOWN = 'grid_plate_dropdown'
GRID_COL_INPUT = 'grid_col'
GRID_ROW_INPUT = 'grid_row'
GRID_ROTATION_DROPDOWN = 'grid_rotation'
GRID_ROTATE_BUTTON = 'grid_rotate_button'
GRID_PLATE_NONE = '(free, no snapping)'
GRID_PLACEMENT_INFO = 'grid_placement_info'
# Body overhang over the plate's side padding (feet always stay on the grid).
GRID_OVERHANG_LEFT = 'grid_overhang_left'
GRID_OVERHANG_RIGHT = 'grid_overhang_right'
GRID_OVERHANG_FRONT = 'grid_overhang_front'
GRID_OVERHANG_BACK = 'grid_overhang_back'

_previewGraphics = PreviewGraphics()
# label -> (token, grid) for the current dialog session.
_plateChoices = {}
# CustomFeature being edited, or None in create mode (edit = double-click on
# a bin feature; this command is its own edit command).
_editedFeature = None
_hiddenBodies = []

def refreshUi():
    global commandUIState
    commandUIState.forceUIRefresh()
    try:
        modeInput = commandUIState.commandInputs.get(BIN_HEIGHT_MODE_ID)
        if modeInput is not None:
            _syncHeight(modeInput.parentCommand.commandInputs)
            _syncTypeVisibility(modeInput.parentCommand.commandInputs)
    except Exception:
        gplog.logExc('refreshUi: syncHeight')
    refreshCompartmentsTable()
    update_actual_compartment_unit_dimensions()
    update_actual_bin_dimensions()
    onChangeValidate()

def initDefaultUiState():
    global commandUIState
    global actualDimensionsTableUiState
    global commandCompartmentsTableUIState
    commandUIState.initValue(INFO_GROUP, True, adsk.core.GroupCommandInput.classType())
    commandUIState.initValue(BIN_BASIC_SIZES_GROUP, True, adsk.core.GroupCommandInput.classType())
    commandUIState.initValue(BIN_DIMENSIONS_GROUP, True, adsk.core.GroupCommandInput.classType())
    commandUIState.initValue(BIN_FEATURES_GROUP, True, adsk.core.GroupCommandInput.classType())
    commandUIState.initValue(BIN_COMPARTMENTS_GROUP_ID, True, adsk.core.GroupCommandInput.classType())
    commandUIState.initValue(BIN_SCOOP_GROUP_ID, True, adsk.core.GroupCommandInput.classType())
    commandUIState.initValue(BIN_TAB_FEATURES_GROUP_ID, True, adsk.core.GroupCommandInput.classType())
    commandUIState.initValue(BIN_BASE_FEATURES_GROUP_ID, True, adsk.core.GroupCommandInput.classType())
    commandUIState.initValue(USER_CHANGES_GROUP_ID, True, adsk.core.GroupCommandInput.classType())
    commandUIState.initValue(PREVIEW_GROUP_ID, True, adsk.core.GroupCommandInput.classType())

    commandUIState.initValue(BIN_BASE_WIDTH_UNIT_INPUT_ID, const.DIMENSION_DEFAULT_WIDTH_UNIT, adsk.core.ValueCommandInput.classType())
    commandUIState.initValue(BIN_BASE_LENGTH_UNIT_INPUT_ID, const.DIMENSION_DEFAULT_WIDTH_UNIT, adsk.core.ValueCommandInput.classType())
    commandUIState.initValue(BIN_HEIGHT_UNIT_INPUT_ID, const.DIMENSION_DEFAULT_HEIGHT_UNIT, adsk.core.ValueCommandInput.classType())
    commandUIState.initValue(BIN_XY_CLEARANCE_INPUT_ID, const.BIN_XY_CLEARANCE, adsk.core.ValueCommandInput.classType())
    commandUIState.initValue(BIN_WIDTH_INPUT_ID, 2, adsk.core.IntegerSpinnerCommandInput.classType())
    commandUIState.initValue(BIN_LENGTH_INPUT_ID, 3, adsk.core.IntegerSpinnerCommandInput.classType())
    commandUIState.initValue(BIN_HEIGHT_INPUT_ID, 5, adsk.core.ValueCommandInput.classType())
    commandUIState.initValue(BIN_HEIGHT_MODE_ID, HEIGHT_MODE_UNITS, adsk.core.DropDownCommandInput.classType())
    commandUIState.initValue(BIN_HEIGHT_UNITS_ID, 5, adsk.core.IntegerSpinnerCommandInput.classType())
    commandUIState.initValue(BIN_HEIGHT_MM_ID, 5 * const.DIMENSION_DEFAULT_HEIGHT_UNIT, adsk.core.ValueCommandInput.classType())

    commandUIState.initValue(BIN_GENERATE_BODY_INPUT_ID, True, adsk.core.BoolValueCommandInput.classType())
    commandUIState.initValue(BIN_TYPE_DROPDOWN_ID, BIN_TYPE_HOLLOW, adsk.core.DropDownCommandInput.classType())
    commandUIState.initValue(BIN_WALL_THICKNESS_INPUT_ID, const.BIN_WALL_THICKNESS, adsk.core.ValueCommandInput.classType())
    commandUIState.initValue(BIN_WITH_LIP_INPUT_ID, True, adsk.core.BoolValueCommandInput.classType())
    commandUIState.initValue(BIN_WITH_LIP_NOTCHES_INPUT_ID, False, adsk.core.BoolValueCommandInput.classType())

    commandUIState.initValue(BIN_COMPARTMENTS_GRID_BASE_WIDTH_ID, 1, adsk.core.IntegerSpinnerCommandInput.classType())
    commandUIState.initValue(BIN_COMPARTMENTS_GRID_BASE_LENGTH_ID, 1, adsk.core.IntegerSpinnerCommandInput.classType())
    commandUIState.initValue(BIN_COMPARTMENTS_GRID_TYPE_ID, BIN_COMPARTMENTS_GRID_TYPE_UNIFORM, adsk.core.DropDownCommandInput.classType())

    commandUIState.initValue(BIN_HAS_SCOOP_INPUT_ID, False, adsk.core.BoolValueCommandInput.classType())
    commandUIState.initValue(BIN_SCOOP_MAX_RADIUS_INPUT_ID, const.BIN_SCOOP_MAX_RADIUS, adsk.core.ValueCommandInput.classType())

    commandUIState.initValue(BIN_HAS_TAB_INPUT_ID, False, adsk.core.BoolValueCommandInput.classType())
    commandUIState.initValue(BIN_TAB_LENGTH_INPUT_ID, 1, adsk.core.ValueCommandInput.classType())
    commandUIState.initValue(BIN_TAB_WIDTH_INPUT_ID, const.BIN_TAB_WIDTH, adsk.core.ValueCommandInput.classType())
    commandUIState.initValue(BIN_TAB_POSITION_INPUT_ID, 0, adsk.core.ValueCommandInput.classType())
    commandUIState.initValue(BIN_TAB_ANGLE_INPUT_ID, '45 deg', adsk.core.ValueCommandInput.classType())

    commandUIState.initValue(BIN_GENERATE_BASE_INPUT_ID, True, adsk.core.BoolValueCommandInput.classType())
    commandUIState.initValue(BIN_SCREW_HOLES_INPUT_ID, False, adsk.core.BoolValueCommandInput.classType())
    commandUIState.initValue(BIN_SCREW_DIAMETER_INPUT, const.DIMENSION_SCREW_HOLE_DIAMETER, adsk.core.ValueCommandInput.classType())
    commandUIState.initValue(BIN_SCREW_DIAMETER_INPUT, const.DIMENSION_SCREW_HOLE_DIAMETER, adsk.core.ValueCommandInput.classType())
    commandUIState.initValue(BIN_MAGNET_CUTOUTS_INPUT_ID, False, adsk.core.BoolValueCommandInput.classType())
    commandUIState.initValue(BIN_MAGNET_CUTOUTS_TABS_INPUT_ID, False, adsk.core.BoolValueCommandInput.classType())
    commandUIState.initValue(BIN_MAGNET_DIAMETER_INPUT, const.DIMENSION_MAGNET_CUTOUT_DIAMETER, adsk.core.ValueCommandInput.classType())
    commandUIState.initValue(BIN_MAGNET_HEIGHT_INPUT, const.DIMENSION_MAGNET_CUTOUT_DEPTH, adsk.core.ValueCommandInput.classType())

    commandCompartmentsTableUIState = []
    recordedDefaults = configUtils.readJsonConfig(UI_INPUT_DEFAULTS_CONFIG_PATH)
    if recordedDefaults is not None and 'static_ui' in recordedDefaults and 'compartments_table' in recordedDefaults:
        staticUiState = recordedDefaults['static_ui']
        compartmentsTableState = recordedDefaults['compartments_table']
        if staticUiState is not None:
            futil.log(f'{CMD_NAME} Found previously saved default values, restoring {staticUiState}')

            try:
                commandUIState.initValues(staticUiState)
                futil.log(f'{CMD_NAME} Successfully restored default values')
            except Exception as err:
                futil.log(f'{CMD_NAME} Failed to restore default values, err: {err}')
        if compartmentsTableState is not None and isinstance(compartmentsTableState, list):
            futil.log(f'{CMD_NAME} Found previously saving default values for compartments table, restoring {compartmentsTableState}')
            try:
                for row in compartmentsTableState:
                    commandCompartmentsTableUIState.append(CommandUiState(CMD_NAME))
                    commandCompartmentsTableUIState[-1].initValues(row)
                futil.log(f'{CMD_NAME} Successfully restored compartments table default values')
            except Exception as err:
                futil.log(f'{CMD_NAME} Failed to restore default values, err: {err}')
    futil.log(f'{CMD_NAME} UI state initialized')

def getErrorMessage(text = "An unknown error occurred, please validate your inputs and try again"):
    stackTrace = traceback.format_exc()
    return f"{text}:<br>{stackTrace}"

def showErrorInMessageBox(text = "An unknown error occurred, please validate your inputs and try again"):
    if ui:
        ui.messageBox(getErrorMessage(text), f"{CMD_NAME} Error")

# Executed when add-in is run.
def start():
    try:
        futil.log(f'{CMD_NAME} Command Start Event')
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
        # Editable bin custom feature; this command doubles as its edit command.
        binFeature.register(CMD_ID, ICON_FOLDER)
        initDefaultUiState()
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

def render_actual_bin_dimensions_table(inputs: adsk.core.CommandInputs):
    global actualDimensionsTableUiState
    actualDimensionsTable = inputs.addTableCommandInput(BIN_REAL_DIMENSIONS_TABLE, "Resulting size", 3, "1:1:1")
    totalWidth = actualDimensionsTable.commandInputs.addStringValueInput(BIN_REAL_DIMENSIONS_TABLE_TOTAL_WIDTH, "", "Width")
    totalWidth.isReadOnly = True
    actualDimensionsTableUiState.registerCommandInput(totalWidth)
    actualDimensionsTableUiState.initValue(totalWidth.id, "", totalWidth.objectType)
    totalLength = actualDimensionsTable.commandInputs.addStringValueInput(BIN_REAL_DIMENSIONS_TABLE_TOTAL_LENGTH, "", "Depth")
    totalLength.isReadOnly = True
    actualDimensionsTableUiState.registerCommandInput(totalLength)
    actualDimensionsTableUiState.initValue(totalLength.id, "", totalLength.objectType)
    totalHeight = actualDimensionsTable.commandInputs.addStringValueInput(BIN_REAL_DIMENSIONS_TABLE_TOTAL_HEIGHT, "", "Height")
    totalHeight.isReadOnly = True
    actualDimensionsTableUiState.registerCommandInput(totalHeight)
    actualDimensionsTableUiState.initValue(totalHeight.id, "", totalHeight.objectType)
    actualDimensionsTable.addCommandInput(totalWidth, 0, 0)
    actualDimensionsTable.addCommandInput(totalLength, 0, 1)
    actualDimensionsTable.addCommandInput(totalHeight, 0, 2)
    actualDimensionsTable.tooltip = 'Resulting outer size of the bin'
    actualDimensionsTable.tablePresentationStyle = adsk.core.TablePresentationStyles.transparentBackgroundTablePresentationStyle
    actualDimensionsTable.hasGrid = False
    actualDimensionsTable.minimumVisibleRows = 1
    actualDimensionsTable.maximumVisibleRows = 1
    return actualDimensionsTable

def render_actual_compartment_dimension_units_table(inputs: adsk.core.CommandInputs):
    global actualCompartmentDimensionsUiState
    actualDimensionsTable = inputs.addTableCommandInput(BIN_COMPARTMENT_REAL_DIMENSIONS_TABLE, "Division size", 2, "1:1")
    totalWidth = actualDimensionsTable.commandInputs.addTextBoxCommandInput(BIN_COMPARTMENT_REAL_DIMENSIONS_WIDTH, "", "Division width", 1, True)
    actualCompartmentDimensionsUiState.registerCommandInput(totalWidth)
    actualCompartmentDimensionsUiState.initValue(totalWidth.id, "", totalWidth.objectType)
    totalLength = actualDimensionsTable.commandInputs.addTextBoxCommandInput(BIN_COMPARTMENT_REAL_DIMENSIONS_LENGTH, "", "Division depth", 1, True)
    actualCompartmentDimensionsUiState.registerCommandInput(totalLength)
    actualCompartmentDimensionsUiState.initValue(totalLength.id, "", totalLength.objectType)
    actualDimensionsTable.addCommandInput(totalWidth, 0, 0)
    actualDimensionsTable.addCommandInput(totalLength, 0, 1)
    actualDimensionsTable.tablePresentationStyle = adsk.core.TablePresentationStyles.transparentBackgroundTablePresentationStyle
    actualDimensionsTable.hasGrid = False
    actualDimensionsTable.minimumVisibleRows = 1
    actualDimensionsTable.maximumVisibleRows = 1
    return actualDimensionsTable

def formatString(text: str, color: str=""):
    if len(color) > 0:
        return f"<p style='color:{color}'>{text}</p>"
    return text

def update_actual_compartment_unit_dimensions():
    global commandUIState
    global actualCompartmentDimensionsUiState
    baseWidth: float = commandUIState.getState(BIN_BASE_WIDTH_UNIT_INPUT_ID)
    baseLength: float = commandUIState.getState(BIN_BASE_LENGTH_UNIT_INPUT_ID)
    binWidth: float = commandUIState.getState(BIN_WIDTH_INPUT_ID)
    binLength: float = commandUIState.getState(BIN_LENGTH_INPUT_ID)
    gridWidth: int = commandUIState.getState(BIN_COMPARTMENTS_GRID_BASE_WIDTH_ID)
    gridLength: int = commandUIState.getState(BIN_COMPARTMENTS_GRID_BASE_LENGTH_ID)
    wallThickness: float = commandUIState.getState(BIN_WALL_THICKNESS_INPUT_ID)
    xyClearance: float = commandUIState.getState(BIN_WITH_LIP_INPUT_ID)
    try:
        minCompartmentDimensionLimit = (const.BIN_CORNER_FILLET_RADIUS - wallThickness) * 2 * 10
        cellWidth = round((baseWidth * binWidth - wallThickness * 2 - xyClearance * 2 - wallThickness * (gridWidth - 1)) / gridWidth * 10, 2)
        actualCompartmentDimensionsUiState.updateValue(BIN_COMPARTMENT_REAL_DIMENSIONS_WIDTH, formatString(f'Division width: {cellWidth} mm', '' if cellWidth >= minCompartmentDimensionLimit else 'red'))
        cellLength = round((baseLength * binLength - wallThickness * 2 - xyClearance * 2 - wallThickness * (gridLength - 1)) / gridLength * 10, 2)
        actualCompartmentDimensionsUiState.updateValue(BIN_COMPARTMENT_REAL_DIMENSIONS_LENGTH, formatString(f'Division depth: {cellLength} mm', '' if cellLength >= minCompartmentDimensionLimit else 'red'))
    except:
        showErrorInMessageBox()

def update_actual_bin_dimensions():
    global actualDimensionsTableUiState
    try:
        actualWidth = commandUIState.getState(BIN_BASE_WIDTH_UNIT_INPUT_ID) * commandUIState.getState(BIN_WIDTH_INPUT_ID) - const.BIN_XY_CLEARANCE * 2
        actualLength = commandUIState.getState(BIN_BASE_LENGTH_UNIT_INPUT_ID) * commandUIState.getState(BIN_LENGTH_INPUT_ID) - const.BIN_XY_CLEARANCE * 2
        actualHeight = commandUIState.getState(BIN_HEIGHT_UNIT_INPUT_ID) * commandUIState.getState(BIN_HEIGHT_INPUT_ID) + ((const.BIN_LIP_EXTRA_HEIGHT - const.BIN_LIP_TOP_RECESS_HEIGHT) if commandUIState.getState(BIN_WITH_LIP_INPUT_ID) else 0)
        totalWidthValue = round(actualWidth * 10, 2)
        totalLengthValue = round(actualLength * 10, 2)
        totalHeightValue = round(actualHeight * 10, 2)
        actualDimensionsTableUiState.updateValue(BIN_REAL_DIMENSIONS_TABLE_TOTAL_WIDTH, f'Width: {totalWidthValue} mm')
        actualDimensionsTableUiState.getInput(BIN_REAL_DIMENSIONS_TABLE_TOTAL_WIDTH).tooltip = f'Total bin width: {totalWidthValue} mm'
        actualDimensionsTableUiState.updateValue(BIN_REAL_DIMENSIONS_TABLE_TOTAL_LENGTH, f'Depth: {totalLengthValue} mm')
        actualDimensionsTableUiState.getInput(BIN_REAL_DIMENSIONS_TABLE_TOTAL_LENGTH).tooltip = f'Total bin depth: {totalLengthValue} mm'
        actualDimensionsTableUiState.updateValue(BIN_REAL_DIMENSIONS_TABLE_TOTAL_HEIGHT, f'Height: {totalHeightValue} mm')
        actualDimensionsTableUiState.getInput(BIN_REAL_DIMENSIONS_TABLE_TOTAL_HEIGHT).tooltip = f'Total bin height: {totalHeightValue} mm'
    except:
        showErrorInMessageBox()

def render_compartments_table(inputs: adsk.core.CommandInputs):
    global commandUIState
    initiallyVisible: bool = commandUIState.getState(BIN_COMPARTMENTS_GRID_TYPE_ID) == BIN_COMPARTMENTS_GRID_TYPE_CUSTOM
    compartmentsGroup: adsk.core.GroupCommandInput = commandUIState.getInput(BIN_COMPARTMENTS_GROUP_ID)
    binCompartmentsTable = compartmentsGroup.children.addTableCommandInput(BIN_COMPARTMENTS_TABLE_ID, "Compartments", 5, "1:1:1:1:1")
    addButton = compartmentsGroup.commandInputs.addBoolValueInput(BIN_COMPARTMENTS_TABLE_ADD_ID, "Add", False, "", False)
    removeButton = compartmentsGroup.commandInputs.addBoolValueInput(BIN_COMPARTMENTS_TABLE_REMOVE_ID, "Remove", False, "", False)
    populateUniform = compartmentsGroup.commandInputs.addBoolValueInput(BIN_COMPARTMENTS_TABLE_UNIFORM_ID, "Make uniform", False, "", False)
    binCompartmentsTable.addToolbarCommandInput(addButton)
    binCompartmentsTable.addToolbarCommandInput(removeButton)
    binCompartmentsTable.addToolbarCommandInput(populateUniform)
    binCompartmentsTable.hasGrid = False
    binCompartmentsTable.tablePresentationStyle = adsk.core.TablePresentationStyles.nameValueTablePresentationStyle
    commandUIState.registerCommandInput(binCompartmentsTable)
    x_input_label = binCompartmentsTable.commandInputs.addStringValueInput("x_input_0_label", "", "Column")
    x_input_label.isReadOnly = True
    x_input_label.isFullWidth = True
    y_input_label = binCompartmentsTable.commandInputs.addStringValueInput("y_input_0_label", "", "Row")
    y_input_label.isReadOnly = True
    y_input_label.isFullWidth = True
    w_input_label = binCompartmentsTable.commandInputs.addStringValueInput("w_input_0_label", "", "Width")
    w_input_label.isFullWidth = True
    w_input_label.isReadOnly = True
    l_input_label = binCompartmentsTable.commandInputs.addStringValueInput("l_input_0_label", "", "Depth")
    l_input_label.isReadOnly = True
    l_input_label.isFullWidth = True
    d_input_label = binCompartmentsTable.commandInputs.addStringValueInput("d_input_0_label", "", "Pocket depth")
    d_input_label.isReadOnly = True
    d_input_label.isFullWidth = True
    binCompartmentsTable.addCommandInput(x_input_label, 0, 0)
    binCompartmentsTable.addCommandInput(y_input_label, 0, 1)
    binCompartmentsTable.addCommandInput(w_input_label, 0, 2)
    binCompartmentsTable.addCommandInput(l_input_label, 0, 3)
    binCompartmentsTable.addCommandInput(d_input_label, 0, 4)
    binCompartmentsTable.maximumVisibleRows = 20
    binCompartmentsTable.isVisible = initiallyVisible
    addButton.isVisible = initiallyVisible
    removeButton.isVisible = initiallyVisible
    populateUniform.isVisible = initiallyVisible

    append_compartments_from_state()

def append_compartments_from_state():
    global commandCompartmentsTableUIState
    for i, rowState in enumerate(commandCompartmentsTableUIState, 1):
        append_compartment_table_row(rowState.getState(f'x_input_{i}'), rowState.getState(f'y_input_{i}'), rowState.getState(f'w_input_{i}'), rowState.getState(f'l_input_{i}'), rowState.getState(f'd_input_{i}'))

def append_compartment_table_row(x: int, y: int, w: int, l: int, defaultDepth: float):
    global commandUIState
    binCompartmentsTable: adsk.core.TableCommandInput = commandUIState.getInput(BIN_COMPARTMENTS_TABLE_ID)
    commandUIState.registerCommandInput(binCompartmentsTable)
    newRow = binCompartmentsTable.rowCount
    x_input = binCompartmentsTable.commandInputs.addIntegerSpinnerCommandInput(f'x_input_{newRow}', 'Column', 0, 100, 1, x)
    x_input.isFullWidth = True
    y_input = binCompartmentsTable.commandInputs.addIntegerSpinnerCommandInput(f'y_input_{newRow}', 'Row', 0, 100, 1, y)
    y_input.isFullWidth = True
    w_input = binCompartmentsTable.commandInputs.addIntegerSpinnerCommandInput(f'w_input_{newRow}', 'Width', 1, 100, 1, w)
    w_input.isFullWidth = True
    l_input = binCompartmentsTable.commandInputs.addIntegerSpinnerCommandInput(f'l_input_{newRow}', 'Depth', 1, 100, 1, l)
    l_input.isFullWidth = True
    d_input = binCompartmentsTable.commandInputs.addValueInput(f'd_input_{newRow}', 'Pocket depth', app.activeProduct.unitsManager.defaultLengthUnits, adsk.core.ValueInput.createByReal(defaultDepth))
    d_input.isFullWidth = True
    binCompartmentsTable.addCommandInput(x_input, newRow, 0)
    binCompartmentsTable.addCommandInput(y_input, newRow, 1)
    binCompartmentsTable.addCommandInput(w_input, newRow, 2)
    binCompartmentsTable.addCommandInput(l_input, newRow, 3)
    binCompartmentsTable.addCommandInput(d_input, newRow, 4)

def is_all_input_valid(inputs: adsk.core.CommandInputs):
    result = True
    base_width_unit: adsk.core.ValueCommandInput = inputs.itemById(BIN_BASE_WIDTH_UNIT_INPUT_ID)
    base_length_unit: adsk.core.ValueCommandInput = inputs.itemById(BIN_BASE_LENGTH_UNIT_INPUT_ID)

    height_unit: adsk.core.ValueCommandInput = inputs.itemById(BIN_HEIGHT_UNIT_INPUT_ID)
    xy_tolerance: adsk.core.ValueCommandInput = inputs.itemById(BIN_XY_CLEARANCE_INPUT_ID)
    bin_width: adsk.core.ValueCommandInput = inputs.itemById(BIN_WIDTH_INPUT_ID)
    bin_length: adsk.core.ValueCommandInput = inputs.itemById(BIN_LENGTH_INPUT_ID)
    bin_height: adsk.core.ValueCommandInput = inputs.itemById(BIN_HEIGHT_INPUT_ID)
    bin_wall_thickness: adsk.core.ValueCommandInput = inputs.itemById(BIN_WALL_THICKNESS_INPUT_ID)
    bin_screw_holes: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_SCREW_HOLES_INPUT_ID)
    bin_magnet_cutouts: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_MAGNET_CUTOUTS_INPUT_ID)
    bin_generate_base: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_GENERATE_BASE_INPUT_ID)
    bin_generate_body: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_GENERATE_BODY_INPUT_ID)
    bin_screw_hole_diameter: adsk.core.ValueCommandInput = inputs.itemById(BIN_SCREW_DIAMETER_INPUT)
    bin_magnet_cutout_diameter: adsk.core.ValueCommandInput = inputs.itemById(BIN_MAGNET_DIAMETER_INPUT)
    bin_magnet_cutout_depth: adsk.core.ValueCommandInput = inputs.itemById(BIN_MAGNET_HEIGHT_INPUT)
    with_lip: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_WITH_LIP_INPUT_ID)
    with_lip_notches: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_WITH_LIP_NOTCHES_INPUT_ID)
    has_scoop: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_HAS_SCOOP_INPUT_ID)
    binScoopMaxRadius: adsk.core.ValueCommandInput = inputs.itemById(BIN_SCOOP_MAX_RADIUS_INPUT_ID)
    hasTabInput: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_HAS_TAB_INPUT_ID)
    binTabLength: adsk.core.ValueCommandInput = inputs.itemById(BIN_TAB_LENGTH_INPUT_ID)
    binTabWidth: adsk.core.ValueCommandInput = inputs.itemById(BIN_TAB_WIDTH_INPUT_ID)
    binTabPosition: adsk.core.ValueCommandInput = inputs.itemById(BIN_TAB_POSITION_INPUT_ID)
    binTabAngle: adsk.core.ValueCommandInput = inputs.itemById(BIN_TAB_ANGLE_INPUT_ID)
    binTypeDropdownInput: adsk.core.DropDownCommandInput = inputs.itemById(BIN_TYPE_DROPDOWN_ID)
    binCompartmentGridTypeDropdownInput: adsk.core.DropDownCommandInput = inputs.itemById(BIN_COMPARTMENTS_GRID_TYPE_ID)
    binCompartmentsTable: adsk.core.TableCommandInput = inputs.itemById(BIN_COMPARTMENTS_TABLE_ID)
    compartmentsX: adsk.core.IntegerSpinnerCommandInput = inputs.itemById(BIN_COMPARTMENTS_GRID_BASE_WIDTH_ID)
    compartmentsY: adsk.core.IntegerSpinnerCommandInput = inputs.itemById(BIN_COMPARTMENTS_GRID_BASE_LENGTH_ID)

    result = result and base_width_unit.value > 1
    result = result and base_length_unit.value > 1
    result = result and height_unit.value > 0.5
    result = result and xy_tolerance.value >= 0.01 and xy_tolerance.value <= 0.05
    result = result and bin_width.value > 0
    result = result and bin_length.value > 0
    result = result and bin_height.value >= 1
    result = result and bin_wall_thickness.value >= 0.04 and bin_wall_thickness.value <= 0.2
    if bin_generate_base.value:
        result = result and (not bin_screw_holes.value or bin_screw_hole_diameter.value > 0.1) and (not bin_magnet_cutouts.value or bin_screw_hole_diameter.value < bin_magnet_cutout_diameter.value)
        result = result and bin_magnet_cutout_depth.value > 0

    if bin_generate_body.value and binTypeDropdownInput.selectedItem.name == BIN_TYPE_HOLLOW:
        if has_scoop.value:
            result = result and binScoopMaxRadius.value > 0
        if hasTabInput.value:
            result = result and binTabLength.value > 0
            result = result and binTabWidth.value > 0
            result = result and binTabPosition.value >= 0
            result = result and binTabAngle.value >= math.radians(30) and binTabAngle.value <= math.radians(65)
        if binCompartmentGridTypeDropdownInput.selectedItem.name == BIN_COMPARTMENTS_GRID_TYPE_CUSTOM:
            for i in range(1, binCompartmentsTable.rowCount):
                posX: adsk.core.IntegerSpinnerCommandInput = binCompartmentsTable.getInputAtPosition(i, 0)
                posY: adsk.core.IntegerSpinnerCommandInput = binCompartmentsTable.getInputAtPosition(i, 1)
                width: adsk.core.IntegerSpinnerCommandInput = binCompartmentsTable.getInputAtPosition(i, 2)
                length: adsk.core.IntegerSpinnerCommandInput = binCompartmentsTable.getInputAtPosition(i, 3)

                result = result and posX.value >= 0 and (posX.value + width.value) <= compartmentsX.value
                result = result and posY.value >= 0 and (posY.value + length.value) <= compartmentsY.value
                result = result and width.value > 0 and (posX.value + width.value) <= compartmentsX.value
                result = result and length.value > 0 and (posY.value + length.value) <= compartmentsY.value

    return result

# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def _resolveEditedBinFeature():
    try:
        for i in range(ui.activeSelections.count):
            entity = ui.activeSelections.item(i).entity
            cf = adsk.fusion.CustomFeature.cast(entity)
            if cf and cf.definition.id == binFeature.FEATURE_ID:
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
    base = binFeature._findBaseFeature(_editedFeature)
    if base:
        for body in base.bodies:
            if body.isLightBulbOn:
                body.isLightBulbOn = False
                _hiddenBodies.append(body)


def command_created(args: adsk.core.CommandCreatedEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Created Event')
    global commandUIState
    global actualDimensionsTableUiState
    global commandCompartmentsTableUIState
    global _editedFeature, _plateChoices

    args.command.setDialogInitialSize(400, 500)

    # Edit mode? (double-click on a bin custom feature routes here)
    _editedFeature = _resolveEditedBinFeature()
    storedParams = binFeature.readParams(_editedFeature) if _editedFeature else None
    if storedParams:
        gplog.session(f'BIN dialog opened in EDIT mode for "{_editedFeature.name}"')
        # Seed the whole dialog from the stored state.
        try:
            if 'geom' in storedParams:
                commandUIState.initValues(storedParams['geom'])
            commandCompartmentsTableUIState = []
            for row in storedParams.get('compartmentsTable', []):
                commandCompartmentsTableUIState.append(CommandUiState(CMD_NAME))
                commandCompartmentsTableUIState[-1].initValues(row)
        except Exception:
            gplog.logExc('bin edit: seeding from stored params')
    else:
        _editedFeature = None
        gplog.session('BIN dialog opened in CREATE mode')

    # https://help.autodesk.com/view/fusion360/ENU/?contextId=CommandInputs
    inputs = args.command.commandInputs
    # Create a value input field and set the default using 1 unit of the default length unit.
    defaultLengthUnits = app.activeProduct.unitsManager.defaultLengthUnits

    infoGroup = inputs.addGroupCommandInput(INFO_GROUP, 'About')
    infoGroup.children.addTextBoxCommandInput("info_text", "Info", INFO_TEXT, 3, True)
    infoGroup.isExpanded = commandUIState.getState(INFO_GROUP)
    commandUIState.registerCommandInput(infoGroup)

    # --- GridfinityPlus: grid placement group ---
    des = adsk.fusion.Design.cast(app.activeProduct)
    plates = binFeature.listPlates(des) if des else []
    _plateChoices = {label: (token, grid) for label, token, grid in plates}
    gridGroup = inputs.addGroupCommandInput(GRID_PLACEMENT_GROUP, 'Placement')
    gridGroup.isExpanded = True
    gridGroup.children.addTextBoxCommandInput(
        GRID_PLACEMENT_INFO, '',
        '<b>Click a cell</b> on the baseplate to place the bin. '
        '<b>Ctrl+Click</b> rotates it by 90°.', 2, True)
    plateDropdown = gridGroup.children.addDropDownCommandInput(
        GRID_PLATE_DROPDOWN, 'Baseplate', adsk.core.DropDownStyles.TextListDropDownStyle)
    storedToken = storedParams.get('plateToken') if storedParams else None
    if storedToken:
        storedToken = binFeature.matchPlateToken(des, storedToken, plates) or storedToken
    selectedAny = False
    for label, token, grid in plates:
        isSel = (token == storedToken) if storedToken else (not selectedAny)
        plateDropdown.listItems.add(label, isSel)
        selectedAny = selectedAny or isSel
    plateDropdown.listItems.add(GRID_PLATE_NONE, not selectedAny)

    colDefault = int(storedParams['col']) if storedParams else 0
    rowDefault = int(storedParams['row']) if storedParams else 0
    rotDefault = int(storedParams.get('rotation', 0)) if storedParams else 0
    gridGroup.children.addIntegerSpinnerCommandInput(GRID_COL_INPUT, 'Column', 1, 100, 1, colDefault + 1)
    gridGroup.children.addIntegerSpinnerCommandInput(GRID_ROW_INPUT, 'Row', 1, 100, 1, rowDefault + 1)
    rotDropdown = gridGroup.children.addDropDownCommandInput(
        GRID_ROTATION_DROPDOWN, 'Rotation', adsk.core.DropDownStyles.TextListDropDownStyle)
    for rot in (0, 90, 180, 270):
        rotDropdown.listItems.add(str(rot), rot == rotDefault)
    rotateButton = gridGroup.children.addBoolValueInput(GRID_ROTATE_BUTTON, 'Rotate 90°', False, '', False)
    rotateButton.text = 'Rotate 90°'
    rotateButton.isFullWidth = True

    # Body extension over the plate's border / partial cells: feet stay on the
    # grid, the body grows by exactly that edge's border or partial width.
    # Auto = only where the bin sits at that plate edge.
    ovhModes = binFeature.extendModes(storedParams.get('overhangFlags', {}) if storedParams else {})
    for inputId, side, label in ((GRID_OVERHANG_LEFT, 'left', 'Fill to edge: left'),
                                 (GRID_OVERHANG_RIGHT, 'right', 'Fill to edge: right'),
                                 (GRID_OVERHANG_FRONT, 'front', 'Fill to edge: front'),
                                 (GRID_OVERHANG_BACK, 'back', 'Fill to edge: back')):
        dd = gridGroup.children.addDropDownCommandInput(inputId, label, adsk.core.DropDownStyles.TextListDropDownStyle)
        for choice in binFeature.EXTEND_CHOICES:
            dd.listItems.add(choice, choice == ovhModes[side])
        dd.tooltip = ('Extend the bin body over the plate border or partial cell on this side.\n'
                      'Auto: only when the bin sits at that plate edge. Yes: always. No: never.\n'
                      'Sides are relative to the bin (they follow its rotation).')

    basicSizesGroup = inputs.addGroupCommandInput(BIN_BASIC_SIZES_GROUP, 'Grid unit')
    basicSizesGroup.isExpanded = commandUIState.getState(BIN_BASIC_SIZES_GROUP)
    commandUIState.registerCommandInput(basicSizesGroup)
    baseWidthUnitInput = basicSizesGroup.children.addValueInput(BIN_BASE_WIDTH_UNIT_INPUT_ID, 'Cell width', defaultLengthUnits, adsk.core.ValueInput.createByReal(commandUIState.getState(BIN_BASE_WIDTH_UNIT_INPUT_ID)))
    baseWidthUnitInput.minimumValue = 1
    baseWidthUnitInput.isMinimumInclusive = True
    commandUIState.registerCommandInput(baseWidthUnitInput)
    baseLengthUnitInput = basicSizesGroup.children.addValueInput(BIN_BASE_LENGTH_UNIT_INPUT_ID, 'Cell depth', defaultLengthUnits, adsk.core.ValueInput.createByReal(commandUIState.getState(BIN_BASE_LENGTH_UNIT_INPUT_ID)))
    baseLengthUnitInput.minimumValue = 1
    baseLengthUnitInput.isMinimumInclusive = True
    commandUIState.registerCommandInput(baseLengthUnitInput)
    binHeightUnitInput = basicSizesGroup.children.addValueInput(BIN_HEIGHT_UNIT_INPUT_ID, 'Height unit', defaultLengthUnits, adsk.core.ValueInput.createByReal(commandUIState.getState(BIN_HEIGHT_UNIT_INPUT_ID)))
    binHeightUnitInput.minimumValue = 0.5
    binHeightUnitInput.isMinimumInclusive = True
    commandUIState.registerCommandInput(binHeightUnitInput)
    xyClearanceInput = basicSizesGroup.children.addValueInput(BIN_XY_CLEARANCE_INPUT_ID, 'Fit clearance', defaultLengthUnits, adsk.core.ValueInput.createByReal(commandUIState.getState(BIN_XY_CLEARANCE_INPUT_ID)))
    xyClearanceInput.minimumValue = 0.01
    xyClearanceInput.isMinimumInclusive = True
    xyClearanceInput.maximumValue = 0.05
    xyClearanceInput.isMaximumInclusive = True
    commandUIState.registerCommandInput(xyClearanceInput)

    binDimensionsGroup = inputs.addGroupCommandInput(BIN_DIMENSIONS_GROUP, 'Size')
    binDimensionsGroup.tooltipDescription = 'Width and depth in grid cells, height in height units'
    binDimensionsGroup.isExpanded = commandUIState.getState(BIN_DIMENSIONS_GROUP)
    commandUIState.registerCommandInput(binDimensionsGroup)
    binWidthInput = binDimensionsGroup.children.addIntegerSpinnerCommandInput(BIN_WIDTH_INPUT_ID, 'Width (cells)', 1, 100, 1, commandUIState.getState(BIN_WIDTH_INPUT_ID))
    commandUIState.registerCommandInput(binWidthInput)
    binLengthInput = binDimensionsGroup.children.addIntegerSpinnerCommandInput(BIN_LENGTH_INPUT_ID, 'Depth (cells)', 1, 100, 1, commandUIState.getState(BIN_LENGTH_INPUT_ID))
    commandUIState.registerCommandInput(binLengthInput)
    # Height: whole height units, or a total height in mm. The hidden
    # BIN_HEIGHT_INPUT_ID carries the effective (possibly fractional) unit
    # count that the generators use.
    effH = float(commandUIState.getState(BIN_HEIGHT_INPUT_ID))
    hUnit = float(commandUIState.getState(BIN_HEIGHT_UNIT_INPUT_ID))
    mode = commandUIState.getState(BIN_HEIGHT_MODE_ID)
    if mode == HEIGHT_MODE_UNITS and abs(effH - round(effH)) > 1e-6:
        mode = HEIGHT_MODE_MM  # stored fractional height: keep it exact
    commandUIState.updateValue(BIN_HEIGHT_MODE_ID, mode)
    commandUIState.updateValue(BIN_HEIGHT_UNITS_ID, max(1, int(round(effH))))
    commandUIState.updateValue(BIN_HEIGHT_MM_ID, effH * hUnit)
    heightModeInput = binDimensionsGroup.children.addDropDownCommandInput(
        BIN_HEIGHT_MODE_ID, 'Height by', adsk.core.DropDownStyles.TextListDropDownStyle)
    heightModeInput.listItems.add(HEIGHT_MODE_UNITS, mode == HEIGHT_MODE_UNITS)
    heightModeInput.listItems.add(HEIGHT_MODE_MM, mode == HEIGHT_MODE_MM)
    heightModeInput.tooltip = ('Units: whole Gridfinity height units (see Grid unit > Height unit, standard 7 mm).\n'
                               'Total height: any height in mm (without the stacking lip).')
    commandUIState.registerCommandInput(heightModeInput)
    heightUnitsInput = binDimensionsGroup.children.addIntegerSpinnerCommandInput(
        BIN_HEIGHT_UNITS_ID, 'Height (units)', 1, 100, 1, max(1, int(round(effH))))
    heightUnitsInput.tooltip = 'Total height = units x height unit (lip comes on top)'
    commandUIState.registerCommandInput(heightUnitsInput)
    heightMmInput = binDimensionsGroup.children.addValueInput(
        BIN_HEIGHT_MM_ID, 'Height', defaultLengthUnits, adsk.core.ValueInput.createByReal(effH * hUnit))
    heightMmInput.minimumValue = hUnit
    heightMmInput.isMinimumInclusive = True
    heightMmInput.tooltip = 'Total height without the stacking lip (at least one height unit)'
    commandUIState.registerCommandInput(heightMmInput)
    binHeightInput = binDimensionsGroup.children.addValueInput(BIN_HEIGHT_INPUT_ID, 'Height (effective units)', '', adsk.core.ValueInput.createByReal(effH))
    binHeightInput.isVisible = False
    commandUIState.registerCommandInput(binHeightInput)
    _syncHeight(inputs)

    render_actual_bin_dimensions_table(binDimensionsGroup.children)

    binFeaturesGroup = inputs.addGroupCommandInput(BIN_FEATURES_GROUP, 'Body')
    binFeaturesGroup.isExpanded = commandUIState.getState(BIN_FEATURES_GROUP)
    commandUIState.registerCommandInput(binFeaturesGroup)
    generateBodyCheckboxInput = binFeaturesGroup.children.addBoolValueInput(BIN_GENERATE_BODY_INPUT_ID, 'Create body', True, '', commandUIState.getState(BIN_GENERATE_BODY_INPUT_ID))
    commandUIState.registerCommandInput(generateBodyCheckboxInput)
    binTypeDropdown = binFeaturesGroup.children.addDropDownCommandInput(BIN_TYPE_DROPDOWN_ID, 'Type', adsk.core.DropDownStyles.LabeledIconDropDownStyle)
    binTypeDropdownDefaultValue = commandUIState.getState(BIN_TYPE_DROPDOWN_ID)
    binTypeDropdown.listItems.add(BIN_TYPE_HOLLOW, binTypeDropdownDefaultValue == BIN_TYPE_HOLLOW)
    binTypeDropdown.listItems.add(BIN_TYPE_SHELLED, binTypeDropdownDefaultValue == BIN_TYPE_SHELLED)
    binTypeDropdown.listItems.add(BIN_TYPE_SOLID, binTypeDropdownDefaultValue == BIN_TYPE_SOLID)
    commandUIState.registerCommandInput(binTypeDropdown)

    binWallThicknessInput = binFeaturesGroup.children.addValueInput(BIN_WALL_THICKNESS_INPUT_ID, 'Wall thickness', defaultLengthUnits, adsk.core.ValueInput.createByReal(commandUIState.getState(BIN_WALL_THICKNESS_INPUT_ID)))
    binWallThicknessInput.minimumValue = 0.04
    binWallThicknessInput.isMinimumInclusive = True
    binWallThicknessInput.maximumValue = 0.2
    binWallThicknessInput.isMaximumInclusive = True
    commandUIState.registerCommandInput(binWallThicknessInput)
    generateLipCheckboxInput = binFeaturesGroup.children.addBoolValueInput(BIN_WITH_LIP_INPUT_ID, 'Stacking lip', True, '', commandUIState.getState(BIN_WITH_LIP_INPUT_ID))
    commandUIState.registerCommandInput(generateLipCheckboxInput)
    hasLipNotches = binFeaturesGroup.children.addBoolValueInput(BIN_WITH_LIP_NOTCHES_INPUT_ID, 'Lip notches', True, '', commandUIState.getState(BIN_WITH_LIP_NOTCHES_INPUT_ID))
    hasLipNotches.isEnabled = commandUIState.getState(BIN_WITH_LIP_INPUT_ID)
    commandUIState.registerCommandInput(hasLipNotches)

    compartmentsGroup: adsk.core.GroupCommandInput = inputs.addGroupCommandInput(BIN_COMPARTMENTS_GROUP_ID, 'Compartments')
    compartmentsGroup.isExpanded = commandUIState.getState(BIN_COMPARTMENTS_GROUP_ID)
    commandUIState.registerCommandInput(compartmentsGroup)
    binCompartmentsWidthInput = compartmentsGroup.children.addIntegerSpinnerCommandInput(BIN_COMPARTMENTS_GRID_BASE_WIDTH_ID, "Divisions across", 1, 100, 1, commandUIState.getState(BIN_COMPARTMENTS_GRID_BASE_WIDTH_ID))
    commandUIState.registerCommandInput(binCompartmentsWidthInput)
    binCompartmentsLengthInput = compartmentsGroup.children.addIntegerSpinnerCommandInput(BIN_COMPARTMENTS_GRID_BASE_LENGTH_ID, "Divisions deep", 1, 100, 1, commandUIState.getState(BIN_COMPARTMENTS_GRID_BASE_LENGTH_ID))
    commandUIState.registerCommandInput(binCompartmentsLengthInput)
    render_actual_compartment_dimension_units_table(compartmentsGroup.children)

    compartmentGridDropdown = compartmentsGroup.children.addDropDownCommandInput(BIN_COMPARTMENTS_GRID_TYPE_ID, "Layout", adsk.core.DropDownStyles.LabeledIconDropDownStyle)
    compartmentGridDropdownDefaultValue = commandUIState.getState(BIN_COMPARTMENTS_GRID_TYPE_ID)
    compartmentGridDropdown.listItems.add(BIN_COMPARTMENTS_GRID_TYPE_UNIFORM, compartmentGridDropdownDefaultValue == BIN_COMPARTMENTS_GRID_TYPE_UNIFORM)
    compartmentGridDropdown.listItems.add(BIN_COMPARTMENTS_GRID_TYPE_CUSTOM, compartmentGridDropdownDefaultValue == BIN_COMPARTMENTS_GRID_TYPE_CUSTOM)
    commandUIState.registerCommandInput(compartmentGridDropdown)
    render_compartments_table(inputs)

    binScoopGroup = compartmentsGroup.children.addGroupCommandInput(BIN_SCOOP_GROUP_ID, 'Finger scoop')
    binScoopGroup.isExpanded = commandUIState.getState(BIN_SCOOP_GROUP_ID)
    commandUIState.registerCommandInput(binScoopGroup)
    generateScoopCheckboxInput = binScoopGroup.children.addBoolValueInput(BIN_HAS_SCOOP_INPUT_ID, 'Finger scoop (front)', True, '', commandUIState.getState(BIN_HAS_SCOOP_INPUT_ID))
    commandUIState.registerCommandInput(generateScoopCheckboxInput)
    binScoopMaxRadiusInput = binScoopGroup.children.addValueInput(BIN_SCOOP_MAX_RADIUS_INPUT_ID, 'Max. radius', defaultLengthUnits, adsk.core.ValueInput.createByReal(commandUIState.getState(BIN_SCOOP_MAX_RADIUS_INPUT_ID)))
    commandUIState.registerCommandInput(binScoopMaxRadiusInput)
    for input in binScoopGroup.children:
        if not input.id == BIN_HAS_SCOOP_INPUT_ID:
            input.isEnabled = commandUIState.getState(BIN_HAS_SCOOP_INPUT_ID)

    binTabFeaturesGroup = compartmentsGroup.children.addGroupCommandInput(BIN_TAB_FEATURES_GROUP_ID, 'Label tab')
    binTabFeaturesGroup.isExpanded = commandUIState.getState(BIN_TAB_FEATURES_GROUP_ID)
    commandUIState.registerCommandInput(binTabFeaturesGroup)
    generateTabCheckboxinput = binTabFeaturesGroup.children.addBoolValueInput(BIN_HAS_TAB_INPUT_ID, 'Label tab (back)', True, '', commandUIState.getState(BIN_HAS_TAB_INPUT_ID))
    commandUIState.registerCommandInput(generateTabCheckboxinput)
    binTabLengthInput = binTabFeaturesGroup.children.addValueInput(BIN_TAB_LENGTH_INPUT_ID, 'Length (cells)', '', adsk.core.ValueInput.createByReal(commandUIState.getState(BIN_TAB_LENGTH_INPUT_ID)))
    commandUIState.registerCommandInput(binTabLengthInput)
    binTabWidthInput = binTabFeaturesGroup.children.addValueInput(BIN_TAB_WIDTH_INPUT_ID, 'Width', defaultLengthUnits, adsk.core.ValueInput.createByReal(commandUIState.getState(BIN_TAB_WIDTH_INPUT_ID)))
    commandUIState.registerCommandInput(binTabWidthInput)
    binTabPostionInput = binTabFeaturesGroup.children.addValueInput(BIN_TAB_POSITION_INPUT_ID, 'Offset from left (cells)', '', adsk.core.ValueInput.createByReal(commandUIState.getState(BIN_TAB_POSITION_INPUT_ID)))
    commandUIState.registerCommandInput(binTabPostionInput)
    tabObverhangAngleInput = binTabFeaturesGroup.children.addValueInput(BIN_TAB_ANGLE_INPUT_ID, 'Overhang angle', 'deg', adsk.core.ValueInput.createByString(str(commandUIState.getState(BIN_TAB_ANGLE_INPUT_ID))))
    tabObverhangAngleInput.minimumValue = math.radians(30)
    tabObverhangAngleInput.isMinimumInclusive = True
    tabObverhangAngleInput.maximumValue = math.radians(65)
    tabObverhangAngleInput.isMaximumInclusive = True
    commandUIState.registerCommandInput(tabObverhangAngleInput)
    for input in binTabFeaturesGroup.children:
        if not input.id == BIN_HAS_TAB_INPUT_ID:
            input.isEnabled = commandUIState.getState(BIN_HAS_TAB_INPUT_ID)

    baseFeaturesGroup = inputs.addGroupCommandInput(BIN_BASE_FEATURES_GROUP_ID, 'Base')
    baseFeaturesGroup.isExpanded = commandUIState.getState(BIN_BASE_FEATURES_GROUP_ID)
    commandUIState.registerCommandInput(baseFeaturesGroup)
    generateBaseCheckboxInput = baseFeaturesGroup.children.addBoolValueInput(BIN_GENERATE_BASE_INPUT_ID, 'Create base', True, '', commandUIState.getState(BIN_GENERATE_BASE_INPUT_ID))
    commandUIState.registerCommandInput(generateBaseCheckboxInput)
    generateScrewHolesCheckboxInput = baseFeaturesGroup.children.addBoolValueInput(BIN_SCREW_HOLES_INPUT_ID, 'Screw holes', True, '', commandUIState.getState(BIN_SCREW_HOLES_INPUT_ID))
    commandUIState.registerCommandInput(generateScrewHolesCheckboxInput)
    screwSizeInput = baseFeaturesGroup.children.addValueInput(BIN_SCREW_DIAMETER_INPUT, 'Screw diameter', defaultLengthUnits, adsk.core.ValueInput.createByReal(commandUIState.getState(BIN_SCREW_DIAMETER_INPUT)))
    screwSizeInput.minimumValue = 0.1
    screwSizeInput.isMinimumInclusive = True
    screwSizeInput.maximumValue = 1
    screwSizeInput.isMaximumInclusive = True
    commandUIState.registerCommandInput(screwSizeInput)
    generateMagnetSocketCheckboxInput = baseFeaturesGroup.children.addBoolValueInput(BIN_MAGNET_CUTOUTS_INPUT_ID, 'Magnet holes', True, '', commandUIState.getState(BIN_MAGNET_CUTOUTS_INPUT_ID))
    commandUIState.registerCommandInput(generateMagnetSocketCheckboxInput)
    generateMagnetsTabCheckboxInput = baseFeaturesGroup.children.addBoolValueInput(BIN_MAGNET_CUTOUTS_TABS_INPUT_ID, 'Press-fit tabs in magnet holes', True, '', commandUIState.getState(BIN_MAGNET_CUTOUTS_TABS_INPUT_ID))
    commandUIState.registerCommandInput(generateMagnetsTabCheckboxInput)
    magnetSizeInput = baseFeaturesGroup.children.addValueInput(BIN_MAGNET_DIAMETER_INPUT, 'Magnet diameter', defaultLengthUnits, adsk.core.ValueInput.createByReal(commandUIState.getState(BIN_MAGNET_DIAMETER_INPUT)))
    magnetSizeInput.minimumValue = 0.1
    magnetSizeInput.isMinimumInclusive = True
    magnetSizeInput.maximumValue = 1
    magnetSizeInput.isMaximumInclusive = True
    commandUIState.registerCommandInput(magnetSizeInput)
    magnetHeightInput = baseFeaturesGroup.children.addValueInput(BIN_MAGNET_HEIGHT_INPUT, 'Magnet depth', defaultLengthUnits, adsk.core.ValueInput.createByReal(commandUIState.getState(BIN_MAGNET_HEIGHT_INPUT)))
    magnetHeightInput.minimumValue = 0.1
    magnetHeightInput.isMinimumInclusive = True
    commandUIState.registerCommandInput(magnetHeightInput)

    userChangesGroup = inputs.addGroupCommandInput(USER_CHANGES_GROUP_ID, 'Defaults')
    userChangesGroup.isExpanded = commandUIState.getState(USER_CHANGES_GROUP_ID)
    commandUIState.registerCommandInput(userChangesGroup)
    saveAsDefaultsButtonInput = userChangesGroup.children.addBoolValueInput(INPUT_CHANGES_SAVE_DEFAULTS, 'Use current values as default', False, '', False)
    saveAsDefaultsButtonInput.text = 'Save'
    resetToDefaultsButtonInput = userChangesGroup.children.addBoolValueInput(INPUT_CHANGES_RESET_TO_DEFAULTS, 'Load saved defaults', False, '', False)
    resetToDefaultsButtonInput.text = 'Load'
    factoryResetButtonInput = userChangesGroup.children.addBoolValueInput(INPUT_CHANGES_RESET_TO_FACTORY, 'Forget saved defaults', False, '', False)
    factoryResetButtonInput.text = 'Reset'

    refreshUi()

    # Hide the edited feature's body so the live preview reads cleanly.
    if _editedFeature is not None:
        _setEditedVisibility(False)

    _syncTypeVisibility(inputs)
    futil.add_handler(args.command.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(args.command.inputChanged, command_input_changed, local_handlers=local_handlers)
    futil.add_handler(args.command.executePreview, command_preview, local_handlers=local_handlers)
    futil.add_handler(args.command.validateInputs, command_validate_input, local_handlers=local_handlers)
    futil.add_handler(args.command.destroy, command_destroy, local_handlers=local_handlers)
    # Interactive placement: click a plate cell; Ctrl+Click rotates.
    futil.add_handler(args.command.mouseClick, command_mouse_click, local_handlers=local_handlers)


def _overhangModes(inputs) -> dict:
    def mode(inputId):
        dd = inputs.itemById(inputId)
        return dd.selectedItem.name if dd and dd.selectedItem else binFeature.EXTEND_AUTO
    return {'left': mode(GRID_OVERHANG_LEFT), 'right': mode(GRID_OVERHANG_RIGHT),
            'front': mode(GRID_OVERHANG_FRONT), 'back': mode(GRID_OVERHANG_BACK)}


def _overhangAmounts(inputs) -> dict:
    """Body extension per bin side in cm (border / partial cell of the plate)."""
    plateDropdown: adsk.core.DropDownCommandInput = inputs.itemById(GRID_PLATE_DROPDOWN)
    label = plateDropdown.selectedItem.name if plateDropdown and plateDropdown.selectedItem else GRID_PLATE_NONE
    grid = _plateChoices[label][1] if label in _plateChoices else None
    if grid is None:
        return {'left': 0.0, 'right': 0.0, 'front': 0.0, 'back': 0.0}
    rotDropdown = inputs.itemById(GRID_ROTATION_DROPDOWN)
    cellParams = {
        'col': int(inputs.itemById(GRID_COL_INPUT).value) - 1,
        'row': int(inputs.itemById(GRID_ROW_INPUT).value) - 1,
        'rotation': int(rotDropdown.selectedItem.name) if rotDropdown and rotDropdown.selectedItem else 0,
        'binW': int(inputs.itemById(BIN_WIDTH_INPUT_ID).value),
        'binL': int(inputs.itemById(BIN_LENGTH_INPUT_ID).value),
    }
    return binFeature.overhangAmounts(grid, cellParams, _overhangModes(inputs))


def _placementParams(inputs) -> dict:
    """Read the grid placement group + key geometry values into a params dict."""
    plateDropdown: adsk.core.DropDownCommandInput = inputs.itemById(GRID_PLATE_DROPDOWN)
    label = plateDropdown.selectedItem.name if plateDropdown and plateDropdown.selectedItem else GRID_PLATE_NONE
    token = _plateChoices[label][0] if label in _plateChoices else None
    rotDropdown: adsk.core.DropDownCommandInput = inputs.itemById(GRID_ROTATION_DROPDOWN)
    rotation = int(rotDropdown.selectedItem.name) if rotDropdown and rotDropdown.selectedItem else 0
    return {
        'plateToken': token,
        # Dialog shows 1-based column/row, params are 0-based.
        'col': int(inputs.itemById(GRID_COL_INPUT).value) - 1,
        'row': int(inputs.itemById(GRID_ROW_INPUT).value) - 1,
        'rotation': rotation,
        'binW': int(inputs.itemById(BIN_WIDTH_INPUT_ID).value),
        'binL': int(inputs.itemById(BIN_LENGTH_INPUT_ID).value),
        'binH': float(inputs.itemById(BIN_HEIGHT_INPUT_ID).value),
        'heightUnit': inputs.itemById(BIN_HEIGHT_UNIT_INPUT_ID).value,
        'baseW': inputs.itemById(BIN_BASE_WIDTH_UNIT_INPUT_ID).value,
        'baseL': inputs.itemById(BIN_BASE_LENGTH_UNIT_INPUT_ID).value,
        'cl': inputs.itemById(BIN_XY_CLEARANCE_INPUT_ID).value,
        'ovh': _overhangAmounts(inputs),
        'overhangFlags': _overhangModes(inputs),
    }


def _fullParams(inputs) -> dict:
    """Placement params + complete dialog state (for storage / edit seeding)."""
    params = _placementParams(inputs)
    params['geom'] = commandUIState.toDict(ignoreKeys=[SHOW_PREVIEW_MANUAL_INPUT, SHOW_PREVIEW_INPUT])
    params['compartmentsTable'] = [x.toDict() for x in commandCompartmentsTableUIState]
    return params


# Every input id that affects bin GEOMETRY (and nothing else). The cache key is
# built from exactly these values — never from UI state dicts, which contain
# placement and expansion state and would defeat the cache on every click.
_GEOMETRY_INPUT_IDS = [
    BIN_BASE_WIDTH_UNIT_INPUT_ID, BIN_BASE_LENGTH_UNIT_INPUT_ID,
    BIN_HEIGHT_UNIT_INPUT_ID, BIN_XY_CLEARANCE_INPUT_ID,
    BIN_WIDTH_INPUT_ID, BIN_LENGTH_INPUT_ID, BIN_HEIGHT_INPUT_ID,
    BIN_WALL_THICKNESS_INPUT_ID, BIN_GENERATE_BASE_INPUT_ID, BIN_GENERATE_BODY_INPUT_ID,
    BIN_SCREW_HOLES_INPUT_ID, BIN_SCREW_DIAMETER_INPUT,
    BIN_MAGNET_CUTOUTS_INPUT_ID, BIN_MAGNET_CUTOUTS_TABS_INPUT_ID,
    BIN_MAGNET_DIAMETER_INPUT, BIN_MAGNET_HEIGHT_INPUT,
    BIN_WITH_LIP_INPUT_ID, BIN_WITH_LIP_NOTCHES_INPUT_ID,
    BIN_HAS_SCOOP_INPUT_ID, BIN_SCOOP_MAX_RADIUS_INPUT_ID,
    BIN_HAS_TAB_INPUT_ID, BIN_TAB_LENGTH_INPUT_ID, BIN_TAB_WIDTH_INPUT_ID,
    BIN_TAB_POSITION_INPUT_ID, BIN_TAB_ANGLE_INPUT_ID,
    BIN_COMPARTMENTS_GRID_BASE_WIDTH_ID, BIN_COMPARTMENTS_GRID_BASE_LENGTH_ID,
]


def _geomCacheKey(inputs) -> str:
    values = []
    for inputId in _GEOMETRY_INPUT_IDS:
        item = inputs.itemById(inputId)
        values.append(item.value if item else None)
    for dropdownId in (BIN_TYPE_DROPDOWN_ID, BIN_COMPARTMENTS_GRID_TYPE_ID):
        dropdown = inputs.itemById(dropdownId)
        values.append(dropdown.selectedItem.name if dropdown and dropdown.selectedItem else None)
    table: adsk.core.TableCommandInput = inputs.itemById(BIN_COMPARTMENTS_TABLE_ID)
    if table:
        for i in range(1, table.rowCount):
            for j in range(table.numberOfColumns):
                values.append(table.getInputAtPosition(i, j).value)
    # Overhang amounts change the body geometry.
    ovh = _overhangAmounts(inputs)
    values.append([ovh['left'], ovh['right'], ovh['front'], ovh['back'],
                   sorted(k for k, v in ovh.get('partial', {}).items() if v)])
    return json.dumps(values)


# This event handler is called when the user clicks the OK button in the command dialog or
# is immediately called after the created event not command inputs were created for the dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Execute Event')
    _previewGraphics.clear()
    inputs = args.command.commandInputs
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        if des.designType == adsk.fusion.DesignTypes.DirectDesignType:
            raise UnsupportedDesignTypeException('Timeline must be enabled')
        params = _fullParams(inputs)
        tempBody = _getBinTempBody(des, inputs, _geomCacheKey(inputs))
        matrix, _ = binFeature.placementMatrix(des, params, world=False)
        placed = binFeature.placedCopy(tempBody, matrix)
        if _editedFeature is not None:
            # Tool cutouts live as separate downstream timeline features
            # (Combine), so they re-apply automatically after this body swap.
            _setEditedVisibility(True)
            binFeature.rebuildFeature(des, _editedFeature, placed, params)
        else:
            binFeature.createFeature(des, placed, params)
    except UnsupportedDesignTypeException:
        args.executeFailed = True
        args.executeFailedMessage = 'Design type is unsupported. Projects with disabled design history are unsupported, please enable timeline feature to proceed.'
        return False
    except Exception as err:
        args.executeFailed = True
        args.executeFailedMessage = getErrorMessage()
        futil.log(f'{CMD_NAME} Error occurred, {err}, {getErrorMessage()}')
        return False


# This event handler is called when the command needs to compute a new preview in the graphics window.
def command_preview(args: adsk.core.CommandEventArgs):
    futil.log(f'{CMD_NAME} Command Preview Event')
    inputs = args.command.commandInputs
    if not is_all_input_valid(inputs):
        args.executeFailed = True
        args.executeFailedMessage = "Some inputs are invalid, unable to generate preview"
        return
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        params = _placementParams(inputs)
        matrix, _ = binFeature.placementMatrix(des, params)
        # Fusion rolls the document back before every preview, which also kills
        # the previous graphics group — so ALWAYS redraw (cheap: ~10 ms). The
        # ghost geometry is a fast approximation; exact geometry is built on OK.
        tempBody = binFastPreview.buildPreviewBin(des, params, inputs)
        _previewGraphics.show(des.rootComponent, tempBody, None, matrix)
    except Exception as err:
        gplog.logExc('bin preview')
        args.executeFailed = True
        args.executeFailedMessage = getErrorMessage()


def command_mouse_click(args: adsk.core.MouseEventArgs):
    """Click on the baseplate -> snap the bin to the cell under the cursor.
    Ctrl+Click -> rotate by 90° instead (keyboard shortcuts collide with
    Fusion's global tool shortcuts and kill the dialog)."""
    try:
        inputs = args.firingEvent.sender.commandInputs
        if args.keyboardModifiers & adsk.core.KeyboardModifiers.CtrlKeyboardModifier:
            _cycleRotation(inputs)
            return
        params = _placementParams(inputs)
        if not params['plateToken']:
            return
        des = adsk.fusion.Design.cast(app.activeProduct)
        occ, grid, comp = binFeature.resolvePlate(des, params['plateToken'])
        if grid is None:
            return
        vp = args.viewport
        if vp is None:
            return
        # Ray from the camera eye through the clicked point, intersected with
        # the plate's top plane (local z=0).
        modelPt = vp.viewToModelSpace(args.viewportPosition)
        eye = vp.camera.eye
        inv = gridRegistry.gridTransform(grid, occ)
        inv.invert()
        localEye = eye.copy()
        localEye.transformBy(inv)
        localPt = modelPt.copy()
        localPt.transformBy(inv)
        direction = localEye.vectorTo(localPt)
        if abs(direction.z) < 1e-9:
            return
        t = -localEye.z / direction.z
        hitX = localEye.x + t * direction.x
        hitY = localEye.y + t * direction.y
        col = int((hitX - grid.originX) // grid.pitchX)
        row = int((hitY - grid.originY) // grid.pitchY)
        gplog.log(f'bin mouseClick: local hit=({hitX:.2f},{hitY:.2f}) -> cell ({col},{row})')
        params['col'], params['row'] = col, row
        col, row = binFeature.clampCell(grid, params)
        inputs.itemById(GRID_COL_INPUT).value = col + 1
        inputs.itemById(GRID_ROW_INPUT).value = row + 1
    except Exception:
        gplog.logExc('bin mouseClick')


def _cycleRotation(inputs):
    rotDropdown: adsk.core.DropDownCommandInput = inputs.itemById(GRID_ROTATION_DROPDOWN)
    current = int(rotDropdown.selectedItem.name) if rotDropdown.selectedItem else 0
    target = str((current + 90) % 360)
    for item in rotDropdown.listItems:
        if item.name == target:
            item.isSelected = True
            break
    gplog.log(f'bin rotation {current} -> {target}')


# NOTE: no keyboard handler on purpose — letter keys are Fusion global tool
# shortcuts (pressing R terminates this dialog before any key event arrives).
# Rotation: Ctrl+Click in the viewport or the "Rotate 90°" button.

def cache_compartments_table_state(inputs: adsk.core.CommandInputs):
    binCompartmentsTable: adsk.core.TableCommandInput = inputs.itemById(BIN_COMPARTMENTS_TABLE_ID)
    global commandCompartmentsTableUIState
    commandCompartmentsTableUIState = []
    for i in range(1, binCompartmentsTable.rowCount):
        commandCompartmentsTableUIState.append(CommandUiState(CMD_NAME))
        for j in range(binCompartmentsTable.numberOfColumns):
            input = binCompartmentsTable.getInputAtPosition(i, j)
            commandCompartmentsTableUIState[-1].initValue(input.id, input.value, input.objectType)
            commandCompartmentsTableUIState[-1].registerCommandInput(input)

def _syncTypeVisibility(inputs):
    """Compartments (incl. scoop / label tab) only exist for Hollow bins."""
    try:
        typeInput = inputs.itemById(BIN_TYPE_DROPDOWN_ID)
        hollow = bool(typeInput and typeInput.selectedItem and typeInput.selectedItem.name == BIN_TYPE_HOLLOW)
        group = inputs.itemById(BIN_COMPARTMENTS_GROUP_ID)
        if group is not None and group.isVisible != hollow:
            group.isVisible = hollow
    except Exception:
        gplog.logExc('syncTypeVisibility')


def _syncHeight(inputs):
    """Height mode -> visibility + effective unit count in BIN_HEIGHT_INPUT_ID."""
    try:
        modeInput = inputs.itemById(BIN_HEIGHT_MODE_ID)
        mode = modeInput.selectedItem.name if modeInput and modeInput.selectedItem else HEIGHT_MODE_UNITS
        unitsInput = inputs.itemById(BIN_HEIGHT_UNITS_ID)
        mmInput = inputs.itemById(BIN_HEIGHT_MM_ID)
        hUnit = inputs.itemById(BIN_HEIGHT_UNIT_INPUT_ID).value
        if unitsInput.isVisible != (mode == HEIGHT_MODE_UNITS):
            unitsInput.isVisible = mode == HEIGHT_MODE_UNITS
        if mmInput.isVisible != (mode == HEIGHT_MODE_MM):
            mmInput.isVisible = mode == HEIGHT_MODE_MM
        if mode == HEIGHT_MODE_UNITS:
            effH = float(unitsInput.value)
        else:
            effH = mmInput.value / hUnit if hUnit > 0 else 1.0
        if abs(float(commandUIState.getState(BIN_HEIGHT_INPUT_ID)) - effH) > 1e-9:
            commandUIState.updateValue(BIN_HEIGHT_INPUT_ID, effH)
    except Exception:
        gplog.logExc('syncHeight')


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    changed_input = args.input
    inputs = args.inputs
    global commandUIState
    if changed_input.id in (BIN_HEIGHT_MODE_ID, BIN_HEIGHT_UNITS_ID, BIN_HEIGHT_MM_ID, BIN_HEIGHT_UNIT_INPUT_ID):
        commandUIState.onInputUpdate(changed_input)
        _syncHeight(args.firingEvent.sender.commandInputs)
    if changed_input.id == BIN_TYPE_DROPDOWN_ID:
        _syncTypeVisibility(args.firingEvent.sender.commandInputs)
    futil.log(f'{CMD_NAME} Input Changed Event fired from a change to {changed_input.id}')
    # Grid placement inputs only move the ghost — skip the heavy UI refresh
    # cascade (forceUIRefresh re-sets every input and re-fires events).
    if changed_input.id == GRID_ROTATE_BUTTON:
        _cycleRotation(inputs)
        return
    if changed_input.id in (GRID_COL_INPUT, GRID_ROW_INPUT, GRID_ROTATION_DROPDOWN,
                            GRID_PLATE_DROPDOWN, GRID_PLACEMENT_GROUP,
                            GRID_OVERHANG_LEFT, GRID_OVERHANG_RIGHT,
                            GRID_OVERHANG_FRONT, GRID_OVERHANG_BACK):
        return
    if changed_input.id == INPUT_CHANGES_SAVE_DEFAULTS:
        saveUIInputsAsDefaults()
    elif changed_input.id == INPUT_CHANGES_RESET_TO_DEFAULTS:
        initDefaultUiState()
        refreshUi()
    elif changed_input.id == INPUT_CHANGES_RESET_TO_FACTORY:
        configUtils.deleteConfigFile(UI_INPUT_DEFAULTS_CONFIG_PATH)
        initDefaultUiState()
        refreshUi()
    elif changed_input.parentCommandInput and changed_input.parentCommandInput.id == BIN_COMPARTMENTS_TABLE_ID:
        cache_compartments_table_state(inputs)
    else:
        commandUIState.onInputUpdate(changed_input)
        refreshUi()

    if isinstance(changed_input, adsk.core.GroupCommandInput) and changed_input.isExpanded == True:
        for input in changed_input.children:
            commandUIState.registerCommandInput(input)
        refreshUi()

    binCompartmentsTable: adsk.core.TableCommandInput = inputs.itemById(BIN_COMPARTMENTS_TABLE_ID)

    try:
        binHeightUnit = commandUIState.getState(BIN_HEIGHT_UNIT_INPUT_ID)
        binHeight = commandUIState.getState(BIN_HEIGHT_INPUT_ID)
        compartmentsGridWidth = commandUIState.getState(BIN_COMPARTMENTS_GRID_BASE_WIDTH_ID)
        compartmentsGridLength = commandUIState.getState(BIN_COMPARTMENTS_GRID_BASE_LENGTH_ID)

        if changed_input.id == BIN_COMPARTMENTS_TABLE_ADD_ID:
            append_compartment_table_row(0, 0, 1, 1, (binHeight + 1) * binHeightUnit - const.BIN_BASE_HEIGHT)
            cache_compartments_table_state(inputs)
        elif changed_input.id == BIN_COMPARTMENTS_TABLE_REMOVE_ID:
            if binCompartmentsTable.selectedRow > 0:
                deleteTableRow(binCompartmentsTable.selectedRow, binCompartmentsTable, commandCompartmentsTableUIState)
            elif binCompartmentsTable.rowCount > 1:
                deleteTableRow(binCompartmentsTable.rowCount - 1, binCompartmentsTable, commandCompartmentsTableUIState)
        elif changed_input.id == BIN_COMPARTMENTS_TABLE_UNIFORM_ID:
            for i in range(binCompartmentsTable.rowCount - 1, 0, -1):
                deleteTableRow(i, binCompartmentsTable, commandCompartmentsTableUIState)
            for i in range(compartmentsGridWidth):
                for j in range(compartmentsGridLength):
                    append_compartment_table_row(i, j, 1, 1, (binHeight + 1) * binHeightUnit - const.BIN_BASE_HEIGHT)
                cache_compartments_table_state(inputs)

    except:
        showErrorInMessageBox()



# This event handler is called when the user interacts with any of the inputs in the dialog
# which allows you to verify that all of the inputs are valid and enables the OK button.
def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Validate Input Event')

    inputs = args.inputs

    # Verify the validity of the input values. This controls if the OK button is enabled or not.
    args.areInputsValid = is_all_input_valid(inputs)
    futil.log(f'{CMD_NAME} Inputs are {"valid" if args.areInputsValid else "invalid"}')


# This event handler is called when the command terminates.
def command_destroy(args: adsk.core.CommandEventArgs):
    # General logging for debug.
    futil.log(f'{CMD_NAME} Command Destroy Event "{args.terminationReason}"')
    global local_handlers, _editedFeature
    _previewGraphics.clear()
    _setEditedVisibility(True)
    _editedFeature = None
    local_handlers = []

def deleteTableRow(rowToDelete: int, tableInput: adsk.core.TableCommandInput, inputState: list[CommandUiState]):
    inputState.pop(rowToDelete - 1)
    tableInput.deleteRow(rowToDelete)

def refreshCompartmentsTable():
    global commandUIState
    binCompartmentsTable: adsk.core.TableCommandInput = commandUIState.getInput(BIN_COMPARTMENTS_TABLE_ID)
    for i in range(binCompartmentsTable.rowCount - 1, 0, -1):
        binCompartmentsTable.deleteRow(i)
    append_compartments_from_state()


def onChangeValidate():
    global commandUIState

    generateBase: bool = commandUIState.getState(BIN_GENERATE_BASE_INPUT_ID)
    commandUIState.getInput(BIN_SCREW_HOLES_INPUT_ID).isEnabled = generateBase
    commandUIState.getInput(BIN_MAGNET_CUTOUTS_INPUT_ID).isEnabled = generateBase
    commandUIState.getInput(BIN_MAGNET_CUTOUTS_TABS_INPUT_ID).isEnabled = generateBase
    commandUIState.getInput(BIN_MAGNET_DIAMETER_INPUT).isEnabled = generateBase
    commandUIState.getInput(BIN_MAGNET_HEIGHT_INPUT).isEnabled = generateBase
    commandUIState.getInput(BIN_SCREW_DIAMETER_INPUT).isEnabled = generateBase

    generateBody: bool = commandUIState.getState(BIN_GENERATE_BODY_INPUT_ID)
    binType: str = commandUIState.getState(BIN_TYPE_DROPDOWN_ID)
    commandUIState.getInput(BIN_WALL_THICKNESS_INPUT_ID).isEnabled = generateBody and not binType == BIN_TYPE_SOLID
    commandUIState.getInput(BIN_WITH_LIP_INPUT_ID).isEnabled = generateBody
    commandUIState.getInput(BIN_WITH_LIP_NOTCHES_INPUT_ID).isEnabled = generateBody
    commandUIState.getInput(BIN_HAS_TAB_INPUT_ID).isEnabled = generateBody
    generateTab: bool = commandUIState.getState(BIN_HAS_TAB_INPUT_ID)
    for input in commandUIState.getInput(BIN_TAB_FEATURES_GROUP_ID).children:
        if not input.id == BIN_HAS_TAB_INPUT_ID:
            input.isEnabled = generateBody and generateTab

    generateLip: bool = commandUIState.getState(BIN_WITH_LIP_INPUT_ID)
    commandUIState.getInput(BIN_WITH_LIP_NOTCHES_INPUT_ID).isEnabled = generateLip

    generateScoop: bool = commandUIState.getState(BIN_HAS_SCOOP_INPUT_ID)
    commandUIState.getInput(BIN_SCOOP_MAX_RADIUS_INPUT_ID).isEnabled = generateScoop

    generateTab: bool = commandUIState.getState(BIN_HAS_TAB_INPUT_ID)
    commandUIState.getInput(BIN_TAB_LENGTH_INPUT_ID).isEnabled = generateTab
    commandUIState.getInput(BIN_TAB_WIDTH_INPUT_ID).isEnabled = generateTab
    commandUIState.getInput(BIN_TAB_ANGLE_INPUT_ID).isEnabled = generateTab
    commandUIState.getInput(BIN_TAB_POSITION_INPUT_ID).isEnabled = generateTab

    compartmentsGridType: str = commandUIState.getState(BIN_COMPARTMENTS_GRID_TYPE_ID)
    commandUIState.getInput(BIN_COMPARTMENTS_TABLE_ID).isVisible = compartmentsGridType == BIN_COMPARTMENTS_GRID_TYPE_CUSTOM

def saveUIInputsAsDefaults():
    futil.log(f'{CMD_NAME} Saving UI state to file')
    result = configUtils.dumpJsonConfig(UI_INPUT_DEFAULTS_CONFIG_PATH, {
        'static_ui': commandUIState.toDict(ignoreKeys=[SHOW_PREVIEW_MANUAL_INPUT, SHOW_PREVIEW_INPUT]),
        'compartments_table': [x.toDict() for x in commandCompartmentsTableUIState]
        })
    if result:
        futil.log(f'{CMD_NAME} Saved successfully')
    else:
        futil.log(f'{CMD_NAME} UI state failed to save')

def _getBinTempBody(des: adsk.fusion.Design, inputs: adsk.core.CommandInputs, cacheKey: str):
    """Build the FULL bin (all upstream features) into an isolated scratch
    component, return an independent temp BRep of the result. Cached by the
    complete dialog geometry state, so previews/moves after the first build of
    a configuration are instant."""
    cached = binFeature.getCachedBody(cacheKey)
    if cached is not None:
        gplog.log('_getBinTempBody: cache HIT')
        return cached

    base_width_unit: adsk.core.ValueCommandInput = inputs.itemById(BIN_BASE_WIDTH_UNIT_INPUT_ID)
    base_length_unit: adsk.core.ValueCommandInput = inputs.itemById(BIN_BASE_LENGTH_UNIT_INPUT_ID)
    height_unit: adsk.core.ValueCommandInput = inputs.itemById(BIN_HEIGHT_UNIT_INPUT_ID)
    xy_clearance: adsk.core.ValueCommandInput = inputs.itemById(BIN_XY_CLEARANCE_INPUT_ID)
    bin_width: adsk.core.ValueCommandInput = inputs.itemById(BIN_WIDTH_INPUT_ID)
    bin_length: adsk.core.ValueCommandInput = inputs.itemById(BIN_LENGTH_INPUT_ID)
    bin_height: adsk.core.ValueCommandInput = inputs.itemById(BIN_HEIGHT_INPUT_ID)
    bin_wall_thickness: adsk.core.ValueCommandInput = inputs.itemById(BIN_WALL_THICKNESS_INPUT_ID)
    bin_screw_holes: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_SCREW_HOLES_INPUT_ID)
    bin_generate_base: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_GENERATE_BASE_INPUT_ID)
    bin_generate_body: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_GENERATE_BODY_INPUT_ID)
    bin_magnet_cutouts: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_MAGNET_CUTOUTS_INPUT_ID)
    bin_screw_hole_diameter: adsk.core.ValueCommandInput = inputs.itemById(BIN_SCREW_DIAMETER_INPUT)
    bin_magnet_cutouts_tabs: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_MAGNET_CUTOUTS_TABS_INPUT_ID)
    bin_magnet_cutout_diameter: adsk.core.ValueCommandInput = inputs.itemById(BIN_MAGNET_DIAMETER_INPUT)
    bin_magnet_cutout_depth: adsk.core.ValueCommandInput = inputs.itemById(BIN_MAGNET_HEIGHT_INPUT)
    with_lip: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_WITH_LIP_INPUT_ID)
    with_lip_notches: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_WITH_LIP_NOTCHES_INPUT_ID)
    has_scoop: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_HAS_SCOOP_INPUT_ID)
    binScoopMaxRadius: adsk.core.ValueCommandInput = inputs.itemById(BIN_SCOOP_MAX_RADIUS_INPUT_ID)
    hasTabInput: adsk.core.BoolValueCommandInput = inputs.itemById(BIN_HAS_TAB_INPUT_ID)
    binTabLength: adsk.core.ValueCommandInput = inputs.itemById(BIN_TAB_LENGTH_INPUT_ID)
    binTabWidth: adsk.core.ValueCommandInput = inputs.itemById(BIN_TAB_WIDTH_INPUT_ID)
    binTabPosition: adsk.core.ValueCommandInput = inputs.itemById(BIN_TAB_POSITION_INPUT_ID)
    binTabAngle: adsk.core.ValueCommandInput = inputs.itemById(BIN_TAB_ANGLE_INPUT_ID)
    binTypeDropdownInput: adsk.core.DropDownCommandInput = inputs.itemById(BIN_TYPE_DROPDOWN_ID)
    binCompartmentGridTypeDropdownInput: adsk.core.DropDownCommandInput = inputs.itemById(BIN_COMPARTMENTS_GRID_TYPE_ID)
    binCompartmentsTable: adsk.core.TableCommandInput = inputs.itemById(BIN_COMPARTMENTS_TABLE_ID)
    compartmentsX: adsk.core.IntegerSpinnerCommandInput = inputs.itemById(BIN_COMPARTMENTS_GRID_BASE_WIDTH_ID)
    compartmentsY: adsk.core.IntegerSpinnerCommandInput = inputs.itemById(BIN_COMPARTMENTS_GRID_BASE_LENGTH_ID)

    isHollow = binTypeDropdownInput.selectedItem.name == BIN_TYPE_HOLLOW
    isSolid = binTypeDropdownInput.selectedItem.name == BIN_TYPE_SOLID
    isShelled = binTypeDropdownInput.selectedItem.name == BIN_TYPE_SHELLED

    root = adsk.fusion.Component.cast(des.rootComponent)
    xyClearance = xy_clearance.value
    startCount = des.timeline.count

    with gplog.timed('bin generator (parametric build)'):
        gridfinityBinComponent = scratchUtils.createScratchComponent(des)
        features: adsk.fusion.Features = gridfinityBinComponent.features

        # create base interface
        baseGeneratorInput = BaseGeneratorInput()
        baseGeneratorInput.originPoint = geometryUtils.createOffsetPoint(
            gridfinityBinComponent.originConstructionPoint.geometry,
            byX=-xyClearance,
            byY=-xyClearance,
        )
        baseGeneratorInput.baseWidth = base_width_unit.value
        baseGeneratorInput.baseLength = base_length_unit.value
        baseGeneratorInput.xyClearance = xyClearance
        baseGeneratorInput.hasScrewHoles = bin_screw_holes.value and not isShelled
        baseGeneratorInput.hasMagnetCutouts = bin_magnet_cutouts.value and not isShelled
        baseGeneratorInput.hasMagnetCutoutsTabs = bin_magnet_cutouts_tabs.value and not isShelled
        baseGeneratorInput.screwHolesDiameter = bin_screw_hole_diameter.value
        baseGeneratorInput.magnetCutoutsDiameter = bin_magnet_cutout_diameter.value
        baseGeneratorInput.magnetCutoutsDepth = bin_magnet_cutout_depth.value

        # Extension over the plate's border / partial cells (bin-local sides).
        ovh = _overhangAmounts(inputs)
        part = ovh.get('partial', {})
        extraL = 1 if part.get('left') else 0
        extraR = 1 if part.get('right') else 0
        extraF = 1 if part.get('front') else 0
        extraB = 1 if part.get('back') else 0

        baseBodies: list[adsk.fusion.BRepBody]
        if bin_generate_base.value:
            # Partial cell on a side: add a full row/column of feet there; the
            # clearance cut below trims it to the partial width (cut foot that
            # matches the plate's cut pocket).
            footInput = baseGeneratorInput
            if extraL or extraF:
                footInput = BaseGeneratorInput()
                for attr in ('baseWidth', 'baseLength', 'xyClearance', 'hasScrewHoles',
                             'hasMagnetCutouts', 'hasMagnetCutoutsTabs', 'screwHolesDiameter',
                             'magnetCutoutsDiameter', 'magnetCutoutsDepth'):
                    setattr(footInput, attr, getattr(baseGeneratorInput, attr))
                footInput.originPoint = geometryUtils.createOffsetPoint(
                    gridfinityBinComponent.originConstructionPoint.geometry,
                    byX=-xyClearance - extraL * base_width_unit.value,
                    byY=-xyClearance - extraF * base_length_unit.value,
                )
            baseBodies = createBaseBodyPattern(
                footInput,
                bin_width.value + extraL + extraR,
                bin_length.value + extraF + extraB,
                gridfinityBinComponent,
            )
            gplog.log(f'binBuild: partial feet extra L{extraL} R{extraR} F{extraF} B{extraB}')

        # create bin body
        # Overhang over plate padding: widen the BODY (not the feet) by the
        # padding amounts. The generator derives the body size from
        # baseWidth * binWidth, so we inflate the per-unit size accordingly and
        # shift the finished body so the feet stay aligned to the grid cells.
        extW = ovh['left'] + ovh['right']
        extL = ovh['front'] + ovh['back']
        binBodyInput = BinBodyGeneratorInput()
        binBodyInput.hasLip = with_lip.value
        binBodyInput.hasLipNotches = with_lip_notches.value
        binBodyInput.binWidth = bin_width.value
        binBodyInput.binLength = bin_length.value
        binBodyInput.binHeight = bin_height.value
        binBodyInput.baseWidth = base_width_unit.value + extW / bin_width.value
        binBodyInput.baseLength = base_length_unit.value + extL / bin_length.value
        binBodyInput.heightUnit = height_unit.value
        binBodyInput.xyClearance = xyClearance
        binBodyInput.binCornerFilletRadius = const.BIN_CORNER_FILLET_RADIUS - xyClearance
        binBodyInput.isSolid = isSolid or isShelled
        binBodyInput.wallThickness = bin_wall_thickness.value
        binBodyInput.hasScoop = has_scoop.value and isHollow
        binBodyInput.scoopMaxRadius = binScoopMaxRadius.value
        binBodyInput.hasTab = hasTabInput.value and isHollow
        binBodyInput.tabLength = binTabLength.value
        binBodyInput.tabWidth = binTabWidth.value
        binBodyInput.tabPosition = binTabPosition.value
        binBodyInput.tabOverhangAngle = binTabAngle.value
        binBodyInput.compartmentsByX = compartmentsX.value
        binBodyInput.compartmentsByY = compartmentsY.value

        if binCompartmentGridTypeDropdownInput.selectedItem.name == BIN_COMPARTMENTS_GRID_TYPE_UNIFORM:
            binBodyInput.compartments = uniformCompartments(binBodyInput.compartmentsByX, binBodyInput.compartmentsByY)
        else:
            binBodyInput.compartments = []
            for i in range(1, binCompartmentsTable.rowCount):
                positionX: adsk.core.IntegerSpinnerCommandInput = binCompartmentsTable.getInputAtPosition(i, 0)
                positionY: adsk.core.IntegerSpinnerCommandInput = binCompartmentsTable.getInputAtPosition(i, 1)
                width: adsk.core.IntegerSpinnerCommandInput = binCompartmentsTable.getInputAtPosition(i, 2)
                length: adsk.core.IntegerSpinnerCommandInput = binCompartmentsTable.getInputAtPosition(i, 3)
                depth: adsk.core.ValueCommandInput = binCompartmentsTable.getInputAtPosition(i, 4)
                binBodyInput.compartments.append(BinBodyCompartmentDefinition(positionX.value, positionY.value, width.value, length.value, depth.value))

        binBody: adsk.fusion.BRepBody

        def _bbox(tag, body):
            try:
                bb = body.boundingBox
                gplog.log(f'binBuild bbox[{tag}]: x[{bb.minPoint.x:.3f},{bb.maxPoint.x:.3f}] '
                          f'y[{bb.minPoint.y:.3f},{bb.maxPoint.y:.3f}] faces={body.faces.count}')
            except Exception:
                gplog.logExc(f'bbox {tag}')

        gplog.log(f'binBuild: ovh={ovh} extW={extW:.3f} extL={extL:.3f} '
                  f'baseW\'={binBodyInput.baseWidth:.4f} baseL\'={binBodyInput.baseLength:.4f}')

        if bin_generate_body.value:
            binBody = createGridfinityBinBody(
                binBodyInput,
                gridfinityBinComponent,
            )
            _bbox('after body gen', binBody)
            if ovh['left'] > 0 or ovh['front'] > 0:
                # Re-anchor the widened body so the feet stay on the grid.
                moveFeats = gridfinityBinComponent.features.moveFeatures
                shift = adsk.core.Matrix3D.create()
                shift.translation = adsk.core.Vector3D.create(-ovh['left'], -ovh['front'], 0)
                moveInput = moveFeats.createInput2(commonUtils.objectCollectionFromList([binBody]))
                moveInput.defineAsFreeMove(shift)
                moveFeats.add(moveInput)
                _bbox('after move', binBody)
        if bin_generate_body.value or bin_generate_base.value:
            # cutBaseClearance trims EVERYTHING outside its rectangle (full-height
            # cut). With body overhang the keep-rectangle must be the enlarged
            # body outline, not the feet outline — otherwise the overhang gets
            # sheared off and walls end up open.
            clearanceInput = baseGeneratorInput
            if extW > 0 or extL > 0:
                clearanceInput = BaseGeneratorInput()
                clearanceInput.baseWidth = binBodyInput.baseWidth
                clearanceInput.baseLength = binBodyInput.baseLength
                clearanceInput.xyClearance = xyClearance
                clearanceInput.originPoint = geometryUtils.createOffsetPoint(
                    gridfinityBinComponent.originConstructionPoint.geometry,
                    byX=-xyClearance - ovh['left'],
                    byY=-xyClearance - ovh['front'],
                )
            cutBaseClearance(
                clearanceInput,
                bin_width.value,
                bin_length.value,
                gridfinityBinComponent,
            )
            if bin_generate_body.value:
                _bbox('after clearance cut', binBody)

        combineFeatures = gridfinityBinComponent.features.combineFeatures

        # merge everything
        if bin_generate_body.value and bin_generate_base.value:
            toolBodies = commonUtils.objectCollectionFromList(baseBodies)
            combineFeatureInput = combineFeatures.createInput(binBody, toolBodies)
            combineFeatures.add(combineFeatureInput)

        if isShelled and bin_generate_body.value:
            # face.boundingBox.maxPoint.z ~ face.boundingBox.minPoint.z => face horizontal
            # largest horizontal face
            horizontalFaces = [face for face in binBody.faces if geometryUtils.isHorizontal(face)]
            topFace = faceUtils.maxByArea(horizontalFaces)
            topFaceMinPoint = topFace.boundingBox.minPoint
            if binBodyInput.hasLip:
                splitBodyFeatures = features.splitBodyFeatures
                splitBodyInput = splitBodyFeatures.createInput(
                    binBody,
                    topFace,
                    True
                )
                splitBodies = splitBodyFeatures.add(splitBodyInput)
                bottomBody = min(splitBodies.bodies, key=lambda x: x.boundingBox.minPoint.z)
                topBody = max(splitBodies.bodies, key=lambda x: x.boundingBox.minPoint.z)
                horizontalFaces = [face for face in bottomBody.faces if geometryUtils.isHorizontal(face)]
                topFace = faceUtils.maxByArea(horizontalFaces)
                shellUtils.simpleShell([topFace], binBodyInput.wallThickness - xyClearance, gridfinityBinComponent)
                toolBodies = adsk.core.ObjectCollection.create()
                toolBodies.add(topBody)
                combineAfterShellFeatureInput = combineFeatures.createInput(bottomBody, toolBodies)
                combineFeatures.add(combineAfterShellFeatureInput)
                binBody = scratchUtils.ownBodies(gridfinityBinComponent)[0]
            else:
                shellUtils.simpleShell([topFace], binBodyInput.wallThickness - xyClearance, gridfinityBinComponent)

            if hasTabInput.value:
                compartmentTabInput = BinBodyTabGeneratorInput()
                tabOriginPoint = adsk.core.Point3D.create(
                    binBodyInput.wallThickness + max(0, min(binBodyInput.tabPosition, binBodyInput.binWidth - binBodyInput.tabLength)) * binBodyInput.baseWidth,
                    const.BIN_LIP_WALL_THICKNESS if binBodyInput.hasLip and binBodyInput.hasScoop else binBodyInput.wallThickness + binBodyInput.binLength * binBodyInput.baseLength - binBodyInput.wallThickness - binBodyInput.xyClearance * 2,
                    (binBodyInput.binHeight - 1) * binBodyInput.heightUnit + max(0, binBodyInput.heightUnit - const.BIN_BASE_HEIGHT),
                )
                compartmentTabInput.origin = tabOriginPoint
                compartmentTabInput.length = max(0, min(binBodyInput.tabLength, binBodyInput.binWidth)) * binBodyInput.baseWidth - binBodyInput.wallThickness * 2 - binBodyInput.xyClearance * 2
                compartmentTabInput.width = binBodyInput.tabWidth
                compartmentTabInput.overhangAngle = binBodyInput.tabOverhangAngle
                compartmentTabInput.topClearance = const.BIN_TAB_TOP_CLEARANCE
                tabBody = createGridfinityBinBodyTab(compartmentTabInput, gridfinityBinComponent)
                combineInput = combineFeatures.createInput(tabBody, commonUtils.objectCollectionFromList([binBody]))
                combineInput.operation = adsk.fusion.FeatureOperations.CutFeatureOperation
                combineInput.isKeepToolBodies = True
                combineFeature = combineFeatures.add(combineInput)
                tabBodies = [body for body in combineFeature.bodies if body.faces != binBody.faces]
                tabMainBody = max([body for body in tabBodies], key=lambda x: x.edges.count)
                bodiesToRemove = [body for body in tabBodies if body is not tabMainBody]
                for body in bodiesToRemove:
                    gridfinityBinComponent.features.removeFeatures.add(body)
                combineUtils.joinBodies(binBody, commonUtils.objectCollectionFromList([tabMainBody]), gridfinityBinComponent)

        # Union everything that is left in the scratch component into ONE temp
        # body (base-only mode leaves separate feet, for example).
        tmgr = adsk.fusion.TemporaryBRepManager.get()
        scratchBodies = scratchUtils.ownBodies(gridfinityBinComponent)
        gplog.log(f'binBuild: final scratch bodies={len(scratchBodies)}')
        for i, b in enumerate(scratchBodies):
            _bbox(f'final body #{i}', b)
        tempBody = None
        for b in scratchBodies:
            piece = tmgr.copy(b)
            if tempBody is None:
                tempBody = piece
            else:
                tmgr.booleanOperation(tempBody, piece, adsk.fusion.BooleanTypes.UnionBooleanType)

    with gplog.timed('bin scratch cleanup'):
        lastIndex = des.timeline.count - 1
        if lastIndex >= startCount:
            group = des.timeline.timelineGroups.add(startCount, lastIndex)
            group.deleteMe(True)
        scratchUtils.release()

    if tempBody is None or tempBody.faces.count == 0:
        raise RuntimeError('Generated bin body is empty')
    binFeature.setCachedBody(cacheKey, tempBody)
    gplog.log(f'_getBinTempBody: built, faces={tempBody.faces.count}, cached')
    return tempBody
