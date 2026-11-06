#!/usr/bin/env python3
"""Occupancy:  a live strand view of the data from one io channel.

One row per chip of the strand (hydra file order) plus an "other" row;  one character per channel:
the digit n for a rate of at least 10^n hits/s, . for under 1/s, blank for none;  per row the
hits/s and the mean ADC.  Refreshed each second over a sliding window;  Ctrl-C to stop.  Run from
the repo top, with data flowing (e.g. after pedestal.py --keep):
    python3 demos/occupancy.py
    python3 demos/occupancy.py --seconds 5    # stop after 5 s
"""

import argparse
import math
import sys
import time
from collections import deque

from larpix_control import common, asic_spec_from_yaml, load_network

N_CHANNELS = 64


def cell(rate: float) -> str:
    if rate <= 0:
        return " "
    if rate < 1:
        return "."
    return str(min(9, int(math.log10(rate))))


def render(hits, chips, window, io_chan, hydra) -> str:
    rows = {}
    for chip, channel, adc in hits:
        row = chip if chip in chips else "other"
        r = rows.setdefault(row, [[0] * N_CHANNELS, 0])
        r[0][channel] += 1
        r[1] += adc
    head = "".join(f"{c:<9d}" for c in range(0, N_CHANNELS, 8))
    lines = [f"strand on io channel 0x{io_chan:X} ({hydra}), rates over the last {window:g} s;  "
             ". under 1/s, n 10^n/s and up", "", f"chip   {head} hits/s  mean ADC"]
    for row in list(chips) + ["other"]:
        counts, adc_sum = rows.get(row, [[0] * N_CHANNELS, 0])
        total = sum(counts)
        cells = " ".join("".join(cell(n / window) for n in counts[c:c + 8])
                         for c in range(0, N_CHANNELS, 8))
        mean = f"{adc_sum / total:8.1f}" if total else "       -"
        lines.append(f"{str(row):>5}  {cells}  {total / window:7.0f}  {mean}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="live strand occupancy")
    parser.add_argument("--network", default="config/network/single_bench.yaml")
    parser.add_argument("--io_group", type=int, default=1)
    parser.add_argument("--io_chan", type=lambda s: int(s, 0), default=1)
    parser.add_argument("--hydra", default="config/hydra/single.yaml")
    parser.add_argument("--asic", default="config/asics/larpix_v3.yaml")
    parser.add_argument("--window", type=float, default=1.0, help="seconds of data per view")
    parser.add_argument("--seconds", type=float, default=0,
                        help="stop after this long (0:  until Ctrl-C)")
    args = parser.parse_args()

    spec = asic_spec_from_yaml(args.asic)
    board = load_network(args.network, spec)[args.io_group]
    chips = [c["chip_id"] for c in common.dict_from_yaml(args.hydra)["chips"]]
    live = sys.stdout.isatty()

    recent = deque()  # (arrival time, chip, channel, adc)
    board.start_data()
    start = next_view = time.monotonic()
    try:
        while not args.seconds or time.monotonic() - start < args.seconds:
            for w in board.read_data(100):
                if w.io_chan == args.io_chan and spec.valid_data_packet(w.word):
                    f = spec.parse_data_packet_fields(w.word)
                    recent.append((time.monotonic(), f["chip"], f["channel"], f["data_word"]))
            now = time.monotonic()
            while recent and recent[0][0] < now - args.window:
                recent.popleft()
            if now >= next_view:
                view = render([r[1:] for r in recent], chips, args.window, args.io_chan, args.hydra)
                print(("\033[H\033[2J" if live else "\n") + view, flush=True)
                next_view = now + 1
    except KeyboardInterrupt:
        pass
    finally:
        board.stop_data()
        board.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
