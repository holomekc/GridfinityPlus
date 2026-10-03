# Here you define the commands that will be added to your add-in.

# TODO Import the modules corresponding to the commands you created.
# If you want to add an additional command, duplicate one of the existing directories and import it here.
# You need to use aliases (import "entry" as "my_module") assuming you have the default module named "entry".
from .commandCreateBin import entry as commandCreateBin
from .commandEditBaseplate import entry as commandEditBaseplate
from .commandCreateBaseplate import entry as commandCreateBaseplate
from .commandToolCutout import entry as commandToolCutout
from .commandCreateCabinet import entry as commandCreateCabinet
from .commandCreateDrawer import entry as commandCreateDrawer
from .commandCreateCover import entry as commandCreateCover
from . import contextEdit

# TODO add imported modules to this list.
# Fusion will automatically call the start() and stop() functions.
# commandEditBaseplate is listed before commandCreateBaseplate so its command
# definition exists when the custom feature definition references it.
# The bin custom feature uses commandCreateBin itself as its edit command.
commands = [
    commandCreateBin,
    commandEditBaseplate,
    commandCreateBaseplate,
    commandToolCutout,
    commandCreateCabinet,
    commandCreateDrawer,
    commandCreateCover,
    # Right-click "Edit …" (Part designs have no timeline edit for add-in features).
    contextEdit,
]


# Assumes you defined a "start" function in each of your modules.
# The start function will be run when the add-in is started.
def start():
    for command in commands:
        command.start()


# Assumes you defined a "stop" function in each of your modules.
# The stop function will be run when the add-in is stopped.
def stop():
    for command in commands:
        command.stop()
