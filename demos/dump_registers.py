#!/usr/bin/env python3
"""Dump the register space of one chip, decoded into its named fields.

Reads every register and marks with * each register whose value differs from its reset value
(from the ASIC YAML;  read-only fields marked ro).  Read-only:  the chip must already be up
(e.g. after hello_asic.py).  Run from the repo top:
    python3 demos/dump_registers.py
    python3 demos/dump_registers.py --changed -n 3
"""

import argparse
import re
import sys

from larpix_control import asic_spec_from_yaml, load_network
from larpix_control.common.interfaces import RegisterOp


def field_resets(spec) -> dict[str, int]:
    """Reset value of every field, array elements named name[i]."""
    base = {}
    for field in spec.asic_dict["register_space"]["fields"]:
        base[field["name"]] = (field["reset_value"], field.get("access", "rw"))
    resets, access = {}, {}  # By field name
    for name in spec.get_field_to_reg_lut():
        m = re.fullmatch(r"(\w+)\[(\d+)\]", name)
        value, acc = base[m.group(1)] if m else base[name]
        resets[name] = value[int(m.group(2))] if m and isinstance(value, list) else value
        access[name] = acc
    return resets, access


def main():
    parser = argparse.ArgumentParser(description="dump the register space of one chip")
    parser.add_argument("--chip", type=int, default=11)
    parser.add_argument("--io_chan", type=lambda s: int(s, 0), default=1)
    parser.add_argument("--network", default="config/network/single_bench.yaml")
    parser.add_argument("--asic", default="config/asics/larpix_v3.yaml")
    parser.add_argument("--changed", action="store_true",
                        help="only registers differing from reset")
    parser.add_argument("-n", "--nrep", type=int, default=1, help="reads of each register")
    args = parser.parse_args()

    spec = asic_spec_from_yaml(args.asic)
    boards = load_network(args.network, spec)
    board = next(b for b in boards.values() if args.io_chan in b.io_chans)
    n_regs = spec.asic_dict["register_space"]["parameters"]["num_registers"]
    f2r, r2f = spec.get_field_to_reg_lut(), spec.get_reg_to_field_lut()
    resets, access = field_resets(spec)

    reads = board.transmit([RegisterOp.read(args.io_chan, args.chip, r, nrep=args.nrep)
                            for r in range(n_regs)]).reads
    board.close()

    missing, changed, discrepant = [], 0, 0
    print(f"chip {args.chip}, io channel 0x{args.io_chan:X}:  {n_regs} registers"
          + (f", {args.nrep} reads each" if args.nrep > 1 else ""))
    for reg in range(n_regs):
        r = reads[(args.io_chan, args.chip, reg)]
        fields = r2f.get(reg, [])
        reset = None
        if fields:
            reset = dict(spec.build_write_list(update={f: resets[f] for f in fields}))[reg]
        differs = r.value is not None and reset is not None and r.value != reset
        changed += differs
        discrepant += r.discrepant
        if r.value is None:
            missing.append(reg)
        if args.changed and not differs and r.value is not None and not r.discrepant:
            continue
        value = "  --" if r.value is None else f"0x{r.value:02X}"
        mark = "*" if differs else " "
        decoded = []
        for f in fields:
            _, width, offset, _ = f2r[f]
            if r.value is not None:
                v = (r.value >> offset) & ((1 << width) - 1)
                decoded.append(f"{f}={v}" + (" ro" if access[f] == "ro" else ""))
        extra = f"  discrepant {r.discrepant}" if r.discrepant else ""
        text = "  ".join(decoded) if decoded else "(no fields)"
        print(f"{reg:3d}  {value} {mark}  {text}{extra}")

    print(f"{n_regs - len(missing)} of {n_regs} answered, {changed} differ from reset"
          + (f", {discrepant} discrepant replies" if discrepant else "")
          + (f";  unanswered:  {missing}" if missing else ""))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
