#!/usr/bin/env python3
import sys
from pathlib import Path

# Add project root (one level up from daq/) to sys.path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from   asic.helpers import dict_from_yaml

from asic import AsicSpec, asic_spec_from_yaml
from asic import chip_state
from asic import HydraStrand
from asic import load_fragment_library

VERBOSE = True

def main():
        toy = AsicConfigToy()
        raw_network = dict_from_yaml("config/hydra/single.yaml")
        raw_params  = dict_from_yaml("config/hydra/parameters.yaml")

        print("INFO: printing grid for hydra strand")
        strand.print_grid()
        print("INFO: printing network state")
        strand.print_network_state()
        strand.reset()

if __name__ == "__main__":
    main()
