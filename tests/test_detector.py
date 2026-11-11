"""Tests for LAMMPS executable detection caching."""
import unittest
from unittest import mock

from app.lammps import detector


class DetectionCacheTests(unittest.TestCase):
    def setUp(self):
        detector._CACHED_DETECTION = None

    def tearDown(self):
        detector._CACHED_DETECTION = None

    def _search_without_lammps(self, calls):
        def which(name):
            calls.append(name)
            return None
        return mock.patch.multiple(
            detector,
            shutil=mock.Mock(which=which),
            LAMMPS_EXECUTABLE="",
        )

    def test_not_found_result_is_cached(self):
        calls = []
        with self._search_without_lammps(calls), \
                mock.patch.object(detector.os.path, "isfile", return_value=False), \
                mock.patch.object(detector.glob, "glob", return_value=[]):
            first = detector.detect_lammps()
            searched = len(calls)
            second = detector.detect_lammps()
        self.assertFalse(first["detected"])
        self.assertEqual(first, second)
        self.assertGreater(searched, 0)
        self.assertEqual(len(calls), searched, "a second call searched again")

    def test_force_refresh_searches_again(self):
        calls = []
        with self._search_without_lammps(calls), \
                mock.patch.object(detector.os.path, "isfile", return_value=False), \
                mock.patch.object(detector.glob, "glob", return_value=[]):
            detector.detect_lammps()
            searched = len(calls)
            detector.detect_lammps(force_refresh=True)
        self.assertEqual(len(calls), 2 * searched)

    def test_custom_path_result_is_not_cached(self):
        calls = []
        with self._search_without_lammps(calls), \
                mock.patch.object(detector.os.path, "isfile", return_value=False), \
                mock.patch.object(detector.glob, "glob", return_value=[]):
            detector.detect_lammps(custom_path="/nowhere/lmp")
        self.assertIsNone(detector._CACHED_DETECTION)


if __name__ == "__main__":
    unittest.main()
