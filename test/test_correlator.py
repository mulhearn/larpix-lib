import unittest

from larpix_control import asic_spec_from_yaml
from larpix_control.asic._correlator import ReplyCorrelator
from larpix_control.common.interfaces import RegisterOp

CHAN = 0x101


class TestReplyCorrelator(unittest.TestCase):

    def setUp(self):
        self.spec = asic_spec_from_yaml("config/asics/larpix_v3.yaml")

    def reply(self, chip, reg, value):
        return self.spec.build_config_packet(chip, reg, value, downstream=1, write=False)

    def test_majority_and_discrepant(self):
        op = RegisterOp.read(CHAN, 11, 125, nrep=3)
        corr = ReplyCorrelator(self.spec, [op])
        corr.ack(op, 3)
        for v in (5, 7, 5):
            corr.add(CHAN, self.reply(11, 125, v))
        self.assertTrue(corr.done())
        r = corr.result().reads[(CHAN, 11, 125)]
        self.assertEqual((r.requests, r.acked, r.value, r.received, r.discrepant), (3, 3, 5, 3, 1))

    def test_tie_takes_last_received(self):
        op = RegisterOp.read(CHAN, 11, 125, nrep=2)
        corr = ReplyCorrelator(self.spec, [op])
        corr.add(CHAN, self.reply(11, 125, 5))
        corr.add(CHAN, self.reply(11, 125, 7))
        self.assertEqual(corr.result().reads[(CHAN, 11, 125)].value, 7)

    def test_missing_reply_incomplete(self):
        op = RegisterOp.read(CHAN, 11, 125)
        corr = ReplyCorrelator(self.spec, [op])
        corr.ack(op)
        self.assertFalse(corr.done())
        res = corr.result()
        self.assertIsNone(res.reads[(CHAN, 11, 125)].value)
        self.assertFalse(res.complete)
        self.assertTrue(corr.result(fire_and_forget=True).complete)

    def test_ignored_words(self):
        op = RegisterOp.read(CHAN, 11, 125)
        corr = ReplyCorrelator(self.spec, [op])
        corr.add(CHAN, self.reply(11, 126, 1))                       # Register not read
        corr.add(0x102, self.reply(11, 125, 1))                      # Other channel
        corr.add(CHAN, self.spec.build_config_write(11, 125, 1))     # Not a reply
        corr.add(CHAN, 0)                                            # Not a config word
        self.assertEqual(corr.result().reads[(CHAN, 11, 125)].received, 0)

    def test_surplus_counted(self):
        op = RegisterOp.read(CHAN, 11, 125)
        corr = ReplyCorrelator(self.spec, [op])
        corr.add(CHAN, self.reply(11, 125, 5))
        corr.add(CHAN, self.reply(11, 125, 5))
        r = corr.result().reads[(CHAN, 11, 125)]
        self.assertEqual((r.received, r.discrepant), (2, 0))

    def test_writes_and_order(self):
        ops = [RegisterOp.write(CHAN, 11, 125, 2), RegisterOp.read(CHAN, 11, 125),
               RegisterOp.write(CHAN, 11, 124, 1, nrep=2), RegisterOp.write(CHAN, 11, 125, 3)]
        corr = ReplyCorrelator(self.spec, ops)
        for op in ops:
            corr.ack(op, op.nrep)
        corr.add(CHAN, self.reply(11, 125, 2))
        res = corr.result()
        self.assertEqual(list(res.writes), [(CHAN, 11, 125), (CHAN, 11, 124)])
        self.assertEqual((res.writes[(CHAN, 11, 125)].requests, res.writes[(CHAN, 11, 124)].acked),
                         (2, 2))
        self.assertTrue(res.complete)


if __name__ == "__main__":
    unittest.main()
