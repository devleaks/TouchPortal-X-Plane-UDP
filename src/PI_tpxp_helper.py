# Creates pair of commandBegin/commandEnd for some commands.
# New commands for "command" are "command/begin" and "command/end".
#
import os
import json
import xp
from traceback import print_exc

CONFIG_DIR = "."
CONFIG_FILE = "states.json"
LONG_PRESS_COMMANDS = "long-press-commands"
DYNAMIC_STATES_FILE_VERSION = 3

REF = "cmdref"
FUN = "cmdfun"
HDL = "cmdhdl"


RELEASE = "1.0.0"  # local version number

# Changelog:
#
# 22-JAN-2024: 1.0.0: Initial release.
#


class PythonInterface:
    def __init__(self):
        self.Name = "Cockpitdecks Helper"
        self.Sig = "xppython3.tpxphelper"
        self.Desc = f"Decompose long press commands into command/begin and command/end. (Rel. {RELEASE})"
        self.Info = self.Name + f" (rel. {RELEASE})"
        self.enabled = False
        self.trace = True  # produces extra print/debugging in XPPython3.log for this class
        self.commands = {}

    def XPluginStart(self):
        """
        Do nothing. Work is done upon aircraft loading
        """
        if self.trace:
            print(self.Info, f"PI::XPluginStart: started.")
        return self.Name, self.Sig, self.Desc

    def XPluginStop(self):
        for k, v in self.commands.items():
            if FUN in v:  # cached commands have no FUN
                xp.unregisterCommandHandler(v[REF], v[FUN], 1, None)
            if self.trace:
                print(self.Info, "PI::XPluginStop: unregistered", k)
        if self.trace:
            print(self.Info, "PI::XPluginStop: stopped.")
        return None

    def XPluginEnable(self):
        try:
            self.load()
            return 1
        except:
            if self.trace:
                print(self.Info, "PI::XPluginEnable: exception.")
            print_exc()
            self.enabled = False
        return 0

    def XPluginDisable(self):
        self.enabled = False
        if self.trace:
            print(self.Info, "PI::XPluginDisable: disabled.")
        return None

    def XPluginReceiveMessage(self, inFromWho, inMessage, inParam):
        return None

    def command(self, command: str, begin: bool) -> int:
        # Execute a long press command
        #
        try:
            if command in self.commands:
                if begin:
                    xp.commandBegin(self.commands[command][REF])
                else:
                    xp.commandEnd(self.commands[command][REF])
            else:
                cmdref = xp.findCommand(command)
                if cmdref is not None:
                    self.commands[command] = {}  # cache it
                    self.commands[command][REF] = cmdref
                    if begin:
                        xp.commandBegin(self.commands[command][REF])
                    else:
                        xp.commandEnd(self.commands[command][REF])
                else:
                    print(self.Info, f"PI::command: {command} not found")
        except:
            if self.trace:
                print(self.Info, "PI::command: exception:")
            print_exc()
        return 0  # callback must return 0 or 1.

    def load(self):
        # Create begin/end commands for long press commands listed in states.json file.
        #
        DEBUG = False

        config = None
        config_dn = CONFIG_DIR
        config_fn = os.path.join(config_dn, CONFIG_FILE)
        if not os.path.exists(config_fn):
            print(self.Info, f"PI::load: Touch Portal X-Plane UDP file '{config_fn}' not found in dir '{config_dn}'")
            return []

        with open(config_fn, "r", encoding="utf-8") as config_fp:
            config = json.load(config_fp)
            version = config.get("version")
            if version != DYNAMIC_STATES_FILE_VERSION:
                print(self.Info, f"states file {DYNAMIC_STATES_FILE_NAME} invalid version {version} vs. {DYNAMIC_STATES_FILE_VERSION}")
                return
            if DEBUG:
                print(self.Info, f"PI::load: loaded file '{config_fn}'")

        commands = config.get(LONG_PRESS_COMMANDS, []) if config is not None else []
        if DEBUG:
            print(self.Info, f"PI::load: loaded '{LONG_PRESS_COMMANDS}' {', '.join(commands)}")
        if len(commands) > 0:
            for command in commands:
                try:
                    # cmdref = xp.findCommand(command)
                    # if cmdref is not None:
                    # As such, we only check for command existence at execution time.
                    cmd = command + "/begin"
                    self.commands[cmd] = {}
                    self.commands[cmd][REF] = xp.createCommand(cmd, "Begin " + cmd)
                    self.commands[cmd][FUN] = lambda *args: self.command(command, True)
                    # self.commands[cmd][FUN] = lambda *args: (xp.commandBegin(cmdref), 0)[1]  # callback must return 0 or 1
                    self.commands[cmd][HDL] = xp.registerCommandHandler(self.commands[cmd][REF], self.commands[cmd][FUN], 1, None)
                    if self.trace:
                        print(self.Info, f"PI::load: added {cmd}")
                    cmd = command + "/end"
                    self.commands[cmd] = {}
                    self.commands[cmd][REF] = xp.createCommand(cmd, "End " + cmd)
                    self.commands[cmd][FUN] = lambda *args: self.command(command, False)
                    # self.commands[cmd][FUN] = lambda *args: (xp.commandEnd(cmdref), 0)[1]  # callback must return 0 or 1
                    self.commands[cmd][HDL] = xp.registerCommandHandler(self.commands[cmd][REF], self.commands[cmd][FUN], 1, None)
                    if self.trace:
                        print(self.Info, f"PI::load: added {cmd}")
                    # else:
                    #     print(self.Info, f"PI::load: {command} not found")
                except Exception as e:
                    if self.trace:
                        print(self.Info, "PI::load: exception:")
                    print_exc()
        else:
            if self.trace:
                print(self.Info, f"PI::load: no command to add.")

        if self.trace:
            print(self.Info, f"PI::load: {len(self.commands)} commands installed.")
