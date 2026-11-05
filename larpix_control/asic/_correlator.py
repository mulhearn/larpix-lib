# larpix_control/asic/_correlator.py
"""Matching of ASIC replies to the register ops of one transmission."""

from collections import Counter

from larpix_control.common.interfaces import (
    OpType, RegisterKey, RegisterOp, WriteReply, ReadReply, OpReplies)
from .asic_spec import AsicSpec


class ReplyCorrelator:
    """Tallies acknowledgements and read replies by register for one transmission."""

    def __init__(self, spec: AsicSpec, ops: list[RegisterOp]):
        self.spec = spec
        self._writes: dict[RegisterKey, list[int]] = {}    # Requests, acked
        self._reads: dict[RegisterKey, list] = {}          # Requests, acked, values
        for op in ops:
            if op.op == OpType.WRITE:
                self._writes.setdefault(op.key, [0, 0])[0] += op.nrep
            else:
                self._reads.setdefault(op.key, [0, 0, []])[0] += op.nrep

    def ack(self, op: RegisterOp, n: int = 1) -> None:
        """Count n acknowledged words of op."""
        table = self._writes if op.op == OpType.WRITE else self._reads
        table[op.key][1] += n

    def add(self, io_chan: int, word: int) -> None:
        """Add a word received on io_chan;  words other than replies to reads here are ignored."""
        if not self.spec.valid_config_read_response(word):
            return
        chip, reg, value = self.spec.parse_chip_address_value(word)
        entry = self._reads.get(RegisterKey(io_chan, chip, reg))
        if entry is not None:
            entry[2].append(value)

    def done(self) -> bool:
        """True once every read has as many replies as requests."""
        return all(len(values) >= requests for requests, _, values in self._reads.values())

    def result(self, fire_and_forget: bool = False) -> OpReplies:
        """The outcome by register, in request order."""
        writes = {key: WriteReply(*key, requests, acked)
                  for key, (requests, acked) in self._writes.items()}
        reads = {}
        for key, (requests, acked, values) in self._reads.items():
            value, agree = _majority(values)
            reads[key] = ReadReply(*key, requests, acked, value, len(values), len(values) - agree)
        complete = (all(w.acked >= w.requests for w in writes.values())
                    and all(r.acked >= r.requests for r in reads.values())
                    and (fire_and_forget or all(r.received >= r.requests for r in reads.values())))
        return OpReplies(writes, reads, complete)


def _majority(values: list[int]) -> tuple:
    """Most frequent value (the last received on a tie) and its count;  (None, 0) if none."""
    if not values:
        return None, 0
    counts = Counter(values)
    best = max(counts.values())
    for value in reversed(values):
        if counts[value] == best:
            return value, best
