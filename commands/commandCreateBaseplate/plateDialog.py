"""
GridfinityPlus — baseplate dialog definition, shared by Create and Edit.

One table (FIELDS) defines every value input: id (kept compatible with saved
defaults), params key, kind, label, default, limits. build() creates the
inputs grouped like this:

    Size        whole cells (columns/rows + border padding) or exact width/depth
    Placement   place on plane/face, optional custom anchor, rotation, offsets
    Grid unit   cell size, bin fit clearance
    Style       plate type, magnets, screws
    Advanced    floor thickness, clearances, connector holes

readParams() turns the dialog back into the params dict the generators use.
"""

import adsk.core, adsk.fusion

from ...lib.gridfinityUtils import const
from ...lib.gridfinityUtils import placement
from ...lib.gridfinityUtils import plateLayout
from ...lib.gridfinityUtils import plateSplit
from ...lib.gridfinityUtils import gplog
from ...lib.gridfinityUtils.const import DIMENSION_DEFAULT_WIDTH_UNIT

def _get(inputs, fid):
    return inputs.itemById(fid)


# ---------------------------------------------------------------- group ids
INFO_GROUP = 'info_group'
SIZE_GROUP = 'xy_dimensions'
PLACEMENT_GROUP = 'placement_group'
GRID_UNIT_GROUP = 'basic_sizes'
STYLE_GROUP = 'plate_features'
MAGNET_GROUP = 'magnet_cutout_group'
SCREW_GROUP = 'screw_hole_group'
ADVANCED_GROUP = 'advanced_plate_size_group'
SPLIT_GROUP = 'split_group'
SPLIT_MODE = 'split_mode'
SPLIT_MAX_W = 'split_max_width'
SPLIT_MAX_D = 'split_max_depth'
SPLIT_CONNECTOR = 'split_connector'
SPLIT_CLEARANCE = 'split_clearance'
SPLIT_INFO = 'split_info'

# ------------------------------------------------------- non-table input ids
SIZE_INFO_SIZE = 'size_info_size'
SIZE_INFO_CELLS = 'size_info_cells'
PLACE_ON_INPUT = 'placement_plane'
ANCHOR_POINT_INPUT = 'placement_point'

# ---------------------------------------------------------------- value ids
COLUMNS = 'plate_width'
ROWS = 'plate_length'
EXACT_WIDTH = 'plate_size_width'
EXACT_DEPTH = 'plate_size_depth'
CUSTOM_ANCHOR = 'placement_custom_anchor'
ANCHOR_ALIGN = 'placement_anchor'
ROTATION = 'placement_rotation'
OFFSET_X = 'placement_offset_x'
OFFSET_Y = 'placement_offset_y'
OFFSET_Z = 'placement_offset_z'
CELL_WIDTH = 'base_width_unit'
CELL_DEPTH = 'base_length_unit'
CLEARANCE = 'bin_xy_clearance'
PLATE_TYPE = 'plate_type_dropdown'
WITH_MAGNETS = 'with_magnet_cutouts'
MAGNET_DIAMETER = 'magnet_diameter'
MAGNET_DEPTH = 'magnet_height'
WITH_SCREWS = 'with_screw_holes'
SCREW_DIAMETER = 'screw_diameter'
SCREW_HEAD = 'screw_head_diameter'
FLOOR_EXTRA = 'extra_bottom_thickness'
BIN_Z_CLEARANCE = 'bin_z_clearance'
WITH_CONNECTORS = 'has_connection_hole'
CONNECTOR_DIAMETER = 'connection_hole_diameter'

PLATE_TYPES = ('Light', 'Skeletonized', 'Full')

SIZE_MODE = 'size_mode'
BORDER_LEFT = 'border_left'
BORDER_RIGHT = 'border_right'
BORDER_FRONT = 'border_front'
BORDER_BACK = 'border_back'
EDGE_LEFT = 'edge_left'
EDGE_RIGHT = 'edge_right'
EDGE_FRONT = 'edge_front'
EDGE_BACK = 'edge_back'
EDGE_TOOLTIP = ('Flush: the plate ends with a whole cell.\n'
                'Border: solid border.\n'
                'Partial cell: an extra cell that is cut.\n'
                'Cells: you set the size of border / partial cell. Exact size: automatic.')

# (id, params key, kind, label, default, extra)
#   kind: bool | int | length | offset | choice ; extra: dict(min, max, choices, tooltip)
FIELDS = [
    # Size group is laid out by hand in build() (tables), 'group' is informational.
    (SIZE_MODE, plateLayout.KEY_SIZE_MODE, 'choice', 'Size by', plateLayout.SIZE_CELLS, dict(
        group=SIZE_GROUP, manual=True, choices=plateLayout.SIZE_MODES,
        tooltip='Cells: number of columns/rows, border width per side set by you.\n'
                'Exact size: total width/depth; whole cells first, the leftover becomes '
                'border or partial cells (split evenly over the non-flush sides).')),
    (COLUMNS, 'plateWidth', 'int', 'Columns', 2, dict(group=SIZE_GROUP, manual=True, min=1, max=100,
        tooltip='Cells from left to right')),
    (ROWS, 'plateLength', 'int', 'Rows', 3, dict(group=SIZE_GROUP, manual=True, min=1, max=100,
        tooltip='Cells from front to back')),
    (EXACT_WIDTH, plateLayout.KEY_WIDTH, 'length', 'Width', 20.0, dict(group=SIZE_GROUP, manual=True, min=0.5,
        tooltip='Total size left to right')),
    (EXACT_DEPTH, plateLayout.KEY_DEPTH, 'length', 'Depth', 15.0, dict(group=SIZE_GROUP, manual=True, min=0.5,
        tooltip='Total size front to back')),
    (EDGE_LEFT, plateLayout.KEY_EDGE_LEFT, 'choice', 'Left edge', plateLayout.EDGE_FLUSH, dict(
        group=SIZE_GROUP, manual=True, choices=plateLayout.EDGE_CHOICES, tooltip=EDGE_TOOLTIP)),
    (EDGE_RIGHT, plateLayout.KEY_EDGE_RIGHT, 'choice', 'Right edge', plateLayout.EDGE_FLUSH, dict(
        group=SIZE_GROUP, manual=True, choices=plateLayout.EDGE_CHOICES, tooltip=EDGE_TOOLTIP)),
    (EDGE_FRONT, plateLayout.KEY_EDGE_FRONT, 'choice', 'Front edge', plateLayout.EDGE_FLUSH, dict(
        group=SIZE_GROUP, manual=True, choices=plateLayout.EDGE_CHOICES, tooltip=EDGE_TOOLTIP)),
    (EDGE_BACK, plateLayout.KEY_EDGE_BACK, 'choice', 'Back edge', plateLayout.EDGE_FLUSH, dict(
        group=SIZE_GROUP, manual=True, choices=plateLayout.EDGE_CHOICES, tooltip=EDGE_TOOLTIP)),
    (BORDER_LEFT, plateLayout.KEY_BORDER_LEFT, 'length', 'Left size', 0.5, dict(group=SIZE_GROUP, manual=True, min=0,
        tooltip='Width of the border, or how much of the partial cell remains')),
    (BORDER_RIGHT, plateLayout.KEY_BORDER_RIGHT, 'length', 'Right size', 0.5, dict(group=SIZE_GROUP, manual=True, min=0,
        tooltip='Width of the border, or how much of the partial cell remains')),
    (BORDER_FRONT, plateLayout.KEY_BORDER_FRONT, 'length', 'Front size', 0.5, dict(group=SIZE_GROUP, manual=True, min=0,
        tooltip='Width of the border, or how much of the partial cell remains')),
    (BORDER_BACK, plateLayout.KEY_BORDER_BACK, 'length', 'Back size', 0.5, dict(group=SIZE_GROUP, manual=True, min=0,
        tooltip='Width of the border, or how much of the partial cell remains')),

    (CUSTOM_ANCHOR, placement.KEY_CUSTOM_ANCHOR, 'bool', 'Custom anchor point', False, dict(
        group=PLACEMENT_GROUP,
        tooltip='Off: the plate is centered on the selected face (or on the origin of a plane).\n'
                'On: pick your own point.')),
    (ANCHOR_ALIGN, placement.KEY_ANCHOR, 'choice', 'Align to point', placement.ANCHOR_CENTER, dict(
        group=PLACEMENT_GROUP, choices=(placement.ANCHOR_CENTER, placement.ANCHOR_CORNER),
        tooltip='Center: plate stays centered on the point when the size changes.\n'
                'Corner: front-left outer corner sits on the point.')),
    (ROTATION, placement.KEY_ROTATION, 'choice', 'Rotation (deg)', '0', dict(
        group=PLACEMENT_GROUP, choices=placement.ROTATIONS)),
    (OFFSET_X, placement.KEY_OFFSET_X, 'offset', 'Offset X', 0.0, dict(group=PLACEMENT_GROUP,
        tooltip='Shift along the X axis of the selected plane/face')),
    (OFFSET_Y, placement.KEY_OFFSET_Y, 'offset', 'Offset Y', 0.0, dict(group=PLACEMENT_GROUP,
        tooltip='Shift along the Y axis of the selected plane/face')),
    (OFFSET_Z, placement.KEY_OFFSET_Z, 'offset', 'Offset Z (height)', 0.0, dict(group=PLACEMENT_GROUP,
        tooltip='Shift away from the selected plane/face')),

    (CELL_WIDTH, 'baseWidth', 'length', 'Cell width', DIMENSION_DEFAULT_WIDTH_UNIT, dict(
        group=GRID_UNIT_GROUP, min=1, tooltip='Grid pitch left to right (standard 42 mm)')),
    (CELL_DEPTH, 'baseLength', 'length', 'Cell depth', DIMENSION_DEFAULT_WIDTH_UNIT, dict(
        group=GRID_UNIT_GROUP, min=1, tooltip='Grid pitch front to back (standard 42 mm)')),
    (CLEARANCE, 'xyClearance', 'length', 'Bin fit clearance', const.BIN_XY_CLEARANCE, dict(
        group=GRID_UNIT_GROUP, min=0.01, max=0.05, tooltip='Gap between bin and cell wall, 0.1 - 0.5 mm')),

    (PLATE_TYPE, 'plateType', 'choice', 'Type', 'Light', dict(group=STYLE_GROUP, choices=PLATE_TYPES,
        tooltip='Light: thin, no floor. Skeletonized: floor with cutouts. Full: solid floor')),
    (WITH_MAGNETS, 'hasMagnetSockets', 'bool', 'Magnet holes', True, dict(group=MAGNET_GROUP,
        tooltip='Only for Skeletonized / Full plates')),
    (MAGNET_DIAMETER, 'magnetSocketSize', 'length', 'Magnet diameter', const.DIMENSION_MAGNET_CUTOUT_DIAMETER, dict(group=MAGNET_GROUP, min=0.01, max=1)),
    (MAGNET_DEPTH, 'magnetSocketDepth', 'length', 'Magnet depth', const.DIMENSION_MAGNET_CUTOUT_DEPTH, dict(group=MAGNET_GROUP, min=0.01)),
    (WITH_SCREWS, 'hasScrewHoles', 'bool', 'Screw holes', True, dict(group=SCREW_GROUP,
        tooltip='Only for Skeletonized / Full plates')),
    (SCREW_DIAMETER, 'screwHoleSize', 'length', 'Screw diameter', const.DIMENSION_PLATE_SCREW_HOLE_DIAMETER, dict(group=SCREW_GROUP, min=0.1, max=1)),
    (SCREW_HEAD, 'screwHeadSize', 'length', 'Screw head diameter', const.DIMENSION_SCREW_HEAD_CUTOUT_DIAMETER, dict(group=SCREW_GROUP, min=0.2, max=1.5)),

    (FLOOR_EXTRA, 'extraBottomThickness', 'length', 'Extra floor thickness', const.BASEPLATE_EXTRA_HEIGHT, dict(
        group=ADVANCED_GROUP, min=0.01, tooltip='Floor added below the cells (Skeletonized / Full)')),
    (BIN_Z_CLEARANCE, 'verticalClearance', 'length', 'Bin height clearance', const.BASEPLATE_BIN_Z_CLEARANCE, dict(
        group=ADVANCED_GROUP, min=0, max=0.3, tooltip='Vertical gap between plate top and bin')),
    (WITH_CONNECTORS, 'hasConnectionHoles', 'bool', 'Connector holes', False, dict(group=ADVANCED_GROUP,
        tooltip='Holes in the side walls to pin plates together (Skeletonized)')),
    (CONNECTOR_DIAMETER, 'connectionHoleSize', 'length', 'Connector hole diameter', const.DIMENSION_PLATE_CONNECTION_SCREW_HOLE_DIAMETER, dict(group=ADVANCED_GROUP, min=0.1, max=0.5)),

    (SPLIT_MODE, plateSplit.KEY_MODE, 'choice', 'Split', plateSplit.SPLIT_OFF, dict(
        group=SPLIT_GROUP, choices=plateSplit.SPLIT_MODES,
        tooltip='Max print size: cut the plate into tiles that fit your print bed.\n'
                'Seams run between cells; the tiles stay assembled in the model\n'
                '(one body per tile, export each one for printing).')),
    (SPLIT_MAX_W, plateSplit.KEY_MAX_W, 'length', 'Max tile width', plateSplit.DEFAULTS[plateSplit.KEY_MAX_W], dict(
        group=SPLIT_GROUP, min=4.2, tooltip='Usable print bed width')),
    (SPLIT_MAX_D, plateSplit.KEY_MAX_D, 'length', 'Max tile depth', plateSplit.DEFAULTS[plateSplit.KEY_MAX_D], dict(
        group=SPLIT_GROUP, min=4.2, tooltip='Usable print bed depth')),
    (SPLIT_CONNECTOR, plateSplit.KEY_CONNECTOR, 'choice', 'Connectors', plateSplit.CONN_DOVETAIL, dict(
        group=SPLIT_GROUP, choices=plateSplit.CONNECTORS,
        tooltip='Dovetail: one per cell along each seam, through the full height.\n'
                'Push the tiles together from the top; they then hold sideways.')),
    (SPLIT_CLEARANCE, plateSplit.KEY_CLEARANCE, 'length', 'Connector clearance', plateSplit.DEFAULTS[plateSplit.KEY_CLEARANCE], dict(
        group=SPLIT_GROUP, min=0.0, max=0.1, tooltip='Gap around the dovetails and along the seams (default 0.15 mm)')),
]

FIELD_BY_ID = {f[0]: f for f in FIELDS}

GROUPS = [
    # (id, label, parent)
    (SIZE_GROUP, 'Size', None),
    (PLACEMENT_GROUP, 'Placement', None),
    (GRID_UNIT_GROUP, 'Grid unit', None),
    (STYLE_GROUP, 'Style', None),
    (MAGNET_GROUP, 'Magnets', STYLE_GROUP),
    (SCREW_GROUP, 'Screws', STYLE_GROUP),
    (SPLIT_GROUP, 'Split for printing', None),
    (ADVANCED_GROUP, 'Advanced', None),
]

ABOUT_TEXT = ('<b>GridfinityPlus</b><br>'
              'Based on FusionGridfinityGenerator by Lev Mishin (CC-BY-NC-SA 4.0).')


def defaults() -> dict:
    """{input id: default value}."""
    return {f[0]: f[4] for f in FIELDS}


def valuesFromParams(params: dict) -> dict:
    """{input id: value} seeded from stored params (missing keys -> default)."""
    vals = defaults()
    params = plateLayout.toV2(params)
    for fid, key, kind, label, default, extra in FIELDS:
        if key in params and params[key] is not None:
            vals[fid] = params[key]
    if not params.get(placement.KEY_FRAME):
        vals[CUSTOM_ANCHOR] = False
    return vals


def build(inputs: adsk.core.CommandInputs, values: dict, groupExpanded=None,
          isEdit: bool = False) -> dict:
    """Create all groups + inputs. Returns {id: CommandInput} for registration."""
    gplog.session(f'plateDialog.build (edit={isEdit})')
    units = adsk.core.Application.get().activeProduct.unitsManager.defaultLengthUnits
    created = {}
    groups = {}
    for gid, label, parent in GROUPS:
        target = groups[parent].children if parent else inputs
        g = target.addGroupCommandInput(gid, label)
        g.isExpanded = groupExpanded(gid) if groupExpanded else True
        groups[gid] = g
        created[gid] = g

        if gid == SIZE_GROUP:
            _buildSizeGroup(g.children, values, units, created)
            continue
        if gid == PLACEMENT_GROUP:
            planePrompt = ('Plane or planar face (empty = keep current)' if isEdit
                           else 'Plane or planar face the plate sits on (empty = top origin plane)')
            planeSel = g.children.addSelectionInput(PLACE_ON_INPUT, 'Place on', planePrompt)
            planeSel.addSelectionFilter('PlanarFaces')
            planeSel.addSelectionFilter('ConstructionPlanes')
            planeSel.setSelectionLimits(0, 1)
            planeSel.tooltip = 'The plate is centered on the selected face (or on the origin of a construction plane).'
            created[PLACE_ON_INPUT] = planeSel
            _addField(g.children, FIELD_BY_ID[CUSTOM_ANCHOR], values, units, created)
            pointSel = g.children.addSelectionInput(ANCHOR_POINT_INPUT, 'Anchor point',
                                                    'Vertex, sketch point or construction point')
            pointSel.addSelectionFilter('Vertices')
            pointSel.addSelectionFilter('SketchPoints')
            pointSel.addSelectionFilter('ConstructionPoints')
            pointSel.setSelectionLimits(0, 1)
            created[ANCHOR_POINT_INPUT] = pointSel
            for fid in (ANCHOR_ALIGN, ROTATION, OFFSET_X, OFFSET_Y, OFFSET_Z):
                _addField(g.children, FIELD_BY_ID[fid], values, units, created)
            continue
        _addFields(g.children, gid, values, units, created)
        if gid == SPLIT_GROUP:
            info = g.children.addStringValueInput(SPLIT_INFO, 'Tiles', '')
            info.isReadOnly = True
            created[SPLIT_INFO] = info

    about = inputs.addGroupCommandInput(INFO_GROUP, 'About')
    about.isExpanded = groupExpanded(INFO_GROUP) if groupExpanded else False
    about.children.addTextBoxCommandInput('info_text', '', ABOUT_TEXT, 2, True)
    created[INFO_GROUP] = about

    refresh(inputs)
    gplog.log(f'plateDialog.build: {len(created)} inputs')
    return created


def _buildSizeGroup(target, values, units, created):
    """Size by | Columns + Rows (or Width + Depth) | 4 edges with border width | result.

    Plain inputs only: tables / dropdown item deletion crashed Fusion.
    """
    for fid in (SIZE_MODE, COLUMNS, ROWS, EXACT_WIDTH, EXACT_DEPTH,
                EDGE_LEFT, BORDER_LEFT, EDGE_RIGHT, BORDER_RIGHT,
                EDGE_FRONT, BORDER_FRONT, EDGE_BACK, BORDER_BACK):
        _addField(target, FIELD_BY_ID[fid], values, units, created)
    for fid, label in ((SIZE_INFO_SIZE, 'Size'), (SIZE_INFO_CELLS, 'Whole cells')):
        inp = target.addStringValueInput(fid, label, '')
        inp.isReadOnly = True
        created[fid] = inp


def _addFields(target, gid, values, units, created):
    for f in FIELDS:
        if f[5].get('group') == gid and not f[5].get('manual'):
            _addField(target, f, values, units, created)


def _addField(target: adsk.core.CommandInputs, field, values, units, created):
    fid, key, kind, label, default, extra = field
    v = values.get(fid, default)
    if kind == 'bool':
        inp = target.addBoolValueInput(fid, label, True, '', bool(v))
    elif kind == 'int':
        inp = target.addIntegerSpinnerCommandInput(fid, label, extra.get('min', 1), extra.get('max', 100), 1, int(v))
    elif kind in ('length', 'offset'):
        inp = target.addValueInput(fid, label, units, adsk.core.ValueInput.createByReal(float(v)))
        if 'min' in extra:
            inp.minimumValue = extra['min']
            inp.isMinimumInclusive = True
        if 'max' in extra:
            inp.maximumValue = extra['max']
            inp.isMaximumInclusive = True
    elif kind == 'choice':
        inp = target.addDropDownCommandInput(fid, label, adsk.core.DropDownStyles.TextListDropDownStyle)
        for c in extra['choices']:
            inp.listItems.add(c, str(c) == str(v))
        if inp.selectedItem is None:
            inp.listItems.item(0).isSelected = True
    else:
        raise ValueError(kind)
    if extra.get('tooltip'):
        inp.tooltip = extra['tooltip']
    created[fid] = inp
    return inp


def _value(inputs, fid):
    inp = _get(inputs, fid)
    kind = FIELD_BY_ID[fid][2]
    if kind == 'choice':
        return inp.selectedItem.name if inp.selectedItem else FIELD_BY_ID[fid][4]
    if kind == 'int':
        return int(inp.value)
    return inp.value


def selectedEntity(inputs: adsk.core.CommandInputs, inputId: str):
    sel = adsk.core.SelectionCommandInput.cast(_get(inputs, inputId))
    if sel is None or sel.selectionCount == 0:
        return None
    return sel.selection(0).entity


def readParams(inputs: adsk.core.CommandInputs, base: dict = None) -> dict:
    """Dialog -> params (without placementFrame; callers add that)."""
    params = dict(base) if base else {}
    for fid, key, kind, label, default, extra in FIELDS:
        params[key] = _value(inputs, fid)
    params['plateWidth'] = int(params['plateWidth'])
    params['plateLength'] = int(params['plateLength'])
    params[plateLayout.KEY_VERSION] = 3
    for k in (plateLayout.KEY_FIT, plateLayout.KEY_CUT_WIDTH, plateLayout.KEY_CUT_DEPTH):
        params.pop(k, None)
    # Border comes from the edge settings now; keep the legacy keys present
    # (generators read them) but neutral.
    params['hasPadding'] = False
    for k in ('paddingLeft', 'paddingRight', 'paddingTop', 'paddingBottom'):
        params[k] = 0.0
    return params


def validate(params: dict) -> bool:
    ok = params['baseWidth'] >= 1 and params['baseLength'] >= 1 \
        and 0.01 <= params['xyClearance'] <= 0.05 \
        and (not params['hasMagnetSockets'] or (0 < params['magnetSocketSize'] <= 1 and params['magnetSocketDepth'] > 0)) \
        and (not params['hasScrewHoles'] or (0 < params['screwHoleSize'] <= 1 and params['screwHoleSize'] < params['screwHeadSize'] <= 1.5)) \
        and (not params['hasConnectionHoles'] or (0 < params['connectionHoleSize'] <= 0.5)) \
        and params['extraBottomThickness'] > 0
    if plateLayout.sizeMode(params) == plateLayout.SIZE_EXACT:
        ok = ok and params[plateLayout.KEY_WIDTH] >= 0.5 and params[plateLayout.KEY_DEPTH] >= 0.5
    else:
        ok = ok and params['plateWidth'] > 0 and params['plateLength'] > 0
        for k in (plateLayout.KEY_BORDER_LEFT, plateLayout.KEY_BORDER_RIGHT,
                  plateLayout.KEY_BORDER_FRONT, plateLayout.KEY_BORDER_BACK):
            ok = ok and params[k] >= 0
    return ok


def refresh(inputs: adsk.core.CommandInputs):
    """Show/hide inputs for the current modes and update the size readout."""
    def show(fid, visible):
        inp = _get(inputs, fid)
        if inp is not None and inp.isVisible != visible:
            inp.isVisible = visible

    modeInput = _get(inputs, SIZE_MODE)
    exact = bool(modeInput and modeInput.selectedItem
                 and modeInput.selectedItem.name == plateLayout.SIZE_EXACT)
    for fid in (COLUMNS, ROWS):
        show(fid, not exact)
    for fid in (EXACT_WIDTH, EXACT_DEPTH):
        show(fid, exact)
    for edgeId, borderId in ((EDGE_LEFT, BORDER_LEFT), (EDGE_RIGHT, BORDER_RIGHT),
                             (EDGE_FRONT, BORDER_FRONT), (EDGE_BACK, BORDER_BACK)):
        dd = adsk.core.DropDownCommandInput.cast(_get(inputs, edgeId))
        if dd is None:
            continue
        hasSize = dd.selectedItem is not None and dd.selectedItem.name != plateLayout.EDGE_FLUSH
        show(borderId, hasSize and not exact)

    custom = bool(_get(inputs, CUSTOM_ANCHOR).value)
    show(ANCHOR_POINT_INPUT, custom)
    show(ANCHOR_ALIGN, custom)
    if not custom:
        sel = adsk.core.SelectionCommandInput.cast(_get(inputs, ANCHOR_POINT_INPUT))
        if sel is not None and sel.selectionCount > 0:
            sel.clearSelection()

    show(SIZE_INFO_CELLS, exact)  # in Cells mode that is just Columns x Rows
    try:
        params = readParams(inputs)
        w, d = plateLayout.outerSize(params)
        lo = plateLayout.layout(params)
        _setText(inputs, SIZE_INFO_SIZE, '{:.1f} x {:.1f} mm'.format(w * 10, d * 10))
        _setText(inputs, SIZE_INFO_CELLS, '{} x {}'.format(lo['fullX'], lo['fullY']))
    except Exception:
        gplog.logExc('plateDialog.refresh: size info')
    try:
        mode = adsk.core.DropDownCommandInput.cast(_get(inputs, SPLIT_MODE))
        on = bool(mode and mode.selectedItem and mode.selectedItem.name == plateSplit.SPLIT_MAX)
        for fid in (SPLIT_MAX_W, SPLIT_MAX_D, SPLIT_CONNECTOR, SPLIT_CLEARANCE, SPLIT_INFO):
            show(fid, on)
        if on:
            _setText(inputs, SPLIT_INFO, plateSplit.describe(readParams(inputs)))
    except Exception:
        gplog.logExc('plateDialog.refresh: split info')


def _setText(inputs, fid, text):
    inp = adsk.core.StringValueCommandInput.cast(_get(inputs, fid))
    if inp is not None and inp.value != text:
        inp.value = text
