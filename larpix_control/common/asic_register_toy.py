# larpix_control/common/asic_register_toy.py
"""Toy AsicRegisterIface:  registers held in memory, no hardware."""

from larpix_control.common.interfaces import (
    AsicRegisterIface, OpReplies, OpType, ReadReply, RegisterKey, RegisterOp, WriteReply)


class AsicRegisterToy(AsicRegisterIface):
    """Acknowledges every op;  reads return the last value written (0 if none)."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.registers: dict[RegisterKey, int] = {}

    def transmit(self, ops: list[RegisterOp], fire_and_forget: bool = False) -> OpReplies:
        """Transmit ops in order;  with fire_and_forget, no replies are collected."""
        writes: dict[RegisterKey, WriteReply] = {}
        reads: dict[RegisterKey, ReadReply] = {}
        for op in ops:
            if self.verbose:
                print(f"[TOY] {op.op.name:5s} chan 0x{op.io_chan:X} chip {op.chip} reg {op.reg} "
                      f"value 0x{op.value:02X} x{op.nrep}")
            if op.op == OpType.WRITE:
                self.registers[op.key] = op.value
                w = writes.setdefault(op.key, WriteReply(*op.key, 0, 0))
                w.requests += op.nrep
                w.acked += op.nrep
            else:
                r = reads.setdefault(op.key, ReadReply(*op.key, 0, 0, None, 0, 0))
                r.requests += op.nrep
                r.acked += op.nrep
                if not fire_and_forget:
                    r.value = self.registers.get(op.key, 0)
                    r.received += op.nrep
        return OpReplies(writes, reads, True)

    def close(self) -> None:
        """Close all connections."""
