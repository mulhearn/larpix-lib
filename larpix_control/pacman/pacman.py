# larpix_control/pacman/pacman.py
"""One PACMAN through its servers:  ASIC register access and board control.

Words and board register writes go out through pacman_cmdserver (REQ/REP), which acknowledges
each one;  ASIC replies come back from pacman_dataserver (PUB), on a SUB socket subscribed only
during a transmission.
"""

import time
from typing import Any

import yaml
import zmq

from larpix_control.asic._correlator import ReplyCorrelator
from larpix_control.asic.asic_spec import AsicSpec
from larpix_control.common.interfaces import (
    AsicRegisterIface, BoardControlIface, OpReplies, OpType, RegisterOp, ResetType)
from larpix_control.pacman import message as pm

DATA_PORT = 5556            # pacman_dataserver
WORDS_PER_MESSAGE = 256     # Words per request to pacman_cmdserver
_RESET_SETTLE_S = 0.001      # Settling time after a reset

# pacman_cmdserver virtual registers (pacman-software pacman_vspace.cc;  zero-referenced)
_VSPACE_VDDA_DAC = 0x00200010        # + tile
_VSPACE_VDDD_DAC = 0x00200020        # + tile
_VSPACE_GLOBAL_POWER_ON = 0x00100114
_VSPACE_TILE_ON = 0x00100214         # Value:  tile
_VSPACE_TILE_OFF = 0x00100210        # Value:  tile
_VSPACE_UART_RX_ON = 0x00100314      # Value:  UART
_VSPACE_UART_RX_OFF = 0x00100310     # Value:  UART
_VSPACE_INTERNAL_RESET = 0x00100410  # Value:  tile mask
_VSPACE_FULL_RESET = 0x00100420      # Value:  tile mask

_VDDA_DAC = 0xE2FF           # Nominal tile power (as pacman_menu)
_VDDD_DAC = 0x75FF


class Pacman(AsicRegisterIface, BoardControlIface):
    """One PACMAN (one io_group):  ASIC register access and board control.

    Built from one entry of a network YAML file:  io_group, hostname, port (pacman_cmdserver),
    data_port (pacman_dataserver;  default DATA_PORT), timeout_ms, first_io_chan, uart_mask and
    uarts_per_tile.  Its io channels are first_io_chan + u for each bit u of uart_mask;  an io
    channel's low byte is the PACMAN channel (UART + 1);  its tile is
    (io_chan - first_io_chan) // uarts_per_tile.  sync_pacman_id sets the PACMAN's own ID to
    io_group.  timeout_ms bounds each acknowledgement and the wait for replies after the last one.
    """

    def __init__(self, entry: dict[str, Any], spec: AsicSpec, verbose: bool = False):
        self.spec = spec
        self.verbose = verbose
        self._io_group = int(entry["io_group"])
        self._hostname = str(entry["hostname"])
        self._port = int(entry["port"])
        self._data_port = int(entry.get("data_port", DATA_PORT))
        self._timeout_ms = int(entry["timeout_ms"])
        self._first_io_chan = int(str(entry["first_io_chan"]), 0)
        self._uarts_per_tile = int(entry["uarts_per_tile"])
        mask = int(str(entry["uart_mask"]), 0)
        chans = [self._first_io_chan + u for u in range(mask.bit_length()) if mask & (1 << u)]
        self.io_chans: list[int] = chans  # This board's io channels
        if not self.io_chans:
            raise ValueError(f"io_group {self._io_group}:  no io channels in uart_mask")
        self._ctx = zmq.Context.instance()
        self._req = self._req_socket()
        self._sub = self._ctx.socket(zmq.SUB)
        self._sub.setsockopt(zmq.LINGER, 0)
        self._sub.connect(f"tcp://{self._hostname}:{self._data_port}")
        self._last_reset = None

    @property
    def io_group(self) -> int:
        """The io_group of this board."""
        return self._io_group

    def _req_socket(self) -> zmq.Socket:
        sock = self._ctx.socket(zmq.REQ)
        sock.setsockopt(zmq.LINGER, 0)
        sock.setsockopt(zmq.RCVTIMEO, self._timeout_ms)
        sock.setsockopt(zmq.SNDTIMEO, self._timeout_ms)
        sock.connect(f"tcp://{self._hostname}:{self._port}")
        return sock

    def _log(self, text: str) -> None:
        if self.verbose:
            print(text)

    def _exchange(self, msg: bytes):
        """One request to pacman_cmdserver;  the reply, or None (the socket is then renewed)."""
        try:
            self._req.send(msg)
            return self._req.recv()
        except zmq.ZMQError as e:
            self._log(f"WARNING:  io_group {self._io_group}:  no reply from pacman_cmdserver ({e})")
            self._req.close()
            self._req = self._req_socket()
            return None

    def ping(self) -> bool:
        """True if pacman_cmdserver answers a ping within the timeout."""
        rep = self._exchange(pm.pack_msg("REQ", [pm.content_ping(pacman=self._io_group)],
                                         timestamp=int(time.time())))
        return rep is not None and pm.unpack_msg(rep)[1][0][0] == "PING"

    def sync_pacman_id(self) -> None:
        """Set the PACMAN's own ID to io_group (it is 0 after the PACMAN boots)."""
        rep = self._exchange(pm.pack_string_msg(f"set_pacman_id id={self._io_group}",
                                                timestamp=int(time.time())))
        if rep is None or "set to" not in pm.unpack_string_msg(rep)[1]:
            self._log(f"WARNING:  io_group {self._io_group}:  PACMAN ID not set")

    def _write(self, addr: int, value: int) -> None:
        """Write one PACMAN register;  a missing acknowledgement is logged."""
        now = int(time.time())
        rep = self._exchange(pm.pack_msg(
            "REQ", [pm.content_write(addr=addr, value=value, pacman=self._io_group)],
            timestamp=now))
        if rep is None or pm.unpack_msg(rep)[1][0][0] != "WRITE":
            self._log(f"WARNING:  io_group {self._io_group}:  write 0x{addr:08X} not acknowledged")

    def _check_chan(self, io_chan: int) -> None:
        if io_chan not in self.io_chans:
            raise ValueError(f"io channel 0x{io_chan:X} not on io_group {self._io_group}")

    def get_tile(self, io_chan: int) -> int:
        """The tile of io_chan, one of this board's io channels."""
        self._check_chan(io_chan)
        return (io_chan - self._first_io_chan) // self._uarts_per_tile

    def _check_tile(self, tile: int) -> None:
        if tile not in {self.get_tile(c) for c in self.io_chans}:
            raise ValueError(f"tile {tile} not on io_group {self._io_group}")

    def transmit(self, ops: list[RegisterOp], fire_and_forget: bool = False) -> OpReplies:
        """Transmit ops in order;  with fire_and_forget, no replies are collected.

        Missing acknowledgements and replies are reported, with no error raised.
        """
        for op in ops:
            self._check_chan(op.io_chan)
        corr = ReplyCorrelator(self.spec, ops)
        if not ops:
            return corr.result(fire_and_forget)
        if not fire_and_forget:
            self._sub.setsockopt(zmq.SUBSCRIBE, b"")
            self._drain()
        try:
            words = [(op, self._packet(op)) for op in ops for _ in range(op.nrep)]
            for i in range(0, len(words), WORDS_PER_MESSAGE):
                if not self._send(words[i:i + WORDS_PER_MESSAGE], corr):
                    break
            if not fire_and_forget:
                self._receive(corr)
        finally:
            if not fire_and_forget:
                self._sub.setsockopt(zmq.UNSUBSCRIBE, b"")
        return corr.result(fire_and_forget)

    def _packet(self, op: RegisterOp) -> int:
        if op.op == OpType.WRITE:
            return self.spec.build_config_write(op.chip, op.reg, op.value)
        return self.spec.build_config_read(op.chip, op.reg)

    def _send(self, words: list, corr: ReplyCorrelator) -> bool:
        """One request of ASIC words;  False if it went unacknowledged."""
        now = int(time.time())
        content = [pm.content_data(channel=op.io_chan & 0xFF, timestamp=now, payload=packet,
                                   pacman=self._io_group) for op, packet in words]
        rep = self._exchange(pm.pack_msg("REQ", content, timestamp=now))
        if rep is None:
            return False
        for (op, packet), w in zip(words, pm.unpack_msg(rep)[1]):
            if w[0] == "DATA" and w[2] == op.io_chan & 0xFF and w[4] == packet:
                corr.ack(op)
        return True

    def _drain(self) -> None:
        """Discard words already waiting:  replies to earlier transmissions."""
        while True:
            try:
                self._sub.recv(zmq.NOBLOCK)
            except zmq.Again:
                return

    def _receive(self, corr: ReplyCorrelator) -> None:
        """Pass words received from the data server to corr until done or the timeout."""
        by_wire = {c & 0xFF: c for c in self.io_chans}
        deadline = time.monotonic() + self._timeout_ms / 1000
        while not corr.done():
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self._sub.poll(int(remaining * 1000)):
                return
            _, words = pm.unpack_msg(self._sub.recv())
            for w in words:
                if w[0] == "DATA" and w[2] in by_wire:
                    corr.add(by_wire[w[2]], w[4])

    def close(self) -> None:
        """Close all connections."""
        for sock in (self._req, self._sub):
            if sock is not None:
                sock.close()
        self._req = self._sub = None

    def reset(self, tile: int, kind: ResetType) -> None:
        """Reset the ASICs of tile;  see wait_on_reset."""
        self._check_tile(tile)
        addr = _VSPACE_FULL_RESET if kind == ResetType.FULL else _VSPACE_INTERNAL_RESET
        self._write(addr, 1 << tile)
        self._last_reset = time.monotonic()

    def wait_on_reset(self) -> None:
        """Return once the resets issued have settled (1 ms after the last)."""
        if self._last_reset is not None:
            time.sleep(max(0.0, self._last_reset + _RESET_SETTLE_S - time.monotonic()))

    def power_on(self, tile: int) -> None:
        """Power the ASICs of tile at the nominal values (as pacman_menu)."""
        self._check_tile(tile)
        self._write(_VSPACE_VDDA_DAC + tile, _VDDA_DAC)
        self._write(_VSPACE_VDDD_DAC + tile, _VDDD_DAC)
        self._write(_VSPACE_GLOBAL_POWER_ON, 0)
        self._write(_VSPACE_TILE_ON, tile)

    def power_off(self, tile: int) -> None:
        """Remove power from the ASICs of tile."""
        self._check_tile(tile)
        self._write(_VSPACE_TILE_OFF, tile)

    def uart_enable(self, io_chan: int) -> None:
        """Deliver words received on io_chan."""
        self._check_chan(io_chan)
        self._write(_VSPACE_UART_RX_ON, io_chan - self._first_io_chan)

    def uart_disable(self, io_chan: int) -> None:
        """Stop delivering words received on io_chan;  they are lost, not queued."""
        self._check_chan(io_chan)
        self._write(_VSPACE_UART_RX_OFF, io_chan - self._first_io_chan)


def load_network(path: str, spec: AsicSpec, verbose: bool = False) -> dict[int, Pacman]:
    """One Pacman for each entry of a network YAML file, by io_group."""
    with open(path) as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict) or "network" not in cfg:
        raise ValueError(f"invalid network file: {path}")
    boards: dict[int, Pacman] = {}
    for entry in cfg["network"]:
        board = Pacman(entry, spec, verbose)
        if board.io_group in boards:
            raise ValueError(f"io_group {board.io_group} listed twice in {path}")
        overlap = set(board.io_chans) & {c for b in boards.values() for c in b.io_chans}
        if overlap:
            raise ValueError(f"io channels {sorted(overlap)} listed twice in {path}")
        boards[board.io_group] = board
    return boards
