import unittest

from larpix_control import asic_spec_from_yaml, fragment_lib_from_yaml, AsicConfig
from larpix_control.common.board_toy import BoardToy


def data_word(chip, channel, timestamp, adc, trigger_type):
    """A data packet with odd overall parity, as the ASIC sends."""
    w = 0b01 | chip << 2 | channel << 10 | timestamp << 16 | adc << 46 | trigger_type << 56
    if bin(w).count("1") % 2 == 0:
        w |= 1 << 63
    return w


class TestDataPacket(unittest.TestCase):

    def setUp(self):
        self.spec = asic_spec_from_yaml("config/asics/larpix_v3.yaml")

    def test_parse(self):
        w = data_word(11, 63, 0xABCDEF0, 1023, 3)
        self.assertTrue(self.spec.valid_data_packet(w))
        f = self.spec.parse_data_packet_fields(w)
        got = (f["chip"], f["channel"], f["timestamp"], f["data_word"], f["trigger_type"])
        self.assertEqual(got, (11, 63, 0xABCDEF0, 1023, 3))
        self.assertNotIn("shared_fifo_count", f)                # enabled_by fields off by default

    def test_invalid(self):
        w = data_word(11, 0, 0, 0, 0)
        self.assertFalse(self.spec.valid_data_packet(w ^ (1 << 63)))    # parity broken
        self.assertFalse(self.spec.valid_data_packet(self.spec.build_config_read(11, 1)))


class TestApplyFragment(unittest.TestCase):

    def test_pedestal_fragments(self):
        spec = asic_spec_from_yaml("config/asics/larpix_v3.yaml")
        lib = fragment_lib_from_yaml("config/fragments/library.yaml", spec.name())
        toy = BoardToy()
        cfg = AsicConfig(toy, spec, lib, 1)
        cfg.apply_fragment(11, "pedestal_trigger")
        cfg.apply_fragment(11, "pedestal_channels")
        regs = {k.reg: v for k, v in toy.registers.items() if k.chip == 11}
        self.assertEqual([regs[r] for r in (166, 167, 168, 169)], [0xA0, 0x86, 0x01, 0x00])
        self.assertTrue(all(regs[r] == 0xFF for r in range(66, 74)))       # CSAs on
        self.assertTrue(all(regs[r] == 0x00 for r in range(131, 139)))     # Channels unmasked
        cfg.apply_fragment(11, "pedestal_stop")
        f2r = spec.get_field_to_reg_lut()
        reg, _, offset, _ = f2r["enable_periodic_trigger"]
        self.assertEqual((toy.registers[(1, 11, reg)] >> offset) & 1, 0)


if __name__ == "__main__":
    unittest.main()
