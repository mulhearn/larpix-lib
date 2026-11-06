# larpix/common/interfaces.py
"""Common interfaces for the LArPix control software.

This module defines abstract base classes (ABCs) for software
interfaces, which have concrete implementations elsewhere.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import NamedTuple, Optional


class AsicConfigIface(ABC):
    """Abstract interface for high-level ASIC configuration operations."""

    @abstractmethod
    def set_chip_id(self, chip_id) -> None:
        """Set the chip_id"""
        pass

    @abstractmethod
    def init_root_chip_io(self, chip_id: int, fpga_port: str) -> None:
        """Initialize the root chip for I/O"""
        pass

    @abstractmethod
    def init_io(self, chip_id: int) -> None:
        """Initialize a non-root chip for I/O"""
        pass

    @abstractmethod
    def set_input_enables(self, chip_id: int, ports: list[str]) -> None:
        """Set enables for receiving (either direction)"""
        pass

    @abstractmethod
    def set_downstream_output_enables(self, chip_id: int, ports: list[str]) -> None:
        """Set enables for transmitting downstream (toward FPGA)"""
        pass

    @abstractmethod
    def set_upstream_output_enables(self, chip_id: int, ports: list[str]) -> None:
        """Set enables for transmitting upstream (from FPGA)"""
        pass


class OpType(Enum):
    """Kinds of register access."""
    WRITE = auto()
    READ = auto()


class RegisterKey(NamedTuple):
    """One register of one chip:  chip IDs are unique only within an io channel."""
    io_chan: int        # In its board's configured range
    chip: int
    reg: int


@dataclass
class RegisterOp:
    """One register access, repeated nrep times back to back."""
    op: OpType
    io_chan: int        # In its board's configured range
    chip: int
    reg: int
    value: int = 0      # Used by writes
    nrep: int = 1

    @classmethod
    def write(cls, io_chan: int, chip: int, reg: int, value: int, nrep: int = 1) -> "RegisterOp":
        return cls(OpType.WRITE, io_chan, chip, reg, value, nrep)

    @classmethod
    def read(cls, io_chan: int, chip: int, reg: int, nrep: int = 1) -> "RegisterOp":
        return cls(OpType.READ, io_chan, chip, reg, 0, nrep)

    @property
    def key(self) -> RegisterKey:
        return RegisterKey(self.io_chan, self.chip, self.reg)


@dataclass
class WriteReply:
    """Outcome of the writes to one register."""
    io_chan: int
    chip: int
    reg: int
    requests: int
    acked: int


@dataclass
class ReadReply:
    """Outcome of the reads of one register."""
    io_chan: int
    chip: int
    reg: int
    requests: int
    acked: int
    value: Optional[int]    # Majority of the replies (last received on a tie);  None if none
    received: int
    discrepant: int         # Replies differing from value


@dataclass
class OpReplies:
    """Outcome of one request, by register in request order."""
    writes: dict[RegisterKey, WriteReply]
    reads: dict[RegisterKey, ReadReply]
    complete: bool          # All acked;  every read received >= requests (unless fire and forget)


class AsicRegisterIface(ABC):
    """Register access to the ASICs: transmit read and write operations and check for send
    acknowledgement. Then, if fire_and_forget is False, also collate read replies.  Implementation
    of timeout and debugging streams is left to concrete instances.

    """

    @abstractmethod
    def transmit(self, ops: list[RegisterOp], fire_and_forget: bool = False) -> OpReplies:
        """Transmit ops in order;  with fire_and_forget, no replies are collected.

        Missing acknowledgements and replies are reported, with no error raised.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close all connections."""
        pass


class ResetType(Enum):
    """Kinds of ASIC reset."""
    FULL = auto()       # Registers to their reset values, chip ID 1
    INTERNAL = auto()   # Internal state cleared, configuration kept


class BoardControlIface(ABC):
    """Control of one readout board (one io_group), other than ASIC configuration.

    Tiles are numbered within the board;  io channels are in the board's configured range.
    Operations take effect on the ASICs as described and return at once, without replies.
    """

    @property
    @abstractmethod
    def io_group(self) -> int:
        """The io_group of this board."""
        pass

    @abstractmethod
    def ping(self) -> bool:
        """True if the board answers:  a query, not a poke."""
        pass

    @abstractmethod
    def get_tile(self, io_chan: int) -> int:
        """The tile of io_chan, one of this board's io channels."""
        pass

    @abstractmethod
    def reset(self, tile: int, kind: ResetType) -> None:
        """Reset the ASICs of tile;  see wait_on_reset."""
        pass

    @abstractmethod
    def wait_on_reset(self) -> None:
        """Return once the resets issued have settled."""
        pass

    @abstractmethod
    def power_on(self, tile: int) -> None:
        """Power the ASICs of tile;  they come up as after a full reset."""
        pass

    @abstractmethod
    def power_off(self, tile: int) -> None:
        """Remove power from the ASICs of tile."""
        pass

    @abstractmethod
    def uart_enable(self, io_chan: int) -> None:
        """Deliver words received on io_chan."""
        pass

    @abstractmethod
    def uart_disable(self, io_chan: int) -> None:
        """Stop delivering words received on io_chan;  they are lost, not queued."""
        pass
