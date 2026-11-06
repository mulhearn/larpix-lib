#!/usr/bin/env python3
"""Hello ASIC:  from a PACMAN just booted (or powered up) to a configured, answering strand.

Waits for the PACMAN, powers and resets the strand's tile, configures the strand, then reads back
every register written and prints PASS or FAIL (exit status 0 or 1).  Run from the repo top:
    python3 demos/hello_asic.py
    python3 demos/hello_asic.py --hydra config/hydra/pair.yaml --io_chan 2
"""

import argparse
import sys
import time

from larpix_control import (
    common, asic_spec_from_yaml, fragment_lib_from_yaml, AsicConfig, HydraStrand, load_network)
from larpix_control.common.interfaces import (
    AsicRegisterIface, OpReplies, OpType, RegisterOp, ResetType)


class RecordingRegisters(AsicRegisterIface):
    """Passes ops to a board and keeps the last value written to each register."""

    def __init__(self, board: AsicRegisterIface):
        self.board = board
        self.written: dict[tuple[int, int, int], int] = {}

    def transmit(self, ops: list[RegisterOp], fire_and_forget: bool = False) -> OpReplies:
        for op in ops:
            if op.op == OpType.WRITE:
                self.written[op.key] = op.value
        return self.board.transmit(ops, fire_and_forget)

    def close(self) -> None:
        self.board.close()


def wait_for_board(board, limit_s: float) -> bool:
    """Ping until the PACMAN answers, or limit_s passes."""
    start = time.monotonic()
    while time.monotonic() - start < limit_s:
        if board.ping():
            return True
        print(f"waiting for io_group {board.io_group} ({time.monotonic() - start:.0f} s)")
        time.sleep(2)
    return False


def main():
    parser = argparse.ArgumentParser(description="hello ASIC:  bring-up, configuration, readback")
    parser.add_argument("--network", default="config/network/single_bench.yaml")
    parser.add_argument("--io_group", type=int, default=1)
    parser.add_argument("--io_chan", type=lambda s: int(s, 0), default=1)
    parser.add_argument("--hydra", default="config/hydra/single.yaml")
    parser.add_argument("--asic", default="config/asics/larpix_v3.yaml")
    parser.add_argument("--wait", type=float, default=120, help="seconds to wait for the PACMAN")
    parser.add_argument("-v", "--verbose", action="store_true", help="trace the configuration")
    args = parser.parse_args()

    spec = asic_spec_from_yaml(args.asic)
    frag_lib = fragment_lib_from_yaml("config/fragments/library.yaml", spec.name())
    board = load_network(args.network, spec, verbose=args.verbose)[args.io_group]
    tile = board.get_tile(args.io_chan)

    if not wait_for_board(board, args.wait):
        print(f"FAIL:  io_group {args.io_group} did not answer within {args.wait:.0f} s")
        return 1
    board.sync_pacman_id()
    print(f"io_group {board.io_group} up;  io channel 0x{args.io_chan:X} on tile {tile}")

    board.uart_disable(args.io_chan)
    board.power_on(tile)
    time.sleep(0.05)
    board.reset(tile, ResetType.FULL)
    board.wait_on_reset()

    regs = RecordingRegisters(board)
    cfg = AsicConfig(regs, spec, frag_lib, args.io_chan, verbose=args.verbose)
    strand = HydraStrand(common.dict_from_yaml(args.hydra),
                         common.dict_from_yaml("config/hydra/parameters.yaml"), cfg)
    strand.init_network()
    board.uart_enable(args.io_chan)

    chips = set(strand.node_tree)
    expected = {key: value for key, value in regs.written.items() if key[1] in chips}
    chip_id_reg = spec.get_field_to_reg_lut()["chip_id"][0]
    expected.update({(args.io_chan, chip, chip_id_reg): chip for chip in chips})
    replies = board.transmit([RegisterOp.read(*key) for key in expected])
    bad = [(key, expected[key], r.value) for key, r in replies.reads.items()
           if r.value != expected[key]]
    board.close()

    print(f"read back {len(expected)} registers of chips {sorted(chips)}:  "
          f"{len(expected) - len(bad)} match")
    for (chan, chip, reg), want, got in bad:
        print(f"  chip {chip} reg {reg}:  wrote 0x{want:02X}, read "
              + ("nothing" if got is None else f"0x{got:02X}"))
    print("PASS" if not bad and replies.complete else "FAIL")
    return 0 if not bad and replies.complete else 1


if __name__ == "__main__":
    sys.exit(main())
