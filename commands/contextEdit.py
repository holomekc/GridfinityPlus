"""
GridfinityPlus — "Edit …" in the right-click menu.

In Part design documents (design intent "Part") Fusion offers neither
"Edit Feature" nor timeline double-click for add-in custom features. With a
bin / baseplate / cabinet / drawer (its timeline node, browser entry or body)
selected, the right-click menu gets "Edit Gridfinity+ …" on top, which opens
the same dialog as the timeline edit does in other designs.

"Copy Gridfinity+ settings" / "Paste Gridfinity+ settings" copy everything
but the position from one feature to another of the same kind: paste opens
the edit dialog with the copied values (preview, OK applies). After a copy,
new features of that kind start with the copied settings too.
"""

import adsk.core, adsk.fusion

from .. import config
from ..lib import fusion360utils as futil
from ..lib.gridfinityUtils import gplog
from ..lib.gridfinityUtils import baseplateFeature
from ..lib.gridfinityUtils import binFeature
from ..lib.gridfinityUtils import boxSystemFeature as box
from .commandEditBaseplate import entry as editBaseplate
from .commandCreateBaseplate import entry as createBaseplate
from ..lib.gridfinityUtils import placement
from .commandCreateBin import entry as createBin
from .commandCreateCabinet import entry as createCabinet
from .commandCreateDrawer import entry as createDrawer
from .commandCreateCover import entry as createCover

app = adsk.core.Application.get()
ui = app.userInterface

_PREFIX = f'{config.COMPANY_NAME}_{config.ADDIN_NAME}_ctxEdit'
# Edit commands of our own, so the menu says "Edit …"; they open the normal
# dialogs, which switch to edit mode for the selected feature.
_OWN = (
    (binFeature.FEATURE_ID, _PREFIX + 'Bin', 'Edit Gridfinity+ Bin', createBin),
    (box.CABINET.featureId, _PREFIX + 'Cabinet', 'Edit Gridfinity+ Cabinet', createCabinet),
    (box.INSERT.featureId, _PREFIX + 'Drawer', 'Edit Gridfinity+ Drawer', createDrawer),
    (box.COVER.featureId, _PREFIX + 'Cover', 'Edit Gridfinity+ Cover', createCover),
)

_menuHandler = None

_COPY_ID = _PREFIX + 'CopySettings'
_PASTE_ID = _PREFIX + 'PasteSettings'
_PASTE_EVENT = _PREFIX + 'PasteEvent'
# Feature definition id -> copied settings (this session).
_clipboard = {}
_copyHandlers = []
_pasteEvent = None
_pasteEventHandler = None

# Keys that place a feature (kept on paste, never copied).
_PLACE_KEYS = {
    binFeature.FEATURE_ID: ('plateToken', 'col', 'row', 'rotation', 'ovh', 'overhangFlags', 'placed'),
    box.CABINET.featureId: ('plateToken', 'col', 'row', 'rotation', 'ovh', 'overhangFlags'),
    box.COVER.featureId: ('plateToken', 'col', 'row', 'rotation', 'ovh', 'overhangFlags'),
    box.INSERT.featureId: ('cabinetToken', 'column', 'row', 'span', 'pullOut'),
    baseplateFeature.FEATURE_ID: tuple(placement.PLACEMENT_KEYS),
}
_KIND_NAMES = {
    binFeature.FEATURE_ID: 'bin', box.CABINET.featureId: 'cabinet', box.COVER.featureId: 'cover',
    box.INSERT.featureId: 'drawer', baseplateFeature.FEATURE_ID: 'baseplate',
}


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
        kind = cf.definition.id
        copyDef = ui.commandDefinitions.itemById(_COPY_ID)
        if copyDef and controls.itemById(_COPY_ID) is None:
            controls.addCommand(copyDef, '', False)
        pasteDef = ui.commandDefinitions.itemById(_PASTE_ID)
        if pasteDef and kind in _clipboard and controls.itemById(_PASTE_ID) is None:
            controls.addCommand(pasteDef, '', False)
        gplog.log(f'context menu: "Edit" for "{cf.name}"')
    except Exception:
        gplog.logExc('context menu')


def _selectedFeatures():
    """All selected features of ours (each once)."""
    edits = _editCommands()
    found = []
    for i in range(ui.activeSelections.count):
        cf, _ = _ownFeature(ui.activeSelections.item(i).entity, edits)
        if cf is not None and cf not in found:
            found.append(cf)
    return found


def _selectedFeature():
    found = _selectedFeatures()
    return found[0] if found else None


def _readParams(cf):
    kind = cf.definition.id
    if kind == binFeature.FEATURE_ID:
        return binFeature.readParams(cf)
    if kind == baseplateFeature.FEATURE_ID:
        return baseplateFeature.readParams(cf)
    for k in (box.CABINET, box.INSERT, box.COVER):
        if k.featureId == kind:
            return k.readParams(cf)
    return None


def settingsOf(kind: str, params: dict) -> dict:
    """Everything but the position."""
    skip = set(_PLACE_KEYS.get(kind, ()))
    return {k: v for k, v in params.items() if k not in skip}


def _seedCreate(kind: str, settings: dict):
    """New features of this kind start with the copied settings."""
    if kind == box.CABINET.featureId:
        createCabinet._lastParams = dict(createCabinet._lastParams, **settings)
    elif kind == box.INSERT.featureId:
        createDrawer._lastParams = dict(createDrawer._lastParams, **settings)
    elif kind == box.COVER.featureId:
        createCover._lastParams = dict(createCover._lastParams, **settings)
    elif kind == binFeature.FEATURE_ID:
        createBin._createSeed = settings
    elif kind == baseplateFeature.FEATURE_ID:
        createBaseplate._createSeed = settings


def _onCopy(args: adsk.core.CommandCreatedEventArgs):
    try:
        cf = _selectedFeature()
        params = _readParams(cf) if cf is not None else None
        if not params:
            ui.messageBox('Select a Gridfinity+ bin, baseplate, cabinet, drawer or cover first.')
            return
        kind = cf.definition.id
        _clipboard[kind] = settingsOf(kind, params)
        _seedCreate(kind, _clipboard[kind])
        gplog.log(f'copy settings from "{cf.name}" ({len(_clipboard[kind])} keys)')
    except Exception:
        gplog.logExc('copy settings')


_pasteHandlers = []


def _onPaste(args: adsk.core.CommandCreatedEventArgs):
    """One target: open its edit dialog with the copied settings (preview, OK).
    Several: apply to all of them right away (one undo step)."""
    try:
        targets = [cf for cf in _selectedFeatures() if cf.definition.id in _clipboard]
        if not targets:
            ui.messageBox('Copy the settings of a feature of the same kind first.')
            return
        if len(targets) == 1:
            # Open the edit dialog once this command has ended.
            app.fireCustomEvent(_PASTE_EVENT, targets[0].entityToken)
            return
        tokens = [cf.entityToken for cf in targets]
        _pasteHandlers.clear()
        futil.add_handler(args.command.execute, lambda a: _pasteOnto(tokens),
                          name='pasteSettingsMany', local_handlers=_pasteHandlers)
    except Exception:
        gplog.logExc('paste settings')


def _pasteOnto(tokens):
    """Apply the copied settings to every feature (position stays)."""
    des = adsk.fusion.Design.cast(app.activeProduct)
    done, failed = 0, []
    for token in tokens:
        cf = None
        for e in des.findEntityByToken(token):
            cf = adsk.fusion.CustomFeature.cast(e)
            if cf is not None:
                break
        if cf is None:
            continue
        name = cf.name
        try:
            kind = cf.definition.id
            merged = dict(_readParams(cf) or {}, **_clipboard[kind])
            if kind == binFeature.FEATURE_ID:
                occ, grid, _ = binFeature.resolvePlate(des, merged.get('plateToken'))
                if grid is not None and merged.get('plateToken'):
                    merged['col'], merged['row'] = binFeature.clampCell(grid, merged)
                    merged['ovh'] = binFeature.overhangAmounts(
                        grid, merged, binFeature.extendModes(merged.get('overhangFlags', {})))
                body = createBin.buildBinBodyFromParams(des, merged)
                matrix, _ = binFeature.placementMatrix(des, merged, world=False)
                binFeature.rebuildFeature(des, cf, binFeature.placedCopy(body, matrix), merged)
            elif kind == baseplateFeature.FEATURE_ID:
                baseplateFeature.rebuildFeature(des, cf, merged)
            elif kind == box.CABINET.featureId:
                box.rebuildCabinet(des, cf, merged)
            elif kind == box.INSERT.featureId:
                box.rebuildInsert(des, cf, merged)
            elif kind == box.COVER.featureId:
                box.rebuildCover(des, cf, merged)
            done += 1
            gplog.log(f'paste settings onto "{name}"')
        except Exception:
            gplog.logExc(f'paste settings onto "{name}"')
            failed.append(name)
    if failed:
        ui.messageBox(f'Settings pasted onto {done} of {len(tokens)}. Failed: ' + ', '.join(failed), 'Gridfinity+')


def _onPasteEvent(args: adsk.core.CustomEventArgs):
    """After the paste command ended: open the edit dialog with the copied
    settings for the feature (token in additionalInfo)."""
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        cf = None
        for e in des.findEntityByToken(args.additionalInfo):
            cf = adsk.fusion.CustomFeature.cast(e)
            if cf is not None:
                break
        if cf is None:
            return
        kind = cf.definition.id
        seed = _clipboard.get(kind)
        if seed is None:
            return
        module = {binFeature.FEATURE_ID: createBin, box.CABINET.featureId: createCabinet,
                  box.INSERT.featureId: createDrawer, box.COVER.featureId: createCover,
                  baseplateFeature.FEATURE_ID: editBaseplate}[kind]
        module._pasteSeed = dict(seed)
        ui.activeSelections.clear()
        ui.activeSelections.add(cf)
        definition = ui.commandDefinitions.itemById(_editCommands()[kind])
        gplog.log(f'paste settings onto "{cf.name}"')
        definition.execute()
    except Exception:
        gplog.logExc('paste settings: open edit dialog')


def start():
    global _menuHandler
    for featureId, cmdId, name, module in _OWN:
        definition = ui.commandDefinitions.itemById(cmdId)
        if not definition:
            definition = ui.commandDefinitions.addButtonDefinition(
                cmdId, name, f'Edit the selected {name[5:]}', module.ICON_FOLDER)
            futil.add_handler(definition.commandCreated, module.command_created)
    _menuHandler = futil.add_handler(ui.markingMenuDisplaying, _onMarkingMenu, name='contextEdit')
    global _pasteEvent, _pasteEventHandler
    for cmdId, name, tip, callback in (
            (_COPY_ID, 'Copy Gridfinity+ settings', 'Copy all settings (not the position) of the selected feature',
             _onCopy),
            (_PASTE_ID, 'Paste Gridfinity+ settings',
             'Paste the copied settings (position stays). One selected: opens its edit dialog. '
             'Several selected: applied to all of them.', _onPaste)):
        definition = ui.commandDefinitions.itemById(cmdId)
        if not definition:
            definition = ui.commandDefinitions.addButtonDefinition(cmdId, name, tip, createBin.ICON_FOLDER)
        _copyHandlers.append(futil.add_handler(definition.commandCreated, callback))
    try:
        app.unregisterCustomEvent(_PASTE_EVENT)
    except Exception:
        pass
    _pasteEvent = app.registerCustomEvent(_PASTE_EVENT)
    _pasteEventHandler = futil.add_handler(_pasteEvent, _onPasteEvent, name='pasteSettings')


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
    global _pasteEvent, _pasteEventHandler
    for cmdId in (_COPY_ID, _PASTE_ID):
        definition = ui.commandDefinitions.itemById(cmdId)
        if definition:
            definition.deleteMe()
    _copyHandlers.clear()
    try:
        if _pasteEvent is not None and _pasteEventHandler is not None:
            _pasteEvent.remove(_pasteEventHandler)
        app.unregisterCustomEvent(_PASTE_EVENT)
    except Exception:
        pass
    _pasteEvent = _pasteEventHandler = None
