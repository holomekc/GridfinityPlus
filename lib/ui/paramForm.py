"""
Tiny declarative helpers for dialogs whose input ids ARE the params keys.

build: add an input seeded from params[id]; read: params dict back from the
inputs. Lengths are Fusion internal units (cm), like everywhere else.
"""

import adsk.core


def length(parent: adsk.core.CommandInputs, inputId: str, label: str, params: dict,
           units: str, minimum: float = None, maximum: float = None, tooltip: str = ''):
    inp = parent.addValueInput(inputId, label, units, adsk.core.ValueInput.createByReal(float(params[inputId])))
    if minimum is not None:
        inp.minimumValue = minimum
        inp.isMinimumInclusive = True
    if maximum is not None:
        inp.maximumValue = maximum
        inp.isMaximumInclusive = True
    if tooltip:
        inp.tooltip = tooltip
    return inp


def offset(parent: adsk.core.CommandInputs, inputId: str, label: str, params: dict,
           units: str, tooltip: str = ''):
    """Signed length (no limits), e.g. a position offset."""
    return length(parent, inputId, label, params, units, tooltip=tooltip)


def unitless(parent: adsk.core.CommandInputs, inputId: str, label: str, params: dict, tooltip: str = ''):
    inp = parent.addValueInput(inputId, label, '', adsk.core.ValueInput.createByReal(float(params[inputId])))
    if tooltip:
        inp.tooltip = tooltip
    return inp


def integer(parent: adsk.core.CommandInputs, inputId: str, label: str, params: dict,
            lo: int, hi: int, tooltip: str = ''):
    value = max(lo, min(hi, int(params[inputId])))
    inp = parent.addIntegerSpinnerCommandInput(inputId, label, lo, hi, 1, value)
    if tooltip:
        inp.tooltip = tooltip
    return inp


def boolean(parent: adsk.core.CommandInputs, inputId: str, label: str, params: dict, tooltip: str = ''):
    inp = parent.addBoolValueInput(inputId, label, True, '', bool(params[inputId]))
    if tooltip:
        inp.tooltip = tooltip
    return inp


def choice(parent: adsk.core.CommandInputs, inputId: str, label: str, params: dict,
           options, tooltip: str = ''):
    inp = parent.addDropDownCommandInput(inputId, label, adsk.core.DropDownStyles.TextListDropDownStyle)
    current = params.get(inputId)
    if current not in options:
        current = options[0]
    for option in options:
        inp.listItems.add(option, option == current)
    if tooltip:
        inp.tooltip = tooltip
    return inp


def text(parent: adsk.core.CommandInputs, inputId: str, label: str, params: dict, tooltip: str = ''):
    inp = parent.addStringValueInput(inputId, label, str(params.get(inputId, '')))
    if tooltip:
        inp.tooltip = tooltip
    return inp


def readOne(inp: adsk.core.CommandInput):
    dd = adsk.core.DropDownCommandInput.cast(inp)
    if dd:
        return dd.selectedItem.name if dd.selectedItem else None
    spinner = adsk.core.IntegerSpinnerCommandInput.cast(inp)
    if spinner:
        return int(spinner.value)
    boolInput = adsk.core.BoolValueCommandInput.cast(inp)
    if boolInput:
        return bool(boolInput.value)
    value = adsk.core.ValueCommandInput.cast(inp)
    if value:
        return float(value.value)
    string = adsk.core.StringValueCommandInput.cast(inp)
    if string:
        return string.value
    return None


def read(inputs: adsk.core.CommandInputs, ids) -> dict:
    out = {}
    for inputId in ids:
        inp = inputs.itemById(inputId)
        if inp is not None:
            out[inputId] = readOne(inp)
    return out


def setVisible(inputs: adsk.core.CommandInputs, inputId: str, visible: bool):
    inp = inputs.itemById(inputId)
    if inp is not None and inp.isVisible != visible:
        inp.isVisible = visible


def selectChoice(inputs: adsk.core.CommandInputs, inputId: str, name: str):
    dd = adsk.core.DropDownCommandInput.cast(inputs.itemById(inputId))
    if dd is None:
        return
    for item in dd.listItems:
        if item.name == name:
            item.isSelected = True
            return


# ------------------------------------------------------------------ results

def _resultId(groupId: str, key: str) -> str:
    # Fusion only accepts ASCII ids ('Ø' in a key made the dialog fail).
    return groupId + '_' + ''.join(ch if ch.isascii() and ch.isalnum() else '_' for ch in key)


def resultGroup(inputs: adsk.core.CommandInputs, groupId: str, title: str, keys):
    """A 'Result' group: one read-only 'key: value' line per key, plus a
    problems box (red) that only shows when there are problems."""
    group = inputs.addGroupCommandInput(groupId, title)
    for key in keys:
        line = group.children.addStringValueInput(_resultId(groupId, key), key, '')
        line.isReadOnly = True
        line.isVisible = False
    problems = group.children.addTextBoxCommandInput(groupId + '_problems', 'Problems', '', 3, True)
    problems.isVisible = False
    return group


def isResultInput(groupId: str, inputId: str) -> bool:
    return inputId.startswith(groupId + '_')


def setResults(inputs: adsk.core.CommandInputs, groupId: str, values: dict, problems=()):
    """values: {key: text or None}; None / missing keys are hidden."""
    group = adsk.core.GroupCommandInput.cast(inputs.itemById(groupId))
    if group is None:
        return
    for i in range(group.children.count):
        line = adsk.core.StringValueCommandInput.cast(group.children.item(i))
        if line is None:
            continue
        text = None
        for key, value in values.items():
            if _resultId(groupId, key) == line.id:
                text = value
        visible = text is not None
        if line.isVisible != visible:
            line.isVisible = visible
        if visible and line.value != text:
            line.value = text
    box = adsk.core.TextBoxCommandInput.cast(inputs.itemById(groupId + '_problems'))
    if box is not None:
        html = '<br>'.join(f'<font color="red">{p}</font>' for p in problems)
        if box.isVisible != bool(problems):
            box.isVisible = bool(problems)
        if box.formattedText != html:
            box.formattedText = html
