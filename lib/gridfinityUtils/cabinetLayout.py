"""
GridfinityPlus — box system (cabinet + inserts): pure layout math.

No geometry here, only numbers, so every dimension the cabinet and its inserts
agree on comes from ONE place. Both the cabinet generator and the insert
(drawer / box) generator call into this module with the cabinet's params.

Cabinet local frame (same convention as a bin, so bin placement code applies):
  x: width  0 .. aW   (aW = unitsW * baseW - 2 * cl)
  y: depth  0 .. aL   front (open side) at y = 0, back wall at y = aL
  On a plate with padding / partial cells the outline may grow past that
  footprint ('ovh', like a bin): x from -ovh.left to aW + ovh.right, front at
  y = -ovh.front, back at aL + ovh.back. The feet stay on the grid.
  z: up     feet from -BIN_BASE_HEIGHT to 0, body from 0 (or -BIN_BASE_HEIGHT
            without feet) up to zTop = height * heightUnit - BIN_BASE_HEIGHT.

Inside, the cabinet is split into columns (vertical dividers) and rows. Inserts
run on either
  * ledges  — shelf strips on the walls; the insert's bottom rests on them, or
  * grooves — V-grooves in the walls; the insert carries matching runners.

Inserts are always derived from the cabinet: pick column + row (+ span), the
insert size follows from walls, guides and clearances.

All lengths in Fusion internal units (cm).
"""

import math

from . import const

GUIDE_LEDGE = 'Ledges'
GUIDE_GROOVE = 'Grooves'
GUIDE_HOOK = 'Hooked grooves (print on its back)'
GUIDE_TYPES = (GUIDE_LEDGE, GUIDE_GROOVE, GUIDE_HOOK)

TOP_FLAT = 'Flat'
TOP_GRID = 'Gridfinity grid (stackable)'
TOP_TYPES = (TOP_FLAT, TOP_GRID)
# The top as its own plate that slides in from the front: the cabinet prints
# standing without a ceiling to bridge, the plate prints flat.
TOP_MOUNT_FIXED = 'Fixed (one piece)'
TOP_MOUNT_SLIDE = 'Slide-in plate'
TOP_MOUNTS = (TOP_MOUNT_SLIDE, TOP_MOUNT_FIXED)
# Feet: built in (the cabinet prints standing), or slide-on feet - one
# Gridfinity foot per cell, printed on its own like a bin's; the cabinet then
# has a flat bottom and prints on its back (fixed top, no bridges). Each
# foot slides onto a dovetail head under its cell, running front to back -
# printed on the back its profile just rises (set the foot on, push it the
# head length to the stop, it clicks). The push direction alternates per
# column (held both ways in a baseplate); the first column's feet are
# pushed backwards, their stops at the front: with a single column the
# cabinet only comes off moved backwards - toward the wall. Mount each
# column from its far end.
FOOT_RIM = 0.15             # foot left beyond the channel's stop end
FOOT_BUILT_IN = 'Built in'
FOOT_SLIDE = 'Slide-on feet (print on its back)'
FOOT_MOUNTS = (FOOT_BUILT_IN, FOOT_SLIDE)
FOOT_HEAD_DEPTH = 0.25      # head height into the foot (flanks 45 deg)
FOOT_PLAY = 0.015           # play around the head
FOOT_CLICK = 0.02           # click bump under the head
FOOT_CLICK_LEN = 0.15
FOOT_CLICK_RIDGE = 0.08     # floor the bump climbs over before it clicks in
# Rail on top of each side wall (outside flush, inside undercut at 45 deg, top
# sloped at 45 deg so the plate's matching slot needs no support either).
RAIL_UNDERCUT = 0.08        # how far the undercut reaches in
RAIL_CLEARANCE = 0.02       # play between rail and slot
RAIL_STOP = 0.3             # rail ends this far before the back: the plate stops there
# Click for the top plate: a bump on each rail's top just before its end and
# a matching hollow in the plate's slot; the plate slides over it only on
# the last millimetres and then clicks in.
# Held from outside: the rail leans inwards ("/"), RAIL_SKIN in from the
# outer face. The plate grips it from both sides: under its inner side (as
# before) and over its outer side, a wedge flush with the outer face that
# thickens upwards. A wall bending outwards would have to lift the plate,
# which the inner side stops - the plate holds the walls.
TOP_LOCK_INSIDE = 'Inside rails'
TOP_LOCK_OUTSIDE = 'Held from outside'
TOP_LOCKS = (TOP_LOCK_OUTSIDE, TOP_LOCK_INSIDE)
RAIL_SKIN = 0.05            # least plate edge outside the rail
RAIL_LEAN = 0.5             # the rail's outer side runs this far in per rise
RAIL_TOP_GRID = 0.28        # rail top line (u + v) under grid pockets
RAIL_TOP_FLAT = 0.45        # ... under a flat top
RAIL_HOOK = 0.1             # wanted inner hook (rail lean over the plate)
RAIL_HOOK_MIN = 0.06
RAIL_PLATE_REF = 0.62       # plate thickness the rail tops above are for
RAIL_EDGE_MIN = 0.04        # plate edge at its thinnest (set rail width)
RAIL_HOOK_SET = 0.05        # least hook with a set rail width
CLICK_FROM_END = 0.2        # bump ends this far before the rail end
CLICK_LENGTH = 0.4          # bump length along the rail
# Top grid over the plate border / partial cells (cabinet 'Fill to edge').
TOP_EDGE_PLATE = 'Like the plate (partial pockets)'
TOP_EDGE_FLAT = 'Flat'
TOP_EDGE_TYPES = (TOP_EDGE_PLATE, TOP_EDGE_FLAT)

INSERT_DRAWER = 'Drawer'
INSERT_BLANK = 'Blank cover'
INSERT_TYPES = (INSERT_DRAWER, INSERT_BLANK)
# Default depth of a blank cover (front + short frame for the guides).
BLANK_DEPTH = 1.2

FRONT_FLUSH = 'Flush'
FRONT_OVERLAY = 'Overlay'
FRONT_STYLES = (FRONT_FLUSH, FRONT_OVERLAY)

INTERIOR_EMPTY = 'Empty'
INTERIOR_COMPARTMENTS = 'Compartments'
INTERIOR_GRID = 'Gridfinity grid'
INTERIOR_SPOOLS = 'Spools (wire)'
INTERIOR_TYPES = (INTERIOR_EMPTY, INTERIOR_COMPARTMENTS, INTERIOR_GRID, INTERIOR_SPOOLS)

HANDLE_NONE = 'None'
HANDLE_RECESS = 'Recessed pull'
HANDLE_PULL = 'Pull handle'
HANDLE_LEDGE = 'Grooved ledge'
HANDLE_NOTCH = 'Top notch'
HANDLE_SLOT = 'Finger hole'
HANDLE_KNOB = 'Knob'
HANDLE_TYPES = (HANDLE_RECESS, HANDLE_PULL, HANDLE_LEDGE, HANDLE_NOTCH, HANDLE_SLOT, HANDLE_KNOB, HANDLE_NONE)
# Notch / finger hole with compartments: dividers in the way are lowered with
# the same round profile - along the front row of compartments, a set depth,
# or not at all.
GRIP_FRONT_ROW = 'Front row'
GRIP_DEPTH = 'Custom depth'
GRIP_OFF = 'Off'
GRIP_MODES = (GRIP_FRONT_ROW, GRIP_DEPTH, GRIP_OFF)

# Pull handle presets for values stored by earlier versions:
# (grip face height, grip thickness, top thickness, side walls; 0 = open).
_PULL_PRESETS = {
    'Hook lip': (1.6, 0.35, 0.3, 0.0),
    'Bar handle': (1.6, 0.35, 0.3, 0.5),
    'Scoop pull': (0.5, 0.25, 0.2, 0.2),
    'Pull tab': (0.5, 0.25, 0.2, 0.2),
}

ALIGN_TOP = 'Top'
ALIGN_CENTER = 'Center'
ALIGN_BOTTOM = 'Bottom'
HANDLE_ALIGNS = (ALIGN_TOP, ALIGN_CENTER, ALIGN_BOTTOM)

KNOB_SUPPORT_STAND = 'Stand'
KNOB_SUPPORT_THIN = 'Thin breakaway'
KNOB_SUPPORT_NONE = 'None'
KNOB_SUPPORTS = (KNOB_SUPPORT_STAND, KNOB_SUPPORT_THIN, KNOB_SUPPORT_NONE)

KNOB_ROUND = 'Round'
KNOB_MUSHROOM = 'Mushroom'
KNOB_SPOOL = 'Spool (U groove)'
KNOB_STYLES = (KNOB_ROUND, KNOB_MUSHROOM, KNOB_SPOOL)

LABEL_NONE = 'None'
LABEL_RECESS = 'Sticker recess'
LABEL_CARD = 'Card holder'
LABEL_TYPES = (LABEL_RECESS, LABEL_CARD, LABEL_NONE)
LABEL_AUTO = 'Auto'
# 3 x 3 grid on the front: (row, column) per position.
LABEL_TOP_LEFT = 'Top left'
LABEL_TOP = 'Top center'
LABEL_TOP_RIGHT = 'Top right'
LABEL_LEFT = 'Middle left'
LABEL_CENTER = 'Center'
LABEL_RIGHT = 'Middle right'
LABEL_BOTTOM_LEFT = 'Bottom left'
LABEL_BOTTOM = 'Bottom center'
LABEL_BOTTOM_RIGHT = 'Bottom right'
LABEL_POSITIONS = (LABEL_AUTO,
                   LABEL_TOP_LEFT, LABEL_TOP, LABEL_TOP_RIGHT,
                   LABEL_LEFT, LABEL_CENTER, LABEL_RIGHT,
                   LABEL_BOTTOM_LEFT, LABEL_BOTTOM, LABEL_BOTTOM_RIGHT)
LABEL_GRID = {
    LABEL_TOP_LEFT: ('top', 'left'), LABEL_TOP: ('top', 'center'), LABEL_TOP_RIGHT: ('top', 'right'),
    LABEL_LEFT: ('middle', 'left'), LABEL_CENTER: ('middle', 'center'), LABEL_RIGHT: ('middle', 'right'),
    LABEL_BOTTOM_LEFT: ('bottom', 'left'), LABEL_BOTTOM: ('bottom', 'center'),
    LABEL_BOTTOM_RIGHT: ('bottom', 'right'),
}

# Values stored by earlier versions -> current ones.
_LEGACY = {
    'insertType': {'Drawer (overlay front)': INSERT_DRAWER, 'Box (flush front)': INSERT_DRAWER},
    'handle': {'Finger notch': HANDLE_NOTCH, 'Finger slot': HANDLE_SLOT, 'Pull tab': HANDLE_PULL,
               'Hook lip': HANDLE_PULL, 'Bar handle': HANDLE_PULL, 'Scoop pull': HANDLE_PULL},
    'labelPos': {'Below handle': LABEL_BOTTOM, 'Above handle': LABEL_TOP,
                 'Left of handle': LABEL_LEFT, 'Right of handle': LABEL_RIGHT,
                 'Top': LABEL_TOP, 'Bottom': LABEL_BOTTOM, 'Left': LABEL_LEFT, 'Right': LABEL_RIGHT},
}

# Smallest free row height an insert can live in.
MIN_ROW_HEIGHT = 1.0
# Minimum material left behind a groove.
GROOVE_MIN_BACKING = 0.12
# Flat tip of the V-groove / runner profile.
GROOVE_TIP = 0.1
# Hooked groove (fractions of the groove depth d, from the groove centre):
# the runner's arm rises 45 deg into the wall from HOOK_LOW * d below the
# centre, its top is flat at HOOK_ARM * d; at its end a barb HOOK_BARB_W * d
# wide stands up to HOOK_BARB * d, behind a lip of the wall. The runner
# cannot leave the groove sideways, so the inserts hold the walls together.
# Needs the cabinet printed on its back (the lip hangs down).
HOOK_LOW = 0.8
HOOK_ARM = 0.2
HOOK_BARB = 0.6
HOOK_BARB_W = 0.4
# Detent: default bump height on the cabinet, its distance from the front and
# the ridge the insert climbs over before it clicks in.
DETENT_HEIGHT = 0.04
DETENT_FRONT_OFFSET = 0.6
DETENT_RIDGE = 0.15
DETENT_CLEARANCE = 0.02
# Extra vertical play over the bump height: the insert lifts over the bump
# (and over a hard stop when it is taken out).
DETENT_LIFT = 0.02
# Insert side of the detent: the flank that holds it closed is steep, the
# ramp it is pushed in over is flat (degrees from the floor).
DETENT_HOLD_ANGLE = 70.0
DETENT_RAMP_ANGLE = 30.0
# The cabinet's bump is a tooth: flat ramp at the front (the insert slides in
# over it), hard steep edge at the back (holds the insert in).
BUMP_FRONT_ANGLE = 30.0
BUMP_BACK_ANGLE = 80.0
# Pull-out stop: solid land at the insert's back end that hits the bump.
STOP_LAND = 0.4
STOP_AUTO = 'Auto'
STOP_SIDE = 'Side bump (pull firmly to remove)'
STOP_TOP = 'Top catch (tilts, ledges)'
STOP_HARD = 'Hard (lift to remove)'
STOP_SOFT = 'Like the detent'
STOP_OFF = 'Off'
STOP_MODES = (STOP_AUTO, STOP_SIDE, STOP_TOP, STOP_HARD, STOP_SOFT, STOP_OFF)
# Side bump: a bump on each column wall just behind the cabinet front and a
# nose on each side wall of the insert near its back. Pulled out, the nose
# runs into the bump's steep face; put in, it slides over the 30 deg face
# (the walls give a little). Nothing hangs in the air when printing.
SIDE_SIZE = 0.04         # bump and nose stand out this far (each)
SIDE_PLAY = 0.005        # play in the shallow tracks they run in
SIDE_H = 0.8             # height of bump and nose
SIDE_HOLD_ANGLE = 75.0
SIDE_LEAD_ANGLE = 30.0
# Top catch (ledges): a tooth under the ledge / ceiling above, just behind
# the front, and a nose on the insert's rim at the back. Pulled out level
# the nose passes under the tooth; when the insert tilts (its back lifts),
# the nose hits the tooth. Like a kitchen drawer: hold it level to take it out.
TOP_Y = 0.3
TOP_LEN = 0.25
TOP_NOSE = 0.025         # nose above the insert's rim
TOP_CLEAR = 0.012        # nose to tooth when level
# Older inserts stored the pull-out stop as a checkbox.
_LEGACY['stop'] = {True: STOP_AUTO, False: STOP_OFF}

# Wall mount screws: clearance hole, countersunk head (DIN 7991, 90°) and
# pan / cheese head (ISO 7045 / ISO 1207) diameter + height, in cm.
MOUNT_SCREWS = {
    'M2': {'hole': 0.24, 'cskD': 0.40, 'panD': 0.40, 'panK': 0.16},
    'M2.5': {'hole': 0.29, 'cskD': 0.50, 'panD': 0.50, 'panK': 0.20},
    'M3': {'hole': 0.34, 'cskD': 0.60, 'panD': 0.56, 'panK': 0.24},
    'M4': {'hole': 0.45, 'cskD': 0.80, 'panD': 0.80, 'panK': 0.31},
    'M5': {'hole': 0.55, 'cskD': 1.00, 'panD': 0.95, 'panK': 0.38},
    'M6': {'hole': 0.66, 'cskD': 1.20, 'panD': 1.20, 'panK': 0.46},
}
MOUNT_SCREW_NAMES = tuple(MOUNT_SCREWS)
HEAD_COUNTERSUNK = 'Countersunk'
HEAD_PAN = 'Pan / cheese head'
MOUNT_HEADS = (HEAD_COUNTERSUNK, HEAD_PAN)
# Head clearance and material left under a pan head / beside a countersink.
MOUNT_HEAD_PLAY = 0.03
MOUNT_MIN_MATERIAL = 0.08


def mountScrew(p: dict) -> dict:
    """Hole geometry for the chosen screw: hole radius, head radius, head
    depth (flush with the inside of the back wall) and the back wall it needs."""
    sc = MOUNT_SCREWS.get(p.get('mountScrew'), MOUNT_SCREWS['M4'])
    hole = sc['hole']
    if p.get('mountHead') == HEAD_PAN:
        headD = sc['panD'] + 2 * MOUNT_HEAD_PLAY
        depth = sc['panK'] + MOUNT_HEAD_PLAY
    else:
        headD = sc['cskD'] + 2 * MOUNT_HEAD_PLAY
        depth = (headD - hole) / 2          # 90° countersink
    return {'holeR': hole / 2, 'headR': headD / 2, 'depth': depth,
            'countersunk': p.get('mountHead') != HEAD_PAN,
            'wall': depth + MOUNT_MIN_MATERIAL}


def mountHoles(cab: dict):
    """[(x, z)] of the wall mount holes in the back wall: rows at mountTop
    below the ceiling (and mountBottom above the floor), evenly spread between
    mountEdge from the side walls. Holes that would cut into a divider move
    into the nearest column."""
    p = cab['p']
    if not p['wallMount']:
        return []
    sc = mountScrew(p)
    cols = cab['columns']
    xa = cols[0][0] + float(p['mountEdge'])
    xb = cols[-1][1] - float(p['mountEdge'])
    n = max(1, int(p['mountPerRow']))
    if n == 1 or xb <= xa:
        xs = [(cols[0][0] + cols[-1][1]) / 2]
    else:
        xs = [xa + i * (xb - xa) / (n - 1) for i in range(n)]
    keep = sc['headR'] + 0.05
    fixed = []
    for x in xs:
        inside = [c for c in cols if c[0] + keep <= x <= c[1] - keep]
        if not inside:
            # Nearest column, kept clear of its walls.
            c = min(cols, key=lambda c: min(abs(x - c[0]), abs(x - c[1])))
            x = min(max(x, c[0] + keep), c[1] - keep)
        fixed.append(x)
    zs = [cab['ceil'] - float(p['mountTop'])]
    if int(p['mountRows']) > 1:
        zs.append(cab['floorTop'] + float(p['mountBottom']))
    return [(x, z) for z in zs for x in fixed]


CABINET_DEFAULTS = {
    'unitsW': 2,
    'unitsL': 3,
    'heightMode': 'Units',
    'heightUnits': 12,
    'heightMm': 12 * const.DIMENSION_DEFAULT_HEIGHT_UNIT,
    'baseW': const.DIMENSION_DEFAULT_WIDTH_UNIT,
    'baseL': const.DIMENSION_DEFAULT_WIDTH_UNIT,
    'heightUnit': const.DIMENSION_DEFAULT_HEIGHT_UNIT,
    'cl': const.BIN_XY_CLEARANCE,
    'wall': 0.12,
    'backWall': 0.12,
    'floor': 0.12,
    'top': 0.12,
    'divider': 0.12,
    'columns': 1,
    'rows': 3,
    'rowWeights': '',
    'guide': GUIDE_LEDGE,
    'ledgeDepth': 0.3,
    'ledgeThickness': 0.15,
    'grooveDepth': 0.2,
    'fitLateral': 0.025,
    'fitVertical': 0.05,
    # Play of a runner in its V-groove (per flank); kept apart from the side
    # clearance so the insert does not wobble in the groove.
    'grooveFit': 0.02,
    'fitBack': 0.0,
    'detent': True,
    'detentHeight': DETENT_HEIGHT,
    'feet': True,
    'footMount': FOOT_BUILT_IN,
    'footHeadLen': 1.6,         # dovetail head length (= push distance)
    'footHeadWidth': 1.0,       # head width at the cabinet bottom (+ 2 x depth below)
    'magnets': False,
    'screws': False,
    'topType': TOP_GRID,
    'topMount': TOP_MOUNT_SLIDE,
    # How much the plate has to squeeze over the click bump (0 = no click).
    'topClick': 0.02,
    'topLock': TOP_LOCK_OUTSIDE,
    'railWidth': 0.0,
    # Experimental, off by default (see README).
    # Bumps / teeth for the inserts' pull-out stops (STOP_SIDE / STOP_TOP).
    'stopParts': True,
    'wallMount': False,
    'mountScrew': 'M4',
    'mountHead': 'Countersunk',
    'mountRows': 1,
    'mountPerRow': 2,
    'mountEdge': 1.5,
    'mountTop': 1.0,
    'mountBottom': 1.0,
    # Body extension over plate border / partial cells, resolved from the plate.
    'ovh': {},
    'topEdge': TOP_EDGE_PLATE,
}

INSERT_DEFAULTS = {
    'insertType': INSERT_DRAWER,
    'frontStyle': FRONT_FLUSH,
    'depth': 0.0,
    'column': 1,
    'row': 1,
    'span': 1,
    'pullOut': 0.0,
    'wall': 0.12,
    'floor': 0.12,
    'front': 0.15,
    'frontGap': 0.05,
    'handle': HANDLE_RECESS,
    'handleWidth': 4.0,
    'handleHeight': 1.6,
    'handleDepth': 1.5,
    'gripDividers': GRIP_FRONT_ROW,
    'gripDepth': 2.5,
    'knobStyle': KNOB_ROUND,
    'knobSupport': KNOB_SUPPORT_STAND,
    'pullGrip': 0.5,
    'fingerGrooveWidth': 1.0,
    'fingerGrooveDepth': 0.4,
    'ledgeRim': 0.2,
    # Grooved ledge total height; 0 = 45° underside.
    'ledgeHeight': 0.0,
    'handleAlign': ALIGN_TOP,
    'pullBar': 0.25,
    'pullTop': 0.2,
    'pullSides': 0.2,
    'label': LABEL_RECESS,
    'labelPos': LABEL_AUTO,
    'labelOffsetX': 0.0,
    'labelOffsetZ': 0.0,
    'labelWidth': 5.0,
    'labelHeight': 1.2,
    # Sticker recess depth (0.2 mm: the sticker sits flush and straight).
    'labelDepth': 0.02,
    'wireHoles': 0,
    'wireDiameter': 0.5,
    'spoolCount': 1,
    'spoolDiameter': 5.0,
    'spoolWidth': 2.5,
    'spoolBore': 1.0,
    'spoolGuides': True,
    # Also draw the spools as a body in the model (planning only, not printed).
    'showSpools': False,
    'spoolPlay': 0.1,
    'spoolDivider': 0.3,
    'spoolEnd': 0.3,
    'spoolMount': 'Open',
    'spoolHolePos': 'Bottom',
    'spoolHoleOffset': 0.0,
    'spoolHoleDiameter': 0.25,
    'axleEndPlay': 0.05,
    'axleCollar': 0.2,
    'axleSplit': 'Bayonet (2 halves)',
    # Round fillet where cradles / eyelet posts meet the floor (0 = off).
    'spoolFillet': 0.2,
    # One-piece axle: length of the end without collar past the end support (0 = to the wall).
    'axleEndLength': 0.0,
    'interior': INTERIOR_EMPTY,
    'divX': 2,
    'divY': 1,
    # Pull-out stop (Auto: hard on ledges, like the detent in grooves).
    'stop': STOP_AUTO,
    'detentHold': DETENT_HOLD_ANGLE,
    'detentRamp': DETENT_RAMP_ANGLE,
}


def stopMode(cab: dict, ip: dict) -> str:
    """Resolved pull-out stop: hard on ledges (lift the insert to take it
    out), like the detent in grooves (the runner can barely lift there)."""
    mode = ip.get('stop', STOP_AUTO)
    if mode not in STOP_MODES:
        mode = STOP_AUTO
    if mode in (STOP_SIDE, STOP_TOP) and not cab['stopParts']:
        mode = STOP_AUTO                     # the cabinet has no stop parts
    if mode == STOP_TOP and cab['grooved']:
        mode = STOP_SIDE                     # no ledge above a grooved slot
    if mode == STOP_AUTO:
        if cab['stopParts']:
            return STOP_SIDE
        return STOP_SOFT if cab['grooved'] else STOP_HARD
    return mode


def bottomStop(cab: dict, ip: dict):
    """Stop at the bottom / in the groove (STOP_HARD, STOP_SOFT) or None.
    Auto with stop bumps uses it together with the side bump: like the
    detent in a groove (the runner cannot lift there), hard on ledges."""
    mode = ip.get('stop', STOP_AUTO)
    resolved = stopMode(cab, ip)
    if resolved in (STOP_HARD, STOP_SOFT):
        return resolved
    if mode not in (STOP_SIDE, STOP_TOP, STOP_OFF, STOP_HARD, STOP_SOFT) and cab['stopParts']:
        return STOP_SOFT if cab['grooved'] else STOP_HARD
    return None


def withDefaults(params: dict, defaults: dict) -> dict:
    out = dict(defaults)
    out.update({k: v for k, v in (params or {}).items() if v is not None})
    oldHandle = (params or {}).get('handle')
    if oldHandle in _PULL_PRESETS and 'pullSides' not in (params or {}):
        out['pullGrip'], out['pullBar'], out['pullTop'], out['pullSides'] = _PULL_PRESETS[oldHandle]
    for key, mapping in _LEGACY.items():
        if out.get(key) in mapping:
            if key == 'insertType' and 'frontStyle' not in (params or {}):
                out['frontStyle'] = FRONT_OVERLAY if out[key] == 'Drawer (overlay front)' else FRONT_FLUSH
            out[key] = mapping[out[key]]
    return out


def heightUnits(p: dict) -> float:
    """Effective height in height units (fractional for mm mode)."""
    if p.get('heightMode') == 'Total height':
        hu = float(p['heightUnit'])
        return float(p['heightMm']) / hu if hu > 0 else 1.0
    return float(p['heightUnits'])


def parseWeights(text: str, count: int):
    """'1, 1, 2' -> [1, 1, 2]; empty/invalid -> count equal rows."""
    weights = []
    for part in str(text or '').replace(';', ',').split(','):
        part = part.strip()
        if not part:
            continue
        try:
            w = float(part)
        except ValueError:
            return [1.0] * max(1, count)
        if w <= 0:
            return [1.0] * max(1, count)
        weights.append(w)
    return weights if weights else [1.0] * max(1, count)


def footprint(p: dict):
    cl = float(p['cl'])
    return int(p['unitsW']) * float(p['baseW']) - 2 * cl, int(p['unitsL']) * float(p['baseL']) - 2 * cl


def cabinet(params: dict) -> dict:
    """Every cabinet dimension, derived from its params. Pure numbers."""
    p = withDefaults(params, CABINET_DEFAULTS)
    aW, aL = footprint(p)
    ovh = p.get('ovh') or {}
    ox0 = -float(ovh.get('left', 0) or 0)
    ox1 = aW + float(ovh.get('right', 0) or 0)
    oy0 = -float(ovh.get('front', 0) or 0)
    oy1 = aL + float(ovh.get('back', 0) or 0)
    baseH = const.BIN_BASE_HEIGHT
    zTop = heightUnits(p) * float(p['heightUnit']) - baseH
    zBottom = -baseH if not p['feet'] else 0.0
    grooved = p['guide'] in (GUIDE_GROOVE, GUIDE_HOOK)
    gd = float(p['grooveDepth'])

    wall = float(p['wall'])
    divider = float(p['divider'])
    if grooved:
        wall = max(wall, gd + GROOVE_MIN_BACKING)
        divider = max(divider, 2 * gd + GROOVE_MIN_BACKING)
    backWall = float(p['backWall'])
    if p['wallMount']:
        # Screw heads must sit flush with the inside: drawers touch the back.
        backWall = max(backWall, mountScrew(p)['wall'])
    floorTop = zBottom + float(p['floor']) if not p['feet'] else float(p['floor'])
    topIsGrid = p['topType'] == TOP_GRID
    topThickness = float(p['top']) + (baseH if topIsGrid else 0.0)
    # Cabinets from before the slide-in plate keep their one-piece top.
    slide = (params or {}).get('topMount', TOP_MOUNT_FIXED) == TOP_MOUNT_SLIDE
    rail = None
    if slide:
        rw = max(0.08, float(p['wall']))
        rail = {'w': rw, 'h': RAIL_UNDERCUT, 'clearance': RAIL_CLEARANCE,
                'height': rw + 2 * RAIL_UNDERCUT, 'y1': oy1 - RAIL_STOP,
                'click': max(0.0, float(p.get('topClick') or 0.0)),
                'skin': 0.0}
        # The plate's slot (rail + play) must stay below the grid pockets
        # (they reach the outer edge only in their top 2.4 mm).
        slot = rail['height'] + 2 * RAIL_CLEARANCE
        # Flat and grid plates are equally thick (as thick as a grid top),
        # so cabinets of the same height match outside and inside, whatever
        # their top. Nothing is added on top.
        topThickness = max(float(p['top']) + baseH, slot + 0.28)
        if (params or {}).get('topLock', TOP_LOCK_INSIDE) == TOP_LOCK_OUTSIDE:
            rail.update(leaningRail(wall, topIsGrid, topThickness, float(p.get('railWidth') or 0.0)))
    ceil = zTop - topThickness
    innerBack = oy1 - backWall

    nCols = max(1, int(p['columns']))
    innerW = (ox1 - ox0) - 2 * wall
    colW = (innerW - (nCols - 1) * divider) / nCols
    columns = []
    x = ox0 + wall
    for i in range(nCols):
        columns.append((x, x + colW))
        x += colW + divider

    weights = parseWeights(p['rowWeights'], int(p['rows']))
    nRows = len(weights)
    ledgeZone = float(p['ledgeThickness']) + float(p['ledgeDepth']) if not grooved else 0.0
    avail = (ceil - floorTop) - (nRows - 1) * ledgeZone
    rows = []
    z = floorTop
    total = sum(weights)
    for i, w in enumerate(weights):
        h = avail * w / total
        rows.append({'bottom': z, 'top': z + h, 'height': h})
        z += h + ledgeZone

    errors = []
    if innerW <= 0 or colW < 2.0:
        errors.append('Columns too narrow (min 20 mm inside)')
    if innerBack - oy0 < 3.0:
        errors.append('Cabinet too shallow')
    if any(r['height'] < MIN_ROW_HEIGHT for r in rows):
        errors.append('Rows too low (min {:g} mm free height)'.format(MIN_ROW_HEIGHT * 10))
    if grooved and any(r['height'] < 2 * gd + GROOVE_TIP + 0.4 for r in rows):  # >= any profile
        errors.append('Rows too low for the grooves')

    radius = const.BIN_CORNER_FILLET_RADIUS - float(p['cl'])
    # Interior back corners are rounded concentric with the outside so the
    # wall keeps its thickness there; ledges / grooves end where they start.
    backCornerR = max(0.0, radius - wall)
    cab = {
        'p': p,
        'aW': aW, 'aL': aL,
        'x0': ox0, 'x1': ox1, 'front': oy0, 'back': oy1,
        'detentY': oy0 + DETENT_FRONT_OFFSET,
        'detentR': float(p['detentHeight']) if p['detent'] else 0.0,
        'partial': {k: bool(v) for k, v in ((ovh.get('partial') or {}).items())},
        'zBottom': zBottom, 'zTop': zTop,
        'radius': radius, 'backCornerR': backCornerR,
        # A groove's tip is deeper in the wall: it must end before the outer
        # corner starts curving (back - radius) to keep the wall there.
        'guideEnd': min(innerBack - backCornerR, oy1 - radius),
        'wall': wall, 'divider': divider, 'backWall': backWall,
        'floorTop': floorTop, 'ceil': ceil, 'innerBack': innerBack,
        'topIsGrid': topIsGrid, 'rail': rail,
        # Cabinets from before grooveFit used the side clearance for it.
        'grooveFit': float((params or {}).get('grooveFit', p['fitLateral'])),
        # Older cabinets have no stop bumps / teeth.
        'stopParts': bool((params or {}).get('stopParts', False)),
        'columns': columns, 'rows': rows,
        'grooved': grooved, 'grooveDepth': gd, 'hooked': p['guide'] == GUIDE_HOOK,
        'ledgeDepth': float(p['ledgeDepth']), 'ledgeThickness': float(p['ledgeThickness']),
        'errors': errors,
    }
    if p['wallMount']:
        r = mountScrew(p)['headR']
        if any(not (floorTop + r <= z <= ceil - r) for _, z in mountHoles(cab)):
            errors.append('Wall mount holes outside the back wall: check the distances from top / bottom')
    return cab


def leaningRail(wall: float, topIsGrid: bool, thickness: float, width: float = 0.0) -> dict:
    """'Held from outside' rail in the real wall (grooved cabinets have
    thicker walls): {'skin', 'foot', 'top'}, u = in from the outer face,
    v = up from the ceiling. Rail foot [skin, foot] on the wall top, top
    line u + v = top. A grid top's pockets leave only the triangle u + v <=
    2.8 mm at the edge; a flat top much more. The foot ends where the inner
    hook (the plate under the rail's 45 deg lean) still gets RAIL_HOOK; plate
    edge and rail foot then split the rest equally; thicker walls and a
    thicker plate make it bigger. width > 0: rail foot this thick, the plate
    edge beside it only RAIL_EDGE_MIN; as far as the wall and the hook
    (RAIL_HOOK_SET at least) allow - the plate never changes for it.
    Skin 0 (inside rails) for walls too thin."""
    play = RAIL_CLEARANCE * math.sqrt(1.0 + RAIL_LEAN ** 2)
    extra = max(0.0, thickness - RAIL_PLATE_REF)
    top = (RAIL_TOP_GRID + extra if topIsGrid
           else min(RAIL_TOP_FLAT + extra, (1.0 + RAIL_LEAN) * (thickness - 0.1)))
    if width > 0:
        skin = RAIL_EDGE_MIN + play
        foot = min(wall, skin + width, top - 2 * RAIL_HOOK_SET)
        if foot - skin < 0.04:
            return {'skin': 0.0}
        return {'skin': skin, 'foot': foot, 'top': top}
    foot = top - 2 * RAIL_HOOK
    if foot < 0.12:
        foot = max(0.12, top - 2 * RAIL_HOOK_MIN)
    foot = min(wall, foot)
    skin = max(RAIL_SKIN, (foot + play) / 2)
    if foot - skin < 0.04:
        return {'skin': 0.0}
    return {'skin': skin, 'foot': foot, 'top': top}


def footHead(cab: dict) -> dict:
    """Slide-on foot dovetail: {'len', 'root', 'depth', 'half'} - as set, as
    far as the foot allows: the channel must fit its length (the foot narrows
    45 deg below its top; `half` = half its length at the channel floor) with
    a rim at the stop end - the entry pocket may run out of the foot's end,
    then the foot slides on from beyond it -, and the widened head + entry
    pocket its width with 1 mm beside."""
    p = cab['p']
    t = FOOT_HEAD_DEPTH
    floor = t + FOOT_PLAY + FOOT_CLICK + 0.03                # entry pocket floor depth
    half = float(p['baseL']) / 2 - float(p['cl']) - floor
    halfW = float(p['baseW']) / 2 - float(p['cl']) - floor
    if int(p['unitsL']) > 1:
        # Several rows: a foot is set on inside its own cell (channel + entry
        # pocket fit the foot), else the next cell's head is in the way.
        maxLen = half - 1.5 * FOOT_PLAY - 0.05
    else:
        maxLen = 2 * half - FOOT_RIM - 2 * FOOT_PLAY
    maxRoot = 2 * (halfW - (t + FOOT_PLAY + 0.02) - 0.1)
    return {'len': max(0.6, min(float(p.get('footHeadLen') or 1.6), maxLen)),
            'root': max(0.3, min(float(p.get('footHeadWidth') or 1.0), maxRoot)),
            'depth': t, 'half': half}


def footCells(cab: dict):
    """Slide-on feet: [(column, row, cx, hy, push)] for every full cell
    (partial cells get no foot); hy = y of the head's centre: head channel
    and entry pocket together are centred in the foot (a long head: the
    channel from the stop rim on, the pocket runs out of the foot), so the
    head sits off the cell centre against the push; push = direction the
    foot is pushed along y to lock: +1 (backwards) in the first column, then
    alternating per column."""
    p = cab['p']
    if not p['feet'] or p.get('footMount', FOOT_BUILT_IN) != FOOT_SLIDE:
        return []
    bw, bl, cl = float(p['baseW']), float(p['baseL']), float(p['cl'])
    fh = footHead(cab)
    hl, pl = fh['len'], FOOT_PLAY
    # far (stop) end of the channel, from the cell centre
    far = min(hl + 2 * pl, fh['half'] - FOOT_RIM)
    out = []
    for i in range(int(p['unitsW'])):
        push = 1 if i % 2 == 0 else -1
        for j in range(int(p['unitsL'])):
            cy = j * bl + bl / 2 - cl
            out.append((i, j, i * bw + bw / 2 - cl, cy - push * (far - hl / 2 - pl), push))
    return out


def grooveCenter(row: dict) -> float:
    return (row['bottom'] + row['top']) / 2


def grooveSpan(cab: dict):
    """(below, above) the groove centre the groove / runner reaches."""
    gd = cab['grooveDepth']
    if cab.get('hooked'):
        return HOOK_LOW * gd, HOOK_BARB * gd
    return GROOVE_TIP / 2 + gd, GROOVE_TIP / 2 + gd


def grooveLowerZ(cab: dict, center: float, u: float) -> float:
    """z of the groove's lower flank (the runner rides on it, 45 deg) u deep
    in the wall."""
    gd = cab['grooveDepth']
    if cab.get('hooked'):
        return center - HOOK_LOW * gd + u
    return center - GROOVE_TIP / 2 - gd + u


def supportZ(cab: dict, rowIndex: int) -> float:
    """z of the surface an insert in this row rests / runs on (ledge variant)."""
    return cab['rows'][rowIndex]['bottom']


def insertVert(cab: dict) -> float:
    """Vertical play of an insert (it rides over the detent bump)."""
    vert = float(cab['p']['fitVertical'])
    if cab['detentR'] > 0:
        vert = max(vert, cab['detentR'] + DETENT_LIFT)
    return vert


def sideBand(cab: dict, rowIndex: int):
    """z range [zs, zt] of the side bump / nose in a row, clear of the
    insert's floor and rim and (grooves) of its runner; None if it does not
    fit."""
    row = cab['rows'][rowIndex]
    zLo = row['bottom'] + 0.3
    zHi = row['top'] - 0.25
    if cab['grooved']:
        below, above = grooveSpan(cab)
        gc = grooveCenter(row)
        lo, hi = gc - below - 0.1, gc + above + 0.1
        a, b = (hi, zHi) if zHi - hi >= lo - zLo else (zLo, lo)
    else:
        a, b = zLo, zHi
    if b - a < 0.3:
        return None
    h = min(SIDE_H, b - a)
    c = (a + b) / 2
    return (c - h / 2, c + h / 2)


def contactStrips(cab: dict, colIndex: int, rowIndex: int):
    """Detent strips [(xA, xB, z)] for one column/row: where the cabinet bump
    sits and the insert gets its notch + relief channel.

    Only a narrow sub-strip of the support is used, so the rest of the ledge /
    groove flank keeps carrying the insert along its full length (a channel over
    the whole support would let the back of the insert sag)."""
    x0, x1 = cab['columns'][colIndex]
    row = cab['rows'][rowIndex]
    if cab['grooved']:
        gd = cab['grooveDepth']
        # Outer half of the lower flank (towards the groove tip).
        z = grooveLowerZ(cab, grooveCenter(row), 0.75 * gd)
        return [(x0 - gd, x0 - gd / 2, z), (x1 + gd / 2, x1 + gd, z)]
    # Middle of the strip where the insert overlaps the ledge, so it is still
    # carried on both sides of the channel. The floor (bottom row) uses the
    # same strips.
    mid = (float(cab['p']['fitLateral']) + cab['ledgeDepth']) / 2
    z = row['bottom']
    return [(x0 + mid - 0.05, x0 + mid + 0.05, z), (x1 - mid - 0.05, x1 - mid + 0.05, z)]


def clampInsert(cab: dict, ip: dict) -> dict:
    """Column/row/span (1-based in params) clamped onto the cabinet layout."""
    nCols = len(cab['columns'])
    nRows = len(cab['rows'])
    col = max(1, min(int(ip['column']), nCols))
    row = max(1, min(int(ip['row']), nRows))
    span = 1 if not cab['grooved'] else max(1, int(ip.get('span', 1)))
    span = min(span, nRows - row + 1)
    return {'column': col, 'row': row, 'span': span}


def insert(cab: dict, insertParams: dict) -> dict:
    """Insert dimensions (closed position, cabinet local frame)."""
    ip = withDefaults(insertParams, INSERT_DEFAULTS)
    cp = cab['p']
    slot = clampInsert(cab, ip)
    c = slot['column'] - 1
    r0 = slot['row'] - 1
    r1 = r0 + slot['span'] - 1
    x0, x1 = cab['columns'][c]
    lat = float(cp['fitLateral'])
    # The insert rides over the bump: it lifts by the bump height.
    vert = insertVert(cab)

    rowLo = cab['rows'][r0]
    rowHi = cab['rows'][r1]
    if cab['grooved']:
        z0 = rowLo['bottom'] + vert / 2
        z1 = rowHi['top'] - vert / 2
    else:
        z0 = rowLo['bottom']
        z1 = rowHi['top'] - vert
    y1 = cab['innerBack'] - float(cp['fitBack'])
    depth = float(ip.get('depth') or 0.0)
    if ip['insertType'] == INSERT_BLANK and depth <= 0:
        depth = BLANK_DEPTH
    if depth > 0:
        y1 = min(y1, cab['front'] + max(depth, DETENT_FRONT_OFFSET + 0.6))

    overlay = ip['frontStyle'] == FRONT_OVERLAY
    gap = float(ip['frontGap'])
    # Overlay front: covers the walls/dividers half way and the ledge zone above.
    nCols = len(cab['columns'])
    left = cab['x0'] if c == 0 else x0 - cab['divider'] / 2
    right = cab['x1'] if c == nCols - 1 else x1 + cab['divider'] / 2
    if r1 + 1 < len(cab['rows']):
        nxt = cab['rows'][r1 + 1]['bottom'] + (vert / 2 if cab['grooved'] else 0.0)
        panelTop = nxt - gap
    else:
        panelTop = cab['zTop'] - gap / 2
    panel = {
        'x0': left + gap / 2, 'x1': right - gap / 2,
        'z0': z0, 'z1': panelTop,
        'y0': cab['front'] - float(ip['front']), 'y1': cab['front'],
    }

    errors = list(cab['errors'])
    w = (x1 - lat) - (x0 + lat)
    h = z1 - z0
    if w < 1.0 or h < 0.6:
        errors.append('Slot too small for an insert')

    result = {
        'p': ip,
        'slot': slot,
        'overlay': overlay,
        'blank': ip['insertType'] == INSERT_BLANK,
        'x0': x0 + lat, 'x1': x1 - lat,
        'y0': cab['front'], 'y1': y1,
        'z0': z0, 'z1': z1,
        'colX0': x0, 'colX1': x1,
        'panel': panel if overlay else None,
        'grooveCenter': grooveCenter(rowLo) if cab['grooved'] else None,
        'contact': contactStrips(cab, c, r0) if cp['detent'] else [],
        'errors': errors,
    }
    result['spools'] = None
    if ip['interior'] == INTERIOR_SPOOLS and not result['blank']:
        result['spools'] = spoolLayout(result)
        errors.extend(result['spools']['errors'])
    return result


def ledgeSize(ip: dict, avail: float) -> dict:
    """Grooved ledge profile: protrusion p = rim + groove + rim, outer face
    hh = rim, total height H (the underside runs straight from the outer
    bottom edge to the front at H). H is the user's 'ledgeHeight' (0 = 45°),
    raised if needed so at least one rim of material stays under the groove,
    and fitted into `avail` (the groove shrinks first)."""
    rim = max(0.08, float(ip['ledgeRim']))
    wg = max(0.2, float(ip['fingerGrooveWidth']))
    dg = max(0.05, float(ip['fingerGrooveDepth']))
    wanted = float(ip.get('ledgeHeight') or 0.0)

    def solve(wg, dg):
        p = 2 * rim + wg
        hh = rim
        # Underside at distance s from the outer face: hh + (H - hh) * s / p
        # below the top. Keep a rim under the groove bottom (centre) and under
        # the start of a deep U groove's round part (s = rim).
        need = [(rim + wg / 2, dg + rim)]
        if dg > wg / 2:
            need.append((rim, dg - wg / 2 + rim))
        hMin = max(hh + max(0.0, depth - hh) * p / s for s, depth in need)
        # Wanted (or 45°) height, capped by the front, never below hMin.
        H = max(min(wanted if wanted > 0 else hh + p, avail), hMin)
        return p, hh, H, hMin
    p, hh, H, hMin = solve(wg, dg)
    if hMin > avail:
        # Even the lowest possible ledge is too high: shrink the groove.
        wg = max(0.3, wg - (hMin - avail))
        p, hh, H, hMin = solve(wg, dg)
        if hMin > avail:
            dg = max(0.05, dg - (hMin - avail))
            p, hh, H, hMin = solve(wg, dg)
    angle = math.degrees(math.atan2(H - hh, p))
    return {'rim': rim, 'wg': wg, 'dg': dg, 'p': p, 'hh': hh, 'H': H, 'hMin': hMin,
            'angle': angle, 'raised': wanted > 0 and H > wanted + 1e-6,
            'capped': wanted > 0 and H < wanted - 1e-6}


# Spool interior: cradle post thickness, spool side play, axle collar.
SPOOL_POST = 0.3
SPOOL_PLAY = 0.15
SPOOL_COLLAR = 0.2
SPOOL_COLLAR_GAP = 0.05
# Spool hangs on the axle: 1 mm over the floor; at the top it may reach the
# drawer rim (the cabinet's height clearance is still above it).
SPOOL_BOTTOM_GAP = 0.1
SPOOL_TOP_GAP = 0.0
SPOOL_BACK_GAP = 0.2
SPOOL_AXLE_PLAY = 0.08
# Wire eyelet post: depth, gap to the front wall and to the spool.
EYELET_DEPTH = 0.3
EYELET_GAP = 0.2
EYELET_ROOM = EYELET_GAP + EYELET_DEPTH + 0.1     # inner front -> spool at the post
# Axle in its cradles: laid in an open U, or clicked past two lips.
MOUNT_OPEN = 'Open'
MOUNT_SNAP = 'Snap-in'
SPOOL_MOUNTS = (MOUNT_OPEN, MOUNT_SNAP)
SPOOL_SNAP = 0.03            # lip overlap per side (0.3 mm)
# Axle: two halves joined by a bayonet in the middle (each printed standing
# on its collar), or one piece with a single collar (printed lying down).
AXLE_BAYONET = 'Bayonet (2 halves)'
AXLE_BAYONET_SMOOTH = 'Bayonet, smooth outside'
AXLE_ONE_PIECE = 'One piece'
AXLE_SPLITS = (AXLE_BAYONET, AXLE_BAYONET_SMOOTH, AXLE_ONE_PIECE)
MIN_SPOOL_WALL = 0.04        # thinnest divider / end support: one 0.4 mm line
# Thinner walls standing on the drawer floor (two 0.4 mm lines) hold badly:
# the dialog warns, nothing is changed.
THIN_WALL_WARNING = 0.08
# Wire outlet height in front of the spools.
HOLE_BOTTOM = 'Bottom'
HOLE_MIDDLE = 'Middle'
HOLE_TOP = 'Top'
HOLE_POSITIONS = (HOLE_BOTTOM, HOLE_MIDDLE, HOLE_TOP)


def spoolLayout(ins: dict) -> dict:
    """Spool interior inside an insert (cabinet local cm): axle position,
    cradle posts, spool centres, wire hole / guide positions, errors.

    Spools hang on one axle across the drawer, centred in depth and height
    (same play all around). With wire guides the eyelet posts stand in front
    of the spools: only as much depth as they need at their height (low
    eyelets fit under the round spool for free); the wire runs forward
    through the eyelet to a hole in the front.
    """
    ip = ins['p']
    tw = float(ip['wall'])
    tf = float(ip['floor'])
    frontT = 0.0 if ins['overlay'] else float(ip['front'])
    px0, px1 = ins['x0'] + tw, ins['x1'] - tw
    py0, py1 = ins['y0'] + frontT, ins['y1'] - tw
    floorZ = ins['z0'] + tf
    n = max(1, int(ip['spoolCount']))
    D = float(ip['spoolDiameter'])
    Ws = float(ip['spoolWidth'])
    axleD = max(0.3, float(ip['spoolBore']) - SPOOL_AXLE_PLAY)
    wireD = max(0.05, float(ip.get('spoolHoleDiameter') or ip['wireDiameter']))
    errors = []

    play = max(0.0, float(ip['spoolPlay']))
    div = max(MIN_SPOOL_WALL, float(ip['spoolDivider']))
    endPost = max(MIN_SPOOL_WALL, float(ip['spoolEnd']))
    collar = max(0.04, float(ip.get('axleCollar', SPOOL_COLLAR)))
    endPlay = max(0.0, float(ip.get('axleEndPlay', SPOOL_COLLAR_GAP)))
    collarRoom = collar + endPlay + 0.05                   # beside the outer posts
    slotW = Ws + 2 * play                                  # space for one spool
    span = 2 * endPost + (n - 1) * div + n * slotW         # end post to end post
    need = span + 2 * collarRoom
    avail = px1 - px0
    if need > avail + 1e-9:
        errors.append('{} spool(s) need {:.0f} mm, {:.0f} mm free inside'.format(n, need * 10, avail * 10))
    topZ = ins['z1'] - SPOOL_TOP_GAP
    maxD = topZ - floorZ - SPOOL_BOTTOM_GAP
    if D > maxD + 1e-9:
        errors.append('Spool too big for this drawer: max {:.0f} mm diameter'.format(maxD * 10))
    # Centred in height, but never closer than SPOOL_BOTTOM_GAP to the floor.
    zA = max(floorZ + SPOOL_BOTTOM_GAP + D / 2, (floorZ + topZ) / 2)
    if axleD >= D - 0.4:
        errors.append('Spool bore must be smaller than the spool')
    guides = bool(ip['spoolGuides'])
    # Wire outlet height (the eyelet follows), kept inside the front.
    wr = wireD / 2
    lo, hi = floorZ + max(0.5, wr + 0.25), ins['z1'] - wr - 0.4
    pos = ip.get('spoolHolePos', HOLE_BOTTOM)
    base = {HOLE_BOTTOM: lo, HOLE_MIDDLE: zA, HOLE_TOP: zA + D / 2}.get(pos, lo)
    holeZ = min(max(base + float(ip.get('spoolHoleOffset') or 0.0), lo), hi)

    r = D / 2
    # Axle distance from the inner front: the spool keeps SPOOL_BACK_GAP to
    # the front. An eyelet post (EYELET_DEPTH deep, up to just above the
    # hole) has to fit in front of the spool at the post's height: low down
    # the round spool is far back, so low eyelets need no extra depth.
    frontReach = SPOOL_BACK_GAP + r
    if guides:
        postTop = holeZ + wr + 0.3
        dz = zA - min(postTop, zA)
        spoolAtPost = math.sqrt(max(0.0, r * r - dz * dz)) if dz < r else 0.0
        frontReach = max(frontReach, EYELET_ROOM + spoolAtPost)
    yMin = py0 + frontReach
    yMax = py1 - SPOOL_BACK_GAP - r
    # Centred in depth.
    yA = min(max((py0 + py1) / 2, yMin), yMax)
    if yMin > yMax + 1e-9:
        errors.append('Drawer too short for this spool: needs {:.1f} mm inside depth, has {:.1f} mm'.format(
            (frontReach + r + SPOOL_BACK_GAP) * 10, (py1 - py0) * 10))
    # Eyelet halfway between the front and the spool at the post's height.
    if guides:
        guideY = max(py0 + EYELET_GAP + EYELET_DEPTH / 2, (py0 + yA - spoolAtPost) / 2)
    else:
        guideY = py0 + EYELET_GAP + EYELET_DEPTH / 2

    # Posts: end support, (spool, divider)*, spool, end support.
    x = (px0 + px1) / 2 - span / 2
    posts, centers = [(x, x + endPost)], []
    x += endPost
    for i in range(n):
        centers.append(x + slotW / 2)
        x += slotW
        thick = endPost if i == n - 1 else div
        posts.append((x, x + thick))
        x += thick

    return {
        'n': n, 'D': D, 'Ws': Ws, 'axleD': axleD, 'wireD': wireD,
        'zA': zA, 'yA': yA, 'floorZ': floorZ, 'maxD': maxD,
        'posts': posts, 'centers': centers, 'play': play,
        'snap': ip.get('spoolMount') == MOUNT_SNAP,
        'holeZ': holeZ, 'guideY': guideY,
        'axleX': (posts[0][0] - collar - endPlay, posts[-1][1] + collar + endPlay),
        'endPlay': endPlay,
        'fillet': max(0.0, float(ip.get('spoolFillet') or 0.0)),
        'axleMode': ip.get('axleSplit', AXLE_BAYONET) if ip.get('axleSplit') in AXLE_SPLITS else AXLE_BAYONET,
        'bayonet': ip.get('axleSplit', AXLE_BAYONET) != AXLE_ONE_PIECE,
        # One piece: the end without collar reaches towards the side wall.
        'plainEnd': (min(posts[-1][1] + float(ip.get('axleEndLength') or 0.0), px1 - endPlay)
                     if float(ip.get('axleEndLength') or 0.0) > 0 else px1 - endPlay),
        'errors': errors,
    }


def gridCells(innerW: float, innerL: float, baseW: float, baseL: float, cl: float):
    """How many Gridfinity cells fit an inner area (cell cutout = base + 2 cl)."""
    nx = int((innerW - 2 * cl) // baseW) if baseW > 0 else 0
    ny = int((innerL - 2 * cl) // baseL) if baseL > 0 else 0
    return max(0, nx), max(0, ny)


def describeCabinet(params: dict) -> str:
    p = withDefaults(params, CABINET_DEFAULTS)
    h = heightUnits(p)
    hText = str(int(round(h))) if abs(h - round(h)) < 1e-6 else '{:g}mm'.format(round(h * float(p['heightUnit']) * 10, 1))
    cab = cabinet(p)
    return 'Cabinet {}x{}x{} ({} col x {} rows)'.format(
        int(p['unitsW']), int(p['unitsL']), hText, len(cab['columns']), len(cab['rows']))


def describeInsert(cab: dict, params: dict) -> str:
    ip = withDefaults(params, INSERT_DEFAULTS)
    slot = clampInsert(cab, ip)
    kind = 'Drawer' if ip['insertType'] == INSERT_DRAWER else 'Cover'
    rows = str(slot['row']) if slot['span'] == 1 else '{}-{}'.format(slot['row'], slot['row'] + slot['span'] - 1)
    return '{} - col {}, row {}'.format(kind, slot['column'], rows)
