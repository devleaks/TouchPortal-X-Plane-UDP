# Base classes for interface with the simulation software
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
from abc import ABC, abstractmethod

from rpc import RPC
from TPPEntry import PLUGIN_ID, TP_PLUGIN_STATES, dotkey

loggerCommand = logging.getLogger("Command")
# loggerCommand.setLevel(logging.DEBUG)

loggerDataref = logging.getLogger("Dataref")
loggerDataref.setLevel(logging.DEBUG)

loggerTPState = logging.getLogger("TPState")
loggerTPState.setLevel(logging.DEBUG)

logger = logging.getLogger("XPlane")
logger.setLevel(logging.DEBUG)


# ########################################
# Global constant
#
# Data too delicate to be put in constant.py
# !! adjust with care !!
# UDP sends at most ~40 to ~50 dataref values per packet.

DATA_SENT = 2  # times per second, X-Plane send that data on UDP every that often. Too often will slow down X-PLANE.

DEFAULT_REQ_FREQUENCY = 1  # if no frequency is supplied (or forced to None), this is used.

LOOP_ALIVE = 100  # report loop activity every 1000 executions on DEBUG, set to None to suppress output
RECONNECT_TIMEOUT = 10  # seconds

SOCKET_TIMEOUT = 5  # seconds
MAX_TIMEOUT_COUNT = 5  # after x timeouts, assumes connection lost, disconnect, and restart later

MAX_DREF_COUNT = 80  # Maximum number of dataref that can be requested to X-Plane, CTD around ~100 datarefs

TERMINATE_QUEUE = "quit"

# Touch Portal (internal) Feedback shortcuts
STATE_XP_CONNECTED = TP_PLUGIN_STATES["XPlaneConnected"]["id"]
STATE_XP_CONNMON = TP_PLUGIN_STATES["ConnectionMonitoringRunning"]["id"]
STATE_XP_DREFMON = TP_PLUGIN_STATES["MonitoringRunning"]["id"]
# Note: in TP, strings are compare as strings: "1" != "1.0"
TRUE = "1"
FALSE = "0"

PATTERN_DOLCB = "{\\$([^\\}]+?)\\$}"  # {$ ... $}: Touch portal variable in formula syntax.
DYNAMIC_STATES = "states.json"


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

    def rounded_value(self, rounding: int = None):
        return self.round(self._current_value, rounding=rounding)

    def has_changed(self):
        if self.previous_value is None and self.current_value is None:
            return False
        elif self.previous_value is None and self.current_value is not None:
            return True
        elif self.previous_value is not None and self.current_value is None:
            return True
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
        self.previous_value = self.current_value  # exposed
        self.current_value = self.rounded_value()
        self._updated = self._updated + 1
        self._last_updated = datetime.now().astimezone()
        if self.has_changed():
            self._changed = self._changed + 1
            self._last_changed = datetime.now().astimezone()
            loggerDataref.debug(f"dataref {self.path} updated {self.previous_value} -> {self.current_value}")
            if cascade:
                self.notify()
            return True
        # loggerDataref.error(f"dataref {self.path} updated")
        return False

    def add_listener(self, obj):
        if not isinstance(obj, DatarefListener):
            loggerDataref.warning(f"{self.path} not a listener {obj}")
        if obj not in self.listeners:
            self.listeners.append(obj)
        loggerDataref.debug(f"{self.path} added listener {obj.name} ({len(self.listeners)})")

    def notify(self):
        if self.has_changed():
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
    def __init__(self, name: str, formula: str, sim) -> None:
        DatarefListener.__init__(self, name=name)
        self.internal_name = TPState.mkintname(name)
        self.formula = formula
        self.sim = sim
        self.previous_value = None

        # Create dynamic state in Touch Portal
        self.sim.tpclient.createState(stateId=self.internal_name, description=name, value="None")
        loggerTPState.debug(f"state {self.name}: created {self.internal_name}")

        # Register dependant datarefs
        self.rounding = self.get_rounding()
        self.dataref_paths = self.extract_datarefs()
        self.datarefs = {}
        for d in self.dataref_paths:
            dref = self.sim.get_dataref(d)
            dref.rounding = self.rounding
            dref.add_listener(self)
            self.datarefs[d] = dref

    @staticmethod
    def mkintname(name):
        temp_name = "".join(e for e in name if e.isalnum()).upper()
        return ".".join([PLUGIN_ID, temp_name])

    def extract_datarefs(self):
        """Extracts dependent datarefs in state formula"""
        datarefs = re.findall(PATTERN_DOLCB, self.formula)
        datarefs = list(datarefs)
        loggerTPState.debug(f"state {self.name}: added datarefs {datarefs}")
        return datarefs

    def get_rounding(self):
        """Extracts rounding from formula if unique"""
        rounds = re.findall("([0-9]+) round", self.formula)
        rounds = list(rounds)
        loggerTPState.debug(f"state {self.name}: rounds {rounds}")
        if len(rounds) == 1:
            return int(rounds[0])
        return None

    def is_int(self):
        """Extracts rounding if unique"""
        return self.rounding == 0

    def dataref_changed(self, dataref):
        """Callback whenever a dataref value has changed"""
        valstr = self.value()
        # logger.debug(f"dataref {dataref.path} changed, setting {self.internal_name}={valstr}")
        self.sim.tpclient.stateUpdate(self.internal_name, valstr)
        loggerTPState.debug(f"state {self.name}: updated {self.previous_value} -> {valstr}")
        self.previous_value = valstr

    def value(self) -> str:
        """Compute state value based on formula and dataref values, returns an empty string on error/not avail."""
        # 1. Substitute dataref variables by their value
        expr = self.formula
        for dataref_name in self.dataref_paths:
            value = self.sim.get_dataref_value(dataref_name)
            value_str = str(value) if value is not None else "0"
            expr = expr.replace(f"{{${dataref_name}$}}", value_str)
        # 2. Execute the formula
        # loggerTPState.debug(f"state {self.name}: formula {self.formula} => {expr}")
        r = RPC(expr)
        value = ""
        try:
            value = r.calculate()
        except:
            loggerTPState.warning(f"state {self.name}: error evaluating expression {self.formula}", exc_info=True)
            value = ""
        # 3. Format
        if value != "":
            if self.is_int():
                value = int(value)
            strvalue = f"{value}"
            # loggerTPState.debug(f"state {self.name}: {expr} => {strvalue}")
        else:
            strvalue = ""
        return strvalue

    def definition(self):
        """Returns a state definition for Touch Portal"""
        return {"id": self.internal_name, "desc": self.name, "type": "text", "default": "0"}

    def to_json(self):
        return json.dumps(self.definition(), indent=2)


# ################################################################################
# X-Plane Simulator UDP Connecton
#
# Beacon-specific error classes
#
class XPlaneIpNotFound(Exception):
    args = "Could not find any running XPlane instance in network."


class XPlaneTimeout(Exception):
    args = "XPlane timeout."


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
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
                    self.update_state(STATE_XP_CONNECTED, TRUE)
                    logger.info(f"XPlane Beacon Version: {beacon_major_version}.{beacon_minor_version}.{application_host_id}")
                else:
                    self.update_state(STATE_XP_CONNECTED, FALSE)
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

    def update_state(self, state: str, value: str):
        logger.debug(f"updating {state} to {value}")
        self.tpclient.stateUpdate(state, value)

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
            self.update_state(STATE_XP_CONNMON, TRUE)
            logger.debug("connect_loop started")
        else:
            logger.debug("connect_loop already started")

    def disconnect(self):
        """
        End connect loop and disconnect
        """
        if self.should_not_connect is not None:
            logger.debug("disconnecting..")
            self.cleanup()
            self.beacon_data = {}
            self.update_state(STATE_XP_CONNECTED, FALSE)
            self.should_not_connect.set()
            wait = RECONNECT_TIMEOUT
            logger.debug(f"..asked to stop connect_loop.. (this may last {wait} secs.)")
            self.connect_thread.join(timeout=wait)
            if self.connect_thread.is_alive():
                logger.warning(f"..thread may hang..")
            self.should_not_connect = None
            self.update_state(STATE_XP_CONNMON, FALSE)
            logger.debug("..disconnected")
        else:
            if self.connected:
                self.beacon_data = {}
                self.update_state(STATE_XP_CONNECTED, FALSE)
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

    # constants
    MCAST_GRP = "239.255.1.1"
    MCAST_PORT = 49707  # (MCAST_PORT was 49000 for XPlane10)
    BEACON_TIMEOUT = 3.0  # seconds

    def __init__(self, tpclient):
        self.all_datarefs = {}  # all registed datarefs, exist only once here: { "sim/time/seconds": <Dataref> }
        self.datarefs_to_monitor = {}  # dataref path and number of objects monitoring

        # list of requested datarefs with index number
        self.datarefidx = 0  # working variable, last index
        self.datarefs = {}  # key = idx, value = dataref path { 25: "sim/time/seconds" }, in UDP packet we receive '25=67545', thus sim/time/seconds=67545.

        self.states = {}  # {state_name: TPState}
        self.pages = {}  # {page_name: dict({path: dataref})}
        self.current_page = "main"

        # internal stats
        self._max_monitored = 0  # higest number of datarefs monitored at one point in time

        # Dataref value enqueue/dequeue
        # -> Reads UDP packets and enqueue values
        # <- Read values, update dataref if has changed and provoke update of listeners
        self.udp_queue = Queue()
        self.udp_thread = None
        self.dref_thread = None
        self.no_upd_enqueue = None

        XPlaneBeacon.__init__(self, tpclient)

    def __del__(self):
        """Quickly ask X-Plane to no longer monitor datarefs we know"""
        for i in range(len(self.datarefs)):
            self._monitor_dataref(next(iter(self.datarefs.values())), freq=0)
        self.disconnect()

    # ################################
    #
    # Dataref creation and registration
    #
    def register(self, dataref):
        if dataref.path not in self.all_datarefs:
            if dataref.path is not None:
                self.all_datarefs[dataref.path] = dataref
        return dataref

    def get_dataref(self, path):
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
    def _monitor_dataref(self, path, freq=None):
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
        if self.datarefidx % LOOP_ALIVE == 0:
            time.sleep(0.2)
        return True

    def _execute_command(self, command: Command):
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
        logger.debug(f"_execute_command: executed {command}")

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
        logger.debug(f"write_dataref: {path}={value}")
        self.socket.sendto(message, (self.beacon_data["IP"], self.beacon_data["Port"]))
        logger.debug(".. sent")

    # ################################
    #
    # Dataref "automatic" monitoring
    #
    def upd_enqueue(self):
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
                        self.update_state(STATE_XP_CONNECTED, FALSE)
                        if self.no_upd_enqueue is not None and not self.no_upd_enqueue.is_set():
                            self.no_upd_enqueue.set()
        self.no_upd_enqueue = None
        logger.debug("..terminated")

    def dataref_listener(self):
        """Continuously read dataref values from queue, update dataref value, and determine if value has changed.
        If value has changed, provoke call to .dataref_changed() of all listeners of the updated dataref.
        """
        logger.debug("starting..")
        dequeue_run = True
        total_updates = 0
        total_values = 0
        total_duration = 0.0
        total_update_duration = 0.0
        maxbl = 0

        while dequeue_run:
            values = self.udp_queue.get()
            bl = self.udp_queue.qsize()
            maxbl = max(bl, maxbl)
            if type(values) is str and values == TERMINATE_QUEUE:
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
                        f"average update time {round(total_update_duration / total_updates, 3)} ({total_updates} updates), {round(total_duration / total_values, 5)} ({total_values} values), backlog {bl}/{maxbl}."
                    )  # ignore

            except RuntimeError:
                logger.warning(f"dataref_listener:", exc_info=True)

        logger.debug("..terminated")

    # ################################
    #
    # Cockpit interface
    #
    def write_dataref(self, dataref: str, value):
        vfloat = value
        if type(value) is not float:
            logger.warning(f"dataref write should only send float")
            try:
                vfloat = float(value)
            except:
                logger.warning(f"dataref {dataref} value {value} failed to convert to float, ignoring")
                return
        self._write_dataref(dataref=dataref, value=vfloat)

    def commandOnce(self, command: str):
        self._execute_command(Command(command))

    def commandBegin(self, command: str):
        self._execute_command(Command(command + "/begin"))

    def commandEnd(self, command: str):
        self._execute_command(Command(command + "/end"))

    # ################################
    #
    # Touch Portal Interface
    #
    def suppress_all_datarefs_monitoring(self):
        if not self.connected:
            logger.warning("no connection")
            return
        for i in range(len(self.datarefs)):
            self._monitor_dataref(next(iter(self.datarefs.values())), freq=0)
        logger.debug("done")
        logger.debug(f">>>>> monitoring++{len(self.datarefs)}/{self._max_monitored}")

    def add_all_datarefs_to_monitor(self):
        """Add all dataref that needs monitoring to monitor"""
        if not self.connected:
            logger.warning("no connection")
            return
        # Add those to monitor
        prnt = []
        for path in self.datarefs_to_monitor.keys():
            if self._monitor_dataref(path, freq=DATA_SENT):
                prnt.append(path)
        logger.info(f"monitoring datarefs {prnt}")
        logger.debug(f">>>>> monitoring++{len(self.datarefs_to_monitor)}/{self._max_monitored}")

    def add_datarefs_to_monitor(self, datarefs):
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
        logger.debug(f">>>>> monitoring++{len(self.datarefs)}/{self._max_monitored}")

    def remove_datarefs_to_monitor(self, datarefs):
        if not self.connected and len(self.datarefs_to_monitor) > 0:
            logger.warning("no connection")
            logger.debug(f"would remove {datarefs.keys()}/{self._max_monitored}")
            return
        # Add those to monitor
        prnt = []
        for d in datarefs.values():
            if d.path in self.datarefs_to_monitor.keys():
                if self.datarefs_to_monitor[d.path] == 1:  # last one to monitor it, remove from X-Plane
                    if self._monitor_dataref(d.path, freq=0):
                        prnt.append(d.path)
                else:  # other(s) still interested in monitoring
                    logger.debug(f"{d.path} monitored {self.datarefs_to_monitor[d.path]} times")

                self.datarefs_to_monitor[d.path] = self.datarefs_to_monitor[d.path] - 1
                if self.datarefs_to_monitor[d.path] == 0:  # if no more interested, remove it
                    prnt.append(d.path)
                    del self.datarefs_to_monitor[d.path]
            else:
                logger.debug(f"no need to remove {d.path}")

        logger.debug(f"removed {prnt}")
        logger.debug(f"currently monitoring {self.datarefs_to_monitor}")
        logger.debug(f">>>>> monitoring--{len(self.datarefs)}/{self._max_monitored}")

    def remove_all_datarefs_to_monitor(self):
        self.suppress_all_datarefs_monitoring()
        self.datarefs_to_monitor = {}
        logger.debug("done")

    def remove_all_datarefs(self):
        if not self.connected and len(self.all_datarefs) > 0:
            logger.warning("no connection")
        logger.debug(f"removing..")
        datarefs = dict([(d, self.all_datarefs[d]) for d in self.datarefs_to_monitor.keys()])
        self.remove_datarefs_to_monitor(datarefs)
        self.all_datarefs = {}
        self.datarefs_to_monitor = {}
        logger.debug(f"..removed")

    def cleanup(self):
        """
        Called when before disconnecting.
        Just before disconnecting, we try to cancel dataref UDP reporting in X-Plane
        """
        self.suppress_all_datarefs_monitoring()

    def start(self):
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
            self.update_state(STATE_XP_DREFMON, TRUE)
            logger.info("dataref listener started")
        else:
            logger.info("dataref listener running.")
        # When restarted after network failure, should clean all datarefs
        # then reload datarefs from current page of each deck
        self.suppress_all_datarefs_monitoring()  # cancel previous subscriptions
        self.add_all_datarefs_to_monitor()  # add all datarefs that need monitoring

    def stop(self):
        self.suppress_all_datarefs_monitoring()  # cancel previous subscriptions
        if self.udp_queue is not None and self.dref_thread is not None:
            self.udp_queue.put(TERMINATE_QUEUE)
            self.dref_thread.join()
            self.dref_thread = None
            self.update_state(STATE_XP_DREFMON, FALSE)
            logger.debug("dataref listener stopped")
        if self.no_upd_enqueue is not None:
            self.no_upd_enqueue.set()
            logger.debug("stopping..")
            wait = SOCKET_TIMEOUT
            logger.debug(f"..asked to stop dataref listener (this may last {wait} secs. for UDP socket to timeout)..")
            self.udp_thread.join(wait)
            if self.udp_thread.is_alive():
                logger.warning("..thread may hang in socket.recvfrom()..")
            self.no_upd_enqueue = None
            logger.debug("..stopped")
        else:
            logger.debug("not running")

    # ################################
    # Cockpit interface
    #
    def terminate(self):
        logger.debug(f"currently {'not ' if self.no_upd_enqueue is None else ''}running. terminating..")
        self.remove_all_datarefs()
        logger.info("terminating..disconnecting..")
        self.disconnect()
        logger.info("..stopping..")
        self.stop()
        logger.info("..terminated")

    # ################################
    # Touch Portal plugin interface
    #
    def init(self):
        pages = {}
        if not os.path.exists(DYNAMIC_STATES):
            logger.debug(f"no file {DYNAMIC_STATES}")
            return

        with open(DYNAMIC_STATES, "r") as fp:
            states = json.load(fp)
            version = states.get("version")
            if version != "2":
                logger.warning(f"states file {DYNAMIC_STATES} invalid version {version}")
                return
            pages = states.get("pages")

        for page, states_defs in pages.items():
            for name, formula in states_defs.items():
                # state_name = dotkey(page, name)
                state = TPState(name=name, formula=formula, sim=self)
                self.add_datarefs_to_monitor(state.datarefs)
                self.states[state.internal_name] = state
            logger.debug(f"page {page} loaded {len(states_defs)}")

        self.connect()

    def change_page(self, page_name: str):
        if page_name in self.pages:
            if self.current_page in self.pages:
                self.remove_datarefs_to_monitor(self.pages[self.current_page])
            self.current_page = page_name
            self.add_datarefs_to_monitor(self.pages[self.current_page])
            logger.info(f"changed to page {self.current_page}")
