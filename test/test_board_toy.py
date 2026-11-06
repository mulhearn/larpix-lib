import unittest

from larpix_control.common.board_toy import BoardToy
from larpix_control.common.interfaces import Rail, RegisterOp, ResetType

ENTRY = {"io_group": 2, "hostname": "localhost", "port": 5555, "timeout_ms": 100,
         "first_io_chan": 0x201, "uart_mask": 0xFF, "uarts_per_tile": 4}


class TestBoardToy(unittest.TestCase):

    def test_write_then_read(self):
        toy = BoardToy()
        res = toy.transmit([RegisterOp.write(1, 11, 125, 2), RegisterOp.read(1, 11, 125, nrep=2)])
        r = res.reads[(1, 11, 125)]
        self.assertEqual((r.requests, r.acked, r.value, r.received), (2, 2, 2, 2))
        self.assertEqual(res.writes[(1, 11, 125)].acked, 1)
        self.assertTrue(res.complete)

    def test_fire_and_forget(self):
        res = BoardToy().transmit([RegisterOp.read(1, 11, 125)], fire_and_forget=True)
        r = res.reads[(1, 11, 125)]
        self.assertEqual((r.acked, r.value, r.received), (1, None, 0))

    def test_uart_disable(self):
        toy = BoardToy()
        toy.uart_disable(1)
        res = toy.transmit([RegisterOp.read(1, 11, 125)])
        self.assertEqual(res.reads[(1, 11, 125)].received, 0)
        self.assertFalse(res.complete)
        toy.uart_enable(1)
        self.assertTrue(toy.transmit([RegisterOp.read(1, 11, 125)]).complete)

    def test_reset_and_power(self):
        toy = BoardToy(ENTRY)
        self.assertEqual(toy.io_group, 2)
        self.assertTrue(toy.ping())
        self.assertEqual([toy.get_tile(c) for c in (0x201, 0x205)], [0, 1])
        toy.transmit([RegisterOp.write(0x201, 11, 125, 2), RegisterOp.write(0x205, 11, 125, 3)])
        toy.reset(0, ResetType.INTERNAL)
        toy.wait_on_reset()
        self.assertEqual(toy.registers[(0x201, 11, 125)], 2)
        toy.reset(0, ResetType.FULL)
        self.assertNotIn((0x201, 11, 125), toy.registers)
        self.assertEqual(toy.registers[(0x205, 11, 125)], 3)    # Tile 1 untouched
        toy.power_off(1)
        self.assertNotIn((0x205, 11, 125), toy.registers)
        with self.assertRaises(ValueError):
            toy.power_on(2)                                      # Not on this board

    def test_rails(self):
        toy = BoardToy()
        toy.transmit([RegisterOp.write(1, 11, 125, 2)])
        toy.rail_off(0, Rail.VDDA)
        toy.rail_on(0, Rail.VDDA)
        self.assertEqual(toy.registers[(1, 11, 125)], 2)        # VDDA keeps the configuration
        toy.rail_off(0, Rail.VDDD)
        self.assertNotIn((1, 11, 125), toy.registers)           # VDDD loses it

    def test_data(self):
        toy = BoardToy()
        toy.start_data()
        self.assertEqual(toy.read_data(1), [])
        toy.stop_data()


if __name__ == "__main__":
    unittest.main()
