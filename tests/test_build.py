from exchangelib.version import Build

from .common import TimedTestCase


class BuildTest(TimedTestCase):
    def test_magic(self):
        self.assertEqual(str(Build(9, 8, 7, 6)), "9.8.7.6")
        hash(Build(9, 8, 7, 6))

    def test_compare(self):
        self.assertEqual(Build(15, 0, 1, 2), Build(15, 0, 1, 2))
        self.assertNotEqual(Build(15, 0, 1, 2), Build(15, 0, 1, 3))
        self.assertLess(Build(15, 0, 1, 2), Build(15, 0, 1, 3))
        self.assertLess(Build(15, 0, 1, 2), Build(15, 0, 2, 2))
        self.assertLess(Build(15, 0, 1, 2), Build(15, 1, 1, 2))
        self.assertLess(Build(15, 0, 1, 2), Build(16, 0, 1, 2))
        self.assertLessEqual(Build(15, 0, 1, 2), Build(15, 0, 1, 2))
        self.assertGreater(Build(15, 0, 1, 2), Build(15, 0, 1, 1))
        self.assertGreater(Build(15, 0, 1, 2), Build(15, 0, 0, 2))
        self.assertGreater(Build(15, 1, 1, 2), Build(15, 0, 1, 2))
        self.assertGreater(Build(15, 0, 1, 2), Build(14, 0, 1, 2))
        self.assertGreaterEqual(Build(15, 0, 1, 2), Build(15, 0, 1, 2))

    def test_api_version(self):
        self.assertEqual(Build(8, 0).api_version(), "Exchange2007")
        self.assertEqual(Build(8, 1).api_version(), "Exchange2007_SP1")
        self.assertEqual(Build(8, 2).api_version(), "Exchange2007_SP1")
        self.assertEqual(Build(8, 3).api_version(), "Exchange2007_SP1")
        self.assertEqual(Build(15, 0, 1, 1).api_version(), "Exchange2013")
        self.assertEqual(Build(15, 0, 1, 1).api_version(), "Exchange2013")
        self.assertEqual(Build(15, 0, 847, 0).api_version(), "Exchange2013_SP1")
        with self.assertRaises(ValueError):
            Build(16, 0).api_version()
        with self.assertRaises(ValueError):
            Build(15, 4).api_version()
