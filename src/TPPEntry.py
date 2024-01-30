# Version string of this plugin (in Python style).
__version__ = "2.7"

DYNAMIC_STATES_SETTING = "Dynamic States File"
DYNAMIC_STATES_FILE_NAME = "states.json"
DYNAMIC_STATES_FILE_VERSION = 4
# In Touch Portal: Execute X-Plane command 'RELOAD_STATES_FILE'
RELOAD_STATES_FILE_COMMAND = "RELOAD_STATES_FILE"  # when this command is executed, the states.json file is reloaded


def dotkey(*a):
    return ".".join(a)


# The unique plugin ID string is used in multiple places.
# It also forms the base for all other ID strings (for states, actions, etc).
PLUGIN_ID = dotkey("tp", "plugin", "xplaneudp")
PLUGIN_ICON = "tpxpudpplugin.png"


def pluginkey(*a):
    return dotkey(PLUGIN_ID, *a)


# Basic plugin metadata
TP_PLUGIN_INFO = {
    "sdk": 6,
    "version": int(float(__version__) * 100) + int(DYNAMIC_STATES_FILE_VERSION),  # TP only recognizes integer version numbers
    "name": "Touch Portal X-Plane UDP Plugin",
    "id": PLUGIN_ID,
    # Startup command, with default logging options read from configuration file (see main() for details)
    "plugin_start_cmd": "sh %TP_PLUGIN_FOLDER%TouchPortal-X-Plane-UDP/start.sh TouchPortal-X-Plane-UDP @plugin_config.txt",
    "plugin_start_cmd_mac": "sh %TP_PLUGIN_FOLDER%TouchPortal-X-Plane-UDP/start.sh TouchPortal-X-Plane-UDP @plugin_config.txt",
    "plugin_start_cmd_linux": "sh %TP_PLUGIN_FOLDER%TouchPortal-X-Plane-UDP/start.sh TouchPortal-X-Plane-UDP @plugin_config.txt",
    "plugin_start_cmd_windows": "%TP_PLUGIN_FOLDER%TouchPortal-X-Plane-UDP\\TouchPortal-X-Plane-UDP.exe @plugin_config.txt",
    "configuration": {"colorDark": "#25274c", "colorLight": "#707ab5"},  # that's a dark blue and lighter blue.
    "doc": {
        "repository": "devleaks:TouchPortal-X-Plane-UDP",
        "Install": "Please refer to the README file",
        "description": "Touch Portal to X-Plane UDP Plugin Adaptor",
    },
}

# Setting(s) for this plugin. These could be either for users to
# set, or to persist data between plugin runs (as read-only settings).
TP_PLUGIN_SETTINGS = {
    DYNAMIC_STATES_SETTING: {
        "name": DYNAMIC_STATES_SETTING,
        # "text" is the default type and could be omitted here
        "type": "text",
        "default": DYNAMIC_STATES_FILE_NAME,
        "readOnly": True,
        "doc": "File containing TP states to X-Plane dataref mappings",
        "value": None,  # we can optionally use the settings struct to hold the current value
    }
}

# This example only uses one Category for actions/etc., but multiple categories are supported also.
TP_PLUGIN_CATEGORIES = {"main": {"id": pluginkey("main"), "name": "X-Plane UDP", "imagepath": "%TP_PLUGIN_FOLDER%TouchPortal-X-Plane-UDP/tpxpudpplugin.png"}}

# Action(s) which this plugin supports.
TP_PLUGIN_ACTIONS = {
    "ExecuteCommand": {
        # Action to execute a command in X-Plane through UDP
        "category": "main",
        "id": pluginkey("act", "ExecuteCommand"),
        "name": "Execute X-Plane command",
        "prefix": TP_PLUGIN_CATEGORIES["main"]["name"],
        "type": "communicate",
        "lines": {"action": [{"language": "default", "data": [{"lineFormat": "Execute $[command]"}]}]},
        "tryInline": True,
        "doc": "Execute X-Plane command",
        # "format" tokens like $[1] will be replaced in the generated JSON with the corresponding data id wrapped with "{$...$}".
        # Numeric token values correspond to the order in which the data items are listed here, while text tokens correspond
        # to the last part of a dotted data ID (the part after the last period; letters, numbers, and underscore allowed).
        "format": "Execute $[command]",
        "data": {"command": {"id": pluginkey("act", "XPlaneCommand", "data", "command"), "type": "text", "label": "Command", "default": None}},
    },
    "ExecuteLongPressCommand": {
        # Action to execute a pair of command in X-Plane through UDP.
        # When button is pressed, 'command/begin' is send to X-Plane plugin,
        # execution of 'command' is started until button is released,
        # in which case 'command/end' is sent to stop the execution of 'command'.
        "category": "main",
        "id": pluginkey("act", "ExecuteLongPressCommand"),
        "name": "Execute X-Plane long press command",
        "prefix": TP_PLUGIN_CATEGORIES["main"]["name"],
        "type": "communicate",
        "lines": {"action": [{"language": "default", "data": [{"lineFormat": "Execute while pressed $[command]"}]}]},
        "tryInline": True,
        "hasHoldFunctionality": True,
        "doc": "Execute X-Plane long press command",
        "format": "Execute while pressed $[command]",
        "data": {"command": {"id": pluginkey("act", "XPlaneLongPressCommand", "data", "command"), "type": "text", "label": "Command", "default": None}},
    },
    "SetDataref": {
        # Action to set the value of a single, writable dataref through UDP.
        # Recall that value set is a float.
        "category": "main",
        "id": pluginkey("act", "SetDataref"),
        "name": "Set X-Plane dataref to a value",
        "prefix": TP_PLUGIN_CATEGORIES["main"]["name"],
        "type": "communicate",
        "lines": {"action": [{"language": "default", "data": [{"lineFormat": "Set $[dataref] to $[datarefvalue]"}]}]},
        "tryInline": True,
        "doc": "Set X-Plane dataref to a value",
        "format": "Set $[dataref] to $[datarefvalue]",
        "data": {
            "dataref": {"id": pluginkey("act", "SetDataref", "data", "dataref"), "type": "text", "label": "Dataref", "default": None},
            "datarefvalue": {"id": pluginkey("act", "SetDataref", "data", "datarefvalue"), "type": "text", "label": "Dataref Value", "default": None},
        },
    },
    "LeavingPage": {
        # Action to transmit the name of the page we are currently leaving.
        "category": "main",
        "id": pluginkey("act", "LeavingPage"),
        "name": "Leaving page",
        "prefix": TP_PLUGIN_CATEGORIES["main"]["name"],
        "type": "communicate",
        "lines": {"action": [{"language": "default", "data": [{"lineFormat": "Leaving page $[pagePath]"}]}]},
        "tryInline": True,
        "hasHoldFunctionality": True,
        "doc": "Leaving page",
        "format": "Leaving page $[pagePath]",
        "data": {"pagePath": {"id": pluginkey("act", "LeavingPage", "data", "pagePath"), "type": "text", "label": "Page path", "default": None}},
    },
}

TP_PLUGIN_CONNECTORS = {}

# Plugin static state(s). These are listed in the entry.tp file,
# vs. dynamic states which would be created/removed at runtime.
TP_PLUGIN_STATES = {
    "XPlaneConnected": {
        # Boolean, true when connected to X-Plane.
        "category": "main",
        "id": pluginkey("state", "XPlaneConnected"),
        "type": "text",
        "desc": "X-Plane running",
        "doc": "1 if X-Plane instance available",
        "default": "0",
    },
    "ConnectionMonitoringRunning": {
        # Boolean, true when the monitoring of the connection to X-Plane runs.
        # If no conncetion to X-Plane, monitor tries to reconnect until it succeeds.
        "category": "main",
        "id": pluginkey("state", "ConnectionMonitoringRunning"),
        "type": "text",
        "desc": "Connection Monitor running",
        "doc": "1 if plugin Connection Monitor running",
        "default": "0",
    },
    "MonitoringRunning": {
        # Boolean, true when the monitoring of datarefs is running.
        "category": "main",
        "id": pluginkey("state", "MonitoringRunning"),
        "type": "text",
        "desc": "Dataref Monitor running",
        "doc": "1 if plugin Dataref Monitor running",
        "default": "0",
    },
}

# Plugin Event(s).
TP_PLUGIN_EVENTS = {}
