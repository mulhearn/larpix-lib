#!/usr/bin/env python3
"""Pedestals:  the periodic trigger on every chip of a strand, as larpix-control's pedestal_qc.py.

The strand must already be up (e.g. after hello_asic.py).  With the tile's VDDA off, writes the
pedestal_trigger and pedestal_channels fragments to each chip, then VDDA on;  counts the words
received for a few seconds and stops the trigger again (unless --keep).  Run from the repo top:
    python3 demos/pedestal.py
    python3 demos/pedestal.py --keep          # leave the trigger running (e.g. for occupancy.py)
"""

import argparse
import sys
import time

from larpix_control import (
    common, asic_spec_from_yaml, fragment_lib_from_yaml, AsicConfig, load_network)
from larpix_control.common.interfaces import Rail


def main():
    parser = argparse.ArgumentParser(description="pedestals:  periodic trigger on a strand")
    parser.add_argument("--network", default="config/network/single_bench.yaml")
    parser.add_argument("--io_group", type=int, default=1)
    parser.add_argument("--io_chan", type=lambda s: int(s, 0), default=1)
    parser.add_argument("--hydra", default="config/hydra/single.yaml")
    parser.add_argument("--asic", default="config/asics/larpix_v3.yaml")
    parser.add_argument("--seconds", type=float, default=3, help="how long to count data")
    parser.add_argument("--keep", action="store_true", help="leave the periodic trigger running")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    spec = asic_spec_from_yaml(args.asic)
    frag_lib = fragment_lib_from_yaml("config/fragments/library.yaml", spec.name())
    board = load_network(args.network, spec, verbose=args.verbose)[args.io_group]
    tile = board.get_tile(args.io_chan)
    chips = [c["chip_id"] for c in common.dict_from_yaml(args.hydra)["chips"]]
    cfg = AsicConfig(board, spec, frag_lib, args.io_chan, verbose=args.verbose)

    board.rail_off(tile, Rail.VDDA)
    for chip in chips:
        cfg.apply_fragment(chip, "pedestal_trigger")
        cfg.apply_fragment(chip, "pedestal_channels")
    board.rail_on(tile, Rail.VDDA)
    print(f"pedestals on chips {chips}, io channel 0x{args.io_chan:X}, tile {tile}")

    board.start_data()
    data, other = {}, 0
    end = time.monotonic() + args.seconds
    while time.monotonic() < end:
        for w in board.read_data(100):
            if spec.valid_data_packet(w.word):
                chip = spec.parse_data_packet_fields(w.word)["chip"]
                data[chip] = data.get(chip, 0) + 1
            else:
                other += 1
    board.stop_data()

    if not args.keep:
        for chip in chips:
            cfg.apply_fragment(chip, "pedestal_stop")
    board.close()

    for chip in chips:
        print(f"chip {chip}:  {data.get(chip, 0) / args.seconds:.0f} data packets/s")
    others = {c: n for c, n in data.items() if c not in chips}
    if others or other:
        print(f"also:  {other} other words, data from chips {sorted(others)}")
    print("trigger left running" if args.keep else "trigger stopped")
    return 0 if all(data.get(chip, 0) for chip in chips) else 1


if __name__ == "__main__":
    sys.exit(main())
