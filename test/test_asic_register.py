import unittest

from larpix_control import asic_spec_from_yaml, PacmanAsicRegister
from larpix_control.common.asic_register_toy import AsicRegisterToy
from larpix_control.common.interfaces import RegisterOp


class TestAsicRegisterToy(unittest.TestCase):

    def test_write_then_read(self):
        toy = AsicRegisterToy()
        res = toy.transmit([RegisterOp.write(1, 11, 125, 2), RegisterOp.read(1, 11, 125, nrep=2)])
        r = res.reads[(1, 11, 125)]
        self.assertEqual((r.requests, r.acked, r.value, r.received), (2, 2, 2, 2))
        self.assertEqual(res.writes[(1, 11, 125)].acked, 1)
        self.assertTrue(res.complete)

    def test_fire_and_forget(self):
        res = AsicRegisterToy().transmit([RegisterOp.read(1, 11, 125)], fire_and_forget=True)
        r = res.reads[(1, 11, 125)]
        self.assertEqual((r.acked, r.value, r.received), (1, None, 0))


class TestPacmanAsicRegister(unittest.TestCase):
    """Routing only:  no PACMAN needed (ZMQ connects lazily)."""

    def setUp(self):
        spec = asic_spec_from_yaml("config/asics/larpix_v3.yaml")
        self.reg_io = PacmanAsicRegister("config/network/single_bench.yaml", spec)

    def tearDown(self):
        self.reg_io.close()

    def test_routes(self):
        self.assertEqual(self.reg_io.routes, {1: 1, 2: 1, 3: 1, 4: 1})

    def test_unknown_channel(self):
        with self.assertRaises(ValueError):
            self.reg_io.transmit([RegisterOp.read(9, 11, 125)])


if __name__ == "__main__":
    unittest.main()
