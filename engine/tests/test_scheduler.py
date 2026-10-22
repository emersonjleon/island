import json
import unittest

from engine.errors import EngineError
from engine.scheduler import Scheduler


class SchedulerTest(unittest.TestCase):
    def test_order_by_due_then_seq(self) -> None:
        s = Scheduler()
        a = s.schedule(200, "x", {"n": "a"})
        b = s.schedule(100, "x", {"n": "b"})
        c = s.schedule(200, "y", {"n": "c"})
        d = s.schedule(100, "y", {"n": "d"})
        self.assertEqual(s.next_due(), 100)
        self.assertEqual([t.id for t in s.pop_due(1000)], [b, d, a, c])
        self.assertIsNone(s.next_due())
        self.assertEqual(len(s), 0)

    def test_pop_respects_now(self) -> None:
        s = Scheduler()
        s.schedule(100, "x")
        s.schedule(101, "x")
        self.assertEqual([t.due_ms for t in s.pop_due(100)], [100])
        self.assertIsNone(s.pop_next(100))
        self.assertEqual(s.next_due(), 101)

    def test_cancel_is_lazy_and_skipped(self) -> None:
        s = Scheduler()
        a = s.schedule(50, "x")
        b = s.schedule(60, "x")
        self.assertTrue(s.cancel(a))
        self.assertFalse(s.cancel(a))
        self.assertFalse(s.cancel(999))
        self.assertFalse(s.cancel(None))
        self.assertEqual(s.next_due(), 60)
        self.assertIsNone(s.get(a))
        self.assertEqual([t.id for t in s.pop_due(100)], [b])
        self.assertFalse(s.cancel(b))   # already fired

    def test_ids_unique_and_increasing(self) -> None:
        s = Scheduler()
        ids = [s.schedule(10, "x") for _ in range(5)]
        self.assertEqual(ids, sorted(set(ids)))

    def test_pending_filter(self) -> None:
        s = Scheduler()
        s.schedule(30, "a")
        s.schedule(10, "b")
        s.schedule(20, "a")
        self.assertEqual([t.due_ms for t in s.pending("a")], [20, 30])
        self.assertEqual([t.kind for t in s.pending()], ["b", "a", "a"])

    def test_serialisation_round_trip_keeps_counters(self) -> None:
        s = Scheduler()
        s.schedule(300, "x", {"k": 1})
        dead = s.schedule(100, "x")
        s.schedule(200, "y", {"k": [1, 2]})
        s.schedule(200, "z")
        s.cancel(dead)
        s.pop_next(1000)  # fires 200 "y"
        d = json.loads(json.dumps(s.to_dict()))
        r = Scheduler.from_dict(d)
        self.assertEqual(r.to_dict(), s.to_dict())
        self.assertEqual(r.schedule(5, "n"), s.schedule(5, "n"))
        self.assertEqual([t.to_list() for t in r.pop_due(10_000)], [t.to_list() for t in s.pop_due(10_000)])

    def test_from_list_defaults(self) -> None:
        r = Scheduler.from_list([[10, 4, 7, "x", {}], [5, 9, 2, "y", {"a": 1}]])
        self.assertEqual(r.next_due(), 5)
        self.assertEqual(r.schedule(1, "z"), 8)
        self.assertEqual(r.to_list()[0], [1, 10, 8, "z", {}])

    def test_rejects_bad_input(self) -> None:
        s = Scheduler()
        for args in [(1.5, "x"), (True, "x"), (-1, "x"), (1, ""), (1, "x", [1])]:
            with self.assertRaises(EngineError):
                s.schedule(*args)  # type: ignore[arg-type]

    def test_payload_copied(self) -> None:
        s = Scheduler()
        p = {"a": 1}
        tid = s.schedule(1, "x", p)
        p["a"] = 2
        self.assertEqual(s.get(tid).payload, {"a": 1})  # type: ignore[union-attr]


if __name__ == "__main__":
    unittest.main()
