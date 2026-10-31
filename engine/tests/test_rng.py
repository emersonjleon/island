import json
import unittest

from engine.rng import Rng


class RngTest(unittest.TestCase):
    def test_pcg32_reference_vector(self) -> None:
        # Output of the reference pcg32-demo: pcg32_srandom(42, 54).
        rng = Rng(42, stream=54)
        got = [rng.next_u32() for _ in range(6)]
        self.assertEqual(got, [0xA15C02B7, 0x7B47F409, 0xBA1D3330, 0x83D2F293, 0xBFA4784B, 0xCBED606E])

    def test_known_sequence_regression(self) -> None:
        rng = Rng(12345)
        self.assertEqual(rng.state, [11739991131726342043, 109])
        self.assertEqual([rng.randbelow(100) for _ in range(10)], [67, 26, 94, 2, 13, 53, 28, 67, 97, 84])
        self.assertEqual(rng.dice(), [2, 2])

    def test_same_seed_same_sequence(self) -> None:
        a, b = Rng(7), Rng(7)
        self.assertEqual([a.randint(1, 6) for _ in range(50)], [b.randint(1, 6) for _ in range(50)])
        self.assertNotEqual([Rng(7).next_u32() for _ in range(5)], [Rng(8).next_u32() for _ in range(5)])

    def test_state_round_trip(self) -> None:
        rng = Rng(99)
        for _ in range(17):
            rng.randbelow(1000)
        state = json.loads(json.dumps(rng.state))
        clone = Rng.from_state(state)
        self.assertEqual(clone, rng)
        self.assertEqual([rng.randbelow(10**12) for _ in range(20)], [clone.randbelow(10**12) for _ in range(20)])

    def test_from_state_rejects_bad_state(self) -> None:
        for bad in ([1], [1, 2], [-1, 3], [1, 2**64 + 1], ["1", 3]):
            with self.assertRaises(ValueError):
                Rng.from_state(bad)  # type: ignore[arg-type]

    def test_randbelow_roughly_uniform(self) -> None:
        rng = Rng(2024)
        n, draws = 6, 60000
        counts = [0] * n
        for _ in range(draws):
            counts[rng.randbelow(n)] += 1
        expected = draws // n
        for c in counts:
            self.assertLess(abs(c - expected), expected // 20)  # within 5 %

    def test_randbelow_bounds_and_errors(self) -> None:
        rng = Rng(1)
        self.assertEqual({rng.randbelow(1) for _ in range(10)}, {0})
        big = 2**70 + 3
        self.assertTrue(all(0 <= rng.randbelow(big) < big for _ in range(100)))
        with self.assertRaises(ValueError):
            rng.randbelow(0)
        with self.assertRaises(ValueError):
            rng.randint(5, 4)

    def test_randint_inclusive(self) -> None:
        rng = Rng(3)
        self.assertEqual({rng.randint(-2, 2) for _ in range(500)}, {-2, -1, 0, 1, 2})

    def test_shuffle_is_permutation(self) -> None:
        rng = Rng(5)
        for size in (0, 1, 2, 10, 50):
            items = list(range(size))
            rng.shuffle(items)
            self.assertEqual(sorted(items), list(range(size)))
        moved = list(range(50))
        rng.shuffle(moved)
        self.assertNotEqual(moved, list(range(50)))

    def test_choice_sample(self) -> None:
        rng = Rng(11)
        seq = ["a", "b", "c", "d"]
        self.assertIn(rng.choice(seq), seq)
        with self.assertRaises(IndexError):
            rng.choice([])
        sample = rng.sample(seq, 3)
        self.assertEqual(len(set(sample)), 3)
        self.assertTrue(set(sample) <= set(seq))
        self.assertEqual(sorted(rng.sample(seq, 4)), seq)
        with self.assertRaises(ValueError):
            rng.sample(seq, 5)

    def test_dice(self) -> None:
        rng = Rng(8)
        rolls = [rng.dice(2, 6) for _ in range(300)]
        self.assertTrue(all(len(r) == 2 and all(1 <= d <= 6 for d in r) for r in rolls))
        self.assertEqual({sum(r) for r in rolls}, set(range(2, 13)))
        self.assertEqual(len(rng.dice(3, 20)), 3)

    def test_no_float_state(self) -> None:
        self.assertTrue(all(isinstance(v, int) for v in Rng(0).state))


if __name__ == "__main__":
    unittest.main()
