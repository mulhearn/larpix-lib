# larpix_control/pacman/asic_register.py
"""ASIC register access through the PACMAN servers.

Words go out through pacman_cmdserver (REQ/REP), which acknowledges each one;  replies come
back from pacman_dataserver (PUB), on a SUB socket subscribed only during a transmission.
"""

import time
from typing import Any

import yaml
import zmq

from larpix_control.asic._correlator import ReplyCorrelator
from larpix_control.asic.asic_spec import AsicSpec
from larpix_control.common.interfaces import AsicRegisterIface, OpReplies, OpType, RegisterOp
from larpix_control.pacman import message as pm

DATA_PORT = 5556            # pacman_dataserver
WORDS_PER_MESSAGE = 256     # Words per request to pacman_cmdserver


class PacmanAsicRegister(AsicRegisterIface):
    """AsicRegisterIface on PACMANs, routed by io channel from a network YAML file.

    The io channel's low byte is the PACMAN channel (UART + 1);  the upper bits select the
    PACMAN.  timeout_ms from the network file bounds each acknowledgement and the wait for
    replies after the last one.
    """

    def __init__(self, config_path: str, spec: AsicSpec, verbose: bool = False):
        self.spec = spec
        self.verbose = verbose
        self._ctx = zmq.Context.instance()
        self.groups: dict[int, dict[str, Any]] = {}    # By io_group
        self.routes: dict[int, int] = {}               # io_chan to io_group
        self._load(config_path)
        for group in self.groups.values():
            group["req"] = self._req_socket(group)
            sub = self._ctx.socket(zmq.SUB)
            sub.setsockopt(zmq.LINGER, 0)
            sub.connect(f"tcp://{group['hostname']}:{group['data_port']}")
            group["sub"] = sub

    def _load(self, path: str) -> None:
        with open(path) as f:
            cfg = yaml.safe_load(f)
        if not isinstance(cfg, dict) or "network" not in cfg:
            raise ValueError(f"invalid network file: {path}")
        for entry in cfg["network"]:
            io_group = int(entry["io_group"])
            if io_group in self.groups:
                raise ValueError(f"io_group {io_group} listed twice in {path}")
            self.groups[io_group] = {
                "hostname": str(entry["hostname"]),
                "port": int(entry["port"]),
                "data_port": int(entry.get("data_port", DATA_PORT)),
                "timeout_ms": int(entry["timeout_ms"]),
            }
            first = int(str(entry["first_io_chan"]), 0)
            mask = int(str(entry["uart_mask"]), 0)
            for bit in range(mask.bit_length()):
                if mask & (1 << bit):
                    io_chan = first + bit
                    if io_chan in self.routes:
                        raise ValueError(f"io channel 0x{io_chan:X} listed twice in {path}")
                    self.routes[io_chan] = io_group
        if not self.routes:
            raise ValueError(f"no io channels in {path}")

    def _req_socket(self, group: dict) -> zmq.Socket:
        sock = self._ctx.socket(zmq.REQ)
        sock.setsockopt(zmq.LINGER, 0)
        sock.setsockopt(zmq.RCVTIMEO, group["timeout_ms"])
        sock.setsockopt(zmq.SNDTIMEO, group["timeout_ms"])
        sock.connect(f"tcp://{group['hostname']}:{group['port']}")
        return sock

    def _log(self, text: str) -> None:
        if self.verbose:
            print(text)

    def transmit(self, ops: list[RegisterOp], fire_and_forget: bool = False) -> OpReplies:
        """Transmit ops in order;  with fire_and_forget, no replies are collected.

        Missing acknowledgements and replies are reported, with no error raised.
        """
        corr = ReplyCorrelator(self.spec, ops)
        for io_chan in {op.io_chan for op in ops}:
            if io_chan not in self.routes:
                raise ValueError(f"unknown io channel 0x{io_chan:X}")
        for io_group, group in self.groups.items():
            group_ops = [op for op in ops if self.routes[op.io_chan] == io_group]
            if group_ops:
                self._transmit_group(io_group, group, group_ops, corr, fire_and_forget)
        return corr.result(fire_and_forget)

    def _transmit_group(self, io_group: int, group: dict, ops: list[RegisterOp],
                        corr: ReplyCorrelator, fire_and_forget: bool) -> None:
        sub = group["sub"]
        if not fire_and_forget:
            sub.setsockopt(zmq.SUBSCRIBE, b"")
            self._drain(sub)
        try:
            words = [(op, self._packet(op)) for op in ops for _ in range(op.nrep)]
            for i in range(0, len(words), WORDS_PER_MESSAGE):
                if not self._send(io_group, group, words[i:i + WORDS_PER_MESSAGE], corr):
                    break
            if not fire_and_forget:
                self._receive(io_group, group, corr)
        finally:
            if not fire_and_forget:
                sub.setsockopt(zmq.UNSUBSCRIBE, b"")

    def _packet(self, op: RegisterOp) -> int:
        if op.op == OpType.WRITE:
            return self.spec.build_config_write(op.chip, op.reg, op.value)
        return self.spec.build_config_read(op.chip, op.reg)

    def _send(self, io_group: int, group: dict, words: list, corr: ReplyCorrelator) -> bool:
        """One request to pacman_cmdserver;  False if it went unacknowledged."""
        now = int(time.time())
        content = [pm.content_data(channel=op.io_chan & 0xFF, timestamp=now, payload=packet,
                                   pacman=io_group) for op, packet in words]
        req = group["req"]
        try:
            req.send(pm.pack_msg("REQ", content, timestamp=now))
            header, rep_words = pm.unpack_msg(req.recv())
        except zmq.ZMQError as e:
            self._log(f"WARNING:  io_group {io_group}:  no acknowledgement ({e});  reconnecting")
            req.close()
            group["req"] = self._req_socket(group)
            return False
        for (op, packet), rep in zip(words, rep_words):
            if rep[0] == "DATA" and rep[2] == op.io_chan & 0xFF and rep[4] == packet:
                corr.ack(op)
        return True

    def _drain(self, sub: zmq.Socket) -> None:
        """Discard words already waiting:  replies to earlier transmissions."""
        while True:
            try:
                sub.recv(zmq.NOBLOCK)
            except zmq.Again:
                return

    def _receive(self, io_group: int, group: dict, corr: ReplyCorrelator) -> None:
        """Pass words received from the data server to corr until done or the timeout."""
        base = {chan & ~0xFF for chan, grp in self.routes.items() if grp == io_group}
        sub = group["sub"]
        deadline = time.monotonic() + group["timeout_ms"] / 1000
        while not corr.done():
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not sub.poll(int(remaining * 1000)):
                return
            _, words = pm.unpack_msg(sub.recv())
            for w in words:
                if w[0] != "DATA":
                    continue
                for b in base:
                    if b | w[2] in self.routes:
                        corr.add(b | w[2], w[4])

    def close(self) -> None:
        """Close all connections."""
        for group in self.groups.values():
            for name in ("req", "sub"):
                if group.get(name) is not None:
                    group[name].close()
                    group[name] = None
