import socket
import threading
import logging
import time
import json

from datetime import datetime

from TPPEntry import pluginkey

# ##############################
# Toliss Airbus FMA display
FMA_DATAREFS = {
    "1w": "AirbusFBW/FMA1w[:36]",
    "1g": "AirbusFBW/FMA1g[:36]",
    "1b": "AirbusFBW/FMA1b[:36]",
    "2w": "AirbusFBW/FMA2w[:36]",
    "2b": "AirbusFBW/FMA2b[:36]",
    "2m": "AirbusFBW/FMA2m[:36]",
    "3w": "AirbusFBW/FMA3w[:36]",
    "3b": "AirbusFBW/FMA3b[:36]",
    "3a": "AirbusFBW/FMA3a[:36]",
}
FMA_BOXES = [  # the first dataref FMA_BOXES[0] MUST be in the states.json file
    "AirbusFBW/FMAAPFDboxing",
    "AirbusFBW/FMAAPLeftArmedBox",
    "AirbusFBW/FMAAPLeftModeBox",
    "AirbusFBW/FMAAPRightArmedBox",
    "AirbusFBW/FMAAPRightModeBox",
    "AirbusFBW/FMAATHRModeBox",
    "AirbusFBW/FMAATHRboxing",
    "AirbusFBW/FMATHRWarning",
]
# Reproduction on Streamdeck touchscreen colors is difficult.
FMA_COLORS = {"b": "#0080FF", "w": "white", "g": "#00FF00", "m": "#FF00FF", "a": "#A04000"}

FMA_LABELS = {"ATHR": "Auto Thrust", "VNAV": "Vertical Navigation", "LNAV": "Horizontal Navigation", "APPR": "Approach", "AP": "Auto Pilot"}
FMA_LABELS_ALT = {"ATHR": "Autothrust Mode", "VNAV": "Vertical Mode", "LNAV": "Horizontal Mode", "APPR": "Approach", "AP": "Autopilot Mode"}
FMA_LABEL_MODE = 3  # 0 (None), 1 (keys), or 2 (values), or 3 alternates

FMA_COUNT = len(FMA_LABELS.keys())
FMA_COLUMNS = [[0, 7], [7, 15], [15, 21], [21, 28], [28, 37]]
FMA_LINE_LENGTH = FMA_COLUMNS[-1][-1]
FMA_LINES = 3

ANY = "0.0.0.0"
FMA_MCAST_PORT = 49505
FMA_UPDATE_FREQ = 2.0
FMA_MCAST_GRP = "239.255.1.1"
FMA_SOCKET_TIMEOUT = 10

loggerFMA = logging.getLogger("FMA")
# loggerFMA.setLevel(logging.DEBUG)
# loggerFMA.setLevel(15)


class FMA:
    def __init__(self, tpclient) -> None:
        self.tpclient = tpclient
        self.collect_fma = None
        self.update_fma = None
        self.fma_thread = None
        self.fma_thread2 = None
        self.fma_text_lock = threading.RLock()
        self.socket = None
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # Allow multiple sockets to use the same PORT number
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bind to the port that we know will receive multicast data
        self.socket.bind((ANY, FMA_MCAST_PORT))
        status = self.socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(FMA_MCAST_GRP) + socket.inet_aton(ANY))

        self.text = {}
        self.raw_lines = []
        self.previous_text = {}
        self.fma_lines = [[] for i in range(FMA_COUNT)]
        self.previous_fma_lines = [[] for i in range(FMA_COUNT)]
        self.FMA_BOXES = FMA_BOXES

    def reader(self):
        loggerFMA.debug("starting FMA collector..")
        total_to = 0
        total_reads = 0
        last_read_ts = datetime.now()
        total_read_time = 0.0
        while self.collect_fma is not None and not self.collect_fma.is_set():
            try:
                self.socket.settimeout(max(FMA_SOCKET_TIMEOUT, FMA_UPDATE_FREQ))
                data, addr = self.socket.recvfrom(1472)
                total_to = 0
                total_reads = total_reads + 1
                now = datetime.now()
                delta = now - last_read_ts
                total_read_time = total_read_time + delta.microseconds / 1000000
                last_read_ts = now
            except socket.error as e:
                total_to = total_to + 1
                if total_to < 6 or total_to % int(120 / FMA_SOCKET_TIMEOUT) == 0:  # every two minutes (120s)
                    loggerFMA.info(f"FMA collector: socket timeout received ({total_to} at {datetime.now().strftime('%H:%M:%S')})")
            else:
                ts = 0
                with self.fma_text_lock:
                    data = json.loads(data.decode("utf-8"))
                    if "ts" in data:
                        ts = data["ts"]
                        del data["ts"]
                    self.text = data
                # loggerFMA.debug(f"from {addr} at {ts}: data: {self.text}")
        self.collect_fma = None
        loggerFMA.debug("..FMA collector terminated")

    def writer(self):
        loggerFMA.debug("starting FMA updater..")
        # total_to = 0
        # total_reads = 0
        # total_values = 0
        # last_read_ts = datetime.now()
        # total_read_time = 0.0
        while not self.update_fma.is_set():
            updated = False
            with self.fma_text_lock:
                if self.text != self.previous_text:  #
                    self.update_all_fma_lines()
                    updated = True
            if updated:
                for i in range(FMA_COUNT):
                    if self.previous_fma_lines[i] != self.fma_lines[i]:
                        self.update_fma_text(i)
                    else:
                        loggerFMA.debug("no FMA change")
                self.previous_text = self.text
            # else:
            #     loggerFMA.debug(f"no change")
            time.sleep(FMA_UPDATE_FREQ)
        self.update_fma = None
        loggerFMA.debug("..FMA updater terminated")

    def is_running(self):
        return self.collect_fma is not None

    def check(self, must_run: bool):
        # loggerFMA.debug(f"check {must_run}, {self.is_running()}")
        if must_run and not self.is_running():
            self.start()
            return
        if not must_run and self.is_running():
            self.stop()
            return

    def update_fma_text(self, idx):
        keyname = f"FMA{idx+1}"
        key = pluginkey(keyname)
        text = "\n".join(self.fma_lines[idx])
        loggerFMA.debug(f"state {keyname} updated to {self.fma_lines[idx]}")
        self.tpclient.stateUpdate(key, text)
        self.previous_fma_lines[idx] = self.fma_lines[idx]

    def start(self) -> None:
        if self.collect_fma is None:
            self.collect_fma = threading.Event()
            self.fma_thread = threading.Thread(target=self.reader)
            self.fma_thread.name = "FMA::collector"
            self.fma_thread.start()
            loggerFMA.info("FMA collector started")
        else:
            loggerFMA.info("FMA collector already running.")
        if self.update_fma is None:
            self.update_fma = threading.Event()
            self.fma_thread2 = threading.Thread(target=self.writer)
            self.fma_thread2.name = "FMA::updater"
            self.fma_thread2.start()
            loggerFMA.info("FMA updater started")
        else:
            loggerFMA.info("FMA updater already running.")

    def stop(self) -> None:
        if self.update_fma is not None:
            self.update_fma.set()
            loggerFMA.debug("stopping FMA updater..")
            self.fma_thread2.join(FMA_UPDATE_FREQ)
            self.collect_fma = None
            loggerFMA.debug("..FMA updater stopped")
        else:
            loggerFMA.debug("FMA updater not running")
        if self.collect_fma is not None:
            self.collect_fma.set()
            loggerFMA.debug("stopping FMA collector..")
            loggerFMA.debug(f"..asked to stop FMA collector (this may last {FMA_SOCKET_TIMEOUT} secs. for UDP socket to timeout)..")
            self.fma_thread.join(FMA_SOCKET_TIMEOUT)
            if self.fma_thread.is_alive():
                loggerFMA.warning("..thread may hang in socket.recvfrom()..")
            self.collect_fma = None
            loggerFMA.debug("..FMA collector stopped")
        else:
            loggerFMA.debug("FMA collector not running")

    def get_fma_lines(self, idx):
        """Get portion of line corresponding to FMA."""
        s = FMA_COLUMNS[idx][0]  # idx * self.text_length
        e = FMA_COLUMNS[idx][1]  # s + self.text_length-
        return [text[s:e] for text in self.raw_lines]

    def update_all_fma_lines(self):
        """Particularities of this get_lines: There is no color!
        So colored line portions are all merged into a single piece of text.
        """

        def get_fma_lines(idx):
            """Get portion of line corresponding to FMA."""
            s = FMA_COLUMNS[idx][0]  # idx * self.text_length
            e = FMA_COLUMNS[idx][1]  # s + self.text_length-
            return [text[s:e] for text in self.raw_lines]

        self.raw_lines = ["" * FMA_LINE_LENGTH for i in range(1, FMA_LINES + 1)]
        for li in range(1, FMA_LINES + 1):  # for each line in FMA
            lines = {k: v for k, v in self.text.items() if int(k[-2]) == li}
            ret = []
            for c in range(FMA_LINE_LENGTH):
                for line in lines.values():
                    if c < len(line) and line[c] != " ":
                        ret.append(line[c])
                if len(ret) < c:
                    ret.append(" ")
            txt = "".join(ret)
            if len(txt) < FMA_LINE_LENGTH:  # ensure proper length
                txt = txt + " " * (FMA_LINE_LENGTH - len(txt))
            if len(txt) > FMA_LINE_LENGTH:
                txt = txt[:FMA_LINE_LENGTH]
            self.raw_lines[li - 1] = txt

        # print(f"\n", "\n".join(self.raw_lines))
        self.fma_lines = [get_fma_lines(i) for i in range(FMA_COUNT)]
