# Classes for X-Plane UDP interface.
# Creates connection, monitors it, re-create if disconnected.
# Execute X-Plane UDP requests (CMD0, RREF).
# Monitors bunch of datarefs, notifies if monitored dataref value has changed.
#
import socket
import struct
import binascii
import platform
import threading
import logging
import time
import json
import os
import re

from datetime import datetime
from queue import Queue
from enum import Enum
from abc import ABC, abstractmethod

from rpc import RPC
from TPPEntry import PLUGIN_ID, TP_PLUGIN_STATES, DYNAMIC_STATES_FILE_NAME, DYNAMIC_STATES_FILE_VERSION

loggerCommand = logging.getLogger("Command")
# loggerCommand.setLevel(logging.DEBUG)

loggerDataref = logging.getLogger("Dataref")
# loggerDataref.setLevel(logging.DEBUG)
# loggerDataref.setLevel(15)

loggerTPState = logging.getLogger("TPState")
# loggerTPState.setLevel(logging.DEBUG)
# loggerTPState.setLevel(15)

logger = logging.getLogger("XPlane")
# logger.setLevel(logging.DEBUG)
# logger.setLevel(15)

# ########################################
# Global constant
#
# !! adjust with care !!
DEFAULT_REQ_FREQUENCY = 1  # if no frequency is supplied (or forced to None), this is used.

MAX_DREF_COUNT = 80  # Absolute maximum number of dataref that can be requested to X-Plane, CTD around ~100 datarefs
# UDP sends at most ~40 to ~50 dataref values per packet.

LOOP_ALIVE = 1000  # report loop activity every LOOP_ALIVE executions on DEBUG, set to None to suppress output
SOCKET_TIMEOUT = 5  # seconds, when not receiving a UDP packet for 5 seconds, declare a timeout
MAX_TIMEOUT_COUNT = 5  # count, after MAX_TIMEOUT_COUNT timeouts, assumes connection lost, disconnect, and try to reconnect
RECONNECT_TIMEOUT = 10  # seconds, when disconnceted, retries every RECONNECT_TIMEOUT seconds

# Touch Portal (internal) feedback shortcuts for connection status
STATE_XP_CONNECTED = TP_PLUGIN_STATES["XPlaneConnected"]["id"]
STATE_XP_CONNMON = TP_PLUGIN_STATES["ConnectionMonitoringRunning"]["id"]
STATE_XP_DREFMON = TP_PLUGIN_STATES["MonitoringRunning"]["id"]
# STATE_XP_CURRPAGE = TP_PLUGIN_STATES["CurrentPage"]["id"]

# Touch Portal dynamic states
# See TPPEntry.DYNAMIC_STATES_FILE_VERSION
PATTERN_DOLCB = "{\\$([^\\}]+?)\\$}"  # {$ ... $}: Touch portal variable in formula syntax.


# Keywords in states.json file
class KW(Enum):
    BOOLEAN = "boolean"
    DATAREF_ROUNDING = "dataref-rounding"
    FLOAT = "float"
    FORMULA = "formula"
    HOME_PAGE = "home-page"
    INTEGER = "int"
    INTERNAL_STATE_NAME = "internal_name"
    LONG_PRESS_COMMAND = "long-press-commands"
    PAGE_NAME = "name"
    PAGES = "pages"
    STATE_NAME = "name"
    STATES = "states"
    SUB_FOLDER = "sub-folder"
    TYPE = "type"
    VERSION = "version"


# Dynamic state values: note: Dynamic state values are always strings, sometimes confined to a valid list of values.
# Strings are compared as strings: "1" != "1.0", not number 1 == 1.0.
INT_TRUE = "1"
INT_FALSE = "0"
BOOL_TRUE = "TRUE"
BOOL_FALSE = "FALSE"


# ################################################################################
# Command
#
# The command keywords are not executed, ignored with a warning
class Command:
    """
    A Button activation will instruct the simulator software to perform an action.
    A Command is the message that the simulation sofware is expecting to perform that action.
    """

    NOT_A_COMMAND = ["none", "noop", "no-operation", "no-command", "do-nothing"]  # all forced to lower cases

    def __init__(self, path: str, name: str = None):
        self.path = path  # some/command
        self.name = name

    def __str__(self) -> str:
        return self.name if self.name is not None else (self.path if self.path is not None else "no command")

    def has_command(self) -> bool:
        return self.path is not None and not self.path.lower() in Command.NOT_A_COMMAND


# ################################################################################
# Dataref and Listener
#
class Dataref:
    """
    A Dataref is an internal value of the simulation software made accessible to outside modules,
    plugins, or other software in general.
    """

    def __init__(self, path: str, update_frequency: int = 1, rounding: int = None):
        self.path = path  # some/path/values[6]
        self.update_frequency = update_frequency  # sent by the simulator that many times per second.
        self.rounding = rounding

        # dataref value
        self._previous_value = None  # raw values
        self._current_value = None
        self.previous_value = None  # rounded values
        self.current_value = None

        # stats
        self._last_updated = None
        self._last_changed = None
        self._updated = 0  # number of time value updated
        self._changed = 0  # number of time value changed

        # objects interested in dataref value
        self.listeners = []  # buttons using this dataref, will get notified if changes.

    def value(self):
        return self.current_value

    def set_rounding(self, rounding: int):
        """Dataref rouding is unique for all instances of the dataref.
        It is set to the finest (largest) required rounding.
        I.e. if a button requires 3 decimals, and another 6, 6 wins.
        """
        if rounding is None:  # we don't change it, to reset, set dataref.rounding = None.
            return
        if self.rounding is not None:
            self.rounding = max(self.rounding, rounding)
        else:
            self.rounding = rounding

    def add_listener(self, obj):
        if not isinstance(obj, DatarefListener):
            loggerDataref.warning(f"{self.path} not a listener {obj}")
        if obj not in self.listeners:
            self.listeners.append(obj)
        loggerDataref.debug(f"{self.path} added listener {obj.name} ({len(self.listeners)} listening)")

    def rounded_value(self, rounding: int = None):
        return self.round(self._current_value, rounding=rounding)

    def has_changed(self):
        # if self.previous_value is None and self.current_value is None:
        #     return False
        # elif self.previous_value is None and self.current_value is not None:
        #     return True
        # elif self.previous_value is not None and self.current_value is None:
        #     return True
        return self.current_value != self.previous_value

    def round(self, new_value, rounding: int = None):
        if type(new_value) not in [int, float]:
            return new_value
        if rounding is not None:
            return round(new_value, rounding)
        return round(new_value, self.rounding) if self.rounding is not None else new_value

    def update_value(self, new_value, cascade: bool = False) -> bool:
        self._previous_value = self._current_value  # raw
        self._current_value = new_value  # raw
        self._updated = self._updated + 1
        self._last_updated = datetime.now().astimezone()
        self.previous_value = self.current_value  # exposed
        self.current_value = self.rounded_value()
        if not self.has_changed():
            return False
        self._changed = self._changed + 1
        self._last_changed = datetime.now().astimezone()
        loggerDataref.log(
            15, f"dataref {self.path} ({self.rounding}) updated {self.previous_value} -> {self.current_value} {'(no cascade)' if not cascade else ''}"
        )
        if cascade:
            self.notify()
        return True

    def notify(self):
        for lsnr in self.listeners:
            lsnr.dataref_changed(self)
            loggerDataref.debug(f"{self.path}: notified {lsnr.name}")


class DatarefListener(ABC):
    # To get notified when a dataref has changed.

    def __init__(self, name: str = "abstract-dataref-listener"):
        self.name = name

    @abstractmethod
    def dataref_changed(self, dataref):
        pass


# ################################################################################
# Touch Portal State <-> X-Plane Dataref Bridge
#
class TPState(DatarefListener):
    def __init__(self, name: str, config: dict, sim) -> None:
        DatarefListener.__init__(self, name=name)
        self.internal_name = TPState.mkintname(name)
        self.formula = config.get(KW.FORMULA.value, "")
        self.datatype = config.get(KW.TYPE.value, "int")
        self.sim = sim
        self.previous_value = None

        # Create dynamic state in Touch Portal
        self.sim.tpclient.createState(stateId=self.internal_name, description=name, value="None")
        loggerTPState.debug(f"state {self.name}: created {self.internal_name}")

        # Register dependant datarefs
        self.dataref_paths = self.extract_datarefs()
        self.datarefs = {}
        for d in self.dataref_paths:
            dref = self.sim.get_dataref(d)
            dref.set_rounding(config.get(KW.DATAREF_ROUNDING.value))
            dref.add_listener(self)
            self.datarefs[d] = dref
        loggerTPState.log(15, f"state {self.name}: created {self.internal_name}, uses datarefs {', '.join(self.datarefs.keys())}")

    def __del__(self):
        """Remove from TP instance"""
        if self.sim.tpclient.isConnected():
            self.sim.tpclient.removeState(stateId=self.internal_name)

    @staticmethod
    def mkintname(name):
        """Create an internal named from the display string, all alphanumeric uppercase, no space, dash, etc."""
        temp_name = "".join(e for e in name if e.isalnum()).upper()
        return ".".join([PLUGIN_ID, temp_name])

    def extract_datarefs(self):
        """Extracts dependent datarefs in state formula"""
        datarefs = re.findall(PATTERN_DOLCB, self.formula)
        datarefs = list(datarefs)
        loggerTPState.debug(f"state {self.name}: added datarefs {datarefs}")
        return datarefs

    def dataref_changed(self, dataref):
        """Callback whenever a dataref value has changed"""
        valstr = self.value()
        # logger.debug(f"dataref {dataref.path} changed, setting {self.internal_name}={valstr}")
        if self.previous_value != valstr:
            self.sim.tpclient.stateUpdate(self.internal_name, valstr if valstr is not None else "")
            loggerTPState.log(15, f"state {self.name}: updated {self.previous_value} -> {valstr}")
            self.previous_value = valstr

    def value(self) -> str:
        """Compute state value based on formula and dataref values, returns an empty string on error/not avail."""
        # 1. Substitute dataref variables by their value
        expr = self.formula
        for dataref_name in self.dataref_paths:
            value = self.sim.get_dataref_value(dataref_name)
            value_str = str(value) if value is not None else "0.0"
            expr = expr.replace(f"{{${dataref_name}$}}", value_str)
        loggerTPState.debug(f"state {self.name}: formula {self.formula} => {expr}")
        # 2. Execute the formula
        r = RPC(expr)
        value = 0.0
        try:
            value = r.calculate()
        except ValueError:
            loggerTPState.warning(f"state {self.name}: error evaluating expression {self.formula}", exc_info=True)
            value = 0.0
        loggerTPState.debug(f"state {self.name}: {expr} => {value}")
        # 3. Format
        # In Touch Portal "0" is quite different from "1.0".
        # So by forcing a "type" for Touch Portal "states", we will prevent sending "1.0" when a integer or boolean is expected.
        if value == "" or value is None:  # no value is no value...
            return ""

        strvalue = ""
        if self.datatype.startswith(KW.INTEGER.value):
            try:
                value = int(value)  # int vs round? ceil? floor?
                strvalue = f"{value}"
                if len(self.datatype) > len(KW.INTEGER.value):
                    fmt = f"{{:{self.datatype[3:]}d}}"
                    strvalue = fmt.format(value)
            except ValueError:
                loggerTPState.warning(f"could not convert '{value}' to datatype {self.datatype}", exc_info=True)
        elif self.datatype in ["number", "decimal"] or self.datatype.startswith(KW.FLOAT.value):
            try:
                value = float(value)
                strvalue = f"{value}"  # should format? yeah!
                if self.datatype.startswith(KW.FLOAT.value) and len(self.datatype) > len(KW.FLOAT.value):
                    fmt = f"{{:{self.datatype[len('float'):]}f}}"
                    strvalue = fmt.format(value)
            except ValueError:
                loggerTPState.warning(f"could not convert '{value}' to datatype {self.datatype}", exc_info=True)
        elif self.datatype in [KW.BOOLEAN.value, "bool", "yesno"]:
            try:
                value = value is not None and value != 0
                strvalue = f"{value}".upper()  # TRUE or FALSE, if 0 or 1 needed, please return a int
            except ValueError:
                loggerTPState.warning(f"could not convert to datatype {self.datatype}", exc_info=True)
        else:
            loggerTPState.warning(f"invalid datatype {self.datatype}")
        # loggerTPState.debug(f"state {self.name}: formula {self.formula} => {strvalue}")
        return strvalue


# ################################################################################
# X-Plane Simulator UDP Connecton
#
# Beacon-specific error classes
#
class XPlaneIpNotFound(Exception):
    args = "Could not find any running XPlane instance in network."


class XPlaneVersionNotSupported(Exception):
    args = "XPlane version not supported."


# XPlaneBeacon
#
class XPlaneBeacon:
    """
    Get data from XPlane via network.
    Use a class to implement RAI Pattern for the UDP socket.
    """

    # constants
    MCAST_GRP = "239.255.1.1"
    MCAST_PORT = 49707  # (MCAST_PORT was 49000 for XPlane10)
    BEACON_TIMEOUT = 3.0  # seconds

    def __init__(self, tpclient):
        self.tpclient = tpclient
        # Open a UDP Socket to receive on Port 49000
        self.socket = None

        self.beacon_data = {}

        self.should_not_connect = None  # threading.Event()
        self.connect_thread = None  # threading.Thread()

    @property
    def connected(self):
        return "IP" in self.beacon_data.keys()

    def FindIp(self):
        """
        Find the IP of XPlane Host in Network.
        It takes the first one it can find.
        """
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.beacon_data = {}

        # open socket for multicast group.
        # this socker is for getting the beacon, it can be closed when beacon is found.
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # SO_REUSEPORT?
        if platform.system() == "Windows":
            sock.bind(("", self.MCAST_PORT))
        else:
            sock.bind((self.MCAST_GRP, self.MCAST_PORT))
        mreq = struct.pack("=4sl", socket.inet_aton(self.MCAST_GRP), socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.settimeout(XPlaneBeacon.BEACON_TIMEOUT)

        # receive data
        try:
            packet, sender = sock.recvfrom(1472)
            logger.debug(f"XPlane Beacon: {packet.hex()}")

            # decode data
            # * Header
            header = packet[0:5]
            if header != b"BECN\x00":
                logger.warning(f"Unknown packet from {sender[0]}, {str(len(packet))} bytes:")
                logger.warning(packet)
                logger.warning(binascii.hexlify(packet))

            else:
                # * Data
                data = packet[5:21]
                # struct becn_struct
                # {
                #   uchar beacon_major_version;     // 1 at the time of X-Plane 10.40
                #   uchar beacon_minor_version;     // 1 at the time of X-Plane 10.40
                #   xint application_host_id;       // 1 for X-Plane, 2 for PlaneMaker
                #   xint version_number;            // 104014 for X-Plane 10.40b14
                #   uint role;                      // 1 for master, 2 for extern visual, 3 for IOS
                #   ushort port;                    // port number X-Plane is listening on
                #   xchr    computer_name[strDIM];  // the hostname of the computer
                # };
                beacon_major_version = 0
                beacon_minor_version = 0
                application_host_id = 0
                xplane_version_number = 0
                role = 0
                port = 0
                (
                    beacon_major_version,  # 1 at the time of X-Plane 10.40
                    beacon_minor_version,  # 1 at the time of X-Plane 10.40
                    application_host_id,  # 1 for X-Plane, 2 for PlaneMaker
                    xplane_version_number,  # 104014 for X-Plane 10.40b14
                    role,  # 1 for master, 2 for extern visual, 3 for IOS
                    port,  # port number X-Plane is listening on
                ) = struct.unpack("<BBiiIH", data)
                hostname = packet[21:-1]  # the hostname of the computer
                hostname = hostname[0 : hostname.find(0)]
                if beacon_major_version == 1 and beacon_minor_version <= 2 and application_host_id == 1:
                    self.beacon_data["IP"] = sender[0]
                    self.beacon_data["Port"] = port
                    self.beacon_data["hostname"] = hostname.decode()
                    self.beacon_data["XPlaneVersion"] = xplane_version_number
                    self.beacon_data["role"] = role
                    self.update_state(STATE_XP_CONNECTED, INT_TRUE)
                    logger.info(f"XPlane Beacon Version: {beacon_major_version}.{beacon_minor_version}.{application_host_id}")
                else:
                    self.update_state(STATE_XP_CONNECTED, INT_FALSE)
                    logger.warning(f"XPlane Beacon Version not supported: {beacon_major_version}.{beacon_minor_version}.{application_host_id}")
                    raise XPlaneVersionNotSupported()

        except socket.timeout:
            logger.debug("XPlane IP not found.")
            raise XPlaneIpNotFound()
        finally:
            sock.close()

        return self.beacon_data

    def start(self):
        logger.warning("nothing to start")

    def stop(self):
        logger.warning("nothing to stop")

    def cleanup(self):
        logger.warning("nothing to clean up")

    def connect_loop(self):
        """
        Trys to connect to X-Plane indefinitely until self.should_not_connect is set.
        If a connection fails, drops, disappears, will try periodically to restore it.
        """
        logger.debug("starting..")
        WARN_FREQ = 10
        cnt = 0
        while self.should_not_connect is not None and not self.should_not_connect.is_set():
            if not self.connected:
                try:
                    self.FindIp()
                    if self.connected:
                        logger.info(self.beacon_data)
                        logger.debug("..connected, starting dataref listener..")
                        self.start()
                        logger.debug("..dataref listener started..")
                except XPlaneVersionNotSupported:
                    self.beacon_data = {}
                    logger.error("..X-Plane Version not supported..")
                except XPlaneIpNotFound:
                    self.beacon_data = {}
                    if cnt % WARN_FREQ == 0:
                        logger.error(f"..X-Plane instance not found on local network.. ({datetime.now().strftime('%H:%M:%S')})")
                    cnt = cnt + 1
                if not self.connected:
                    self.should_not_connect.wait(RECONNECT_TIMEOUT)
                    logger.debug("..trying..")
            else:
                self.should_not_connect.wait(RECONNECT_TIMEOUT)  # could be n * RECONNECT_TIMEOUT
                logger.debug("..monitoring connection..")
        logger.debug("..ended")

    def connection_monitor_running(self) -> bool:
        return self.should_not_connect is not None and not self.should_not_connect.is_set()

    def update_state(self, state: str, value: str):
        if self.tpclient.isConnected():
            logger.debug(f"updating {state} to {value}")
            self.tpclient.stateUpdate(state, value)
        else:
            logger.warning(f"TPClient not connected")

    # ################################
    # Interface
    #
    def connect(self):
        """
        Starts connect loop.
        """
        if self.should_not_connect is None:
            self.should_not_connect = threading.Event()
            self.connect_thread = threading.Thread(target=self.connect_loop)
            self.connect_thread.name = "XPlaneBeacon::connect_loop"
            self.connect_thread.start()
            self.update_state(STATE_XP_CONNMON, INT_TRUE)
            logger.debug("connect_loop started")
        else:
            logger.debug("connect_loop already running")

    def disconnect(self):
        """
        End connect loop and disconnect
        """
        logger.debug("disconnecting..")
        if self.should_not_connect is not None:
            self.cleanup()
            self.beacon_data = {}
            self.update_state(STATE_XP_CONNECTED, INT_FALSE)
            self.should_not_connect.set()
            wait = RECONNECT_TIMEOUT
            logger.debug(f"..asked to stop connect_loop.. (this may last {wait} secs.)")
            self.connect_thread.join(timeout=wait)
            if self.connect_thread.is_alive():
                logger.warning(f"..thread may hang..")
            self.should_not_connect = None
            self.update_state(STATE_XP_CONNMON, INT_FALSE)
            logger.debug("..disconnected")
        else:
            if self.connected:
                self.beacon_data = {}
                self.update_state(STATE_XP_CONNECTED, INT_FALSE)
                logger.debug("..connect_loop not running..disconnected")
            else:
                logger.debug("..not connected")


# ################################################################################
# XPlane UDP Handler
#
class XPlane(XPlaneBeacon):
    """
    Get data from XPlane via network.
    Use a class to implement RAI Pattern for the UDP socket.
    """

    # Internal key word
    TERMINATE_QUEUE = "__quit__"

    def __init__(self, tpclient):
        self.all_datarefs = {}  # all registed datarefs, exist only once here: { "sim/time/seconds": <Dataref> }
        self.datarefs_to_monitor = {}  # dataref path and number of objects monitoring

        # list of requested datarefs with index number
        self.datarefidx = 0  # working variable, last index
        self.datarefs = {}  # key = idx, value = dataref path { 25: "sim/time/seconds" }, in UDP packet we receive '25=67545', thus sim/time/seconds=67545.

        self.states = {}  # {state_internal_name: TPState}
        self.pages = {}  # {page_name: {dref-path: Dataref}}
        self.page_usages = {}  # {page_name: usage_count}

        # Dataref value enqueue/dequeue
        # -> Reads UDP packets and enqueue values
        # <- Read values, update dataref if has changed and provoke update of listeners
        self.udp_queue = Queue()
        self.udp_thread = None
        self.dref_thread = None
        self.no_upd_enqueue = None

        # internal stats
        self._max_monitored = 0  # higest number of datarefs monitored at one point in time

        XPlaneBeacon.__init__(self, tpclient)

        # Special Toliss FMA display, if available
        self.fma = None
        try:
            from fma import FMA

            self.fma = FMA(tpclient=tpclient)
        except:
            logger.warning(f"no Toliss Airbus FMA reader")

    def __del__(self):
        """Quickly ask X-Plane to no longer monitor datarefs we know"""
        for i in range(len(self.datarefs)):
            self._unmonitor_dataref(next(iter(self.datarefs.values())))
        # is the connection monitor still running? if yes, stop it
        if self.connection_monitor_running():
            self.disconnect()

    # ################################
    #
    # Dataref creation and registration
    #
    def register(self, dataref) -> Dataref:
        """Records a new dataref in the "global" dataref database"""
        if dataref.path not in self.all_datarefs:
            if dataref.path is not None:
                self.all_datarefs[dataref.path] = dataref
        return dataref

    def get_dataref(self, path) -> Dataref:
        """Get an existing dataref or create and register a new one.
        Returns the dataref.
        """
        if path in self.all_datarefs.keys():
            return self.all_datarefs[path]
        return self.register(Dataref(path))

    def get_dataref_value(self, dataref, default=None):
        """Returns the current value of a dataref or the default value if the dataref exists
        but has no value.
        Returns None if the dataref does not exist.
        """
        d = self.all_datarefs.get(dataref)
        if d is None:
            logger.warning(f"{dataref} not found")
            return None
        return d.value() if d.value() is not None else default

    # ################################
    #
    # Internal X-Plnae UDP requests
    #
    def _monitor_dataref(self, path, freq=None) -> bool:
        """
        Configure XPlane to send the dataref with a certain frequency.
        You can disable a dataref by setting freq to 0.
        """
        if not self.connected:
            logger.warning(f"no connection ({path}, {freq})")
            return False

        idx = -9999
        if freq is None:
            freq = DEFAULT_REQ_FREQUENCY

        if path in self.datarefs.values():
            idx = list(self.datarefs.keys())[list(self.datarefs.values()).index(path)]
            if freq == 0 and idx in self.datarefs.keys():
                del self.datarefs[idx]  # note: dref no longer in self.datarefs but we might still get values from X-Plane for it. We'll ignore them.
        else:
            if freq != 0 and len(self.datarefs) > MAX_DREF_COUNT:
                logger.warning(f"requesting too many datarefs ({len(self.datarefs)})")
                return False

            idx = self.datarefidx
            self.datarefs[self.datarefidx] = path
            self.datarefidx += 1

        self._max_monitored = max(self._max_monitored, len(self.datarefs))

        cmd = b"RREF\x00"
        string = path.encode()
        message = struct.pack("<5sii400s", cmd, freq, idx, string)
        assert len(message) == 413
        self.socket.sendto(message, (self.beacon_data["IP"], self.beacon_data["Port"]))
        # if self.datarefidx % LOOP_ALIVE == 0:
        #     time.sleep(0.2)
        return True

    def _unmonitor_dataref(self, path):
        return self._monitor_dataref(path=path, freq=0)

    def _execute_command(self, command: Command) -> None:
        """Instruct X-Plane to execute a command. It only works with commandOnce command."""
        if command is None:
            logger.warning(f"no command")
            return
        elif not command.has_command():
            logger.warning(f"command '{command}' not sent (command placeholder, no command, do nothing)")
            return
        if not self.connected:
            logger.warning(f"no connection ({command})")
            return
        message = "CMND0" + command.path
        self.socket.sendto(message.encode(), (self.beacon_data["IP"], self.beacon_data["Port"]))
        logger.log(15, f"executed {command}")

    def _write_dataref(self, dataref, value, vtype="float"):
        """
        Write Dataref to XPlane
        DREF0+(4byte byte value)+dref_path+0+spaces to complete the whole message to 509 bytes
        DREF0+(4byte byte value of 1)+ sim/cockpit/switches/anti_ice_surf_heat_left+0+spaces to complete to 509 bytes
        """
        path = dataref
        if not self.connected:
            logger.warning(f"no connection ({path}={value})")
            return

        cmd = b"DREF\x00"
        path = path + "\x00"
        string = path.ljust(500).encode()
        message = "".encode()
        if vtype == "float":
            message = struct.pack("<5sf500s", cmd, value, string)
        elif vtype == "int":
            message = struct.pack("<5si500s", cmd, value, string)
        elif vtype == "bool":
            message = struct.pack("<5sI500s", cmd, int(value), string)

        assert len(message) == 509
        logger.debug(f"({self.beacon_data['IP']}, {self.beacon_data['Port']}): {path}={value} ..")
        logger.log(15, f"writing dataref {path}={value}")
        self.socket.sendto(message, (self.beacon_data["IP"], self.beacon_data["Port"]))
        logger.debug(".. sent")

    # ################################
    #
    # Dataref "automatic" monitoring
    #
    def upd_enqueue(self) -> None:
        """Continuously and decode socket messages and enqueue dataref values.
        Terminates after 5 timeouts.
        """
        logger.debug("starting..")
        total_to = 0
        total_reads = 0
        total_values = 0
        last_read_ts = datetime.now()
        total_read_time = 0.0
        while not self.no_upd_enqueue.is_set():
            if len(self.datarefs) > 0:
                try:
                    # Receive packet
                    self.socket.settimeout(SOCKET_TIMEOUT)
                    data, addr = self.socket.recvfrom(1472)  # maximum bytes of an RREF answer X-Plane will send (Ethernet MTU - IP hdr - UDP hdr)
                    # Decode Packet
                    # Read the Header "RREF,".
                    total_to = 0
                    total_reads = total_reads + 1
                    now = datetime.now()
                    delta = now - last_read_ts
                    total_read_time = total_read_time + delta.microseconds / 1000000
                    last_read_ts = now
                    header = data[0:5]
                    if header == b"RREF,":  # (was b"RREFO" for XPlane10)
                        # We get 8 bytes for every dataref sent:
                        # An integer for idx and the float value.
                        values = data[5:]
                        lenvalue = 8
                        numvalues = int(len(values) / lenvalue)
                        total_values = total_values + numvalues
                        for i in range(0, numvalues):
                            singledata = data[(5 + lenvalue * i) : (5 + lenvalue * (i + 1))]
                            (idx, value) = struct.unpack("<if", singledata)
                            self.udp_queue.put((idx, value))
                    else:
                        logger.warning(f"{binascii.hexlify(data)}")
                    if total_reads % 10 == 0:
                        logger.debug(
                            f"average socket time between reads {round(total_read_time / total_reads, 3)} ({total_reads} reads; {total_values} values enqueued ({round(total_values/total_reads, 1)} per packet))"
                        )  # ignore
                except:  # socket timeout
                    total_to = total_to + 1
                    logger.info(f"socket timeout received ({total_to}/{MAX_TIMEOUT_COUNT})")  # ignore
                    if total_to >= MAX_TIMEOUT_COUNT:  # attemps to reconnect
                        logger.warning("too many times out, disconnecting, upd_enqueue terminated")  # ignore
                        self.beacon_data = {}
                        self.update_state(STATE_XP_CONNECTED, INT_FALSE)
                        if self.fma is not None and self.fma.is_running():
                            logger.info("stopping FMA..")
                            self.fma.stop()
                        if self.no_upd_enqueue is not None and not self.no_upd_enqueue.is_set():
                            self.no_upd_enqueue.set()
        self.no_upd_enqueue = None
        logger.debug("..terminated")

    def dataref_listener(self) -> None:
        """Continuously read dataref values from queue, update dataref value, and determine if value has changed.
        If value has changed, provoke call to .dataref_changed() of all listeners of the updated dataref.
        """
        logger.debug("starting..")
        dequeue_run = True
        total_updates = 0
        total_values = 0
        total_duration = 0.0
        total_update_duration = 0.0
        total_bl = 0
        runs = 0
        maxbl = 0

        while dequeue_run:
            values = self.udp_queue.get()
            bl = self.udp_queue.qsize()
            total_bl = total_bl + bl
            runs = runs + 1
            bl_avg = round(total_bl / runs, 1)
            maxbl = max(bl_avg, maxbl)
            if type(values) is str and values == XPlane.TERMINATE_QUEUE:
                dequeue_run = False
                continue
            try:
                before = datetime.now()
                d = self.datarefs.get(values[0])
                total_values = total_values + 1
                value = values[1]
                if value < 0.0 and value > -0.001:  # convert -0.0 values to positive 0.0
                    value = 0.0
                if d is not None:
                    if self.all_datarefs[d].update_value(value, cascade=d in self.datarefs_to_monitor.keys()):
                        total_updates = total_updates + 1
                        duration = datetime.now() - before
                        total_update_duration = total_update_duration + duration.microseconds / 1000000
                else:
                    logger.debug(f"no dataref ({values}), probably no longer monitored")  # See deletion of index in self.datarefs in _monitor_dataref().
                duration = datetime.now() - before
                total_duration = total_duration + duration.microseconds / 1000000
                if total_values % LOOP_ALIVE == 0 and total_updates > 0:
                    logger.debug(
                        f"average update time {round(total_update_duration / total_updates, 3)} ({total_updates} updates), {round(total_duration / total_values, 5)} ({total_values} values), backlog {bl_avg}/{maxbl}."
                    )  # ignore

            except RuntimeError:
                logger.warning(f"dataref_listener:", exc_info=True)

        logger.debug("..terminated")

    # ################################
    #
    # Touch Portal plugin API wrappers.
    # These functions are called by tht Touch Portal plugin
    # to perform actions in the X-Plane UDP.
    #
    # Cockpit interface
    #
    def write_dataref(self, dataref: str, value) -> None:
        """Touch Portal plugin API wrapper"""
        vfloat = value
        if type(value) is not float:
            logger.warning(f"dataref write should only send float")
            try:
                vfloat = float(value)
            except:
                logger.warning(f"dataref {dataref} value {value} failed to convert to float, ignoring")
                return
        self._write_dataref(dataref=dataref, value=vfloat)

    def commandOnce(self, command: str) -> None:
        """Touch Portal plugin API wrapper"""
        self._execute_command(Command(path=command))

    def commandBegin(self, command: str) -> None:
        """Touch Portal plugin API wrapper"""
        self._execute_command(Command(path=command + "/begin"))

    def commandEnd(self, command: str) -> None:
        """Touch Portal plugin API wrapper"""
        self._execute_command(Command(path=command + "/end"))

    # ################################
    #
    # Touch Portal Interface
    #
    def suppress_monitoring_of_all_datarefs_to_monitor(self) -> None:
        """Removes monitoring of all currently monitored datarefs"""
        if not self.connected:
            logger.warning("no connection")
            return
        for d in self.datarefs.values():
            self._unmonitor_dataref(d)
        logger.debug(f">>>>> monitoring--{len(self.datarefs)}/{len(self.all_datarefs)}")

    def start_monitoring_of_datarefs_to_monitor(self) -> None:
        """Request monitoring of all dataref that needs monitoring.
        Used on startup, when we don't know the status of X-Plane
        """
        if not self.connected:
            logger.warning("no connection")
            return
        if len(self.datarefs_to_monitor) == 0:
            logger.debug("no dataref to monitor")
            return
        # Add those to monitor
        prnt = []
        for path in self.datarefs_to_monitor.keys():
            d = self.all_datarefs.get(path)
            if d is not None:
                if self._monitor_dataref(d.path, freq=d.update_frequency):
                    prnt.append(d.path)
            else:
                logger.warning(f"dataref {path} not found")
        logger.info(f"monitoring datarefs {prnt}")
        logger.debug(f">>>>> monitoring++{len(self.datarefs_to_monitor)}/{len(self.all_datarefs)}")

    def add_datarefs_to_monitor(self, datarefs) -> None:
        """Add datarefs to monitor"""
        if not self.connected:
            logger.warning("no connection")
        # Add those to monitor
        prnt = []
        for d in datarefs.values():
            if d.path not in self.datarefs_to_monitor.keys():
                self.datarefs_to_monitor[d.path] = 1
                if self.connected:
                    if self._monitor_dataref(d.path, freq=d.update_frequency):
                        prnt.append(d.path)
                else:
                    prnt.append(d.path)
            else:  # already monitoring, add just one more interested in dref
                self.datarefs_to_monitor[d.path] = self.datarefs_to_monitor[d.path] + 1
        logger.debug(f"add_datarefs_to_monitor: added {prnt}")
        logger.debug(f">> monitoring++{len(self.datarefs)}/{self._max_monitored}")
        # logger.info(f"monitoring datarefs {prnt}")

    def remove_datarefs_to_monitor(self, datarefs) -> None:
        """Removes datarefs from monitoring"""
        if not self.connected and len(self.datarefs_to_monitor) > 0:
            logger.warning("no connection")
            logger.debug(f"would remove {datarefs.keys()}/{self._max_monitored}")
            return
        # Add those to monitor
        prnt = []
        for d in datarefs.values():
            if d.path in self.datarefs_to_monitor.keys():
                if self.datarefs_to_monitor[d.path] == 1:  # last one to monitor it, remove from X-Plane
                    if self._unmonitor_dataref(d.path):
                        prnt.append(d.path)
                else:  # other(s) still interested in monitoring
                    logger.debug(f"{d.path} monitored {self.datarefs_to_monitor[d.path]} times")

                self.datarefs_to_monitor[d.path] = self.datarefs_to_monitor[d.path] - 1
                if self.datarefs_to_monitor[d.path] == 0:  # if no more interested, remove it
                    del self.datarefs_to_monitor[d.path]
            else:
                logger.debug(f"no need to remove {d.path}")

        logger.debug(f"removed {prnt}")
        logger.debug(f"currently monitoring {self.datarefs_to_monitor}")
        logger.debug(f">> monitoring--{len(self.datarefs)}/{self._max_monitored}")

    def delete_all_datarefs(self) -> None:
        """Remove all datarefs from local database.
        First stop monitoring them, then reset database."""
        if not self.connected and len(self.all_datarefs) > 0:
            logger.warning("no connection")
        logger.debug(f"removing..")
        datarefs = {d: self.all_datarefs[d] for d in self.datarefs_to_monitor.keys()}
        self.remove_datarefs_to_monitor(datarefs)
        self.all_datarefs = {}
        self.datarefs_to_monitor = {}
        logger.debug(f"..removed")

    def cleanup(self) -> None:
        """
        Called when before disconnecting.
        Just before disconnecting, we try to cancel dataref UDP reporting in X-Plane
        """
        if self.fma is not None and self.fma.is_running():
            logger.info("stopping FMA..")
            self.fma.stop()
        self.suppress_monitoring_of_all_datarefs_to_monitor()

    def start(self) -> None:
        """Starts both udp reader and local dataref handler"""
        if not self.connected:
            logger.warning("no IP address. could not start.")
            return
        if self.no_upd_enqueue is None:
            self.no_upd_enqueue = threading.Event()
            self.udp_thread = threading.Thread(target=self.upd_enqueue)
            self.udp_thread.name = "XPlaneUDP::upd_enqueue"
            self.udp_thread.start()
            logger.info("XPlaneUDP started")
        else:
            logger.info("XPlaneUDP already running.")
        if self.dref_thread is None:
            self.dref_thread = threading.Thread(target=self.dataref_listener)
            self.dref_thread.name = "XPlaneUDP::dataref_listener"
            self.dref_thread.start()
            self.update_state(STATE_XP_DREFMON, INT_TRUE)
            logger.info("dataref listener started")
        else:
            logger.info("dataref listener running.")
        if self.fma is not None:  # restart FMA reader if needed
            self.check_fma()
        # When restarted after network failure, should clean all datarefs
        # then reload datarefs from current page of each deck
        logger.debug("cancel previous subscriptions")
        self.suppress_monitoring_of_all_datarefs_to_monitor()  # cancel previous subscriptions
        logger.debug("add current subscriptions")
        self.start_monitoring_of_datarefs_to_monitor()  # add all datarefs that need monitoring

    def stop(self) -> None:
        """Stop both udp reader and local dataref handler.
        First suppress (disable) monitoring of all monitored datarefs."""
        self.suppress_monitoring_of_all_datarefs_to_monitor()  # cancel previous subscriptions
        if self.udp_queue is not None and self.dref_thread is not None:
            logger.debug("stopping dataref listener..")
            self.udp_queue.put(XPlane.TERMINATE_QUEUE)
            self.dref_thread.join()
            self.dref_thread = None
            self.update_state(STATE_XP_DREFMON, INT_FALSE)
            logger.debug("..dataref listener stopped")
        if self.no_upd_enqueue is not None:
            self.no_upd_enqueue.set()
            logger.debug("stopping XPlaneUDP..")
            wait = SOCKET_TIMEOUT
            logger.debug(f"..asked to stop XPlaneUDP (this may last {wait} secs. for UDP socket to timeout)..")
            self.udp_thread.join(wait)
            if self.udp_thread.is_alive():
                logger.warning("..thread may hang in socket.recvfrom()..")
            self.no_upd_enqueue = None
            logger.debug("..XPlaneUDP stopped")
        else:
            logger.debug("not running")

    # ################################
    # X-Plane UDP start and stop API
    #
    def terminate(self) -> None:
        """Cleanly terminates XPlane UDP. Cleanly stop monitoring, shutdown all threads."""
        if not self.connected:
            logger.debug(f"XPlaneUDP currently not running")
            if self.connection_monitor_running():
                logger.debug(f"stopping connection monitor..")
                self.disconnect()  # this stops the connection monitor
                logger.debug(f"..stopped")
            return
        logger.debug(f"XPlaneUDP currently running; terminating..")
        logger.info("..stopping..")
        self.stop()
        logger.info("..stop dataref monitoring..")
        self.cleanup()
        self.delete_all_datarefs()
        logger.info("..disconnecting..")
        self.disconnect()
        logger.info("..terminated")

    # ############################################
    # State creation/supression
    #
    def init(self) -> None:
        """Initialize XPlane UDP: create dynamic Touch Portal states,
        collects datarefs per page, loads home page state datarefs, and connect to X-Plane.
        """
        pages = {}
        if not os.path.exists(DYNAMIC_STATES_FILE_NAME):
            logger.debug(f"no file {DYNAMIC_STATES_FILE_NAME}")
            return

        with open(DYNAMIC_STATES_FILE_NAME, "r") as fp:
            states = json.load(fp)
            version = states.get(KW.VERSION.value)
            if version != DYNAMIC_STATES_FILE_VERSION:
                logger.warning(f"states file {DYNAMIC_STATES_FILE_NAME} invalid version {version} vs. {DYNAMIC_STATES_FILE_VERSION}")
                return
            pages = states.get(KW.PAGES.value)

        tot_drefs = 0
        for page in pages:
            page_name = page.get(KW.PAGE_NAME.value)
            self.pages[page_name] = {}
            self.page_usages[page_name] = 0
            page_states = page.get(KW.STATES.value)
            for state in page_states:
                name = state.get(KW.STATE_NAME.value)
                internal_name = state.get(KW.INTERNAL_STATE_NAME.value, TPState.mkintname(name))
                if internal_name not in self.states.keys():
                    self.states[internal_name] = TPState(name=name, config=state, sim=self)
                # else state already created, just add datarefs to page
                self.pages[page_name] = self.pages[page_name] | self.states[internal_name].datarefs
            dref_cnt = len(self.pages[page_name])
            tot_drefs = tot_drefs + dref_cnt
            logger.info(f"page {page_name} loaded {len(page_states)} states, {dref_cnt} datarefs")

        logger.info(f"declared {len(self.states)} states, {tot_drefs} datarefs")
        self.connect()
        logger.info("\n*\n" + "*" * 80 + "\n*\n*  Please start client(s) now, or reflesh client pages if already started\n*\n" + "*" * 80 + "\n*")

    def reinit(self, fn: str = None):
        """Reloads states.json file. Allow for non standard locations.
        First tests the states.json file to see if it is ok,
        then cleanly removes current states (and associated datarefs),
        finally create new states and collect datarefs used per page (in init() procedure)"""
        # first tests if states.json file ok
        try:
            filename = fn if fn is not None else DYNAMIC_STATES_FILE_NAME
            if not os.path.exists(filename):
                logger.debug(f"no file {filename}")
                return

            with open(filename, "r") as fp:
                states = json.load(fp)
                version = states.get(KW.VERSION.value)
                if version != DYNAMIC_STATES_FILE_VERSION:
                    logger.warning(f"states file {filename} invalid version {version} vs. {DYNAMIC_STATES_FILE_VERSION}")
                    return
        except:
            logger.warning(f"states file {filename} is invalid, states not reloaded", exc_info=True)
            return
        # unload existing states dataref monitoring of current page of all clients
        for page in self.pages:
            if self.page_usages[page] > 0:
                self.page_usages[page] = 1  # will force unload
                self._unload_page(page)
        # reset plugin
        self.pages = {}
        # delete existing states
        for state in self.states.values():
            del state
        # load states file again
        self.init()

    # ############################################
    # Page manipulations
    #
    def check_fma(self):
        if self.fma is not None:
            run = False
            for page in self.page_usages:
                if self.page_usages[page] > 0:
                    if not run:
                        run = run or self.fma.FMA_BOXES[0] in self.pages[page]
            logger.debug(f"check_fma {run}")
            self.fma.check(run)

    def _unload_page(self, page_name: str):
        # logger.debug(f"page usage before unload: {page_name}: {self.page_usages[page_name]}")
        if page_name in self.pages.keys():
            if self.page_usages[page_name] > 0:
                self.page_usages[page_name] = self.page_usages[page_name] - 1
                if self.page_usages[page_name] == 0:
                    self.remove_datarefs_to_monitor(self.pages[page_name])
        else:
            logger.warning(f"page {page_name} not found")
        logger.debug(f"page usage: {self.page_usages}")

    def _load_page(self, page_name: str):
        # logger.debug(f"page usage before load: {page_name}: {self.page_usages[page_name]}")
        if page_name in self.pages.keys():
            logger.debug(f"page usage: {page_name}: {self.page_usages[page_name]}")
            if self.page_usages[page_name] == 0:
                self.add_datarefs_to_monitor(self.pages[page_name])
            self.page_usages[page_name] = self.page_usages[page_name] + 1
        else:
            logger.warning(f"page {page_name} not found")
        logger.debug(f"page usage: {self.page_usages}")

    def leaving_page(self, page_name: str):
        if page_name in self.pages.keys():
            self._unload_page(page_name)
            logger.debug(f"left page {page_name}")
            self.check_fma()
        else:
            logger.warning(f"page {page_name} not found")

    def entering_page(self, page_name: str):
        """Called on Touch Portal page changes.
        Unloads currently monitored datarefs and load datarefs needed on new page.
        Args:
            page_name (str): Name of page being loaded. Must match the named supplied in states.json.
        """
        if page_name in self.pages:
            self._load_page(page_name)
            logger.debug(f"entered page {page_name}")
            self.check_fma()
        else:
            logger.warning(f"page {page_name} not found in {DYNAMIC_STATES_FILE_NAME} file")
