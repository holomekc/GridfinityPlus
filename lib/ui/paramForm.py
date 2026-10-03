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
