import sys
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from source_collector import explore_url, make_window, parse_multiline  # noqa: E402

SAMPLES = HERE.parents[2] / "collectors" / "07_search_interest" / "samples"
W = "2025-11-10 2026-11-10"
SET = ["Batiste dry shampoo", "Living Proof shampoo", "Death Wish Coffee", "Black Rifle Coffee", "Jinx dog food"]


def load(name):
    lines = (SAMPLES / name).read_text(encoding="utf-8").split("\n")
    return lines[0], "\n".join(lines[2:])


class ParseTest(unittest.TestCase):
    def test_window_and_url(self):
        self.assertEqual(make_window(date(2026, 11, 10)), W)
        self.assertEqual(make_window(date(2028, 2, 29)), "2027-02-28 2028-02-29")
        self.assertEqual(
            explore_url(["Batiste dry shampoo"], W),
            "https://trends.google.com/trends/explore?date=2025-11-10%202026-11-10&geo=US&q=Batiste%20dry%20shampoo")

    def test_samples(self):
        url, body = load("multiline_batiste_dry_shampoo_fixed.txt")
        req, pts = parse_multiline(url, body, ["Batiste dry shampoo"], W)
        self.assertEqual(len(pts), 53)
        self.assertEqual((pts[0]["time"], pts[0]["value"]), ("1762646400", [21]))
        self.assertEqual(pts[22]["value"], [100])
        self.assertEqual((pts[52]["time"], pts[52]["value"]), ("1794096000", [22]))
        self.assertTrue(pts[52]["isPartial"])
        self.assertFalse(any("isPartial" in p for p in pts[:52]))
        url, body = load("multiline_compare5_qualified_fixed.txt")
        req, pts = parse_multiline(url, body, SET, W)
        self.assertEqual(len(pts), 53)
        self.assertEqual(pts[0]["value"], [9, 21, 11, 100, 7])
        self.assertEqual(pts[52]["value"], [10, 17, 9, 61, 7])

    def test_errors(self):
        url, body = load("multiline_batiste_term_fixed.txt")
        with self.assertRaises(ValueError):
            parse_multiline(url, body, ["Batiste dry shampoo"], W)
        url, body = load("multiline_batiste_dry_shampoo_fixed.txt")
        with self.assertRaises(ValueError):
            parse_multiline(url, body, ["Batiste dry shampoo"], "2025-11-11 2026-11-11")
        with self.assertRaises(ValueError):
            parse_multiline(url, body.split("\n", 1)[1], ["Batiste dry shampoo"], W)


if __name__ == "__main__":
    unittest.main()
