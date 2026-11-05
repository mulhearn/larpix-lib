import unittest

from larpix_control import HydraStrand, common

from larpix_control.hydra.asic_config_toy import AsicConfigToy
VERBOSE = True

class TestHydraStrand(unittest.TestCase):
    """tests related to asic model structure and verification"""

    def setUp(self):
        self.toy        = AsicConfigToy()
        self.raw_hydra  = common.dict_from_yaml("config/hydra/row.yaml")
        self.raw_params = common.dict_from_yaml("config/hydra/parameters.yaml")
        self.strand = HydraStrand(self.raw_hydra, self.raw_params, self.toy)

    def test_aaa_hydra_strand(self):
        print("")
        print("INFO: printing grid for hydra strand")
        self.strand.print_hydra_grid()
        print("INFO: printing network state")
        self.strand.print_network_state()
        self.strand.reset()


if __name__ == "__main__":
    unittest.main()
