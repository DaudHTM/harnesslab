import unittest

from normalizer import normalize_tags


class NormalizerTests(unittest.TestCase):
    def test_lowercase_and_sort(self):
        self.assertEqual(normalize_tags(["Zebra", "apple"]), ["apple", "zebra"])
