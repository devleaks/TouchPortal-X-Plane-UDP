"""
Touch Portal Plugin Example
"""

import sys

# Load the TP Python API. Note that TouchPortalAPI must be installed (eg. with pip)
# _or_ be in a folder directly below this plugin file.
import TouchPortalAPI as TP
from xplane import XPlane

# Importing our python entry struct so we can get infomations of the plugin without copy and paste
# So you can change a action id and it will update here.
import TPPEntry

# imports below are optional, to provide argument parsing and logging functionality
from argparse import ArgumentParser
from TouchPortalAPI.logger import Logger

# Crate the (optional) global logger, an instance of `TouchPortalAPI::Logger` helper class.
# Logging configuration is set up in main().
g_log = Logger(name=TPPEntry.PLUGIN_ID)


# Create the Touch Portal API client.
try:
    TPClient = TP.Client(
        pluginId=TPPEntry.PLUGIN_ID,  # required ID of this plugin
        sleepPeriod=0.05,  # allow more time than default for other processes
        autoClose=True,  # automatically disconnect when TP sends "closePlugin" message
        checkPluginId=True,  # validate destination of messages sent to this plugin
        maxWorkers=4,  # run up to 4 event handler threads
        updateStatesOnBroadcast=False,  # do not spam TP with state updates on every page change
    )
except Exception as e:
    sys.exit(f"Could not create TP Client, exiting. Error was:\n{repr(e)}")
# TPClient: TP.Client = None  # instance of the TouchPortalAPI Client, created in main()

# Create the X-Plane client.
# XPClient = None
try:
    XPClient = XPlane(tpclient=TPClient)
except Exception as e:
    sys.exit(f"Could not create X-Plane client instance, exiting. Error was:\n{repr(e)}")


# Settings will be sent by TP upon initial connection to the plugin,
# as well as whenever they change at runtime. This example uses a
# shared function to handle both cases. See also onConnect() and onSettingUpdate()
def handleSettings(settings, on_connect=False):
    # the settings array from TP can just be flattened to a single dict,
    # from:
    #   [ {"Setting 1" : "value"}, {"Setting 2" : "value"} ]
    # to:
    #   { "Setting 1" : "value", "Setting 2" : "value" }
    settings = {list(settings[i])[0]: list(settings[i].values())[0] for i in range(len(settings))}
    if TPClient is not None and XPClient is not None:
        states_fn = settings.get(TPPEntry.DYNAMIC_STATES_SETTING, TPPEntry.DYNAMIC_STATES_FILE_NAME)
        g_log.info(f"loading settings file {states_fn}")
        # g_log.info("reloading states  file")
        # XPClient.reinit(states_fn)

    # now we can just get settings, and their values, by name
    # if (value := settings.get(TPPEntry.TP_PLUGIN_SETTINGS["example"]["name"])) is not None:
    #     # this example doesn't do anything useful with the setting, just saves it
    #     TPPEntry.TP_PLUGIN_SETTINGS["example"]["value"] = value


## TP Client event handler callbacks


# Initial connection handler
@TPClient.on(TP.TYPES.onConnect)
def onConnect(data):
    g_log.info(f"Connected to TP v{data.get('tpVersionString', '?')}, plugin v{data.get('pluginVersion', '?')}.")
    g_log.debug(f"Connection: {data}")
    if settings := data.get("settings"):
        handleSettings(settings, True)

    g_log.debug("Initialising X-Plane client..")
    # This will create all dynamic states, establish X-Plane connection,
    # and start monitoring datarefs.
    XPClient.init()
    g_log.debug("..X-Plane client started")


# Settings handler
@TPClient.on(TP.TYPES.onSettingUpdate)
def onSettingUpdate(data):
    g_log.debug(f"Settings: {data}")
    if settings := data.get("values"):
        handleSettings(settings, False)


# Action handler
@TPClient.on(TP.TYPES.onAction)
def onAction(data):
    g_log.debug(f"Action: {data}")
    # check that `data` and `actionId` members exist and save them for later use
    if not (action_data := data.get("data")) or not (aid := data.get("actionId")):
        return

    if aid == TPPEntry.TP_PLUGIN_ACTIONS["ExecuteCommand"]["id"]:
        action_value = TPClient.getActionDataValue(action_data, TPPEntry.TP_PLUGIN_ACTIONS["ExecuteCommand"]["data"]["command"]["id"])
        if action_value == "":
            g_log.warning("Key press has no command associated")
            return
        if action_value == TPPEntry.RELOAD_STATES_FILE_COMMAND:  # hack, trick, special keyword for developments
            g_log.info("reloading states  file")
            XPClient.reinit()
            return
        XPClient.commandOnce(action_value)
        g_log.debug(f"commandOnce {action_value}")

    elif aid == TPPEntry.TP_PLUGIN_ACTIONS["SetDataref"]["id"]:
        dataref_name = TPClient.getActionDataValue(action_data, TPPEntry.TP_PLUGIN_ACTIONS["SetDataref"]["data"]["dataref"]["id"])
        dataref_value = TPClient.getActionDataValue(action_data, TPPEntry.TP_PLUGIN_ACTIONS["SetDataref"]["data"]["datarefvalue"]["id"])
        XPClient.write_dataref(dataref=dataref_name, value=dataref_value)
        g_log.debug(f"setDataref {dataref_name}={dataref_value}")

    elif aid == TPPEntry.TP_PLUGIN_ACTIONS["LeavingPage"]["id"]:
        page_path = TPClient.getActionDataValue(action_data, TPPEntry.TP_PLUGIN_ACTIONS["LeavingPage"]["data"]["pagePath"]["id"])
        XPClient.leaving_page(page_name=page_path)
        g_log.info(f"Left page {page_path}")

    else:
        g_log.warning("Got unknown action ID: " + aid)


@TPClient.on(TP.TYPES.onHold_down)
def onAction(data):
    g_log.debug(f"Action: {data}")

    # check that `data` and `actionId` members exist and save them for later use
    if not (action_data := data.get("data")) or not (aid := data.get("actionId")):
        return

    if aid == TPPEntry.TP_PLUGIN_ACTIONS["ExecuteLongPressCommand"]["id"]:
        action_value = TPClient.getActionDataValue(action_data, TPPEntry.TP_PLUGIN_ACTIONS["ExecuteLongPressCommand"]["data"]["command"]["id"])
        XPClient.commandBegin(action_value)
        g_log.debug(f"commandBegin {action_value}")


@TPClient.on(TP.TYPES.onHold_up)
def onAction(data):
    g_log.debug(f"Action: {data}")

    # check that `data` and `actionId` members exist and save them for later use
    if not (action_data := data.get("data")) or not (aid := data.get("actionId")):
        return

    if aid == TPPEntry.TP_PLUGIN_ACTIONS["ExecuteLongPressCommand"]["id"]:
        action_value = TPClient.getActionDataValue(action_data, TPPEntry.TP_PLUGIN_ACTIONS["ExecuteLongPressCommand"]["data"]["command"]["id"])
        XPClient.commandEnd(action_value)
        g_log.debug(f"commandEnd {action_value}")


# Shutdown handler
@TPClient.on(TP.TYPES.onShutdown)
def onShutdown(data):
    g_log.info("Received shutdown event from TP Client.")
    g_log.info(f"Terminating XP client..")
    XPClient.terminate()
    g_log.info(f"..terminated")
    if TPClient.isConnected():
        g_log.info(f"Disconnecting from Touch Portal..")
        TPClient.disconnect()
        g_log.info(f"..disconnected")


# Error handler
# @TPClient.on(TP.TYPES.onError)
# def onError(exc):
#     g_log.error(f"Error in TP Client event handler: {repr(exc)}")


@TPClient.on(TP.TYPES.onBroadcast)
def onAction(data):
    g_log.debug(data)

    # {'type': 'broadcast', 'event': 'pageChange', 'pageName': '/(main).tml'}
    if not (broadcast_event := data.get("event")) or not (page_name := data.get("pageName")):
        return

    if broadcast_event == "pageChange":
        XPClient.entering_page(page_name)
        g_log.info(f"Entered page {page_name}")


# @TPClient.on(TP.TYPES.allMessage)
# def onAction(data):
#     g_log.debug(data)


# Main
def main():
    global TPClient, XPClient, g_log
    ret = 0  # sys.exit() value

    # default log file destination
    logFile = f"./{TPPEntry.PLUGIN_ID}.log"
    # default log stream destination
    logStream = sys.stdout

    # Set up and handle CLI arguments. These all relate to logging options.
    # The plugin can be run with "-h" option to show available argument options.
    # Addtionally, a file constaining any of these arguments can be specified on the command line
    # with the `@` prefix. For example: `plugin-example.py @config.txt`
    # The file must contain one valid argument per line, including the `-` or `--` prefixes.
    # See the plugin-example-conf.txt file for an example config file.
    parser = ArgumentParser(fromfile_prefix_chars="@")
    parser.add_argument("-d", action="store_true", help="Use debug logging.")
    parser.add_argument("-w", action="store_true", help="Only log warnings and errors.")
    parser.add_argument("-q", action="store_true", help="Disable all logging (quiet).")
    parser.add_argument("-l", metavar="<logfile>", help=f"Log file name (default is '{logFile}'). Use 'none' to disable file logging.")
    parser.add_argument("-s", metavar="<stream>", help="Log to output stream: 'stdout' (default), 'stderr', or 'none'.")

    # his processes the actual command line and populates the `opts` dict.
    opts = parser.parse_args()
    del parser

    # trim option string (they may contain spaces if read from config file)
    opts.l = opts.l.strip() if opts.l else "none"
    opts.s = opts.s.strip().lower() if opts.s else "stdout"
    # print(opts)

    # Set minimum logging level based on passed arguments
    logLevel = "INFO"
    if opts.q:
        logLevel = None
    elif opts.d:
        logLevel = "DEBUG"
    elif opts.w:
        logLevel = "WARNING"

    # set log file if -l argument was passed
    if opts.l:
        logFile = None if opts.l.lower() == "none" else opts.l
    # set console logging if -s argument was passed
    if opts.s:
        if opts.s == "stderr":
            logStream = sys.stderr
        elif opts.s == "stdout":
            logStream = sys.stdout
        else:
            logStream = None

    # Configure the Client logging based on command line arguments.
    # Since the Client uses the "root" logger by default,
    # this also sets all default logging options for any added child loggers, such as our g_log instance we created earlier.
    TPClient.setLogFile(logFile)
    TPClient.setLogStream(logStream)
    TPClient.setLogLevel(logLevel)

    # ready to go
    g_log.info(f"Starting {TPPEntry.TP_PLUGIN_INFO['name']} v{TPPEntry.__version__} on {sys.platform}.")

    try:
        # Connect to Touch Portal desktop application.
        # If connection succeeds, this method will not return (blocks) until the client is disconnected.
        TPClient.connect()
        g_log.info("TP Client closed.")
    except KeyboardInterrupt:
        g_log.warning("Caught keyboard interrupt, exiting.")
    except Exception:
        # This will catch and report any critical exceptions in the base TPClient code,
        # _not_ exceptions in this plugin's event handlers (use onError(), above, for that).
        from traceback import format_exc

        g_log.error(f"Exception in TP Client:\n{format_exc()}")
        ret = -1
    finally:
        # Make sure TP Client is stopped, this will do nothing if it is already disconnected.
        g_log.info(f"Terminating XP client..")
        XPClient.terminate()
        g_log.info(f"..terminated")
        if TPClient.isConnected():
            g_log.info(f"Disconnecting from Touch Portal..")
            TPClient.disconnect()
            g_log.info(f"..disconnected")

    # TP disconnected, clean up.
    del XPClient
    del TPClient

    g_log.info(f"{TPPEntry.TP_PLUGIN_INFO['name']} stopped.")
    return ret


if __name__ == "__main__":
    sys.exit(main())
