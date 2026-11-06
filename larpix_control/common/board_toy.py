# larpix_control/common/board_toy.py
"""Toy board:  AsicRegisterIface and BoardControlIface, registers in memory, no hardware."""

from typing import Any

from larpix_control.common.interfaces import (
    AsicRegisterIface, BoardControlIface, OpReplies, OpType, ReadReply, RegisterKey, RegisterOp,
    ResetType, WriteReply)

_DEFAULT_ENTRY = {"io_group": 1, "first_io_chan": 1, "uart_mask": 0xF, "uarts_per_tile": 4}


class BoardToy(AsicRegisterIface, BoardControlIface):
    """A readout board without hardware:  registers held in memory.

    Acknowledges every op.  Reads return the last value written (0 if none), and get no reply on
    a disabled io channel.  A full reset, or power off, clears the registers of the tile's
    channels.

    entry:  a network file entry, as for Pacman (hostname and ports unused).  None gives a
    stand-alone board for tests and demos:  io_group 1, first_io_chan 1, uart_mask 0xF,
    uarts_per_tile 4 (io channels 1 to 4, one tile).  It is not tied to any network file:  beside
    one, pass the matching entry.
    """

    def __init__(self, entry: dict[str, Any] | None = None, verbose: bool = False):
        entry = _DEFAULT_ENTRY if entry is None else entry
        self.verbose = verbose
        self.registers: dict[RegisterKey, int] = {}
        self._io_group = int(entry["io_group"])
        self._first_io_chan = int(str(entry["first_io_chan"]), 0)
        self._uarts_per_tile = int(entry["uarts_per_tile"])
        mask = int(str(entry["uart_mask"]), 0)
        self._io_chans = [self._first_io_chan + u for u in range(mask.bit_length())
                          if mask & (1 << u)]
        self._disabled: set[int] = set()

    @property
    def io_group(self) -> int:
        """The io_group of this board."""
        return self._io_group

    def ping(self) -> bool:
        """True:  a toy board always answers."""
        return True

    def get_tile(self, io_chan: int) -> int:
        """The tile of io_chan, one of this board's io channels."""
        self._check_chan(io_chan)
        return (io_chan - self._first_io_chan) // self._uarts_per_tile

    def _check_chan(self, io_chan: int) -> None:
        if io_chan not in self._io_chans:
            raise ValueError(f"io channel 0x{io_chan:X} not on io_group {self._io_group}")

    def _check_tile(self, tile: int) -> None:
        if tile not in {self.get_tile(c) for c in self._io_chans}:
            raise ValueError(f"tile {tile} not on io_group {self._io_group}")

    def _clear(self, tile: int) -> None:
        self.registers = {k: v for k, v in self.registers.items()
                          if self.get_tile(k.io_chan) != tile}

    def transmit(self, ops: list[RegisterOp], fire_and_forget: bool = False) -> OpReplies:
        """Transmit ops in order;  with fire_and_forget, no replies are collected."""
        for op in ops:
            self._check_chan(op.io_chan)
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
                if not fire_and_forget and op.io_chan not in self._disabled:
                    r.value = self.registers.get(op.key, 0)
                    r.received += op.nrep
        complete = fire_and_forget or all(r.received >= r.requests for r in reads.values())
        return OpReplies(writes, reads, complete)

    def close(self) -> None:
        """Close all connections."""

    def reset(self, tile: int, kind: ResetType) -> None:
        """Reset the ASICs of tile."""
        self._check_tile(tile)
        if kind == ResetType.FULL:
            self._clear(tile)

    def wait_on_reset(self) -> None:
        """Return at once:  toy resets settle immediately."""

    def power_on(self, tile: int) -> None:
        """Power up the ASICs of tile."""
        self._check_tile(tile)

    def power_off(self, tile: int) -> None:
        """Power down the ASICs of tile."""
        self._check_tile(tile)
        self._clear(tile)

    def uart_enable(self, io_chan: int) -> None:
        """Enable UART RX at io_chan."""
        self._check_chan(io_chan)
        self._disabled.discard(io_chan)

    def uart_disable(self, io_chan: int) -> None:
        """Disable (silence) UART RX at io_chan."""
        self._check_chan(io_chan)
        self._disabled.add(io_chan)
