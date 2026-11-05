#!/usr/bin/env python3
import sys
from pathlib import Path

from larpix_control import common, AsicSpec, asic_spec_from_yaml, fragment_lib_from_yaml, AsicConfig, HydraStrand, PacmanAsicRegister

VERBOSE = False

def main():
        asic_spec = asic_spec_from_yaml("config/asics/larpix_v3.yaml")
        frag_lib = fragment_lib_from_yaml("config/fragments/library.yaml", "larpix_v3")
        #raw_network = common.dict_from_yaml("config/hydra/row.yaml")
        raw_network = common.dict_from_yaml("config/hydra/single.yaml")
        #raw_network = common.dict_from_yaml("config/hydra/pair.yaml")
        raw_params  = common.dict_from_yaml("config/hydra/parameters.yaml")
        reg_io = PacmanAsicRegister("config/network/single_bench.yaml", asic_spec)
        cfg = AsicConfig(reg_io, asic_spec, frag_lib, 1, verbose=VERBOSE)
        strand = HydraStrand(raw_network, raw_params, cfg)

        if VERBOSE:
                print("INFO: printing table for hydra strand")
                strand.print_hydra_table()


        if VERBOSE:
                print("INFO: printing grid for hydra strand")
                strand.print_hydra_table()

        strand.reset()

        if VERBOSE:
                print("INFO: printing network state")
                strand.print_network_state()

        strand.init_network()

        if VERBOSE:
                strand.print_network_state()


if __name__ == "__main__":
    main()
