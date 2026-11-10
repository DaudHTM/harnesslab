import os
import sys
import unittest

sys.path.insert(0, os.getcwd())
from normalizer import normalize_tags


class HiddenTests(unittest.TestCase):
    def test_trim(self):
        self.assertEqual(normalize_tags(["  AI  "]), ["ai"])

    def test_deduplicate(self):
        self.assertEqual(normalize_tags(["AI", "ai", " AI "]), ["ai"])

    def test_empty(self):
        self.assertEqual(normalize_tags(["", "  "]), [])

    def test_regression(self):
        self.assertEqual(normalize_tags(["Zebra", "apple"]), ["apple", "zebra"])
