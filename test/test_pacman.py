import unittest

from larpix_control import asic_spec_from_yaml, load_network, Pacman
from larpix_control.common.interfaces import RegisterOp, ResetType

ENTRY = {"io_group": 2, "hostname": "localhost", "port": 5555, "timeout_ms": 100,
         "first_io_chan": 0x201, "uart_mask": 0xFF, "uarts_per_tile": 4}


class TestPacman(unittest.TestCase):
    """Configuration only:  no PACMAN needed (ZMQ connects lazily)."""

    def setUp(self):
        self.spec = asic_spec_from_yaml("config/asics/larpix_v3.yaml")

    def test_entry(self):
        board = Pacman(ENTRY, self.spec)
        self.assertEqual((board.io_group, board.io_chans), (2, list(range(0x201, 0x209))))
        self.assertEqual([board.get_tile(c) for c in (0x201, 0x204, 0x205, 0x208)], [0, 0, 1, 1])
        with self.assertRaises(ValueError):
            board.transmit([RegisterOp.read(0x101, 11, 125)])
        with self.assertRaises(ValueError):
            board.reset(2, ResetType.FULL)
        board.close()

    def test_ping_without_board(self):
        board = Pacman(ENTRY, self.spec)
        self.assertFalse(board.ping())                           # Nothing listening:  timeout
        board.close()

    def test_load_network(self):
        boards = load_network("config/network/network_eg.yaml", self.spec)
        self.assertEqual(sorted(boards), [1, 2])
        self.assertEqual(boards[1].io_chans, [0x101, 0x102, 0x103, 0x104])
        for board in boards.values():
            board.close()


if __name__ == "__main__":
    unittest.main()
