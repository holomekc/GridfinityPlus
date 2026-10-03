"""
GridfinityPlus — "Edit …" in the right-click menu.

In Part design documents (design intent "Part") Fusion offers neither
"Edit Feature" nor timeline double-click for add-in custom features. With a
bin / baseplate / cabinet / drawer (its timeline node, browser entry or body)
selected, the right-click menu gets "Edit Gridfinity+ …" on top, which opens
the same dialog as the timeline edit does in other designs.
"""

import adsk.core, adsk.fusion

from .. import config
from ..lib import fusion360utils as futil
from ..lib.gridfinityUtils import gplog
from ..lib.gridfinityUtils import baseplateFeature
from ..lib.gridfinityUtils import binFeature
from ..lib.gridfinityUtils import boxSystemFeature as box
from .commandEditBaseplate import entry as editBaseplate
from .commandCreateBin import entry as createBin
from .commandCreateCabinet import entry as createCabinet
from .commandCreateDrawer import entry as createDrawer

app = adsk.core.Application.get()
ui = app.userInterface

_PREFIX = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_ctxEdit'
# Edit commands of our own, so the menu says "Edit …"; they open the normal
# dialogs, which switch to edit mode for the selected feature.
_OWN = (
    (binFeature.FEATURE_ID, _PREFIX + 'Bin', 'Edit Gridfinity+ Bin', createBin),
    (box.CABINET.featureId, _PREFIX + 'Cabinet', 'Edit Gridfinity+ Cabinet', createCabinet),
    (box.INSERT.featureId, _PREFIX + 'Drawer', 'Edit Gridfinity+ Drawer', createDrawer),
)

_menuHandler = None


def _editCommands():
    """custom feature definition id -> command id shown in the menu."""
    edits = {featureId: cmdId for featureId, cmdId, _, _ in _OWN}
    edits[baseplateFeature.FEATURE_ID] = editBaseplate.CMD_ID
    return edits


def _ownFeature(entity, edits):
    """(customFeature, command id) for a feature of ours or one of its bodies."""
    cf = adsk.fusion.CustomFeature.cast(entity)
    if cf:
        return (cf, edits[cf.definition.id]) if cf.definition.id in edits else (None, None)
    body = adsk.fusion.BRepBody.cast(entity)
    if not body:
        return None, None
    native = body.nativeObject if body.nativeObject else body
    feats = native.parentComponent.features.customFeatures
    for i in range(feats.count):
        cf = feats.item(i)
        if cf.definition.id not in edits:
            continue
        for feat in cf.features:
            base = adsk.fusion.BaseFeature.cast(feat)
            if base and any(b == native for b in base.bodies):
                return cf, edits[cf.definition.id]
    return None, None


def _onMarkingMenu(args: adsk.core.MarkingMenuEventArgs):
    try:
        edits = _editCommands()
        cf, cmdId = None, None
        for entity in args.selectedEntities:
            cf, cmdId = _ownFeature(entity, edits)
            if cf is not None:
                break
        if cf is None:
            return
        definition = ui.commandDefinitions.itemById(cmdId)
        controls = args.linearMarkingMenu.controls
        if definition and controls.itemById(cmdId) is None:
            controls.addSeparator(_PREFIX + 'Separator', '', False)
            controls.addCommand(definition, '', False)
        gplog.log(f'context menu: "Edit" for "{cf.name}"')
    except Exception:
        gplog.logExc('context menu')


def start():
    global _menuHandler
    for featureId, cmdId, name, module in _OWN:
        definition = ui.commandDefinitions.itemById(cmdId)
        if not definition:
            definition = ui.commandDefinitions.addButtonDefinition(
                cmdId, name, f'Edit the selected {name[5:]}', module.ICON_FOLDER)
            futil.add_handler(definition.commandCreated, module.command_created)
    _menuHandler = futil.add_handler(ui.markingMenuDisplaying, _onMarkingMenu, name='contextEdit')


def stop():
    global _menuHandler
    if _menuHandler is not None:
        try:
            ui.markingMenuDisplaying.remove(_menuHandler)
        except Exception:
            pass
        _menuHandler = None
    for featureId, cmdId, name, module in _OWN:
        definition = ui.commandDefinitions.itemById(cmdId)
        if definition:
            definition.deleteMe()
